#!/usr/bin/env python3
"""Lifecycle ventures : états, gates, une seule ACTIVE."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.funnels.lifecycle import (  # noqa: E402
    VentureError,
    collect_ready,
    create_venture,
    to_extend,
    to_full_ready,
    to_full_running,
    to_invalid_retry,
    to_killed,
    to_pivot,
    to_scale,
    to_smoke_done,
    to_smoke_ready,
    to_smoke_running,
)
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets import create_ticket, decide, publish  # noqa: E402

NOW = '2026-09-09T19:00:00+00:00'


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.commit()
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.connection.close()

    def _row(self, venture_id: str) -> tuple[str, int]:
        row = self.connection.execute(
            'SELECT lifecycle, schedulable FROM ventures WHERE id=?',
            (venture_id,),
        ).fetchone()
        return str(row[0]), int(row[1])

    def _campaign(self, venture_id: str) -> None:
        self.connection.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            ' created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                f'c_{venture_id}',
                venture_id,
                'named',
                'email',
                'READY',
                NOW,
                NOW,
            ),
        )

    def _approve_full_hypothesis(self, venture_id: str) -> None:
        ticket_id = create_ticket(
            self.connection,
            self.types,
            'HYPOTHESIS',
            'h',
            {'venture_id': venture_id, 'niveau': 'full'},
            now=NOW,
        )
        publish(self.connection, ticket_id)
        decide(self.connection, ticket_id, 'APPROVED')

    def _canary(self, venture_id: str) -> None:
        self.connection.execute(
            'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
            ' intent_id, status, created_at, updated_at)'
            " VALUES(?,?,'canary',1.0,?,'succeeded',?,?)",
            (
                f'tx_{venture_id}',
                venture_id,
                f'intent_{venture_id}',
                NOW,
                NOW,
            ),
        )

    def test_chemin_smoke_nominal(self) -> None:
        venture_id = create_venture(self.connection, 'V1')
        self.assertEqual(self._row(venture_id), ('CANDIDATE', 0))
        to_smoke_ready(self.connection, venture_id)
        with self.assertRaises(VentureError):
            to_smoke_running(self.connection, venture_id)
        self._campaign(venture_id)
        to_smoke_running(self.connection, venture_id)
        self.assertEqual(self._row(venture_id), ('SMOKE_RUNNING', 1))
        to_smoke_done(self.connection, venture_id)
        self.assertEqual(self._row(venture_id), ('SMOKE_DONE', 0))

    def test_gates_full(self) -> None:
        venture_id = create_venture(self.connection, 'V1')
        to_smoke_ready(self.connection, venture_id)
        self._campaign(venture_id)
        to_smoke_running(self.connection, venture_id)
        to_smoke_done(self.connection, venture_id)
        self.assertFalse(collect_ready(self.connection, venture_id))
        with self.assertRaises(VentureError):
            to_full_ready(self.connection, venture_id)
        self._approve_full_hypothesis(venture_id)
        with self.assertRaises(VentureError):
            to_full_ready(self.connection, venture_id)
        self._canary(venture_id)
        self.assertTrue(collect_ready(self.connection, venture_id))
        to_full_ready(self.connection, venture_id)
        to_full_running(self.connection, venture_id)
        self.assertEqual(self._row(venture_id), ('FULL_RUNNING', 1))

    def test_une_seule_active(self) -> None:
        first = create_venture(self.connection, 'V1')
        to_smoke_ready(self.connection, first)
        self._campaign(first)
        to_smoke_running(self.connection, first)
        second = create_venture(self.connection, 'V2')
        to_smoke_ready(self.connection, second)
        self._campaign(second)
        with self.assertRaises(VentureError):
            to_smoke_running(self.connection, second)
        to_smoke_done(self.connection, first)
        to_smoke_running(self.connection, second)
        self.assertEqual(self._row(second), ('SMOKE_RUNNING', 1))

    def test_verdicts_et_restart(self) -> None:
        venture_id = create_venture(self.connection, 'V1')
        to_smoke_ready(self.connection, venture_id)
        self._campaign(venture_id)
        to_smoke_running(self.connection, venture_id)
        to_smoke_done(self.connection, venture_id)
        to_scale(self.connection, venture_id)
        self.assertEqual(self._row(venture_id), ('SCALE', 1))
        with self.assertRaises(VentureError):
            to_killed(self.connection, venture_id)
        other = create_venture(self.connection, 'V2')
        to_smoke_ready(self.connection, other)
        self._campaign(other)
        with self.assertRaises(VentureError):
            to_smoke_running(self.connection, other)

    def test_pivot_extend_invalid_retry(self) -> None:
        venture_id = create_venture(self.connection, 'V1')
        to_smoke_ready(self.connection, venture_id)
        self._campaign(venture_id)
        to_smoke_running(self.connection, venture_id)
        to_smoke_done(self.connection, venture_id)
        self._approve_full_hypothesis(venture_id)
        self._canary(venture_id)
        to_full_ready(self.connection, venture_id)
        to_full_running(self.connection, venture_id)
        to_extend(self.connection, venture_id)
        self.assertEqual(self._row(venture_id), ('EXTEND', 0))
        to_full_running(self.connection, venture_id)
        to_pivot(self.connection, venture_id)
        to_full_ready(self.connection, venture_id)
        to_full_running(self.connection, venture_id)
        to_killed(self.connection, venture_id)
        self.assertEqual(self._row(venture_id), ('KILLED', 0))
        with self.assertRaises(VentureError):
            to_smoke_ready(self.connection, venture_id)

    def test_invalid_retry_revient_en_ready(self) -> None:
        venture_id = create_venture(self.connection, 'V1')
        to_smoke_ready(self.connection, venture_id)
        self._campaign(venture_id)
        to_smoke_running(self.connection, venture_id)
        to_invalid_retry(self.connection, venture_id)
        self.assertEqual(self._row(venture_id), ('INVALID_RETRY', 0))
        to_smoke_ready(self.connection, venture_id)
        kinds = [
            row[0]
            for row in self.connection.execute(
                'SELECT type FROM events WHERE venture_id=? ORDER BY id',
                (venture_id,),
            )
        ]
        self.assertEqual(
            kinds,
            [
                'venture.candidate',
                'venture.smoke_ready',
                'venture.smoke_running',
                'venture.invalid_retry',
                'venture.smoke_ready',
            ],
        )


if __name__ == '__main__':
    unittest.main()
