#!/usr/bin/env python3
"""Les modifications d'objets déjà en base (section ``changes``).

Scénarios :
- une modification passe une seule fois, et son résultat est noté ;
- une valeur changée dans Mission Control est gardée ;
- une instance neuve, déjà à jour, n'est pas touchée ;
- une instance du lot 7 telle qu'elle a été déployée (25 tours d'outils
  pour « Explorer le web », 300 lignes par page, anciens prompts) reçoit
  les réglages qui renvoient moins de jetons, et les réglages nouveaux ;
- une modification mal écrite est refusée.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.pipeline_changes import apply_changes  # noqa: E402
from serge.pipeline_seed import ensure_pipeline  # noqa: E402
from serge.policy import config_dir, read_yaml_file  # noqa: E402
from serge.seed_base import PipelineSeedError  # noqa: E402


def _changement(de: int, vers: int, ident: str = 'tours') -> list[dict]:
    return [
        {
            'id': ident,
            'table': 'invocations',
            'where': {'id': 'explorer_web'},
            'set': {'max_tool_turns': {'from': de, 'to': vers}},
        }
    ]


class ChangesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _tours(self) -> int:
        return int(
            self.conn.execute(
                "SELECT max_tool_turns FROM invocations WHERE id='explorer_web'"
            ).fetchone()[0]
        )

    def _resultat(self, ident: str) -> str:
        return str(
            self.conn.execute(
                'SELECT result FROM pipeline_changes WHERE id=?', (ident,)
            ).fetchone()[0]
        )

    def test_une_modification_passe_une_seule_fois(self) -> None:
        apply_changes(self.conn, _changement(10, 7))
        self.assertEqual(self._tours(), 7)
        self.assertEqual(self._resultat('tours'), 'max_tool_turns : 10 → 7')
        self.conn.execute(
            "UPDATE invocations SET max_tool_turns=10 WHERE id='explorer_web'"
        )
        apply_changes(self.conn, _changement(10, 7))
        self.assertEqual(self._tours(), 10)

    def test_une_valeur_changee_dans_mission_control_est_gardee(self) -> None:
        self.conn.execute(
            "UPDATE invocations SET max_tool_turns=4 WHERE id='explorer_web'"
        )
        apply_changes(self.conn, _changement(10, 7))
        self.assertEqual(self._tours(), 4)
        self.assertIn('changé dans Mission Control', self._resultat('tours'))

    def test_une_instance_neuve_est_deja_a_jour(self) -> None:
        resultats = dict(
            self.conn.execute('SELECT id, result FROM pipeline_changes')
        )
        self.assertEqual(
            resultats['lot7_explorer_10_tours'], 'max_tool_turns déjà à jour'
        )
        self.assertEqual(
            resultats['lot7_formuler_a_plusieurs_pages'], 'prompt déjà à jour'
        )

    def test_une_modification_mal_ecrite_est_refusee(self) -> None:
        for mauvais in (
            {'table': 'ventures'},
            {'set': {'colonne_inconnue': {'from': 1, 'to': 2}}},
            {'where': {}},
        ):
            change = {**_changement(10, 7, 'mauvais')[0], **mauvais}
            with self.assertRaises(PipelineSeedError, msg=mauvais):
                apply_changes(self.conn, [change])


class InstanceDuLot7Tests(unittest.TestCase):
    """Le serveur de Julien, tel que le lot 7 l'a laissé."""

    def test_elle_recoit_les_reglages_qui_renvoient_moins_de_jetons(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        anciens = {
            c['where']['id']: c['set']['prompt']['from']
            for c in data['changes']
            if 'prompt' in c['set']
        }
        for ident, tours in (
            ('explorer_web', 25),
            ('formuler_a', 10),
            ('formuler_b', 10),
        ):
            conn.execute(
                'UPDATE invocations SET max_tool_turns=?, prompt=? WHERE id=?',
                (tours, anciens[ident].strip(), ident),
            )
        conn.executescript(
            "UPDATE invocation_tools SET max_calls='' WHERE tool_id="
            "'lire_page_entiere';"
            "UPDATE invocation_settings SET value='300' WHERE"
            " name='lignes_page_entiere';"
            "DELETE FROM invocation_settings WHERE name='pages_entieres_max';"
            'DELETE FROM pipeline_changes;'
        )
        conn.execute(
            "UPDATE triggers SET confirm_text=? WHERE id='bouton_abandonner_cycle'",
            (
                'Le cycle ouvert est fermé, pour pouvoir en lancer un autre.'
                ' Ses tâches déjà en file continuent, mais ne peuvent plus le'
                ' fermer.',
            ),
        )
        ensure_pipeline(conn)
        question = conn.execute(
            "SELECT confirm_text FROM triggers WHERE id='bouton_abandonner_cycle'"
        ).fetchone()[0]
        self.assertIn('tâches en attente sont annulées', question)
        tours = dict(
            conn.execute(
                'SELECT id, max_tool_turns FROM invocations WHERE id IN'
                " ('explorer_web', 'formuler_a', 'formuler_b')"
            )
        )
        self.assertEqual(
            tours, {'explorer_web': 10, 'formuler_a': 5, 'formuler_b': 5}
        )
        self.assertEqual(
            conn.execute(
                'SELECT DISTINCT max_calls FROM invocation_tools'
                " WHERE tool_id='lire_page_entiere'"
            ).fetchall(),
            [('pages_entieres_max',)],
        )
        reglages = conn.execute(
            'SELECT invocation_id, name, value FROM invocation_settings'
            " WHERE name IN ('lignes_page_entiere', 'pages_entieres_max')"
            ' ORDER BY invocation_id, name'
        ).fetchall()
        self.assertEqual(
            reglages,
            [
                ('formuler_a', 'lignes_page_entiere', '150'),
                ('formuler_a', 'pages_entieres_max', '10'),
                ('formuler_b', 'lignes_page_entiere', '150'),
                ('formuler_b', 'pages_entieres_max', '10'),
            ],
        )
        prompt = conn.execute(
            "SELECT prompt FROM invocations WHERE id='formuler_b'"
        ).fetchone()[0]
        self.assertIn("Demande plusieurs pages d'un coup", prompt)


if __name__ == '__main__':
    unittest.main()
