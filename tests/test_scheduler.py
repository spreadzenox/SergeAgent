#!/usr/bin/env python3
"""Scheduler SQL-first: priorité, FIFO, schedulable, transitions, idempotence."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.scheduler import (  # noqa: E402
    claim,
    complete,
    enqueue,
    fail,
    next_ready,
)


class SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SCALE',1,'t','t')"
        )
        self.connection.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v2','CANDIDATE',0,'t','t')"
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()

    def test_idle_legitime_quand_rien(self) -> None:
        self.assertIsNone(next_ready(self.connection))

    def test_priorite_puis_fifo(self) -> None:
        enqueue(
            self.connection, kind='a', idempotency_key='k1', venture_id='v1'
        )
        enqueue(
            self.connection,
            kind='b',
            idempotency_key='k2',
            venture_id='v1',
            priority=10,
        )
        first = next_ready(self.connection)
        assert first is not None
        self.assertEqual(first['kind'], 'b')
        claim(self.connection, first['id'])
        complete(self.connection, first['id'])
        second = next_ready(self.connection)
        assert second is not None
        self.assertEqual(second['kind'], 'a')

    def test_non_schedulable_jamais_servi(self) -> None:
        enqueue(
            self.connection, kind='x', idempotency_key='k9', venture_id='v2'
        )
        self.assertIsNone(next_ready(self.connection))

    def test_blocked_until_respecte(self) -> None:
        enqueue(
            self.connection,
            kind='w',
            idempotency_key='k8',
            venture_id='v1',
            blocked_until='2999-01-01T00:00:00+00:00',
        )
        self.assertIsNone(
            next_ready(self.connection, now='2026-01-01T00:00:00+00:00')
        )
        item = next_ready(self.connection, now='2999-06-01T00:00:00+00:00')
        assert item is not None
        self.assertEqual(item['kind'], 'w')

    def test_enqueue_idempotent(self) -> None:
        first = enqueue(
            self.connection, kind='a', idempotency_key='same', venture_id='v1'
        )
        second = enqueue(
            self.connection, kind='a', idempotency_key='same', venture_id='v1'
        )
        self.assertEqual(first, second)
        count = self.connection.execute(
            'SELECT COUNT(*) FROM work_items'
        ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_claim_complete_fail(self) -> None:
        item_id = enqueue(
            self.connection, kind='a', idempotency_key='kc', venture_id='v1'
        )
        claimed = claim(self.connection, item_id)
        assert claimed is not None
        self.assertEqual(claimed['status'], 'RUNNING')
        self.assertEqual(claimed['attempts'], 1)
        self.assertIsNone(claim(self.connection, item_id))
        self.assertTrue(complete(self.connection, item_id, {'ok': True}))
        self.assertIsNone(next_ready(self.connection))
        other = enqueue(
            self.connection, kind='b', idempotency_key='kf', venture_id='v1'
        )
        claim(self.connection, other)
        self.assertTrue(fail(self.connection, other, 'EXTERNAL_500'))
        row = self.connection.execute(
            'SELECT status FROM work_items WHERE id=?', (other,)
        ).fetchone()[0]
        self.assertEqual(row, 'FAILED')

    def test_fail_avec_retry_replanifie(self) -> None:
        item_id = enqueue(
            self.connection, kind='a', idempotency_key='kr', venture_id='v1'
        )
        claim(self.connection, item_id)
        retry_at = '2026-05-01T00:00:00+00:00'
        self.assertTrue(fail(self.connection, item_id, 'RATE_LIMIT', retry_at))
        self.assertIsNone(
            next_ready(self.connection, now='2026-04-01T00:00:00+00:00')
        )
        item = next_ready(self.connection, now='2026-06-01T00:00:00+00:00')
        assert item is not None
        self.assertEqual(item['id'], item_id)

    def test_transitions_tracees_en_episodes(self) -> None:
        item_id = enqueue(
            self.connection, kind='a', idempotency_key='ke', venture_id='v1'
        )
        claim(self.connection, item_id)
        complete(self.connection, item_id)
        kinds = [
            row[0]
            for row in self.connection.execute(
                'SELECT type FROM events ORDER BY id'
            )
        ]
        self.assertEqual(
            kinds, ['work.enqueued', 'work.claimed', 'work.completed']
        )


if __name__ == '__main__':
    unittest.main()
