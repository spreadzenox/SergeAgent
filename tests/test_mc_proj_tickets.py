#!/usr/bin/env python3
"""Projecteurs P3 : goldens liste/carte + endpoint carte."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_tickets import project_carte, project_tickets  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {}

TYPES = """schema_version: 1
types:
  VETO_AMONT:
    role: x
    urgency: haute
    default: pas_de_changement
    default_detail: Le prix reste.
    fields: [decision]
    buttons: [approuver, rejeter, discuter]
    expiry_hours: 1
  GUICHET:
    role: x
    urgency: haute
    default: rien
    fields: [captcha]
    buttons: [approuver, rejeter]
    expiry_minutes: 15
  ALERT:
    role: x
    urgency: haute
    default: rien
    fields: []
    buttons: [approuver]
    expiry_hours: 24
  POLICY:
    role: x
    urgency: normale
    default: pas_de_changement
    default_detail: La policy actuelle reste.
    fields: [diff_avant_apres, justification, impact]
    buttons: [approuver, rejeter, discuter]
    expiry_hours: 72
  MEMORY:
    role: x
    urgency: fenetre
    default: auto
    fields: [lecons]
    buttons: []
    items_per_lesson: [garder, modifier, jeter]
    expiry_hours: 48
"""


class ProjTicketsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix='serge-p3-')
        self.addCleanup(self.tmp.cleanup)
        (Path(self.tmp.name) / 'ticket-types.yaml').write_text(
            TYPES, encoding='utf-8'
        )
        patcher = mock.patch.dict(
            os.environ, {'SERGE_CONFIG_DIR': self.tmp.name}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        conn = self.conn
        tickets = (
            (
                't1',
                'VETO_AMONT',
                'Ticket t_abc123def456 soldé',
                'OPEN',
                '{"decision": "augmenter"}',
                '2026-09-10T12:30:00+00:00',
                '2026-09-10T11:00:00+00:00',
            ),
            (
                't2',
                'GUICHET',
                'Captcha',
                'OPEN',
                '{}',
                '2026-09-10T12:10:00+00:00',
                '2026-09-10T11:30:00+00:00',
            ),
            (
                't3',
                'ALERT',
                'Quota',
                'OPEN',
                '{}',
                '',
                '2026-09-10T10:00:00+00:00',
            ),
            (
                't4',
                'POLICY',
                'Plafond',
                'DISCUSSING',
                '{"diff_avant_apres": "5->7", "justification": "pic",'
                ' "impact": "faible"}',
                '2026-09-13T12:00:00+00:00',
                '2026-09-10T11:45:00+00:00',
            ),
            (
                't5',
                'MEMORY',
                'Leçons',
                'OPEN',
                '{}',
                '2026-09-12T12:00:00+00:00',
                '2026-09-10T11:15:00+00:00',
            ),
            (
                't6',
                'VETO_AMONT',
                'Vieux',
                'APPROVED',
                '{}',
                '2026-09-09T12:00:00+00:00',
                '2026-09-09T11:00:00+00:00',
            ),
            (
                't7',
                'HYPOTHESIS',
                'Piste',
                'OPEN',
                '{}',
                '2026-09-20T12:00:00+00:00',
                '2026-09-10T11:05:00+00:00',
            ),
        )
        for tid, typ, titre, etat, charge, expiry, updated in tickets:
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json,'
                ' expiry_at, created_at, updated_at)'
                ' VALUES(?,?,?,?,?,?,?,?)',
                (tid, typ, titre, etat, charge, expiry, updated, updated),
            )
        conn.execute(
            'INSERT INTO ticket_items(id, ticket_id, kind, label, state)'
            " VALUES('i1','t5','MEMORY','Leçon A','open'),"
            "('i2','t5','MEMORY','Leçon B','keep')"
        )
        conn.execute(
            'INSERT INTO ticket_events(ticket_id, ts, actor, kind)'
            " VALUES('t1','2026-09-10T11:00:00+00:00','serge',"
            "'transition.draft')"
        )
        conn.execute(
            'INSERT INTO ticket_events(ticket_id, ts, actor, kind)'
            " VALUES('t4','2026-09-10T11:45:00+00:00','owner','mc.fil')"
        )
        conn.execute(
            "UPDATE tickets SET versions_json=? WHERE id='t1'",
            ('[{"n": 1, "note": "v1", "at": "2026-09-10T11:30:00+00:00"}]',),
        )

    def test_liste_golden(self) -> None:
        projete = project_tickets(self.conn, POLICY, NOW)['items']
        self.assertEqual(
            [(t['id'], t['urgent']) for t in projete],
            [
                ('t2', True),
                ('t5', False),
                ('t7', False),
                ('t1', True),
                ('t3', True),
                ('t4', False),
                ('t6', False),
            ],
        )
        boutons = {t['id']: t['boutons'] for t in projete}
        self.assertEqual(boutons['t1'], ['approuver', 'rejeter', 'discuter'])
        self.assertEqual(boutons['t2'], ['approuver', 'rejeter'])
        self.assertEqual(boutons['t5'], [])
        self.assertEqual(boutons['t7'], [])
        titres = {t['id']: t['titre'] for t in projete}
        self.assertEqual(titres['t1'], 'Ticket  soldé')

    def test_carte_golden(self) -> None:
        carte = project_carte(self.conn, 't1')
        self.assertEqual(
            carte['ticket'],
            {
                'id': 't1',
                'type': 'VETO_AMONT',
                'titre': 'Ticket  soldé',
                'etat': 'OPEN',
                'expiry_at': '2026-09-10T12:30:00+00:00',
                'defaut': '',
                'defaut_detail': 'Le prix reste.',
            },
        )
        self.assertEqual(
            carte['champs'],
            [{'titre': 'decision', 'texte': 'augmenter'}],
        )
        self.assertEqual(
            carte['boutons'], ['approuver', 'rejeter', 'discuter']
        )
        self.assertEqual(carte['items'], [])
        self.assertEqual(
            carte['events'],
            [
                {
                    'ts': '2026-09-10T11:00:00+00:00',
                    'acteur': 'serge',
                    'kind': 'transition.draft',
                }
            ],
        )
        self.assertEqual(
            carte['versions'],
            [{'n': 1, 'note': 'v1', 'at': '2026-09-10T11:30:00+00:00'}],
        )

    def test_carte_memory(self) -> None:
        carte = project_carte(self.conn, 't5')
        self.assertEqual(carte['boutons'], [])
        self.assertEqual(carte['items_actes'], ['garder', 'modifier', 'jeter'])
        self.assertEqual(
            [(i['id'], i['etat']) for i in carte['items']],
            [('i1', 'open'), ('i2', 'keep')],
        )
        self.assertEqual(carte['champs'], [{'titre': 'lecons', 'texte': '—'}])

    def test_carte_inconnue(self) -> None:
        self.assertIsNone(project_carte(self.conn, 't-zzz'))


class CarteEndpointTests(McServerCase):
    def test_carte_endpoint(self) -> None:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json,'
                " expiry_at, created_at, updated_at) VALUES('t1',"
                "'VETO_AMONT','Prix','OPEN','{\"decision\": \"x\"}','',"
                "'t','t')"
            )
            conn.commit()
        finally:
            conn.close()
        status, _, _ = self._request(
            'GET', '/owner/api/ticket/carte?ticket=t1'
        )
        self.assertEqual(status, 401)
        status, headers, _ = self._login()
        self.assertEqual(status, 302)
        cookie = {'Cookie': self._cookie(headers)}
        status, _, _ = self._request(
            'GET', '/owner/api/ticket/carte', headers=cookie
        )
        self.assertEqual(status, 400)
        status, _, _ = self._request(
            'GET', '/owner/api/ticket/carte?ticket=t-zzz', headers=cookie
        )
        self.assertEqual(status, 404)
        status, _, corps = self._request(
            'GET', '/owner/api/ticket/carte?ticket=t1', headers=cookie
        )
        self.assertEqual(status, 200)
        charge = json.loads(corps.decode('utf-8'))
        self.assertEqual(charge['ticket']['titre'], 'Prix')
        self.assertTrue(len(charge['boutons']) > 0)
