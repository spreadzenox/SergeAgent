#!/usr/bin/env python3
"""Séquenceur : auto-qualif, éligibilité, cooldowns, guards, 1 à la fois."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.funnels.contacts import create_contact  # noqa: E402
from serge.funnels.sequencer import (  # noqa: E402
    SequencerError,
    auto_qualify,
    next_send,
    resolve_steps,
    step_due,
)
from serge.registry import load_sequences  # noqa: E402

NOW = '2026-09-09T10:30:00+00:00'
POLICY = {
    'consent': {'opt_in_channels': ['voice', 'sms']},
    'calling_zones': {'default': 'FR', 'FR': {'contact_per_30d': 4}},
}
STEPS = [
    {'channel': 'email', 'delay_days': 0},
    {'channel': 'email', 'delay_days': 3},
]


class SequencerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        seuils = json.dumps({'scale_min_positifs': 3})
        self.connection.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            ' n_target, budget_cap_eur, thresholds_json, created_at,'
            ' updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (
                'c1',
                'v1',
                'named',
                'email',
                'RUNNING',
                50,
                0,
                seuils,
                't',
                't',
            ),
        )
        self.connection.commit()
        self.sequences = load_sequences()

    def tearDown(self) -> None:
        self.connection.close()

    def _contact(self, email: str = 'a@x.io', phone: str = '') -> str:
        return create_contact(self.connection, 'v1', 'A', email, phone)

    def test_registre_sequences_valide(self) -> None:
        self.assertIn('default_named', self.sequences)
        steps = resolve_steps(self.sequences, {}, 'named')
        self.assertEqual(steps[0]['channel'], 'email')
        inline = resolve_steps(self.sequences, {'sequence': STEPS}, 'named')
        self.assertEqual(len(inline), 2)
        with self.assertRaises(SequencerError):
            resolve_steps(self.sequences, {'sequence': 'nope'}, 'named')
        with self.assertRaises(SequencerError):
            resolve_steps(self.sequences, {}, 'ads')

    def test_auto_qualify(self) -> None:
        good = self._contact('ada@x.io')
        bad = self._contact('pas-un-email')
        self.assertEqual(auto_qualify(self.connection, 'v1'), [good])
        state = self.connection.execute(
            'SELECT funnel_state FROM contacts WHERE id=?', (bad,)
        ).fetchone()[0]
        self.assertEqual(state, 'NEW')

    def test_next_send_nominal(self) -> None:
        contact_id = self._contact()
        auto_qualify(self.connection, 'v1')
        item_id = next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        self.assertIsNotNone(item_id)
        row = self.connection.execute(
            'SELECT kind, campaign_id, contact_id, status FROM work_items'
            ' WHERE id=?',
            (item_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ('email.send', 'c1', contact_id, 'READY'))

    def test_un_seul_a_la_fois(self) -> None:
        self._contact('a@x.io')
        self._contact('b@x.io')
        auto_qualify(self.connection, 'v1')
        first = next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        second = next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)
        third = next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        self.assertIsNone(third)

    def test_etape_non_due(self) -> None:
        contact_id = self._contact()
        auto_qualify(self.connection, 'v1')
        self.connection.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, created_at, updated_at)'
            " VALUES('t0','c1',?,'email','sent','k0',?,?)",
            (contact_id, NOW, NOW),
        )
        step = step_due(
            self.connection,
            'c1',
            contact_id,
            STEPS,
            '2026-09-10T10:30:00+00:00',
        )
        self.assertIsNone(step)
        step = step_due(
            self.connection,
            'c1',
            contact_id,
            STEPS,
            '2026-09-13T10:30:00+00:00',
        )
        assert step is not None
        self.assertEqual(step['index'], 1)

    def test_guards_saute_le_contact_bloque(self) -> None:
        from serge.privacy import subject_hash

        blocked = self._contact('spam@x.io')
        auto_qualify(self.connection, 'v1')
        self.connection.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, reason,'
            " added_at) VALUES('b1','email',?,'owner',?)",
            (subject_hash('spam@x.io'), NOW),
        )
        item_id = next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        self.assertIsNone(item_id)
        good = self._contact('ok@x.io')
        auto_qualify(self.connection, 'v1')
        item_id = next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        assert item_id is not None
        row = self.connection.execute(
            'SELECT contact_id FROM work_items WHERE id=?', (item_id,)
        ).fetchone()[0]
        self.assertEqual(row, good)
        self.assertNotEqual(blocked, good)

    def test_fenetre_n_budget_bloquent(self) -> None:
        self._contact()
        auto_qualify(self.connection, 'v1')
        self.connection.execute(
            "UPDATE campaigns SET window_end='2026-09-01T00:00:00+00:00'"
            " WHERE id='c1'"
        )
        self.assertIsNone(
            next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        )
        self.connection.execute(
            "UPDATE campaigns SET window_end='', n_target=0 WHERE id='c1'"
        )
        self.assertIsNone(
            next_send(self.connection, 'v1', POLICY, self.sequences, NOW)
        )

    def test_canal_inconnu_leve(self) -> None:
        self._contact()
        auto_qualify(self.connection, 'v1')
        self.connection.execute(
            'UPDATE campaigns SET thresholds_json=? WHERE id=?',
            (
                json.dumps({'sequence': [{'channel': 'pigeon'}]}),
                'c1',
            ),
        )
        with self.assertRaises(SequencerError):
            next_send(self.connection, 'v1', POLICY, self.sequences, NOW)


if __name__ == '__main__':
    unittest.main()
