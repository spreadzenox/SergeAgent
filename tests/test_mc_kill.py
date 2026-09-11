#!/usr/bin/env python3
"""MC kills M8 : flags runtime + ticket POLICY + endpoints (passant/refusé)."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import utcnow  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.llm.runtime import run_registered_point  # noqa: E402
from serge.registry import (  # noqa: E402
    KillError,
    llm_enabled,
    poser_kill,
    retirer_kill,
    runtime_allows,
)
from tests.mc_server_case import McServerCase  # noqa: E402

NOW = utcnow()
POLICY: dict = {}

REGISTRE = """schema_version: 1
points:
  qualify:
    verdict: LLM-1
    tier: T1
    checklist: {entree: true}
    context: {fixed: [], retrieved: [], couche5: {allowed: false},
      forbidden: [], envelope_tokens: 2500}
    garde_fou: strict
    repli: manuel
    enabled: true
"""

TYPES = """schema_version: 1
types:
  POLICY:
    role: x
    urgency: normale
    default: pas_de_changement
    fields: []
    buttons: []
    expiry_hours: 72
"""


def _ok_caller(*args, **kwargs):
    return ChatResult('oui', 50, 10, 'm', 12)


class KillBackendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix='serge-kill-')
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'llm-points.yaml').write_text(REGISTRE, encoding='utf-8')
        (root / 'ticket-types.yaml').write_text(TYPES, encoding='utf-8')
        (root / 'llm').mkdir()
        (root / 'secrets').mkdir()
        (root / 'llm/slots.json').write_text(
            json.dumps(
                {
                    'referer': 'https://r.test',
                    'slots': {'CHEAP': {'openrouter_id': 'm/cheap'}},
                }
            ),
            encoding='utf-8',
        )
        (root / 'secrets/openrouter-api-key').write_text(
            'sk-test-key\n', encoding='utf-8'
        )
        patcher = mock.patch.dict(
            os.environ, {'SERGE_CONFIG_DIR': self.tmp.name}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def test_kill_pose_flag_ticket_event(self) -> None:
        resultat = poser_kill(
            self.conn,
            'qualify',
            'dérive test',
            decision_id='d1',
            now_iso=NOW,
        )
        attendue = (
            datetime.fromisoformat(NOW) + timedelta(hours=24)
        ).isoformat()
        self.assertEqual(resultat['expires_at'], attendue)
        flag = self.conn.execute(
            'SELECT value, reason, expires_at FROM runtime_flags'
            " WHERE name='llm.qualify'"
        ).fetchone()
        self.assertEqual(
            (flag[0], flag[1], flag[2]),
            ('kill', 'dérive test', attendue),
        )
        ticket = self.conn.execute(
            'SELECT type, state, title FROM tickets WHERE id=?',
            (resultat['ticket_id'],),
        ).fetchone()
        self.assertEqual(ticket[0], 'POLICY')
        self.assertEqual(ticket[1], 'DRAFT')
        self.assertIn('qualify', ticket[2])
        event = self.conn.execute(
            "SELECT actor, payload_json FROM events WHERE type='mc_act'"
        ).fetchone()
        self.assertEqual(event[0], 'owner')
        charge = json.loads(event[1])
        self.assertEqual(
            (charge['acte'], charge['decision_id']), ('kill', 'd1')
        )
        self.assertFalse(runtime_allows(self.conn, 'qualify', NOW))
        self.assertFalse(llm_enabled('qualify', self.conn))
        self.assertTrue(llm_enabled('qualify'))

    def test_kill_expire(self) -> None:
        poser_kill(self.conn, 'qualify', 'vieux', ttl_h=-1, now_iso=NOW)
        self.assertTrue(runtime_allows(self.conn, 'qualify', NOW))

    def test_kill_idempotent(self) -> None:
        poser_kill(self.conn, 'qualify', 'x', decision_id='dd', now_iso=NOW)
        second = poser_kill(
            self.conn, 'qualify', 'x', decision_id='dd', now_iso=NOW
        )
        self.assertEqual(second, {'duplicata': 'true'})
        total = self.conn.execute(
            "SELECT COUNT(*) FROM tickets WHERE type='POLICY'"
        ).fetchone()[0]
        self.assertEqual(total, 1)

    def test_kill_refus(self) -> None:
        with self.assertRaises(KillError):
            poser_kill(self.conn, 'qualify', '  ', now_iso=NOW)
        with self.assertRaises(KillError):
            poser_kill(self.conn, 'nope', 'x', now_iso=NOW)

    def test_unkill(self) -> None:
        poser_kill(self.conn, 'qualify', 'x', now_iso=NOW)
        self.assertEqual(
            retirer_kill(self.conn, 'qualify'),
            {'retire': 'true'},
        )
        self.assertTrue(runtime_allows(self.conn, 'qualify', NOW))
        actes = self.conn.execute(
            "SELECT payload_json FROM events WHERE type='mc_act'"
            ' ORDER BY id DESC LIMIT 1'
        ).fetchone()[0]
        self.assertEqual(json.loads(actes)['acte'], 'unkill')
        with self.assertRaises(KillError):
            retirer_kill(self.conn, 'qualify')

    def test_run_point_tue_puis_relance(self) -> None:
        messages = [{'role': 'user', 'content': 'x'}]
        root = Path(self.tmp.name)
        premier = run_registered_point(
            self.conn,
            POLICY,
            'qualify',
            messages,
            root=root,
            caller=_ok_caller,
        )
        self.assertTrue(premier.ok)
        poser_kill(self.conn, 'qualify', 'x', now_iso=NOW)
        tue = run_registered_point(
            self.conn,
            POLICY,
            'qualify',
            messages,
            root=root,
            caller=_ok_caller,
        )
        self.assertFalse(tue.ok)
        verdicts = self.conn.execute(
            "SELECT verdict FROM llm_usage WHERE point='qualify'"
            ' ORDER BY id DESC LIMIT 1'
        ).fetchone()[0]
        self.assertEqual(verdicts, 'killed')
        retirer_kill(self.conn, 'qualify')
        relance = run_registered_point(
            self.conn,
            POLICY,
            'qualify',
            messages,
            root=root,
            caller=_ok_caller,
        )
        self.assertTrue(relance.ok)


class KillEndpointTests(McServerCase):
    POINT = 'qualify_prospect'

    def test_kill_ok(self) -> None:
        cookie = self._auth_cookie()
        status, _, corps = self._api_post(
            '/owner/api/kill',
            {
                'point': self.POINT,
                'raison': 'dérive vue en matrice',
                'decision_id': 'e1',
                'ttl_h': 1,
            },
            cookie,
        )
        self.assertEqual(status, 200)
        reponse = json.loads(corps.decode('utf-8'))
        self.assertTrue(reponse['ok'])
        self.assertIn('ticket_id', reponse)
        conn = sqlite3.connect(self.db_path)
        try:
            flag = conn.execute(
                'SELECT value FROM runtime_flags WHERE name=?',
                (f'llm.{self.POINT}',),
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(flag[0], 'kill')

    def test_kill_refus(self) -> None:
        cookie = self._auth_cookie()
        cas = [
            ({'point': 'nope', 'raison': 'x'}, 404),
            ({'point': self.POINT, 'raison': ''}, 400),
            ({'point': self.POINT, 'raison': 'x', 'ttl_h': 0}, 400),
            ('{pas json', 400),
        ]
        for charge, code in cas:
            with self.subTest(charge=charge):
                status, _, _ = self._api_post(
                    '/owner/api/kill', charge, cookie
                )
                self.assertEqual(status, code)
        status, _, _ = self._api_post(
            '/owner/api/kill', {'point': self.POINT, 'raison': 'x'}
        )
        self.assertEqual(status, 401)

    def test_kill_idempotent_endpoint(self) -> None:
        cookie = self._auth_cookie()
        charge = {
            'point': self.POINT,
            'raison': 'x',
            'decision_id': 'e2',
        }
        for _ in range(2):
            status, _, _ = self._api_post('/owner/api/kill', charge, cookie)
            self.assertEqual(status, 200)
        conn = sqlite3.connect(self.db_path)
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM tickets WHERE type='POLICY'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(total, 1)

    def test_unkill_endpoint(self) -> None:
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/kill',
            {'point': self.POINT, 'raison': 'x'},
            cookie,
        )
        self.assertEqual(status, 200)
        status, _, corps = self._api_post(
            '/owner/api/unkill', {'point': self.POINT}, cookie
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(corps.decode('utf-8'))['retire'], 'true')
        status, _, _ = self._api_post(
            '/owner/api/unkill', {'point': self.POINT}, cookie
        )
        self.assertEqual(status, 404)
