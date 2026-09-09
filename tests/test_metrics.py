#!/usr/bin/env python3
"""U1-U5 : compteurs depuis touches + signaux universels."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.funnels.metrics import (  # noqa: E402
    campaign_metrics,
    venture_metrics,
)

NOW = '2026-09-09T19:00:00+00:00'


class MetricsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        init_schema(self.connection)
        self.connection.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        self.connection.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel,'
            " created_at, updated_at) VALUES('c1','v1','named','email','t','t')"
        )
        self.connection.execute(
            'INSERT INTO contacts(id, venture_id, display, funnel_state,'
            " created_at, updated_at) VALUES('p1','v1','A','NEW','t','t')"
        )
        self.connection.execute(
            'INSERT INTO contacts(id, venture_id, display, funnel_state,'
            " created_at, updated_at) VALUES('p2','v1','B','INVALID','t','t')"
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()

    def _touch(
        self,
        key: str,
        status: str,
        contact: str = 'p1',
        cost: float = 0.01,
    ) -> None:
        self.connection.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, cost_eur, idempotency_key, created_at, updated_at)'
            ' VALUES(?,?,?,?,?,?,?,?,?)',
            (key, 'c1', contact, 'email', status, cost, key, NOW, NOW),
        )

    def _inbound(
        self, item_id: str, signal: str, cls: str = '', cost: float = 0.0
    ) -> None:
        self.connection.execute(
            'INSERT INTO inbound_events(id, campaign_id, contact_id, channel,'
            ' native_type, signal, class, cost_eur, received_at)'
            " VALUES(?,?,'','email','RECEIVED',?,?,?,?)",
            (item_id, 'c1', signal, cls, cost, NOW),
        )

    def test_campagne_vide(self) -> None:
        metrics = campaign_metrics(self.connection, 'c1')
        self.assertEqual(
            (metrics['u1'], metrics['u2'], metrics['u3']),
            (0, 0, 0),
        )
        self.assertEqual(metrics['u4_eur'], 0.0)
        self.assertEqual(metrics['u5_classes'], 0)

    def test_compteurs_et_taux(self) -> None:
        for index in range(10):
            self._touch(f't{index}', 'sent')
        self._touch('tb', 'bounced')
        self._touch('ti', 'sent', contact='p2')
        self._inbound('e1', 'ENGAGED')
        self._inbound('e2', 'REPLIED', cls='question')
        self._inbound('e3', 'INTENT', cls='meeting', cost=0.5)
        self._inbound('e4', 'INTENT', cls='meeting')
        self._inbound('e5', 'OPT_OUT')
        metrics = campaign_metrics(self.connection, 'c1')
        self.assertEqual(metrics['u1'], 11)
        self.assertEqual(metrics['n_valid'], 10)
        self.assertEqual(metrics['u2'], 2)
        self.assertEqual(metrics['u3'], 2)
        self.assertEqual(metrics['positifs'], 2)
        self.assertEqual(metrics['u5_classes'], 2)
        self.assertEqual(metrics['verbatims'], 3)
        self.assertAlmostEqual(metrics['intent_rate'], 2 / 11, places=4)
        self.assertAlmostEqual(metrics['bounce_rate'], 1 / 11, places=4)
        # Coût : 12 touches × 0.01 + 0.5 inbound = 0.62 ; U4 = 0.62/2.
        self.assertEqual(metrics['cost_eur'], 0.62)
        self.assertEqual(metrics['u4_eur'], 0.31)

    def test_u4_sans_intent_egale_depense(self) -> None:
        self._touch('t0', 'sent', cost=0.2)
        metrics = campaign_metrics(self.connection, 'c1')
        self.assertEqual(metrics['u4_eur'], 0.2)

    def test_agregat_venture(self) -> None:
        self.connection.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel,'
            " created_at, updated_at) VALUES('c2','v1','ads','meta','t','t')"
        )
        self._touch('t0', 'sent')
        self.connection.execute(
            'INSERT INTO touches(id, campaign_id, channel, status, cost_eur,'
            ' idempotency_key, created_at, updated_at)'
            " VALUES('a0','c2','meta','sent',1.0,'a0',?,?)",
            (NOW, NOW),
        )
        self._inbound('e1', 'INTENT', cls='trial')
        self.connection.execute(
            'INSERT INTO inbound_events(id, campaign_id, channel, native_type,'
            ' signal, class, received_at)'
            " VALUES('a1','c2','meta','CONVERTED','INTENT','trial',?)",
            (NOW,),
        )
        metrics = venture_metrics(self.connection, 'v1')
        self.assertEqual(metrics['u1'], 2)
        self.assertEqual(metrics['u3'], 2)
        self.assertEqual(metrics['u5_classes'], 1)
        self.assertEqual(metrics['cost_eur'], 1.01)


if __name__ == '__main__':
    unittest.main()
