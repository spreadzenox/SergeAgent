#!/usr/bin/env python3
"""MC auth : sessions hashées, bearer/cookie, rate-limit (déterministe)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.auth import (  # noqa: E402
    RateLimiter,
    check_owner,
    create_session,
    hash_token,
    revoke_session,
    verify_session,
)

T0 = '2026-01-01T00:00:00+00:00'
T11H = '2026-01-01T11:00:00+00:00'
T12H = '2026-01-01T12:00:00+00:00'
T12H01 = '2026-01-01T12:00:01+00:00'


class McAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_session_cycle(self) -> None:
        token, expires = create_session(self.conn, T0)
        self.conn.commit()
        self.assertEqual(expires, T12H)
        self.assertTrue(verify_session(self.conn, token, T11H))
        self.assertFalse(verify_session(self.conn, token, T12H01))
        self.assertFalse(verify_session(self.conn, 'nope', T11H))
        revoke_session(self.conn, token)
        self.conn.commit()
        self.assertFalse(verify_session(self.conn, token, T11H))

    def test_session_never_stored_raw(self) -> None:
        token, _ = create_session(self.conn, T0)
        self.conn.commit()
        stored = self.conn.execute(
            'SELECT token_hash FROM mc_sessions'
        ).fetchone()[0]
        self.assertEqual(stored, hash_token(token))
        self.assertNotEqual(stored, token)
        self.assertTrue(verify_session(self.conn, token, T11H))
        seen = self.conn.execute(
            'SELECT last_seen_at FROM mc_sessions'
        ).fetchone()[0]
        self.assertEqual(seen, T11H)

    def test_check_owner_paths(self) -> None:
        token, _ = create_session(self.conn, T0)
        self.conn.commit()
        good = {'authorization': 'Bearer tok-owner-1'}
        self.assertTrue(check_owner(good, {}, self.conn, 'tok-owner-1', T11H))
        self.assertFalse(check_owner(good, {}, self.conn, 'tok-owner-2', T11H))
        header = {'x-serge-owner-token': 'tok-owner-1'}
        self.assertTrue(
            check_owner(header, {}, self.conn, 'tok-owner-1', T11H)
        )
        cookies = {'serge_mc': token}
        self.assertTrue(check_owner({}, cookies, self.conn, 'x', T11H))
        self.assertFalse(check_owner({}, {}, self.conn, 'x', T11H))
        self.assertFalse(
            check_owner({}, {'serge_mc': 'nope'}, self.conn, 'x', T11H)
        )

    def test_rate_limiter_window(self) -> None:
        now = [0.0]
        limiter = RateLimiter(max_hits=3, window_s=60.0, now_fn=lambda: now[0])
        self.assertEqual(
            [limiter.allow('ip') for _ in range(3)], [True, True, True]
        )
        self.assertFalse(limiter.allow('ip'))
        self.assertTrue(limiter.allow('other'))
        now[0] = 61.0
        self.assertTrue(limiter.allow('ip'))


if __name__ == '__main__':
    unittest.main()
