#!/usr/bin/env python3
"""Campagnes : création, gates READY/RUN, fenêtre, N, verdicts."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.funnels.campaigns import (  # noqa: E402
    CampaignError,
    cancel,
    create_campaign,
    finish,
    n_reached,
    pause,
    resume,
    start,
    thresholds,
    to_ready,
    window_elapsed,
    window_open,
)

NOW = '2026-09-09T19:00:00+00:00'
SEUILS = {'scale_min_positifs': 3}


class CampaignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()

    def _state(self, campaign_id: str) -> str:
        return str(
            self.connection.execute(
                'SELECT state FROM campaigns WHERE id=?', (campaign_id,)
            ).fetchone()[0]
        )

    def _make(self, **overrides) -> str:
        params = {
            'venture_id': 'v1',
            'family': 'named',
            'channel': 'email',
            'n_target': 50,
            'thresholds': dict(SEUILS),
        }
        params.update(overrides)
        return create_campaign(self.connection, **params)

    def test_creation_et_gates(self) -> None:
        with self.assertRaises(CampaignError):
            self._make(family='nope')
        with self.assertRaises(CampaignError):
            self._make(channel=' ')
        with self.assertRaises(CampaignError):
            self._make(
                window_start='2026-09-10T00:00:00+00:00',
                window_end='2026-09-01T00:00:00+00:00',
            )
        campaign_id = self._make()
        self.assertEqual(self._state(campaign_id), 'DRAFT')
        self.assertEqual(thresholds(self.connection, campaign_id), SEUILS)
        with self.assertRaises(CampaignError):
            start(self.connection, campaign_id)
        to_ready(self.connection, campaign_id)
        start(self.connection, campaign_id)
        self.assertEqual(self._state(campaign_id), 'RUNNING')

    def test_ready_exige_n_et_seuils(self) -> None:
        bare = self._make(n_target=0)
        with self.assertRaises(CampaignError):
            to_ready(self.connection, bare)
        noseuil = self._make(thresholds={})
        with self.assertRaises(CampaignError):
            to_ready(self.connection, noseuil)

    def test_run_exige_venture_en_test(self) -> None:
        self.connection.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v2','CANDIDATE',0,'t','t')"
        )
        campaign_id = self._make(venture_id='v2')
        to_ready(self.connection, campaign_id)
        with self.assertRaises(CampaignError):
            start(self.connection, campaign_id)

    def test_pause_resume_finish_cancel(self) -> None:
        campaign_id = self._make()
        to_ready(self.connection, campaign_id)
        start(self.connection, campaign_id)
        pause(self.connection, campaign_id)
        self.assertEqual(self._state(campaign_id), 'PAUSED')
        resume(self.connection, campaign_id)
        finish(self.connection, campaign_id, 'SCALE', {'u3': 5})
        self.assertEqual(self._state(campaign_id), 'DONE')
        other = self._make()
        cancel(self.connection, other)
        self.assertEqual(self._state(other), 'CANCELLED')
        with self.assertRaises(CampaignError):
            start(self.connection, other)

    def test_fenetre_et_n(self) -> None:
        campaign_id = self._make(
            window_start='2026-09-01T00:00:00+00:00',
            window_end='2026-09-10T00:00:00+00:00',
            n_target=2,
        )
        self.assertTrue(window_open(self.connection, campaign_id, NOW))
        self.assertFalse(window_elapsed(self.connection, campaign_id, NOW))
        self.assertTrue(
            window_elapsed(
                self.connection, campaign_id, '2026-09-11T00:00:00+00:00'
            )
        )
        self.assertFalse(n_reached(self.connection, campaign_id))
        for index in range(2):
            self.connection.execute(
                'INSERT INTO touches(id, campaign_id, channel, status,'
                ' idempotency_key, created_at, updated_at)'
                " VALUES(?,?,'email','sent',?,?,?)",
                (f't{index}', campaign_id, f'k{index}', NOW, NOW),
            )
        self.assertTrue(n_reached(self.connection, campaign_id))
        kinds = [
            row[0]
            for row in self.connection.execute(
                'SELECT type FROM events ORDER BY id'
            )
        ]
        self.assertEqual(kinds, ['campaign.draft'])


if __name__ == '__main__':
    unittest.main()
