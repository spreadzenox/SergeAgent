#!/usr/bin/env python3
"""Migrations canon : vide → tête, déjà à jour, refus (trou / code trop vieux)."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.migrate import (  # noqa: E402
    MigrateError,
    apply_pending,
    read_version,
)
from serge.db.schema import SCHEMA_VERSION, TABLES  # noqa: E402
from serge.db.v015 import apply_v015  # noqa: E402
from serge.db.v018 import apply_v018  # noqa: E402
from serge.db.v020 import apply_v020  # noqa: E402
from serge.db.v021 import apply_v021  # noqa: E402
from serge.db.v022 import apply_v022  # noqa: E402
from serge.db.v023 import apply_v023  # noqa: E402


def _until(version: int) -> list:
    """Les migrations jusqu'à ``version`` : ne bouge pas quand on en ajoute."""
    from serge.db.migrate import MIGRATIONS

    return [m for m in MIGRATIONS if m[0] <= version]


class MigrateTests(unittest.TestCase):
    def test_v20_ajoute_les_metadonnees_llm_avec_defaults_valides(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute(
            'CREATE TABLE llm_points (id TEXT PRIMARY KEY,'
            " updated_at TEXT NOT NULL DEFAULT 'legacy')"
        )
        conn.execute("INSERT INTO llm_points(id) VALUES('legacy')")
        apply_v020(conn)
        columns = {
            row[1]: row[4]
            for row in conn.execute('PRAGMA table_info(llm_points)')
        }
        self.assertEqual(columns['prompt'], "''")
        self.assertEqual(columns['output_mode'], "'text'")
        self.assertEqual(columns['external_info'], '0')
        self.assertEqual(
            conn.execute(
                "SELECT updated_at FROM llm_points WHERE id='legacy'"
            ).fetchone()[0],
            '',
        )
        conn.execute("INSERT INTO llm_points(id) VALUES('p')")
        self.assertEqual(
            conn.execute(
                'SELECT prompt, output_mode, external_info FROM llm_points'
            ).fetchone(),
            ('', 'text', 0),
        )

    def test_v21_fond_les_business_dans_ventures(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.executescript(
            """
            CREATE TABLE ventures (
                id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
                lifecycle TEXT NOT NULL DEFAULT 'CANDIDATE',
                schedulable INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
                actor TEXT NOT NULL, venture_id TEXT NOT NULL DEFAULT '',
                type TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
                links_json TEXT NOT NULL DEFAULT '{}');
            CREATE TABLE tool_db_tables (tool_id TEXT, table_name TEXT,
                position INTEGER);
            """
        )
        apply_v015(conn)
        conn.executescript(
            """
            INSERT INTO business_candidates(id, title, content,
                normalized_key, status, created_at, updated_at)
            VALUES ('b1', 'Devis vocal', 'Outil pour artisans', 'k1',
                'POC_SELECTED', 't1', 't1'),
                ('b2', 'Autre', 'Autre besoin', 'k2', 'CANDIDATE', 't2', 't2');
            INSERT INTO business_candidate_sources VALUES ('b1', 'd1', 'c1');
            INSERT INTO poc_selections(id, cycle_id, candidate_id, rank,
                selected_at) VALUES ('c1:b1', 'c1', 'b1', 1, 't3');
            INSERT INTO tool_db_tables VALUES
                ('eligible_poc_candidates', 'business_candidates', 0);
            """
        )
        apply_v021(conn)
        self.assertEqual(
            conn.execute(
                'SELECT id, name, lifecycle, description, dedup_key'
                ' FROM ventures ORDER BY id'
            ).fetchall(),
            [
                (
                    'b1',
                    'Devis vocal',
                    'POC_SELECTED',
                    'Outil pour artisans',
                    'k1',
                ),
                ('b2', 'Autre', 'CANDIDATE', 'Autre besoin', 'k2'),
            ],
        )
        self.assertEqual(
            conn.execute('SELECT * FROM venture_sources').fetchall(),
            [('b1', 'd1', 'c1')],
        )
        evenement = conn.execute(
            'SELECT venture_id, type, payload_json FROM events'
        ).fetchone()
        self.assertEqual(evenement[:2], ('b1', 'venture.poc_selected'))
        self.assertEqual(json.loads(evenement[2])['cycle_id'], 'c1')
        restantes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertFalse(
            {
                'business_candidates',
                'business_candidate_sources',
                'poc_selections',
            }
            & restantes
        )
        self.assertEqual(
            conn.execute('SELECT COUNT(*) FROM tool_db_tables').fetchone()[0],
            0,
        )

    def test_v18_backfill_reconstruit_contacts(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute(
            """CREATE TABLE contacts (
                id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
                display TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
                venue TEXT NOT NULL DEFAULT '', handle TEXT NOT NULL DEFAULT '',
                profile_url TEXT NOT NULL DEFAULT '',
                regime TEXT NOT NULL DEFAULT 'OUTBOUND',
                funnel_state TEXT NOT NULL DEFAULT 'NEW',
                last_inbound_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)
            """
        )
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email, phone, venue,'
            ' handle, profile_url, regime, funnel_state, created_at, updated_at)'
            " VALUES('p1','v1','Ada','ada@x.io','+33612345678','linkedin',"
            "'ada','https://linkedin.test/ada','INBOUND','ENGAGED','t','t')"
        )
        apply_v018(conn)
        columns = {
            row[1] for row in conn.execute('PRAGMA table_info(contacts)')
        }
        self.assertNotIn('email', columns)
        self.assertNotIn('phone', columns)
        row = conn.execute(
            'SELECT contact_reference_by_canal, regime, funnel_state'
            ' FROM contacts WHERE id=?',
            ('p1',),
        ).fetchone()
        references = json.loads(row[0])
        self.assertEqual(references['email']['address'], 'ada@x.io')
        self.assertEqual(references['voice']['phone'], '+33612345678')
        self.assertEqual(references['linkedin']['handle'], 'ada')
        self.assertEqual(row[1:], ('INBOUND', 'ENGAGED'))

    def test_v22_range_les_adresses_une_par_ligne(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute(
            """CREATE TABLE contacts (
                id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
                display TEXT NOT NULL DEFAULT '',
                contact_reference_by_canal TEXT NOT NULL DEFAULT '{}',
                regime TEXT NOT NULL DEFAULT 'OUTBOUND',
                funnel_state TEXT NOT NULL DEFAULT 'NEW',
                last_inbound_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)
            """
        )
        references = {
            'email': {'address': 'Ada@X.io', 'active': False},
            'voice': {'phone': '+33 6 12 34 56 78', 'active': True},
            'linkedin': {
                'handle': 'ada',
                'profile_url': 'https://linkedin.test/ada',
            },
        }
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display,'
            ' contact_reference_by_canal, created_at, updated_at)'
            " VALUES('p1','v1','Ada',?,'t','t')",
            (json.dumps(references),),
        )
        apply_v022(conn)
        apply_v022(conn)
        columns = {
            row[1] for row in conn.execute('PRAGMA table_info(contacts)')
        }
        self.assertNotIn('contact_reference_by_canal', columns)
        rows = conn.execute(
            'SELECT channel, value, value_norm, active FROM contact_addresses'
            " WHERE contact_id='p1' ORDER BY channel, value"
        ).fetchall()
        self.assertEqual(
            rows,
            [
                ('email', 'Ada@X.io', 'ada@x.io', 0),
                ('linkedin', 'ada', 'ada', 1),
                (
                    'linkedin',
                    'https://linkedin.test/ada',
                    'https://linkedin.test/ada',
                    1,
                ),
                ('phone', '+33 6 12 34 56 78', '+33612345678', 1),
            ],
        )

    def test_v23_retire_le_faux_business_des_abonnements(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.executescript(
            """
            CREATE TABLE subscriptions (
                id TEXT PRIMARY KEY, venture_id TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL);
            CREATE TABLE transactions (
                id TEXT PRIMARY KEY, venture_id TEXT NOT NULL);
            INSERT INTO subscriptions VALUES
                ('abo_1','serge-collect-stripe','stripe','t','t'),
                ('abo_2','v1','stripe','t','t');
            INSERT INTO transactions VALUES
                ('tx_1','serge-collect-stripe'), ('tx_2','v1');
            """
        )
        apply_v023(conn)
        apply_v023(conn)
        self.assertEqual(
            conn.execute(
                'SELECT venture_id, last_transaction_id FROM subscriptions'
                ' ORDER BY id'
            ).fetchall(),
            [('', ''), ('v1', '')],
        )
        self.assertEqual(
            conn.execute(
                'SELECT venture_id FROM transactions ORDER BY id'
            ).fetchall(),
            [('',), ('v1',)],
        )

    def test_vide_atteint_la_tete(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        reached = apply_pending(conn)
        self.assertEqual(reached, SCHEMA_VERSION)
        self.assertEqual(read_version(conn), SCHEMA_VERSION)
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table in TABLES:
            self.assertIn(table, names)

    def test_deja_a_jour_ne_restamp_pas(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn)
        before = conn.execute(
            'SELECT version, applied_at FROM schema_version'
        ).fetchone()
        apply_pending(conn)
        after = conn.execute(
            'SELECT version, applied_at FROM schema_version'
        ).fetchone()
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])

    def test_code_plus_vieux_que_la_db_refuse(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn)
        conn.execute('DELETE FROM schema_version')
        conn.execute(
            'INSERT INTO schema_version(version, applied_at)'
            " VALUES(?, datetime('now'))",
            (SCHEMA_VERSION + 5,),
        )
        with self.assertRaises(MigrateError) as ctx:
            apply_pending(conn)
        self.assertIn('plus récent', str(ctx.exception))

    def test_trou_apres_le_socle_refuse(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn)

        def _noop(_conn: sqlite3.Connection) -> None:
            return None

        with self.assertRaises(MigrateError) as ctx:
            apply_pending(
                conn,
                migrations=(
                    (SCHEMA_VERSION, _noop),
                    (SCHEMA_VERSION + 2, _noop),
                ),
                head=SCHEMA_VERSION + 2,
            )
        self.assertIn('trou', str(ctx.exception))

    def test_v7_vers_v8_remappe_les_etapes(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        from serge.db.migrate import MIGRATIONS, stamp
        from serge.db.schema import apply_v007

        apply_v007(conn)
        stamp(conn, 7)
        conn.execute(
            'INSERT INTO pipeline_steps(id, enabled, kinds_json, rang)'
            " VALUES('ecoute', 0, '[]', 0), ('test', 1, '[]', 2)"
        )
        conn.execute(
            'INSERT INTO work_items(id, kind, idempotency_key, created_at,'
            " updated_at) VALUES('w1','listen.collect','k','t','t')"
        )
        self.assertEqual(apply_pending(conn, MIGRATIONS[:2], head=8), 8)
        etape = conn.execute(
            "SELECT etape_id FROM work_items WHERE id='w1'"
        ).fetchone()[0]
        self.assertEqual(etape, 'pre_prospection')
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        marche = conn.execute(
            "SELECT enabled FROM pipeline_steps WHERE id='pre_prospection'"
        ).fetchone()[0]
        self.assertEqual(marche, 0)

    def test_v25_retire_l_ancien_fonctionnement(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)

        apply_pending(conn, _until(24), head=24)
        conn.execute(
            'INSERT INTO runtime_flags(name, value, set_at) VALUES'
            " ('kind.email.send', 'kill', 't'), ('llm.fill_slots', 'kill',"
            " 't'), ('scheduler.heartbeat', 'kill', 't')"
        )
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        tables = {
            str(r[0])
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for old in (
            'llm_points',
            'llm_point_tools',
            'tech_invocations',
            'db_readers',
            'llm_point_readers',
            'db_reader_fixed_params',
            'db_reader_fixed_joins',
            'etape_liens',
            'work_items',
            'brique_canaux',
        ):
            self.assertNotIn(old, tables)
        colonnes = {
            str(r[1]) for r in conn.execute('PRAGMA table_info(tools)')
        }
        self.assertNotIn('kind', colonnes)
        self.assertIn('capability_id', colonnes)
        colonnes = {
            str(r[1])
            for r in conn.execute('PRAGMA table_info(pipeline_steps)')
        }
        self.assertNotIn('kinds_json', colonnes)
        flags = [r[0] for r in conn.execute('SELECT name FROM runtime_flags')]
        self.assertEqual(flags, ['scheduler.heartbeat'])

    def test_init_schema_seme_apres_migrate(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        row = conn.execute(
            'SELECT id, titre, files_sha, updated_at FROM pipeline_steps'
            " WHERE id='pre_prospection'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 'Pré-prospection')
        self.assertTrue(row[2])
        self.assertTrue(row[3])
        outil = conn.execute(
            "SELECT capability_id FROM tools WHERE id='preuves_des_candidats'"
        ).fetchone()
        self.assertEqual(outil, ('db_read',))
        jointures = conn.execute(
            'SELECT left_table, right_table FROM tool_db_joins'
            " WHERE tool_id='preuves_des_candidats' ORDER BY position"
        ).fetchall()
        self.assertEqual(
            jointures,
            [
                ('venture_sources', 'ventures'),
                ('venture_sources', 'listen_docs'),
            ],
        )

    def test_v26_ajoute_les_reglages_et_garde_les_parametres(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)

        apply_pending(conn, _until(25), head=25)
        conn.execute(
            'INSERT INTO invocation_tool_params(invocation_id,'
            ' invocation_tool_id, param_name, source, value)'
            " VALUES('inv', 1, 'cycle_id', 'task', 'cycle_id')"
        )
        conn.execute(
            'INSERT INTO link_params(link_id, param_name, source, value)'
            " VALUES('l1', 'venture_id', 'row', 'id')"
        )
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        self.assertEqual(
            conn.execute(
                'SELECT param_name, source FROM invocation_tool_params'
            ).fetchall(),
            [('cycle_id', 'task')],
        )
        conn.execute(
            'INSERT INTO link_params(link_id, param_name, source, value)'
            " VALUES('l1', 'n', 'setting', 'nombre_idees')"
        )
        colonnes = {
            str(r[1])
            for r in conn.execute('PRAGMA table_info(invocation_writes)')
        }
        self.assertIn('max_rows', colonnes)
        for table in ('invocation_settings', 'table_quotas'):
            self.assertIsNotNone(
                conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    ' AND name=?',
                    (table,),
                ).fetchone()
            )

    def test_v27_reprend_l_historique_des_lignes(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)

        apply_pending(conn, _until(26), head=26)
        conn.executemany(
            'INSERT INTO events(ts, actor, venture_id, type, payload_json)'
            ' VALUES(?,?,?,?,?)',
            [
                ('t1', 'guard', 'v1', 'transition.x', '{}'),
                (
                    't2',
                    'invocation:a',
                    '',
                    'write.inserted',
                    '{"table": "listen_cycles", "id": 7}',
                ),
                ('t3', 'owner', '', 'mc_act', '{"table": "ventures"}'),
            ],
        )
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        self.assertEqual(
            conn.execute(
                'SELECT event_id, table_name, row_id FROM event_rows'
                ' ORDER BY event_id'
            ).fetchall(),
            [(1, 'ventures', 'v1'), (2, 'listen_cycles', '7')],
        )

    def test_v29_range_le_cycle_sur_la_page_et_nettoie_le_catalogue(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)

        apply_pending(conn, _until(28), head=28)
        conn.executescript(
            'INSERT INTO listen_docs(id, source, fetched_at, cluster_id)'
            " VALUES('d1', 'rss', 't', 'cA');"
            "INSERT INTO listen_cycle_docs(cycle_id, doc_id) VALUES('c1', 'd1');"
            'INSERT INTO tools(id, titre, capability_id) VALUES'
            " ('pages_du_cycle', 'x', 'db_read');"
            'INSERT INTO tool_db_tables(tool_id, table_name, position) VALUES'
            " ('pages_du_cycle', 'listen_cycle_docs', 0);"
            'INSERT INTO tool_db_columns(tool_id, table_name, column_name,'
            " position) VALUES ('cycle', 'listen_cycles', 'needs_target', 0);"
            'INSERT INTO writable_tables(table_name, can_update) VALUES'
            " ('ventures', 1);"
        )
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        self.assertEqual(
            conn.execute('SELECT cycle_id FROM listen_docs').fetchone(),
            ('c1',),
        )
        for requete in (
            "SELECT 1 FROM tools WHERE id='pages_du_cycle'",
            "SELECT 1 FROM tool_db_columns WHERE column_name='needs_target'",
            "SELECT 1 FROM sqlite_master WHERE name='listen_cycle_docs'",
        ):
            self.assertIsNone(conn.execute(requete).fetchone(), requete)
        colonnes = {
            str(r[1]) for r in conn.execute('PRAGMA table_info(listen_cycles)')
        }
        self.assertNotIn('needs_target', colonnes)
        self.assertEqual(
            conn.execute(
                "SELECT can_delete FROM writable_tables WHERE table_name='ventures'"
            ).fetchone(),
            (0,),
        )

    def test_v30_ajoute_le_cout_reel_et_le_suivi_des_modifications(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)

        apply_pending(conn, _until(29), head=29)
        conn.execute(
            'INSERT INTO llm_usage(point, tier, created_at)'
            " VALUES('a', 'mid', 't')"
        )
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        self.assertEqual(
            conn.execute('SELECT cost_usd FROM llm_usage').fetchone(), (None,)
        )
        conn.execute(
            "INSERT INTO pipeline_changes(id, applied_at) VALUES('x', 't')"
        )

    def test_v31_ajoute_le_prix_maximum_et_la_tolerance_des_niveaux(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)

        apply_pending(conn, _until(30), head=30)
        # Une instance existante : les niveaux et le modèle choisi sont là.
        for tier, model in (('fast', ''), ('mid', 'a/choisi'), ('smart', '')):
            conn.execute(
                'INSERT INTO llm_models(tier, model) VALUES(?, ?)',
                (tier, model),
            )
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        self.assertEqual(
            conn.execute(
                'SELECT tier, model, max_price_usd, tolerance_pct'
                ' FROM llm_models ORDER BY tier'
            ).fetchall(),
            [
                ('fast', '', 0.0, 95),
                ('mid', 'a/choisi', 0.0, 95),
                ('smart', '', 0.0, 95),
            ],
        )
        # La base refuse l'absurde.
        for bad in (
            'UPDATE llm_models SET tolerance_pct=0',
            'UPDATE llm_models SET tolerance_pct=101',
            'UPDATE llm_models SET tolerance_pct=NULL',
            'UPDATE llm_models SET max_price_usd=-1',
        ):
            with self.assertRaises(sqlite3.IntegrityError, msg=bad):
                conn.execute(bad)
        # Rejouée, la migration ne change rien.
        from serge.db.v031 import apply_v031

        apply_v031(conn)
        self.assertEqual(
            conn.execute(
                "SELECT model FROM llm_models WHERE tier='mid'"
            ).fetchone(),
            ('a/choisi',),
        )

    def test_v32_ajoute_les_regles_d_annulation(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn, _until(31), head=31)
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        conn.execute(
            'INSERT INTO task_cancel_rules(table_name, column_name, value,'
            " param_name) VALUES('t', 'c', 'v', 'p')"
        )


if __name__ == '__main__':
    unittest.main()
