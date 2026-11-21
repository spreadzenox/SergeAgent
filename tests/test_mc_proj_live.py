#!/usr/bin/env python3
"""Projecteurs P0 : golden sur fixtures (hero, urgents, files, feed, jauges).

Le feed est la liste « Activité » : une ligne de tâche y porte le titre de
son invocation, les détails d'une tâche (ses appels d'outils, ses
écritures) n'y sont pas, et les tâches de routine pareilles font une
seule ligne.
"""

from __future__ import annotations

import json
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
    'channels': {
        'email': {'max_per_day': 40},
        'voice': {'max_per_day': 50},
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
            ('t-guichet2h', 'GUICHET', 'Tard', '2026-09-10T14:00:00+00:00'),
            ('t-plan', 'PLAN_POC', 'Prix', '2026-09-10T12:05:00+00:00'),
            ('t-info', 'FYI', 'Quota', ''),
            ('t-test', 'TEST_POC', 'H1', ''),
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
        # Seul un guichet qui expire dans le quart d'heure est urgent.
        self.assertEqual([item['id'] for item in items], ['t-guichet'])

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
        self.conn.executemany(
            'INSERT INTO inbound_events(id, contact_id, channel, address,'
            ' status, reaction, received_at) VALUES(?,?,?,?,?,?,?)',
            [
                (
                    'i1',
                    'p1',
                    'email',
                    'ada@example.org',
                    'attached',
                    'question',
                    '2026-09-10T11:58:00+00:00',
                ),
                (
                    'i2',
                    '',
                    'email',
                    'x@example.org',
                    'unattached',
                    '',
                    '2026-09-10T11:59:00+00:00',
                ),
            ],
        )
        items = project_feed(self.conn, POLICY, NOW)['items']
        stamps = [item['ts'] for item in items]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        self.assertEqual(
            {item['source'] for item in items},
            {'event', 'ticket', 'touche', 'reçu'},
        )
        self.assertLessEqual(len(items), 30)
        recus = [
            (item['kind'], item['titre'], item['extra']['contact_id'])
            for item in items
            if item['source'] == 'reçu'
        ]
        self.assertEqual(
            recus,
            [
                ('email.recu', 'x@example.org (pas rattaché)', ''),
                ('email.recu', 'Ada (question)', 'p1'),
            ],
        )

    def _fait(self, seconde: int, sorte: str, **contenu: object) -> None:
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('invocation:x', ?, '', ?, ?)",
            (
                sorte,
                json.dumps(contenu),
                f'2026-09-10T13:00:{seconde:02d}+00:00',
            ),
        )

    def test_l_activite_dit_de_quelle_tache_elle_parle(self) -> None:
        """Une ligne de tâche porte le titre de son invocation ; ce que la
        tâche a fait en tournant (ses appels d'outils, ses écritures) n'y
        est pas ; les tâches de routine pareilles font une ligne, celles
        qu'un bouton a lancées gardent la leur."""
        invocations(
            self.conn,
            ('relever', 'Relever les messages', 'prospection_light'),
            ('relancer', 'Chercher les relances', 'prospection_light'),
            ('fouiller', 'Fouiller un réseau', 'prospection_light'),
        )
        self.conn.execute(
            'INSERT INTO triggers(id, title, invocation_id, event)'
            " VALUES('bouton_fouiller', 'Fouiller un réseau', 'fouiller',"
            " 'button')"
        )
        releves = [
            tache(self.conn, 'relever', key=f'k-rel{n}', status='done')
            for n in range(3)
        ]
        relance = tache(self.conn, 'relancer', key='k-rl', status='done')
        fouilles = [
            tache(self.conn, 'fouiller', key=f'k-fou{n}', status='done')
            for n in range(2)
        ]
        self.conn.execute(
            "UPDATE tasks SET origin='button' WHERE invocation_id='fouiller'"
        )
        rate = tache(
            self.conn, 'relever', key='k-rate', status='failed', error='x'
        )
        for seconde, sorte, contenu in (
            (
                1,
                'mc_act',
                {
                    'acte': 'bouton',
                    'trigger_id': 'bouton_fouiller',
                    'task': fouilles[0],
                },
            ),
            (2, 'task.done', {'task': releves[0], 'rows_written': 1}),
            (3, 'tool.call', {'task': fouilles[0], 'tool': 'agir'}),
            (4, 'write.updated', {'task': releves[1], 'table': 'canaux'}),
            (5, 'task.done', {'task': releves[1], 'rows_written': 1}),
            (6, 'task.done', {'task': relance, 'rows_written': 0}),
            (7, 'task.done', {'task': fouilles[0], 'rows_written': 0}),
            (8, 'task.done', {'task': releves[2], 'rows_written': 1}),
            (9, 'task.done', {'task': fouilles[1], 'rows_written': 0}),
            (10, 'task.failed', {'task': rate, 'error': 'HTTP 429'}),
            (11, 'write.refused', {'task': rate, 'reason': 'aucune ligne'}),
            (12, 'sms.received', {'de': 'XApp', 'code': 'oui'}),
            # Une écriture faite hors d'une tâche reste dans l'activité.
            (13, 'write.updated', {'table': 'canaux'}),
        ):
            self._fait(seconde, sorte, **contenu)
        items = [
            item
            for item in project_feed(self.conn, POLICY, NOW)['items']
            if item['ts'].startswith('2026-09-10T13:00')
        ]
        self.assertEqual(
            [
                (item['kind'], item['titre'], item.get('n', 1))
                for item in items
            ],
            [
                ('write.updated', '', 1),
                ('sms.received', 'XApp', 1),
                ('write.refused', 'Relever les messages : aucune ligne', 1),
                ('task.failed', 'Relever les messages : HTTP 429', 1),
                ('task.done', 'Fouiller un réseau', 1),
                ('task.done', 'Relever les messages', 3),
                ('task.done', 'Fouiller un réseau', 1),
                ('task.done', 'Chercher les relances', 1),
                ('mc_act', 'bouton « Fouiller un réseau »', 1),
            ],
        )
        groupe = items[5]
        # La ligne garde la plus récente des trois relèves, même si
        # d'autres tâches sont passées entre elles, et dit depuis quand.
        self.assertEqual(groupe['extra']['task'], releves[2])
        self.assertEqual(groupe['ts'], '2026-09-10T13:00:08+00:00')
        self.assertEqual(groupe['depuis'], '2026-09-10T13:00:02+00:00')
        self.assertEqual(groupe['libelle'], 'Tâche terminée')
        self.assertNotIn('routine', groupe)
        self.assertEqual(items[1]['libelle'], 'SMS reçu')

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
        self.assertNotIn('linkedin', jauges)


if __name__ == '__main__':
    unittest.main()
