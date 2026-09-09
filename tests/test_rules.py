#!/usr/bin/env python3
"""Règles kill/scale : verdicts purs depuis métriques + seuils."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.funnels.rules import evaluate_full, evaluate_smoke  # noqa: E402


def _metrics(**overrides):
    base = {
        'positifs': 0,
        'u4_eur': 0.0,
        'u5_classes': 0,
        'bounce_rate': 0.0,
    }
    base.update(overrides)
    return base


class RulesTests(unittest.TestCase):
    def test_smoke_jamais_kill(self) -> None:
        self.assertEqual(evaluate_smoke(_metrics(positifs=5)), 'SCALE')
        self.assertEqual(evaluate_smoke(_metrics(positifs=3)), 'SCALE')
        self.assertEqual(evaluate_smoke(_metrics(positifs=0)), 'FULL')
        custom = evaluate_smoke(
            _metrics(positifs=1), {'scale_min_positifs': 1}
        )
        self.assertEqual(custom, 'SCALE')

    def test_full_running_tant_qu_incomplet(self) -> None:
        for n_reached, elapsed in (
            (False, False),
            (True, False),
            (False, True),
        ):
            self.assertEqual(
                evaluate_full(
                    _metrics(positifs=99),
                    n_reached=n_reached,
                    window_elapsed=elapsed,
                    extended=False,
                ),
                'RUNNING',
            )

    def test_full_scale(self) -> None:
        verdict = evaluate_full(
            _metrics(positifs=12, u4_eur=9.0),
            n_reached=True,
            window_elapsed=True,
            extended=False,
        )
        self.assertEqual(verdict, 'SCALE')
        # U4 trop cher : pas de SCALE.
        verdict = evaluate_full(
            _metrics(positifs=12, u4_eur=99.0, u5_classes=0),
            n_reached=True,
            window_elapsed=True,
            extended=True,
        )
        self.assertEqual(verdict, 'KILL')

    def test_full_invalid_avant_tout(self) -> None:
        verdict = evaluate_full(
            _metrics(positifs=50, u4_eur=1.0, bounce_rate=0.2),
            n_reached=True,
            window_elapsed=True,
            extended=False,
        )
        self.assertEqual(verdict, 'INVALID')

    def test_full_extend_une_fois(self) -> None:
        metrics = _metrics(positifs=5, u4_eur=50.0, u5_classes=0)
        verdict = evaluate_full(
            metrics,
            n_reached=True,
            window_elapsed=True,
            extended=False,
        )
        self.assertEqual(verdict, 'EXTEND')
        verdict = evaluate_full(
            metrics,
            n_reached=True,
            window_elapsed=True,
            extended=True,
        )
        self.assertEqual(verdict, 'KILL')

    def test_full_pivot_quand_on_apprend(self) -> None:
        verdict = evaluate_full(
            _metrics(positifs=1, u4_eur=60.0, u5_classes=4),
            n_reached=True,
            window_elapsed=True,
            extended=True,
        )
        self.assertEqual(verdict, 'PIVOT')
        verdict = evaluate_full(
            _metrics(positifs=1, u4_eur=60.0, u5_classes=1),
            n_reached=True,
            window_elapsed=True,
            extended=True,
        )
        self.assertEqual(verdict, 'KILL')


if __name__ == '__main__':
    unittest.main()
