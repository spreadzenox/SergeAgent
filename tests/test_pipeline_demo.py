#!/usr/bin/env python3
"""Le demi-cycle de démonstration de `config/pipeline.yaml`, de bout en bout.

Scénario : Serge est démarré ; le bouton « Lancer un cycle (démo) » ouvre
un cycle avec un texte de guidage ; « Formuler des idées » (faux modèle)
écrit deux business candidats, dont un sans offre ; « Choisir un business »
en passe un en POC_SELECTED. Puis Mission Control montre l'ordre des
invocations et tous leurs réglages, lus en base.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.mc.proj_cerveau import project_matrice  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'


def _bloc(texte: str, titre: str) -> Any:
    """Les lignes d'un bloc donné d'office (« ## titre » puis du JSON)."""
    suite = texte.split(f'## {titre}\n', 1)[1]
    return json.loads(suite.split('\n', 1)[0])


IDEES = [
    {
        'title': 'Devis dictés',
        'description': 'les artisans dictent leurs devis',
        'offre': 'un devis en 2 minutes',
    },
    {
        'title': 'Relance des impayés',
        'description': 'relancer les clients qui ne paient pas',
    },
    {'title': 'Planning de chantier', 'description': 'organiser les équipes'},
]


class FauxModele:
    """Rend le nombre d'idées demandé dans le prompt (ou ``idees`` s'il est
    donné), et choisit ``choix`` business parmi les candidats."""

    def __init__(self, idees: int | None = None, choix: int = 1) -> None:
        self.recus: dict[str, str] = {}
        self.systemes: list[str] = []
        self.idees = idees
        self.choix = choix

    def __call__(self, _key, model, messages, **_kwargs) -> ChatResult:
        system, user = messages[0]['content'], messages[1]['content']
        demande = re.search(r'Propose exactement (\d+) idées', system)
        if demande:
            self.recus['formuler'] = user
            self.systemes.append(system)
            nombre = self.idees or int(demande.group(1))
            self.idees = None  # une seule mauvaise réponse
            reponse: dict = {'fiches': IDEES[:nombre]}
        else:
            self.recus['choisir'] = user
            candidats = _bloc(user, 'Les business candidats')
            reponse = {
                'choix': [
                    {'venture_id': c['id'], 'raison': 'simple'}
                    for c in candidats[: self.choix]
                ]
            }
        return ChatResult(json.dumps(reponse), 10, 10, model, 1)


class PipelineDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _tourner(self, modele: FauxModele) -> list[str | None]:
        return [
            process_one(self.conn, 'works', now=NOW, caller=modele)
            for _ in range(4)
        ]

    def test_le_demi_cycle_tourne(self) -> None:
        self.assertIsNotNone(
            fire_button(self.conn, 'demo_lancer_cycle', {'guide': 'artisans'})
        )
        modele = FauxModele()
        passes = self._tourner(modele)
        self.assertIsNone(passes[3])
        cycle = self.conn.execute(
            'SELECT id, guide, status FROM listen_cycles'
        ).fetchone()
        self.assertEqual(cycle[1:], ('artisans', 'OPEN'))
        self.assertEqual(
            _bloc(modele.recus['formuler'], 'Le cycle en cours')[0]['guide'],
            'artisans',
        )
        business = self.conn.execute(
            'SELECT name, sellable_offer, lifecycle FROM ventures'
            ' ORDER BY name'
        ).fetchall()
        self.assertEqual(
            business,
            [
                ('Devis dictés', 'un devis en 2 minutes', 'POC_SELECTED'),
                ('Relance des impayés', '', 'CANDIDATE'),
            ],
        )
        statuts = self.conn.execute(
            'SELECT invocation_id, status FROM tasks ORDER BY created_at, id'
        ).fetchall()
        self.assertEqual(
            sorted(statuts),
            [
                ('demo_choisir', 'done'),
                ('demo_formuler', 'done'),
                ('demo_ouvrir_cycle', 'done'),
            ],
        )

    def _lancer(self, modele: FauxModele) -> None:
        fire_button(self.conn, 'demo_lancer_cycle', {'guide': 'artisans'})
        self._tourner(modele)

    def _journal(self, kind: str) -> list[dict]:
        return [
            json.loads(r[0])
            for r in self.conn.execute(
                'SELECT payload_json FROM events WHERE type=? ORDER BY id',
                (kind,),
            )
        ]

    def test_un_reglage_change_le_prompt_et_la_verification(self) -> None:
        """Julien passe « nombre d'idées » de 2 à 3 : tout suit."""
        self.conn.execute(
            "UPDATE invocation_settings SET value='3'"
            " WHERE invocation_id='demo_formuler' AND name='nombre_idees'"
        )
        modele = FauxModele()
        self._lancer(modele)
        self.assertIn('Propose exactement 3 idées', modele.systemes[0])
        self.assertIn('exactement 3 élément(s)', modele.systemes[0])
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM ventures').fetchone(),
            (3,),
        )

    def test_un_mauvais_nombre_d_idees_est_redemande(self) -> None:
        self._lancer(FauxModele(idees=3))
        verdicts = [
            r[0]
            for r in self.conn.execute(
                "SELECT verdict FROM llm_usage WHERE point='demo_formuler'"
                ' ORDER BY id'
            )
        ]
        self.assertEqual(verdicts, ['format_invalide', 'ok'])
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM ventures').fetchone(),
            (2,),
        )

    def test_au_plus_n_lignes_par_passage(self) -> None:
        """Le format ne limite plus le choix : l'écriture limite quand même."""
        self.conn.execute(
            "UPDATE invocation_output_fields SET max_items=''"
            " WHERE invocation_id='demo_choisir'"
        )
        self._lancer(FauxModele(choix=2))
        choisis = self.conn.execute(
            "SELECT COUNT(*) FROM ventures WHERE lifecycle='POC_SELECTED'"
        ).fetchone()
        self.assertEqual(choisis, (1,))
        refus = self._journal('write.refused')
        self.assertIn('au plus 1 ligne', refus[0]['reason'])

    def test_le_quota_des_business_choisis(self) -> None:
        """3 business déjà choisis : le quatrième est refusé."""
        for n in range(3):
            self.conn.execute(
                'INSERT INTO ventures(id, name, lifecycle, created_at,'
                " updated_at) VALUES(?, ?, 'POC_SELECTED', 't', 't')",
                (f'v{n}', f'Déjà choisi {n}'),
            )
        self._lancer(FauxModele())
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM ventures WHERE lifecycle='POC_SELECTED'"
            ).fetchone(),
            (3,),
        )
        refus = self._journal('write.refused')
        self.assertIn('quota business_choisis', refus[0]['reason'])

    def test_mission_control_montre_le_pipeline(self) -> None:
        etape = project_objet(self.conn, 'etape', 'pre_prospection')
        assert etape is not None
        ordre = next(
            c for c in etape['cadres'] if c['titre'].startswith('Invocations')
        )
        self.assertEqual(
            [lien['id'] for lien in ordre['liens']],
            ['demo_ouvrir_cycle', 'demo_formuler', 'demo_choisir'],
        )
        fiche = project_objet(self.conn, 'llm', 'demo_formuler')
        assert fiche is not None
        cadres = {c['titre']: c for c in fiche['cadres']}
        self.assertIn(
            'Propose exactement {nombre_idees} idées',
            cadres['Le texte qu’on lui donne (prompt)']['texte'],
        )
        donnes = cadres['Ce qu’elle reçoit d’office']['champs']
        self.assertEqual(
            donnes[0],
            {
                'k': 'Le cycle en cours',
                'v': 'cycle_id ← le paramètre « cycle_id » de la tâche',
            },
        )
        self.assertIn('20 lignes au plus', donnes[1]['v'])
        self.assertEqual(
            [f['k'] for f in cadres['Le format de sa réponse']['champs']],
            ['fiches', 'fiches.title', 'fiches.description', 'fiches.offre'],
        )
        ecrit = cadres['Où sa réponse est écrite']['champs'][0]
        self.assertIn('lifecycle ← « CANDIDATE »', ecrit['v'])
        champs = {c['k']: c['v'] for c in fiche['champs']}
        self.assertEqual(champs['Reçoit « Qui est Serge »'], 'oui')
        matrice = project_matrice(self.conn, {}, NOW)['points']
        self.assertEqual(
            [p['nom'] for p in matrice],
            ['demo_ouvrir_cycle', 'demo_formuler', 'demo_choisir'],
        )
        self.assertEqual(champs['Appels d’outils au plus'], '4')


class PipelineDemoFrontTests(McBrowserCase):
    """Ce que Julien voit dans Mission Control, sur une base neuve."""

    def test_la_fiche_affiche_les_reglages(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/objet/llm/demo_formuler')
        fiche = page.locator('#page')
        for texte in (
            'Formuler des idées (démo)',
            'Propose exactement {nombre_idees} idées',
            'nombre_idees',
            'modifiable sur la page Policy',
            'Le cycle en cours',
            'cycle_id ← le paramètre « cycle_id » de la tâche',
            'Chercher sur le web public',
            'Demander une nouvelle capacité (partout)',
            'fiches.description',
            'Ajouter dans ventures',
            'lifecycle ← « CANDIDATE »',
            'Le cycle ouvert part en exploration',
            'Les idées formulées passent au choix',
        ):
            expect(fiche).to_contain_text(texte, timeout=10000)

    def test_cerveau_et_ecoute(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/mind')
        expect(page.locator('table.matrice tbody tr')).to_have_count(
            3, timeout=10000
        )
        expect(page.locator('[data-section="matrice"]')).to_contain_text(
            'Choisir un business (démo)'
        )
        page.goto(f'{self.base}/owner#/ecoute')
        expect(page.locator('[data-ecoute-action="lancer"]')).to_have_text(
            'Lancer un cycle (démo)', timeout=10000
        )
        expect(page.locator('[data-ecoute="invocations"]')).to_contain_text(
            'Ouvrir un cycle (démo)'
        )


if __name__ == '__main__':
    unittest.main()
