#!/usr/bin/env python3
"""L'étape 2 de bout en bout : du choix d'un business à son test léger
(lot 10, PR 4, décisions Q34, Q35 et Q91).

Le modèle, Docker et la réponse du produit sont des faux ; le pipeline en
base, l'interpréteur, les liens, les tickets, la publication et Caddy
sont réels.

Scénarios :
- « Essayer l'étape 2 » : le business est choisi pour un POC ; le plan est
  conçu, critiqué « à corriger », reconçu, jugé bon ; le ticket « Plan »
  s'ouvre ; validé, le POC est construit au niveau « code », publié en
  staging, relu « à corriger », reconstruit, publié en v2, relu bon ; le
  ticket « Tester le produit » s'ouvre ; validé, le POC passe en prod, sa
  campagne est prête et le business passe au test léger ;
- « Arrêter le business » sur le ticket « Plan » l'arrête et libère sa
  place de test ;
- sans réponse sous 48 heures, le plan s'applique : la construction
  commence ;
- « À corriger » sur le ticket « Tester le produit » relance la
  construction avec les consignes ;
- la fiche du business montre le plan, la critique et les passages.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.ingress import caddy  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import expirer_tickets, process_one  # noqa: E402
from serge.interpreter.rules import quota_usage  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.mc.proj_faits import project_fait_pipe  # noqa: E402
from serge.sandbox import publier  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402

FORMULAIRE = {
    'nom': 'Devis Artisan',
    'description': 'Un générateur de devis en ligne pour les artisans.',
    'offre': 'Trois devis gratuits, puis 29 € par mois.',
}


def _plan(tour: int) -> dict[str, Any]:
    return {
        'hypothese': f'Les artisans veulent faire leurs devis en ligne ({tour}).',
        'cible': 'Plombiers et électriciens indépendants, en France.',
        'canal': 'email',
        'prospects': 40,
        'duree_jours': 10,
        'prix': '29 € par mois',
        'relances': 'Une relance à J+3, une autre à J+7.',
        'livrable': 'Un générateur de devis : trois devis gratuits.',
        'plan': 'Une page d’accueil, un formulaire de devis, un PDF.',
        'scenarios': '1. Ouvrir la page, remplir un devis, le télécharger.',
        'fiche_resume': 'Des devis propres en deux minutes.',
        'fiche_limites': 'Pas de factures.',
        'fiche_prix': 'Gratuit pendant le test.',
        'fiche_delais': 'Tout de suite.',
        'fiche_usage': 'On remplit le formulaire, on télécharge le PDF.',
        'faq': [
            {'question': 'C’est gratuit ?', 'reponse': 'Oui, pendant le test.'}
        ],
    }


def _ecrire(ident: str, path: str, content: str) -> ToolCall:
    return ToolCall(
        ident,
        'chantier_ecrire',
        json.dumps({'path': path, 'content': content}),
    )


def _t(rows: Any) -> Any:
    """Les lignes de la base en tuples, pour les comparer."""
    if isinstance(rows, list):
        return [tuple(r) for r in rows]
    return tuple(rows) if rows is not None else None


class FauxModeles:
    """Le concepteur, le critique, le constructeur et le relecteur."""

    def __init__(self, critiques: list[str], relectures: list[str]) -> None:
        self.critiques = list(critiques)
        self.relectures = list(relectures)
        self.tours = 0
        self.par_role: dict[str, list[str]] = {}

    def _role(self, system: str) -> str:
        for marque, role in (
            ('Tu conçois le POC', 'concevoir'),
            ('Tu critiques le plan du POC', 'critiquer'),
            ('Tu construis le POC', 'construire'),
            ('Tu essaies le POC', 'relire'),
        ):
            if marque in system:
                return role
        raise AssertionError(f'prompt inattendu : {system[:80]}')

    def __call__(self, _key, model, messages, tools=None, **_kw):
        role = self._role(messages[0]['content'])
        self.par_role.setdefault(role, []).append(model)
        if role == 'concevoir':
            self.tours += 1
            return self._json(_plan(self.tours))
        if role == 'critiquer':
            verdict = self.critiques.pop(0)
            remarques = (
                [{'texte': 'Le scénario 1 ne dit pas ce qu’on doit voir.'}]
                if verdict == 'a_corriger'
                else []
            )
            return self._json(
                {
                    'verdict': verdict,
                    'avis': 'Réaliste.',
                    'remarques': remarques,
                }
            )
        if role == 'construire':
            if not any(m.get('role') == 'tool' for m in messages):
                calls = (
                    _ecrire(
                        'd',
                        'Dockerfile',
                        'FROM node:22\nCMD ["node", "app.js"]\n',
                    ),
                    _ecrire(
                        'a',
                        'app.js',
                        'require("http").createServer().listen(8080)\n',
                    ),
                )
                return ChatResult('', 10, 10, model, 1, tool_calls=calls)
            return self._json(
                {'fini': 'oui', 'compte_rendu': 'Le POC marche.'}
            )
        verdict = self.relectures.pop(0)
        return self._json(
            {
                'verdict': verdict,
                'remarques': 'Le bouton sort de l’écran sur mobile.'
                if verdict == 'a_corriger'
                else '',
                'compte_rendu': 'Scénario 1 essayé.',
            }
        )

    @staticmethod
    def _json(data: dict[str, Any]) -> ChatResult:
        return ChatResult(json.dumps(data), 10, 10, 'faux', 1)


class Etape2Tests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        instance = self.dossier / 'instance.toml'
        instance.write_text(
            '[identity]\npublic_hostname = "serge.exemple.fr"\n',
            encoding='utf-8',
        )
        env = {
            'SERGE_SYSTEM_ROOT': str(self.dossier),
            'SERGE_INSTANCE_FILE': str(instance),
            **faux_docker(self.dossier),
        }
        for patcher in (
            mock.patch.dict(os.environ, env),
            mock.patch.object(publier, '_repond', return_value=True),
            mock.patch.object(caddy, 'reload', return_value=''),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        # Rien d'autre ne tourne : pas de relève de boîte, pas de relances.
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at')"
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _vider(self, modeles: FauxModeles) -> None:
        for _ in range(80):
            travaux = process_one(self.conn, 'works', caller=modeles)
            echanges = process_one(self.conn, 'conversations', caller=modeles)
            if travaux is None and echanges is None:
                return
        raise AssertionError('les files ne se vident pas')

    def _echecs(self) -> list[tuple]:
        return [
            tuple(r)
            for r in self.conn.execute(
                "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
            )
        ]

    def _ticket(self, sorte: str) -> str:
        row = self.conn.execute(
            'SELECT id FROM tickets WHERE type=? ORDER BY created_at DESC',
            (sorte,),
        ).fetchone()
        self.assertIsNotNone(row, f'pas de ticket {sorte}')
        return str(row[0])

    def _repondre(self, sorte: str, acte: str, texte: str = '') -> None:
        noter_reponse(self.conn, self._ticket(sorte), acte, texte, 'owner')
        self.conn.commit()

    def _business(self) -> tuple[str, str]:
        row = self.conn.execute(
            "SELECT id, lifecycle FROM ventures WHERE name='Devis Artisan'"
        ).fetchone()
        return str(row[0]), str(row[1])

    def _essai(self, modeles: FauxModeles) -> str:
        self.assertIsNotNone(
            fire_button(self.conn, 'bouton_essayer_etape2', FORMULAIRE)
        )
        self.conn.commit()
        self._vider(modeles)
        return self._business()[0]

    def test_du_choix_au_test_leger(self) -> None:
        modeles = FauxModeles(['a_corriger', 'bon'], ['a_corriger', 'bon'])
        venture = self._essai(modeles)
        self.assertEqual(self._echecs(), [])
        plans = self.conn.execute(
            'SELECT round, status FROM product_plans WHERE venture_id=?'
            ' ORDER BY round',
            (venture,),
        ).fetchall()
        self.assertEqual(
            [tuple(p) for p in plans], [(1, 'challenged'), (2, 'challenged')]
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT round FROM plan_critiques WHERE venture_id=?',
                    (venture,),
                ).fetchall()
            ),
            [(1,)],
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT state, channel, n_target FROM campaigns'
                    ' WHERE venture_id=?',
                    (venture,),
                ).fetchone()
            ),
            ('DRAFT', 'email', 40),
        )
        # Le plan validé : construire, publier, relire, deux passages.
        self._repondre('PLAN_POC', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        passages = self.conn.execute(
            'SELECT pass, status, verdict FROM builds WHERE venture_id=?'
            ' ORDER BY pass',
            (venture,),
        ).fetchall()
        self.assertEqual(
            [tuple(p) for p in passages],
            [(1, 'reviewed', 'a_corriger'), (2, 'reviewed', 'bon')],
        )
        self.assertEqual(
            set(modeles.par_role['construire']), {'anthropic/claude-opus-5.5'}
        )
        staging = self.conn.execute(
            "SELECT version, hostname, status FROM deployments WHERE target='staging'"
        ).fetchone()
        self.assertEqual(
            tuple(staging),
            (2, 'staging-devis-artisan.serge.exemple.fr', 'running'),
        )
        self.assertEqual(self._business()[1], 'POC_SELECTED')
        # Essayé et validé : en prod, campagne prête, test léger.
        self._repondre('TEST_POC', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(self._business()[1], 'SMOKE_READY')
        self.assertEqual(
            _t(
                self.conn.execute(
                    "SELECT hostname, status FROM deployments WHERE target='prod'"
                ).fetchone()
            ),
            ('devis-artisan.serge.exemple.fr', 'running'),
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT state FROM campaigns WHERE venture_id=?',
                    (venture,),
                ).fetchone()
            ),
            ('READY',),
        )
        fiche = project_fait_pipe(self.conn, 'venture', venture)
        assert fiche is not None
        titres = [c['titre'] for c in fiche['cadres']]
        for titre in (
            'Le plan',
            'Les passages de construction',
            'En ligne',
            'Versions',
        ):
            self.assertIn(titre, titres)

    def test_arreter_le_business_libere_sa_place(self) -> None:
        modeles = FauxModeles(['bon'], [])
        venture = self._essai(modeles)
        self.assertEqual(quota_usage(self.conn, 'places_de_test')[0], 1)
        self._repondre('PLAN_POC', 'arreter_business')
        self._vider(modeles)
        self.assertEqual(self._business()[1], 'KILLED')
        self.assertEqual(quota_usage(self.conn, 'places_de_test')[0], 0)
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT status FROM product_plans WHERE venture_id=?',
                    (venture,),
                ).fetchone()
            ),
            ('refused',),
        )
        self.assertNotIn('construire', modeles.par_role)

    def test_sans_reponse_sous_48_heures_le_plan_s_applique(self) -> None:
        modeles = FauxModeles(['bon'], ['bon'])
        self._essai(modeles)
        self.conn.execute(
            "UPDATE tickets SET expiry_at='2000-01-01T00:00:00+00:00'"
            " WHERE type='PLAN_POC'"
        )
        expirer_tickets(self.conn)
        self.conn.commit()
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertIn('construire', modeles.par_role)
        self._ticket('TEST_POC')

    def test_a_corriger_au_test_relance_la_construction(self) -> None:
        modeles = FauxModeles(['bon'], ['bon', 'bon'])
        venture = self._essai(modeles)
        self._repondre('PLAN_POC', 'valider')
        self._vider(modeles)
        self._repondre('TEST_POC', 'a_corriger', 'Mets le prix en gros.')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        consignes = self.conn.execute(
            'SELECT owner_notes FROM builds WHERE venture_id=?'
            ' ORDER BY created_at',
            (venture,),
        ).fetchall()
        self.assertEqual(
            [c[0] for c in consignes],
            ['Mets le prix en gros.', 'Mets le prix en gros.'],
        )
        self.assertEqual(len(modeles.par_role['construire']), 4)


if __name__ == '__main__':
    unittest.main()
