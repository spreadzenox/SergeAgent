#!/usr/bin/env python3
"""Projecteurs P1 : goldens campagnes/population/email (fixtures partagées)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.proj_campagnes import (  # noqa: E402
    project_campagnes,
    project_email,
    project_population,
)
from tests.test_mc_proj_ilots import (  # noqa: E402
    NOW,
    POLICY,
    ProjSystemFixtures,
)


class ProjCampagnesTests(ProjSystemFixtures):
    def test_campagnes_golden(self) -> None:
        self.assertEqual(
            project_campagnes(self.conn, POLICY, NOW),
            {
                'items': [
                    {
                        'id': 'c1',
                        'family': 'named',
                        'channel': 'email',
                        'state': 'RUNNING',
                        'n_target': 10,
                        'envoyes': 1,
                        'touches': 2,
                    },
                    {
                        'id': 'c2',
                        'family': 'named',
                        'channel': 'sms',
                        'state': 'DRAFT',
                        'n_target': 5,
                        'envoyes': 1,
                        'touches': 1,
                    },
                ],
                'cooldowns': [
                    {
                        'venue': 'gmail',
                        'handle': 'a@x.io',
                        'jusqu_a': '2026-09-10T14:00:00+00:00',
                    }
                ],
            },
        )

    def test_population_email_golden(self) -> None:
        self.assertEqual(
            project_population(self.conn, POLICY, NOW),
            {
                'contacts': {'CONTACTING': 1, 'NEW': 1},
                'ventures': {'SMOKE_RUNNING': 1, 'CANDIDATE': 1},
            },
        )
        self.assertEqual(
            project_email(self.conn, POLICY, NOW),
            {
                'par_statut': {'sent': 1, 'queued': 1},
                'derniere_activite': '2026-09-10T11:30:00+00:00',
            },
        )
