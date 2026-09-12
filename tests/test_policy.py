#!/usr/bin/env python3
"""Policy loader: base + overlay test, validée. Fail-closed."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.policy import (  # noqa: E402
    PolicyError,
    is_test_env,
    load_policy,
    validate_policy,
)


class PolicyTests(unittest.TestCase):
    def test_prod_policy_loads_with_validated_values(self) -> None:
        with mock.patch.dict(os.environ, {'SERGE_ENV': ''}, clear=False):
            os.environ.pop('SERGE_ENV', None)
            policy = load_policy()
        self.assertEqual(policy['budget']['monthly_eur'], 50.0)
        self.assertEqual(policy['quotas']['voice_max_calls_per_day'], 50)
        self.assertEqual(policy['calling_zones']['default'], 'FR')
        self.assertIn('mon', policy['calling_zones']['FR']['voice_days'])
        self.assertEqual(policy['testing']['n_smoke_min'], 30)

    def test_test_overlay_applies_plancher(self) -> None:
        with mock.patch.dict(os.environ, {'SERGE_ENV': 'test'}):
            self.assertTrue(is_test_env())
            policy = load_policy()
        self.assertEqual(policy['budget']['monthly_eur'], 2.0)
        self.assertEqual(policy['quotas']['email_per_mailbox_per_day'], 2)
        self.assertEqual(policy['quotas']['voice_max_calls_per_day'], 0)
        self.assertEqual(policy['quotas']['linkedin_connect_per_day'], 0)
        # Non surchargé = valeur prod conservée.
        self.assertEqual(policy['budget']['allocator_reserve_ratio'], 0.20)
        self.assertEqual(policy['memory']['serge_md_max_lines'], 100)

    def test_invalid_policy_refuses(self) -> None:
        with self.assertRaises(PolicyError):
            validate_policy({'schema_version': 999})
        with self.assertRaises(PolicyError):
            validate_policy({**load_policy(), 'budget': {'monthly_eur': -1}})
        bad = load_policy()
        bad['tickets']['trust_min_rate'] = 1.5
        with self.assertRaises(PolicyError):
            validate_policy(bad)


if __name__ == '__main__':
    unittest.main()
