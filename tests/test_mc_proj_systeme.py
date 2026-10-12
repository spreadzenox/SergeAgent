#!/usr/bin/env python3
"""Page Système : la population (fixtures partagées avec les îlots)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.proj_systeme import project_population  # noqa: E402
from tests.test_mc_proj_ilots import (  # noqa: E402
    NOW,
    POLICY,
    ProjSystemFixtures,
)


class ProjSystemeTests(ProjSystemFixtures):
    def test_population_golden(self) -> None:
        self.assertEqual(
            project_population(self.conn, POLICY, NOW),
            {
                'contacts': {'CONTACTING': 1, 'NEW': 1},
                'ventures': {'SMOKE_RUNNING': 1, 'CANDIDATE': 1},
            },
        )
