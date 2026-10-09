#!/usr/bin/env python3
"""Les modifications d'objets déjà en base (section ``changes``).

Scénarios :
- une modification passe une seule fois, et son résultat est noté ;
- une valeur changée dans Mission Control est gardée ;
- une instance neuve, déjà à jour, n'est pas touchée ;
- une instance du lot 7 telle qu'elle a été déployée (25 tours d'outils
  pour « Explorer le web », 300 lignes par page, anciens prompts) reçoit
  les réglages qui renvoient moins de jetons, et les réglages nouveaux ;
- une instance déployée avant les réglages de recommandation (niveaux de
  modèle sans prix maximum) les reçoit, sans écraser un prix que Julien a
  déjà changé ;
- un outil nouveau s'ajoute une seule fois à une invocation déjà en base,
  à la fin de ses outils, avec ses paramètres ;
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
        self.assertEqual(
            resultats['voix_email_du_contact'], 'email_du_contact déjà là'
        )

    def test_un_outil_nouveau_s_ajoute_une_seule_fois(self) -> None:
        outil = {
            'tool': 'fiche_contact',
            'mode': 'given',
            'label': 'Sa fiche',
            'params': {
                'contact_id': {'source': 'task', 'value': 'contact_id'}
            },
        }
        self.conn.execute(
            "DELETE FROM invocation_tools WHERE invocation_id='explorer_web'"
            " AND tool_id='fiche_contact'"
        )
        changes = [
            {
                'id': 'outil',
                'invocation': 'explorer_web',
                'add_tools': [outil],
            },
            {'id': 'absente', 'invocation': 'inconnue', 'add_tools': [outil]},
        ]
        apply_changes(self.conn, changes)
        self.assertEqual(self._resultat('outil'), 'fiche_contact ajouté')
        self.assertEqual(self._resultat('absente'), 'objet absent')
        lien, position = self.conn.execute(
            'SELECT id, position FROM invocation_tools'
            " WHERE invocation_id='explorer_web' AND tool_id='fiche_contact'"
        ).fetchone()
        self.assertEqual(
            position,
            self.conn.execute(
                'SELECT MAX(position) FROM invocation_tools'
                " WHERE invocation_id='explorer_web'"
            ).fetchone()[0],
        )
        self.assertEqual(
            self.conn.execute(
                'SELECT param_name, source, value FROM invocation_tool_params'
                ' WHERE invocation_tool_id=?',
                (lien,),
            ).fetchall(),
            [('contact_id', 'task', 'contact_id')],
        )
        with self.assertRaises(PipelineSeedError):
            apply_changes(
                self.conn,
                [{'id': 'mal', 'invocation': 'explorer_web', 'add_tools': {}}],
            )
        # Les champs d'une réponse et les valeurs d'une écriture : une
        # invocation ou une écriture absente est notée, une forme fausse
        # est refusée.
        apply_changes(
            self.conn,
            [
                {
                    'id': 'sortie_absente',
                    'invocation': 'inconnue',
                    'add_outputs': [{'path': 'x', 'type': 'text'}],
                },
                {
                    'id': 'ecriture_absente',
                    'invocation': 'explorer_web',
                    'write': 99,
                    'add_write_values': {'x': {'source': 'fixed'}},
                },
            ],
        )
        self.assertEqual(self._resultat('sortie_absente'), 'objet absent')
        self.assertEqual(
            self._resultat('ecriture_absente'), 'écriture absente'
        )
        for mauvais in (
            {'add_outputs': [{'path': 'x'}]},
            {'write': 'deux', 'add_write_values': {}},
        ):
            with self.assertRaises(PipelineSeedError, msg=mauvais):
                apply_changes(
                    self.conn,
                    [{'id': 'mal2', 'invocation': 'explorer_web', **mauvais}],
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
            if 'prompt' in c.get('set', {})
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


class NiveauxDeModeleTests(unittest.TestCase):
    """Le prix maximum et la tolérance des niveaux, sur une instance existante."""

    def _niveaux(self, conn: sqlite3.Connection) -> dict[str, tuple]:
        return {
            tier: (price, pct, model)
            for tier, price, pct, model in conn.execute(
                'SELECT tier, max_price_usd, tolerance_pct, model'
                ' FROM llm_models'
            )
        }

    def test_une_instance_neuve_a_les_valeurs_de_depart(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        self.assertEqual(
            self._niveaux(conn),
            {
                'fast': (0.3, 85, ''),
                'mid': (1.5, 95, ''),
                'smart': (8.0, 95, ''),
            },
        )

    def test_une_instance_existante_les_recoit_sans_ecraser_julien(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        # L'instance telle qu'elle était avant : niveaux sans réglage, un
        # modèle choisi sur le niveau moyen, un prix déjà changé à la main.
        conn.executescript(
            'UPDATE llm_models SET max_price_usd=0, tolerance_pct=95;'
            "UPDATE llm_models SET model='a/choisi' WHERE tier='mid';"
            "UPDATE llm_models SET max_price_usd=2.5 WHERE tier='smart';"
            "DELETE FROM pipeline_changes WHERE id LIKE 'modele_%';"
        )
        ensure_pipeline(conn)
        self.assertEqual(
            self._niveaux(conn),
            {
                'fast': (0.3, 85, ''),
                'mid': (1.5, 95, 'a/choisi'),
                'smart': (2.5, 95, ''),
            },
        )
        resultats = dict(
            conn.execute(
                'SELECT id, result FROM pipeline_changes'
                " WHERE id LIKE 'modele_%'"
            )
        )
        self.assertIn(
            'gardé (changé dans Mission Control)',
            resultats['modele_smart_prix_max'],
        )
        # Rejouée, elle ne change plus rien.
        ensure_pipeline(conn)
        self.assertEqual(self._niveaux(conn)['smart'][0], 2.5)


if __name__ == '__main__':
    unittest.main()
