#!/usr/bin/env python3
"""Point B1 : build artifact, scan secrets/trackers/URLs/prix."""

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
from serge.points.build import build_artifact, scan_forbidden  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'builder': {'artifact_max_files': 20, 'artifact_max_chars': 200000},
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


def _artifact(content: str) -> str:
    return json.dumps(
        {
            'files': [{'path': 'index.html', 'content': content}],
            'notes': 'v1',
        }
    )


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_scan(self) -> None:
        # Fixtures découpées : le scan repo lit le fichier brut (strict),
        # le test assemble à l'exécution (faux secrets, jamais de vrais).
        fake_key = 'api_' + 'key = "sk-live-' + 'abc123xyz789"'
        fake_pem = 'x -----BEGIN ' + 'RSA PRIVATE KEY----- y'
        self.assertEqual(scan_forbidden('<h1>Hi</h1>'), [])
        self.assertTrue(scan_forbidden(fake_key))
        self.assertIn('private_key', scan_forbidden(fake_pem))
        self.assertTrue(
            scan_forbidden('<script src="https://hotjar.com/x.js"></script>')
        )
        self.assertEqual(
            scan_forbidden(
                '<img src="https://cdn.x.io/i.png">',
                allowlist=['cdn.x.io'],
            ),
            [],
        )
        self.assertTrue(scan_forbidden('<a href="https://evil.io/x">y</a>'))

    def test_propose_ok(self) -> None:
        caller = _caller_for(_artifact('<h1>Offre 99 €</h1>'))
        result = build_artifact(
            self.conn,
            POLICY,
            'Landing offre 99 €',
            'stack html',
            spec_prices='99 €',
            caller=caller,
        )
        self.assertEqual(result['action'], 'propose')
        self.assertEqual(len(result['files']), 1)

    def test_secret_vers_qna(self) -> None:
        leaked = '<p>x</p><!-- ' + 'api_key = "sk-live-' + 'abc123" -->'
        caller = _caller_for(_artifact(leaked))
        result = build_artifact(
            self.conn, POLICY, 'Landing', '', caller=caller
        )
        self.assertEqual(result['action'], 'qna')
        self.assertIn('scan', result['reason'])

    def test_prix_invente_vers_qna(self) -> None:
        caller = _caller_for(_artifact('<h1>Offre 499 €</h1>'))
        result = build_artifact(
            self.conn,
            POLICY,
            'Landing offre 99 €',
            '',
            spec_prices='99 €',
            caller=caller,
        )
        self.assertEqual(result['action'], 'qna')
        self.assertIn('nombres', result['reason'])

    def test_killed_qna(self) -> None:
        caller = _caller_for('no json')
        result = build_artifact(
            self.conn, POLICY, 'Landing', '', caller=caller
        )
        self.assertEqual(result['action'], 'qna')
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
