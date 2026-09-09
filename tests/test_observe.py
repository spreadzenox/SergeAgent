#!/usr/bin/env python3
"""Observation : normaliseurs + routage déterministe par signal."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.funnels.contacts import (  # noqa: E402
    create_contact,
    qualify,
    start_contacting,
)
from serge.observe import ingest  # noqa: E402

NOW = '2026-09-09T19:00:00+00:00'
POLICY = {'observation': {'tech_fail_pattern_per_week': 3}}


class ObserveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()

    def _contact(self) -> str:
        contact_id = create_contact(
            self.connection, 'v1', 'Ada', email='ada@x.io'
        )
        qualify(self.connection, contact_id)
        start_contacting(self.connection, contact_id)
        return contact_id

    def _state(self, contact_id: str) -> tuple[str, str]:
        row = self.connection.execute(
            'SELECT funnel_state, regime FROM contacts WHERE id=?',
            (contact_id,),
        ).fetchone()
        return str(row[0]), str(row[1])

    def test_replied_classe_et_passe_inbound(self) -> None:
        contact_id = self._contact()
        result = ingest(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'native_type': 'RECEIVED',
                'contact_id': contact_id,
                'venture_id': 'v1',
            },
            NOW,
        )
        self.assertEqual(result['signal'], 'REPLIED')
        self.assertEqual(result['actions'], ['classify'])
        self.assertEqual(self._state(contact_id)[1], 'INBOUND')
        kinds = [
            row[0]
            for row in self.connection.execute('SELECT kind FROM work_items')
        ]
        self.assertEqual(kinds, ['inbound.classify'])

    def test_intent_prioritaire_attribue_et_progresse(self) -> None:
        contact_id = self._contact()
        self.connection.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, created_at, updated_at)'
            " VALUES('t0','c1',?,'email','sent','k0',?,?)",
            (contact_id, NOW, NOW),
        )
        result = ingest(
            self.connection,
            POLICY,
            {
                'channel': 'voice',
                'native_type': 'DTMF_1',
                'contact_id': contact_id,
                'venture_id': 'v1',
            },
            NOW,
        )
        self.assertEqual(result['signal'], 'INTENT')
        self.assertEqual(result['actions'], ['reply_priority'])
        self.assertEqual(self._state(contact_id), ('INTENT', 'INBOUND'))
        row = self.connection.execute(
            "SELECT kind, priority FROM work_items WHERE kind='inbound.reply_priority'"
        ).fetchone()
        self.assertEqual(int(row[1]), 100)
        types = [
            row[0]
            for row in self.connection.execute(
                "SELECT type FROM events WHERE type LIKE 'attribution.%'"
            )
        ]
        self.assertEqual(types, ['attribution.intent'])

    def test_tech_fail_pattern_et_invalid(self) -> None:
        contact_id = self._contact()
        results = [
            ingest(
                self.connection,
                POLICY,
                {
                    'channel': 'email',
                    'native_type': 'BOUNCED',
                    'contact_id': contact_id,
                    'venture_id': 'v1',
                },
                NOW,
            )
            for _ in range(3)
        ]
        self.assertIn('contact_invalid', results[0]['actions'])
        self.assertNotIn('alert', results[0]['actions'])
        self.assertIn('alert', results[2]['actions'])
        self.assertEqual(self._state(contact_id)[0], 'INVALID')

    def test_negative_stoppe_et_lecon(self) -> None:
        contact_id = self._contact()
        # NEGATIVE vient du classify (signal pré-normalisé, même tuyau).
        result = ingest(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'native_type': 'CLASSIFIED',
                'signal': 'NEGATIVE',
                'contact_id': contact_id,
                'venture_id': 'v1',
            },
            NOW,
        )
        self.assertEqual(result['signal'], 'NEGATIVE')
        self.assertIn('contact_stopped', result['actions'])
        self.assertIn('lesson_candidate', result['actions'])
        self.assertEqual(self._state(contact_id)[0], 'UNREACHABLE')

    def test_other_va_au_juge(self) -> None:
        result = ingest(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'native_type': 'QUELQUECHOSE',
                'venture_id': 'v1',
            },
            NOW,
        )
        self.assertEqual(result['signal'], 'OTHER')
        self.assertEqual(result['actions'], ['judge_other'])

    def test_opt_out_bloque_canal_et_global(self) -> None:
        contact_id = self._contact()
        result = ingest(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'native_type': 'COMPLAINED',
                'contact_id': contact_id,
                'subject': 'ada@x.io',
                'venture_id': 'v1',
            },
            NOW,
        )
        self.assertEqual(result['signal'], 'OPT_OUT')
        self.assertIn('blocked', result['actions'])
        self.assertIn('contact_opted_out', result['actions'])
        self.assertEqual(self._state(contact_id)[0], 'OPTED_OUT')
        scopes = {
            row[0]
            for row in self.connection.execute('SELECT channel FROM blocklist')
        }
        self.assertEqual(scopes, {'email', '*'})

    def test_seen_silencieux(self) -> None:
        result = ingest(
            self.connection,
            POLICY,
            {'channel': 'email', 'native_type': 'OPENED'},
            NOW,
        )
        self.assertEqual(result['signal'], 'SEEN')
        self.assertEqual(result['actions'], [])
        count = self.connection.execute(
            'SELECT COUNT(*) FROM inbound_events'
        ).fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == '__main__':
    unittest.main()
