#!/usr/bin/env python3
"""Runtime LLM : modèles, clé, kill-switch, budget, metering, dérive."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.llm.client import ChatResult, LlmError  # noqa: E402
from serge.llm.runtime import (  # noqa: E402
    daily_tokens,
    read_api_key,
    resolve_model,
    run_point,
    run_registered_point,
)

POLICY = {'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004}}
SPEC = {
    'verdict': 'LLM-1',
    'tier': 'T1',
    'enabled': True,
    'context': {'envelope_tokens': 100},
}


def _ok_caller(*args, **kwargs):
    model = args[1] if len(args) > 1 else 'm'
    return ChatResult('oui', 50, 10, model, 12)


class LlmRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'llm').mkdir()
        (self.root / 'secrets').mkdir()
        (self.root / 'llm/slots.json').write_text(
            json.dumps(
                {
                    'referer': 'https://r.test',
                    'slots': {'CHEAP': {'openrouter_id': 'm/cheap'}},
                }
            ),
            encoding='utf-8',
        )
        (self.root / 'secrets/openrouter-api-key').write_text(
            'sk-test-key\n', encoding='utf-8'
        )
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def test_resolve_model_slots_et_fallback(self) -> None:
        model, referer = resolve_model('T1', self.root)
        self.assertEqual((model, referer), ('m/cheap', 'https://r.test'))
        model, _ = resolve_model('T3', self.root)
        self.assertTrue(model)
        model, _ = resolve_model('T1', self.root / 'vide')
        self.assertTrue(model)

    def test_read_api_key(self) -> None:
        self.assertEqual(read_api_key(self.root), 'sk-test-key')
        self.assertEqual(read_api_key(self.root / 'vide'), '')
        (self.root / 'secrets/openrouter-api-key').write_text(
            'OPENROUTER_API_KEY=sk-dotenv\n', encoding='utf-8'
        )
        self.assertEqual(read_api_key(self.root), 'sk-dotenv')

    def test_kill_switch(self) -> None:
        spec = dict(SPEC)
        spec['enabled'] = False
        result = run_point(
            self.conn,
            POLICY,
            spec,
            'p1',
            [],
            root=self.root,
            caller=_ok_caller,
        )
        self.assertEqual((result.ok, result.fallback), (False, 'killed'))
        verdict = self.conn.execute(
            'SELECT verdict FROM llm_usage'
        ).fetchone()[0]
        self.assertEqual(verdict, 'killed')

    def test_budget_bloque(self) -> None:
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, tokens_in, tokens_out,'
            " verdict, created_at) VALUES('p','T1',2000000,0,'ok',"
            " '2026-09-09T00:00:00+00:00')"
        )
        result = run_point(
            self.conn,
            POLICY,
            SPEC,
            'p1',
            [],
            root=self.root,
            caller=_ok_caller,
            day='2026-09-09',
        )
        self.assertEqual(result.fallback, 'budget')

    def test_succes_metered(self) -> None:
        result = run_point(
            self.conn,
            POLICY,
            SPEC,
            'classify_reply',
            [{'role': 'user', 'content': 'hi'}],
            root=self.root,
            caller=_ok_caller,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.text, 'oui')
        row = self.conn.execute(
            'SELECT point, tier, tokens_in, tokens_out, verdict FROM llm_usage'
        ).fetchone()
        self.assertEqual(tuple(row), ('classify_reply', 'T1', 50, 10, 'ok'))
        self.assertEqual(daily_tokens(self.conn), (50, 10))

    def test_erreur_caller_fallback(self) -> None:
        def _boom(*args, **kwargs):
            raise LlmError('NETWORK: down')

        result = run_point(
            self.conn, POLICY, SPEC, 'p1', [], root=self.root, caller=_boom
        )
        self.assertEqual((result.ok, result.fallback), (False, 'error'))

    def test_dervie_enveloppe_loguee(self) -> None:
        def _gros(*args, **kwargs):
            return ChatResult('x', 500, 5, 'm', 9)

        run_point(
            self.conn, POLICY, SPEC, 'p1', [], root=self.root, caller=_gros
        )
        types = [
            row[0] for row in self.conn.execute('SELECT type FROM events')
        ]
        self.assertEqual(types, ['alert.llm_envelope_drift'])

    def test_point_inconnu_killed(self) -> None:
        result = run_registered_point(
            self.conn,
            POLICY,
            'nope_zzz',
            [],
            root=self.root,
            caller=_ok_caller,
        )
        self.assertEqual(result.fallback, 'killed')


if __name__ == '__main__':
    unittest.main()
