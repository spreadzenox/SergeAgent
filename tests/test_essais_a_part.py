#!/usr/bin/env python3
"""Les business d'essai sont à part (lot 12, décision Q98).

Un bouton d'essai de la page Système crée un business marqué « essai »
(``ventures.trial``). La base, l'interpréteur et le pipeline de départ sont
réels ; aucun modèle n'est appelé.

Scénarios :
- les trois places de test sont prises par de vrais business : « Bout en
  bout : le POC d'une calculatrice » part quand même, son business est un
  essai, et les places restent à 3 sur 3 ;
- un business d'essai en test ne prend pas de place : un vrai business
  peut encore être choisi ;
- une base du lot 11 : au démarrage, ses business d'essai sont marqués (le
  business de « Lancer un essai », la calculatrice d'un bout en bout), pas
  les vrais ;
- une instance du lot 11 : ses boutons d'essai ne dépendent plus des places
  de test, et leurs business sont marqués.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.migrate import MIGRATIONS, apply_pending  # noqa: E402
from serge.interpreter.flow import fire_button, trigger_refusal  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.rules import quota_refusal, quota_usage  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from serge.policy import config_dir  # noqa: E402
from serge.registry import read_yaml_file  # noqa: E402

MAINTENANT = '2026-11-16T18:00:00+00:00'


def _business(conn: sqlite3.Connection, nom: str, statut: str, **plus) -> None:
    colonnes = {'id': f'ven_{nom}', 'name': nom, 'lifecycle': statut, **plus}
    conn.execute(
        f'INSERT INTO ventures({", ".join(colonnes)}, created_at, updated_at)'
        f' VALUES({", ".join("?" * len(colonnes))}, ?, ?)',
        (*colonnes.values(), MAINTENANT, MAINTENANT),
    )


class PlacesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event<>'button'"
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _places(self) -> tuple[int, int]:
        usage = quota_usage(self.conn, 'places_de_test')
        assert usage is not None
        return usage[0], usage[1]

    def test_un_essai_part_meme_quand_les_places_sont_prises(self) -> None:
        for nom in ('devis', 'paie', 'stock'):
            _business(self.conn, nom, 'POC_SELECTED')
        self.assertEqual(self._places(), (3, 3))
        self.assertIn('3 sur 3', trigger_refusal(self.conn, 'lancer_cycle'))
        tache = fire_button(self.conn, 'bouton_bout_en_bout_poc', {})
        self.assertIsNotNone(tache, 'le bouton d’essai n’est pas refusé')
        self.conn.commit()
        process_one(self.conn, 'works', now=MAINTENANT)
        essai, statut = self.conn.execute(
            "SELECT trial, lifecycle FROM ventures WHERE name='Calculatrice'"
        ).fetchone()
        self.assertEqual((essai, statut), (1, 'POC_SELECTED'))
        self.assertEqual(self._places(), (3, 3), 'l’essai ne compte pas')

    def test_un_essai_ne_prend_pas_la_place_d_un_vrai_business(self) -> None:
        _business(self.conn, 'calculatrice', 'SMOKE_READY', trial=1)
        _business(self.conn, 'devis', 'POC_SELECTED')
        _business(self.conn, 'paie', 'POC_SELECTED')
        self.assertEqual(self._places(), (2, 3))
        choisir = {'lifecycle': 'POC_SELECTED'}
        # Un troisième vrai business entre ; le quatrième est refusé.
        self.assertEqual(
            quota_refusal(self.conn, 'ventures', choisir, None), ''
        )
        _business(self.conn, 'stock', 'POC_SELECTED')
        self.assertIn(
            'places_de_test',
            quota_refusal(self.conn, 'ventures', choisir, None),
        )
        # Un essai, lui, n'est jamais refusé : créé comme essai, ou déjà
        # marqué quand son statut change.
        self.assertEqual(
            quota_refusal(
                self.conn, 'ventures', {**choisir, 'trial': 1}, None
            ),
            '',
        )
        self.assertEqual(
            quota_refusal(
                self.conn,
                'ventures',
                choisir,
                {'lifecycle': 'CANDIDATE', 'trial': 1},
            ),
            '',
        )


class BaseDuLot11Tests(unittest.TestCase):
    def test_les_essais_deja_en_base_sont_marques(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn, [m for m in MIGRATIONS if m[0] <= 51], head=51)
        _business(conn, 'devis_vocal', 'TEST')
        _business(
            conn,
            'calculatrice',
            'PRODUCT_READY',
            choice_reason='Essai de bout en bout du produit fini depuis'
            ' Mission Control.',
        )
        _business(
            conn,
            'paie',
            'POC_SELECTED',
            choice_reason='Douze artisans demandent la même chose.',
        )
        apply_pending(conn, MIGRATIONS)
        marques = dict(conn.execute('SELECT name, trial FROM ventures'))
        self.assertEqual(
            marques, {'devis_vocal': 1, 'calculatrice': 1, 'paie': 0}
        )

    def test_une_instance_du_lot_11_met_ses_essais_a_part(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        # Comme avant le lot 12 : les places comptent tout, deux boutons
        # d'essai en dépendent, et rien ne marque les business d'essai.
        conn.execute(
            "UPDATE table_quotas SET where_column='', where_value=''"
            " WHERE id='places_de_test'"
        )
        conn.executemany(
            'INSERT INTO trigger_conditions(trigger_id, quota_id)'
            " VALUES(?, 'places_de_test')",
            [('bouton_essayer_etape2',), ('bouton_bout_en_bout_poc',)],
        )
        conn.execute(
            "DELETE FROM invocation_write_values WHERE column_name='trial'"
        )
        conn.execute(
            "DELETE FROM pipeline_changes WHERE id LIKE 'essais_a_part_%'"
        )
        seed_pipeline(conn, data)
        self.assertEqual(
            conn.execute(
                'SELECT where_column, where_value FROM table_quotas'
                " WHERE id='places_de_test'"
            ).fetchone(),
            ('trial', '0'),
        )
        self.assertEqual(
            [
                r[0]
                for r in conn.execute(
                    'SELECT trigger_id FROM trigger_conditions'
                    " WHERE quota_id='places_de_test' ORDER BY trigger_id"
                )
            ],
            ['lancer_cycle'],
        )
        marquent = {
            str(r[0])
            for r in conn.execute(
                'SELECT w.invocation_id FROM invocation_write_values v'
                ' JOIN invocation_writes w ON w.id=v.write_id'
                " WHERE v.column_name='trial' AND v.value='1'"
            )
        }
        self.assertEqual(
            marquent,
            {
                'lancer_essai',
                'creer_business_essai',
                'bout_en_bout_poc',
                'bout_en_bout_produit',
            },
        )


if __name__ == '__main__':
    unittest.main()
