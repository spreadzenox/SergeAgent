#!/usr/bin/env python3
"""L'étape 1 : ses réglages, ses protections, et ce qu'en montre MC.

Scénarios :
- Julien passe « nombre d'idées » de A de 3 à 2 : le prompt et la
  vérification du format suivent ; une réponse avec trop d'idées est
  redemandée ;
- « au plus N pages retenues » limite l'écriture même si le format ne le
  fait plus ; le quota des places de test refuse un choix de trop ;
- la fiche d'une invocation, la page Cerveau et la page Écoute montrent
  l'étape telle qu'elle est en base : boutons, conditions, confirmation,
  flux suivis (et le bouton pour en couper un).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.mc.proj_cerveau import project_matrice  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'


IDEES = (
    ('Devis dictés', 'les artisans dictent leurs devis au téléphone'),
    ('Relance des impayés', 'relancer les clients qui ne paient pas'),
    ('Planning de chantier', 'organiser les équipes et les livraisons'),
)


def _fiche(n: int) -> dict[str, Any]:
    titre, description = IDEES[n - 1]
    return {
        'titre': titre,
        'description': description,
        'famille': 'autre',
        'pages': ['p1'],
    }


class Repondeur:
    """Rend, dans l'ordre, les réponses données ; garde les prompts."""

    def __init__(self, *reponses: dict) -> None:
        self.reponses = list(reponses)
        self.systemes: list[str] = []

    def __call__(self, _key, model, messages, **_kw) -> ChatResult:
        self.systemes.append(messages[0]['content'])
        reponse = self.reponses.pop(0) if self.reponses else {}
        return ChatResult(json.dumps(reponse), 10, 10, model, 1)


class ReglagesEtProtectionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        self.conn.execute(
            'INSERT INTO listen_docs(id, source, url, label, fetched_at)'
            " VALUES('p1', 'web', 'https://x.test/p1', 'besoin_nouveau', 't')"
        )
        # Seule l'invocation testée tourne : pas de suite par les liens.
        self.conn.execute('UPDATE links SET enabled=0')
        self.conn.commit()

    def _tourner(self, invocation: str, modele: Repondeur) -> None:
        enqueue_task(self.conn, invocation, {'cycle_id': 'c1'})
        process_one(self.conn, 'works', now=NOW, caller=modele)

    def _verdicts(self, invocation: str) -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                'SELECT verdict FROM llm_usage WHERE point=? ORDER BY id',
                (invocation,),
            )
        ]

    def _refus(self) -> list[str]:
        return [
            json.loads(r[0])['reason']
            for r in self.conn.execute(
                "SELECT payload_json FROM events WHERE type='write.refused'"
            )
        ]

    def test_un_reglage_change_le_prompt_et_la_verification(self) -> None:
        self.conn.execute(
            "UPDATE invocation_settings SET value='2'"
            " WHERE invocation_id='formuler_a' AND name='nombre_idees'"
        )
        modele = Repondeur(
            {'fiches': [_fiche(1), _fiche(2), _fiche(3)]},
            {'fiches': [_fiche(1), _fiche(2)]},
        )
        self._tourner('formuler_a', modele)
        self.assertIn('Propose au plus 2 idées', modele.systemes[0])
        self.assertIn('au plus 2 élément(s)', modele.systemes[0])
        self.assertEqual(
            self._verdicts('formuler_a'), ['format_invalide', 'ok']
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM ventures WHERE family='autre'"
            ).fetchone(),
            (2,),
        )

    def test_au_plus_n_pages_retenues(self) -> None:
        """Le format ne limite plus les pages : l'écriture limite quand même."""
        self.conn.execute(
            "UPDATE invocation_output_fields SET max_items=''"
            " WHERE invocation_id='explorer_web' AND path='pages'"
        )
        self.conn.execute(
            "UPDATE invocation_settings SET value='1'"
            " WHERE invocation_id='explorer_web' AND name='pages_max'"
        )
        pages = [
            {'url': f'https://x.test/{n}', 'titre': 'T', 'apercu': 'A'}
            for n in range(2)
        ]
        self._tourner('explorer_web', Repondeur({'pages': pages}))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM listen_docs WHERE source='web'"
                " AND url LIKE 'https://x.test/_'"
            ).fetchone(),
            (1,),
        )
        self.assertIn('au plus 1 ligne(s) par passage', self._refus()[0])

    def test_le_quota_des_places_de_test(self) -> None:
        self.conn.executescript(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES ('t1', 'a', 'POC_SELECTED', 't', 't'),"
            " ('t2', 'b', 'SMOKE_READY', 't', 't'),"
            " ('t3', 'c', 'SMOKE_DONE', 't', 't'),"
            " ('c1', 'd', 'CANDIDATE', 't', 't');"
        )
        choix = {'choix': [{'business': 'c1', 'raison': 'bien'}]}
        self._tourner('choisir_business', Repondeur(choix))
        self.assertEqual(
            self.conn.execute(
                "SELECT lifecycle FROM ventures WHERE id='c1'"
            ).fetchone(),
            ('CANDIDATE',),
        )
        self.assertIn('quota places_de_test', self._refus()[0])

    def test_mission_control_montre_l_etape(self) -> None:
        self.conn.execute('UPDATE links SET enabled=1')
        fiche = project_objet(self.conn, 'llm', 'formuler_a')
        assert fiche is not None
        cadres = {c['titre']: c for c in fiche['cadres']}
        self.assertIn(
            'Propose au plus {nombre_idees} idées',
            cadres['Le texte qu’on lui donne (prompt)']['texte'],
        )
        comparer = cadres['Ce qu’elle voit pour comparer (version courte)']
        self.assertEqual(
            comparer['champs'][0],
            {'k': 'Les business', 'v': 'id, name — elle y écrit'},
        )
        self.assertIn('retirée à la main', comparer['champs'][1]['v'])
        lu = cadres['Ce qu’elle lit d’office (ce qu’elle doit traiter)']
        self.assertEqual(lu['champs'][0]['k'], 'Les pages « besoin nouveau »')
        noms = [
            p['nom'] for p in project_matrice(self.conn, {}, NOW)['points']
        ]
        self.assertEqual(
            noms[:7],
            [
                'ouvrir_cycle',
                'explorer_web',
                'rattacher_pages',
                'trier_pages',
                'formuler_a',
                'formuler_b',
                'choisir_business',
            ],
        )


class EtapeUnFrontTests(McBrowserCase):
    """Ce que Julien voit dans Mission Control, sur une base neuve."""

    def _base(self, sql: str) -> list[tuple]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(sql).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def test_la_fiche_de_formuler(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/objet/llm/formuler_a')
        fiche = page.locator('#page')
        for texte in (
            'Formuler des business A',
            'Propose au plus {nombre_idees} idées',
            'modifiable sur la page Policy',
            'Les pages « besoin nouveau »',
            'Lire une page en entier',
            'fiches.famille',
            'Ajouter dans ventures',
            'Puis à B, qui voit les idées de A',
        ):
            expect(fiche).to_contain_text(texte, timeout=10000)

    def test_la_page_ecoute(self) -> None:
        from playwright.sync_api import expect

        self._base(
            'INSERT INTO listen_feeds(id, url, title, active, created_at)'
            " VALUES('f1', 'https://a.test/rss', 'Forum A', 1, 't')"
        )
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/ecoute')
        boutons = page.locator('[data-ecoute="boutons"]')
        expect(boutons).to_contain_text(
            'Places de test occupées : 0 sur 3.', timeout=10000
        )
        expect(page.locator('[data-trigger="lancer_cycle"]')).to_be_enabled()
        page.locator('[data-trigger="bouton_effacer_idees"]').click()
        expect(page.locator('.modale')).to_contain_text('Les pages restent.')
        page.locator('.modale').get_by_role('button', name='Annuler').click()
        flux = page.locator('[data-ecoute="flux"]')
        expect(flux).to_contain_text('Forum A')
        flux.get_by_role('button', name='Couper').click()
        expect(flux).to_contain_text('Forum A (coupé)')
        self.assertEqual(
            self._base("SELECT active FROM listen_feeds WHERE id='f1'"), [(0,)]
        )

    def test_le_bouton_grise_quand_les_places_sont_prises(self) -> None:
        from playwright.sync_api import expect

        self._base(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES ('t1', 'a', 'POC_SELECTED', 't', 't'),"
            " ('t2', 'b', 'SMOKE_READY', 't', 't'),"
            " ('t3', 'c', 'SMOKE_DONE', 't', 't')"
        )
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/ecoute')
        expect(page.locator('[data-trigger="lancer_cycle"]')).to_be_disabled(
            timeout=10000
        )
        expect(page.locator('[data-ecoute="boutons"]')).to_contain_text(
            'Pas maintenant : Places de test occupées : 3 sur 3.'
        )


if __name__ == '__main__':
    unittest.main()
