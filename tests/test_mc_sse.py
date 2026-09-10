#!/usr/bin/env python3
"""MC SSE : framing, cache TTL, T1/T2/A10, auth API, page inconnue."""

from __future__ import annotations

import http.client
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import SnapshotCache, sig  # noqa: E402
from serge.mc.sse import format_event  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402


class SseUnitTests(unittest.TestCase):
    def test_framing_exact(self) -> None:
        raw = format_event('meta', 'abc', 12, {'v': 1})
        self.assertEqual(
            raw,
            b'event: section\n'
            b'data: {"section": "meta", "sig": "abc", "age_ms": 12,'
            b' "payload": {"v": 1}}\n\n',
        )

    def test_sig_stable_et_sensible(self) -> None:
        self.assertEqual(sig({'a': 1}), sig({'a': 1}))
        self.assertEqual(sig({'a': 1, 'b': 2}), sig({'b': 2, 'a': 1}))
        self.assertNotEqual(sig({'a': 1}), sig({'a': 2}))

    def test_cache_ttl(self) -> None:
        now = [100.0]
        calls = []
        cache = SnapshotCache(now_fn=lambda: now[0])

        def _compute():
            calls.append(1)
            return {'n': len(calls)}

        first = cache.get('p0', 'meta', 10.0, _compute)
        second = cache.get('p0', 'meta', 10.0, _compute)
        self.assertEqual(len(calls), 1)
        self.assertEqual(first[1], second[1])
        self.assertEqual(second[2], 0)
        now[0] = 105.0
        third = cache.get('p0', 'meta', 10.0, _compute)
        self.assertEqual(len(calls), 1)
        self.assertEqual(third[2], 5000)
        now[0] = 111.0
        cache.get('p0', 'meta', 10.0, _compute)
        self.assertEqual(len(calls), 2)


class SseE2ETests(McServerCase):
    def _boot_state(self, cookie: str):
        _, _, body = self._request('GET', '/owner', headers={'Cookie': cookie})
        match = re.search(
            r'<script type="application/json" id="serge-boot">(.*?)</script>',
            body.decode('utf-8'),
            re.DOTALL,
        )
        assert match is not None
        return json.loads(match.group(1))

    def _first_event(self, cookie: str):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=10)
        try:
            conn.request(
                'GET',
                '/owner/api/stream?page=p0',
                headers={'Cookie': cookie},
            )
            resp = conn.getresponse()
            self.assertEqual(resp.status, 200)
            head = resp.fp.readline().decode('utf-8')
            data = resp.fp.readline().decode('utf-8')
            self.assertTrue(head.startswith('event: section'))
            self.assertTrue(data.startswith('data: '))
            return json.loads(data[len('data: ') :])
        finally:
            conn.close()

    def test_boot_egale_state_egale_sse(self) -> None:
        status, headers, _ = self._login()
        self.assertEqual(status, 302)
        cookie = self._cookie(headers)
        boot = self._boot_state(cookie)
        _, _, raw = self._request(
            'GET', '/owner/api/state?page=p0', headers={'Cookie': cookie}
        )
        state = json.loads(raw.decode('utf-8'))
        self.assertEqual(boot, state)
        event = self._first_event(cookie)
        self.assertEqual(event['section'], 'meta')
        self.assertEqual(event['sig'], state['sections']['meta']['sig'])
        self.assertEqual(
            event['payload'], state['sections']['meta']['payload']
        )

    def test_api_sans_auth_401_json(self) -> None:
        for path in ('/owner/api/state?page=p0', '/owner/api/stream?page=p0'):
            status, headers, body = self._request('GET', path)
            self.assertEqual(status, 401)
            self.assertIn('application/json', headers.get('content-type', ''))
            payload = json.loads(body.decode('utf-8'))
            self.assertEqual(payload['code'], 'auth')

    def test_api_bearer_ok_et_page_inconnue(self) -> None:
        headers = {'Authorization': f'Bearer {self.TOKEN}'}
        status, _, _ = self._request(
            'GET', '/owner/api/state?page=p0', headers=headers
        )
        self.assertEqual(status, 200)
        status, _, body = self._request(
            'GET', '/owner/api/state?page=nope', headers=headers
        )
        self.assertEqual(status, 400)
        self.assertIn('inconnue', body.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
