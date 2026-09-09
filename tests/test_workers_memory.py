#!/usr/bin/env python3
"""Workers mémoire : apply MEMORY (keep/edit/drop) + batch."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402
from serge.scheduler import claim, enqueue  # noqa: E402
from serge.tickets import (  # noqa: E402
    add_item,
    create_ticket,
    decide,
    publish,
    set_item,
)
from serge.workers.dispatch import execute  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'memory': {
        'consolidation_days': 3,
        'consolidate_max_items': 10,
        'serge_md_max_lines': 100,
    },
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class MemoryWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.conn.commit()
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.conn.close()

    def _item(self, kind: str, key: str, payload: dict) -> dict:
        item_id = enqueue(
            self.conn,
            kind=kind,
            idempotency_key=key,
            venture_id='v1',
            payload=payload,
        )
        claimed = claim(self.conn, item_id)
        assert claimed is not None
        return claimed

    def test_apply_keep_edit_drop(self) -> None:
        ticket_id = create_ticket(
            self.conn, self.types, 'MEMORY', 'm', {'lecons': []}
        )
        keep = add_item(
            self.conn,
            ticket_id,
            'lesson',
            'Relancer J+3.',
            {
                'enonce': 'Relancer J+3.',
                'confiance': 0.7,
                'sources': ['e1'],
                'scope': 'global',
            },
        )
        edit = add_item(
            self.conn,
            ticket_id,
            'lesson',
            'Brouillon.',
            {'enonce': 'Brouillon.', 'confiance': 0.5, 'sources': []},
        )
        drop = add_item(self.conn, ticket_id, 'lesson', 'Banalité.')
        book = add_item(
            self.conn,
            ticket_id,
            'playbook',
            'Relance',
            {'nom': 'Relance', 'conditions': 'silence', 'etapes': ['J+3']},
        )
        set_item(self.conn, keep, 'keep')
        set_item(self.conn, edit, 'edit', {'statement': 'Version corrigée.'})
        set_item(self.conn, drop, 'drop')
        set_item(self.conn, book, 'keep')
        publish(self.conn, ticket_id)
        decide(self.conn, ticket_id, 'APPROVED')
        result = execute(
            self.conn,
            POLICY,
            self._item('memory.apply', 'k-a1', {'ticket_id': ticket_id}),
        )
        self.assertEqual(result['status'], 'done')
        self.assertEqual(
            (result['lessons'], result['playbooks'], result['skipped']),
            (2, 1, 1),
        )
        statements = {
            row[0]
            for row in self.conn.execute('SELECT statement FROM lessons')
        }
        self.assertIn('Relancer J+3.', statements)
        self.assertIn('Version corrigée.', statements)
        self.assertNotIn('Banalité.', statements)

    def test_apply_non_decide(self) -> None:
        ticket_id = create_ticket(
            self.conn, self.types, 'MEMORY', 'm', {'lecons': []}
        )
        publish(self.conn, ticket_id)
        result = execute(
            self.conn,
            POLICY,
            self._item('memory.apply', 'k-a2', {'ticket_id': ticket_id}),
        )
        self.assertEqual(result['error'], 'ticket_non_decide')

    def test_consolidate_worker(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'lecons': [
                        {
                            'enonce': 'X.',
                            'confiance': 0.6,
                            'sources': ['e1'],
                            'scope': 'global',
                        }
                    ],
                    'playbooks': [],
                    'pitfalls': [],
                }
            ),
            json.dumps({'serge_md': '# S\n', 'changements': ['init']}),
        )
        result = execute(
            self.conn,
            POLICY,
            self._item('memory.consolidate', 'k-c1', {}),
            caller=caller,
        )
        self.assertEqual(result['status'], 'done')
        self.assertTrue(result['due'])
        self.assertIsNotNone(result['ticket_id'])


if __name__ == '__main__':
    unittest.main()
