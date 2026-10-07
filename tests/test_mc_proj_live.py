#!/usr/bin/env python3
"""Projecteurs P0 : golden sur fixtures (hero, urgents, files, feed, jauges)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.funnels.contacts import add_address  # noqa: E402
from serge.mc.proj_live import (  # noqa: E402
    project_feed,
    project_jauges,
    project_urgents,
)
from serge.mc.proj_taches import (  # noqa: E402
    project_file,
    project_file_detail,
    project_hero,
)
from tests.taches_fixtures import invocations, tache  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY = {
    'budget': {'llm_daily_eur': 5.0},
    'channels': {'email': {'max_per_day': 40}},
    'quotas': {
        'voice_max_calls_per_day': 50,
        'linkedin_connect_per_day': 20,
    },
}


class ProjLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, regime, funnel_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                'p1',
                'v1',
                'Ada',
                'OUTBOUND',
                'CONTACTING',
                't',
                't',
            ),
        )
        add_address(self.conn, 'p1', 'email', 'ada@x.io')
        invocations(
            self.conn,
            ('envoyer', 'Envoyer un e-mail', 'prospection_light'),
            ('classer', 'Classer une réponse', 'prospection_lourde'),
        )
        tache(
            self.conn,
            'envoyer',
            {'venture_id': 'v1'},
            key='k-run',
            status='running',
            created_at='2026-09-10T11:00:00+00:00',
        )
        self.first = tache(
            self.conn,
            'classer',
            {'venture_id': 'v1'},
            key='k-r1',
            created_at='2026-09-10T10:00:00+00:00',
        )
        tache(self.conn, 'classer', {'venture_id': 'v1'}, key='k-r2')
        for tid, typ, title, expiry in (
            ('t-guichet', 'GUICHET', 'Captcha', '2026-09-10T12:10:00+00:00'),
            ('t-veto30', 'VETO_AMONT', 'Prix', '2026-09-10T12:30:00+00:00'),
            ('t-veto2h', 'VETO_AMONT', 'Tard', '2026-09-10T14:00:00+00:00'),
            ('t-alert', 'ALERT', 'Quota', ''),
            ('t-hypo', 'HYPOTHESIS', 'H1', ''),
        ):
            self.conn.execute(
                'INSERT INTO tickets(id, type, title, state, expiry_at,'
                " created_at, updated_at) VALUES(?,?,?,'OPEN',?,?,?)",
                (tid, typ, title, expiry, NOW, NOW),
            )
        self.conn.execute(
            'INSERT INTO ticket_events(ticket_id, ts, actor, kind)'
            " VALUES('t-guichet','2026-09-10T11:30:00+00:00','serge','created')"
        )
        self.conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, sent_at, created_at, updated_at)'
            " VALUES('t1', 'c1','p1','email','sent','k-t1',?,?,?)",
            (NOW, NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, sent_at, created_at, updated_at)'
            " VALUES('t0', 'c1','p1','email','sent','k-t0',"
            "'2026-09-09T10:00:00+00:00', '2026-09-09T10:00:00+00:00',"
            "'2026-09-09T10:00:00+00:00')"
        )
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            " tokens_out, latency_ms, verdict, created_at) VALUES('classify',"
            "'T1','m',1000,500,10,'ok',?)",
            (NOW,),
        )
        append_event(
            self.conn, actor='runner', type='cycle', payload={'done': 1}
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_hero_running_et_ready(self) -> None:
        hero = project_hero(self.conn, POLICY, NOW)
        self.assertEqual(hero['running']['kind'], 'Envoyer un e-mail')
        self.assertEqual(hero['running']['venture_id'], 'v1')
        self.assertEqual(hero['ready'], 2)
        self.assertEqual(hero['next']['kind'], 'Classer une réponse')

    def test_urgents_ordonnes(self) -> None:
        items = project_urgents(self.conn, POLICY, NOW)['items']
        self.assertEqual(
            [item['id'] for item in items],
            ['t-guichet', 't-veto30', 't-alert'],
        )

    def test_file_next_fifo(self) -> None:
        file = project_file(self.conn, POLICY, NOW)
        self.assertEqual(len(file['running']), 1)
        self.assertEqual(file['ready_count'], 2)
        self.assertEqual(file['next']['id'], self.first)

    def test_file_detail_ordre_et_libelles(self) -> None:
        fiche = project_file_detail(self.conn, NOW)
        self.assertEqual(fiche['type'], 'file')
        lignes = fiche['tableau']['lignes']
        self.assertEqual(len(lignes), 3)
        self.assertEqual(lignes[0]['cellules'][1], 'Envoyer un e-mail')
        self.assertEqual(lignes[0]['cellules'][3], 'En cours')
        self.assertEqual(lignes[1]['cellules'][3], 'Prochaine')
        self.assertEqual(lignes[1]['cellules'][1], 'Classer une réponse')
        self.assertEqual(lignes[1]['id'], self.first)
        self.assertEqual(lignes[2]['cellules'][3], 'Prête')

    def test_une_tache_qui_ne_partira_pas_n_a_pas_de_rang(self) -> None:
        """Une tâche restée prête d'une invocation supprimée : dernière,
        sans rang, et pas comptée parmi les prêtes."""
        avant = project_file_detail(self.conn, NOW)['champs'][0]['v']
        invocations(self.conn, ('vieille', 'Une ancienne démo', 'caisse'))
        tache(self.conn, 'vieille', {'n': '1'}, key='k_vieille')
        self.conn.execute(
            "UPDATE invocations SET deleted_at='t' WHERE id='vieille'"
        )
        fiche = project_file_detail(self.conn, NOW)
        derniere = fiche['tableau']['lignes'][-1]['cellules']
        self.assertEqual(derniere[0], '—')
        self.assertEqual(derniere[3], 'Ne partira pas : invocation supprimée')
        self.assertEqual(fiche['champs'][0]['v'], avant)

    def test_le_plafond_du_jour_explique_l_attente(self) -> None:
        """Plafond atteint : la tâche LLM prête n'est plus « prochaine »,
        la raison est donnée, comme la file la sautera."""
        self.conn.execute(
            "UPDATE invocations SET type='llm' WHERE id='classer'"
        )
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, verdict, cost_usd, created_at)'
            " VALUES('classer', 'mid', 'ok', 100.0, ?)",
            (NOW,),
        )
        politique = {
            **POLICY,
            'budget': {**POLICY['budget'], 'eur_per_usd': 0.9},
        }
        file = project_file(self.conn, politique, NOW)
        self.assertNotEqual(
            (file['next'] or {}).get('kind'), 'Classer une réponse'
        )
        self.assertIn('Plafond du jour atteint', file['attente'])
        with mock.patch(
            'serge.mc.proj_taches.policy_en_vigueur', return_value=politique
        ):
            fiche = project_file_detail(self.conn, NOW)
        etats = {
            ligne['cellules'][1]: ligne['cellules'][3]
            for ligne in fiche['tableau']['lignes']
        }
        self.assertEqual(
            etats['Classer une réponse'],
            'En attente : plafond du jour atteint',
        )

    def test_le_plafond_du_mois_explique_l_attente(self) -> None:
        """Ce que Serge a coûté ce mois-ci dépasse le plafond du mois : les
        tâches LLM attendent le mois suivant, même sous le plafond du jour."""
        self.conn.execute(
            "UPDATE invocations SET type='llm' WHERE id='classer'"
        )
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, verdict, cost_usd, created_at)'
            " VALUES('classer', 'mid', 'ok', 40.0, '2026-09-02T09:00:00')",
        )
        politique = {
            **POLICY,
            'budget': {
                'llm_daily_eur': 5.0,
                'monthly_eur': 30.0,
                'eur_per_usd': 0.9,
            },
        }
        file = project_file(self.conn, politique, NOW)
        self.assertNotEqual(
            (file['next'] or {}).get('kind'), 'Classer une réponse'
        )
        self.assertIn('Plafond du mois atteint', file['attente'])
        self.assertIn('le mois prochain', file['attente'])
        jauges = project_jauges(self.conn, politique, NOW)
        self.assertAlmostEqual(jauges['mois']['eur'], 36.0)
        self.assertEqual(jauges['mois']['plafond_eur'], 30.0)

    def test_feed_tri_et_sources(self) -> None:
        items = project_feed(self.conn, POLICY, NOW)['items']
        stamps = [item['ts'] for item in items]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        self.assertEqual(
            {item['source'] for item in items}, {'event', 'ticket', 'touche'}
        )
        self.assertLessEqual(len(items), 30)

    def test_jauges_llm_et_email(self) -> None:
        jauges = project_jauges(self.conn, POLICY, NOW)
        llm = jauges['llm']
        self.assertEqual(llm['tokens_jour'], 1500)
        # L'appel du jeu de données n'a pas de coût connu : ses jetons sont
        # comptés à part, sans estimation, et la jauge reste à zéro.
        self.assertEqual(llm['jetons_sans_cout'], 1500)
        self.assertEqual(llm['eur'], 0)
        self.assertEqual(llm['ratio'], 0)
        email = jauges['email']
        self.assertEqual((email['envoyes'], email['quota']), (1, 40))
        self.assertEqual(email['libelle'], 'E-mails')
        self.assertAlmostEqual(email['ratio'], 0.025)
        self.assertEqual(jauges['voix']['libelle'], 'Appels')
        self.assertEqual(
            (jauges['voix']['faits'], jauges['voix']['quota']), (0, 50)
        )
        self.assertEqual(jauges['linkedin']['libelle'], 'Invitations LinkedIn')
        self.assertEqual(jauges['linkedin']['quota'], 20)


if __name__ == '__main__':
    unittest.main()
