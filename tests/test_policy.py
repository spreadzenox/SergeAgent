#!/usr/bin/env python3
"""Policy loader: base + overlay test, validée. Fail-closed."""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.policy import (  # noqa: E402
    PolicyError,
    fusionner_semence,
    is_test_env,
    load_policy,
    validate_policy,
)

# Là où un réglage n'est pas « lu » : la vérification et le catalogue de la
# page Policy (titres et aides).
NE_LISENT_PAS = {
    ROOT / 'serge/policy.py',
    ROOT / 'serge/mc/static/mc/policy_champs.js',
}


def _feuilles(node: dict, chemin: str = ''):
    for cle, val in node.items():
        if isinstance(val, dict):
            yield from _feuilles(val, f'{chemin}{cle}.')
        else:
            yield f'{chemin}{cle}'


class PolicyTests(unittest.TestCase):
    def test_prod_policy_loads_with_validated_values(self) -> None:
        with mock.patch.dict(os.environ, {'SERGE_ENV': ''}, clear=False):
            os.environ.pop('SERGE_ENV', None)
            policy = load_policy()
        self.assertEqual(policy['budget']['monthly_eur'], 50.0)
        self.assertEqual(policy['quotas']['voice_max_calls_per_day'], 50)
        self.assertEqual(policy['calling_zones']['default'], 'FR')
        self.assertEqual(policy['calling_zones']['FR']['contact_per_30d'], 4)
        self.assertEqual(policy['testing']['n_smoke_min'], 30)
        self.assertEqual(policy['standing']['cout_usage'], 0.10)
        self.assertEqual(policy['standing']['capital_min'], 0.20)

    def test_test_overlay_applies_plancher(self) -> None:
        with mock.patch.dict(os.environ, {'SERGE_ENV': 'test'}):
            self.assertTrue(is_test_env())
            policy = load_policy()
        self.assertEqual(policy['budget']['monthly_eur'], 2.0)
        self.assertEqual(policy['quotas']['email_per_mailbox_per_day'], 2)
        self.assertEqual(policy['quotas']['voice_max_calls_per_day'], 0)
        self.assertEqual(policy['quotas']['linkedin_connect_per_day'], 0)
        # Non surchargé = valeur prod conservée.
        self.assertEqual(policy['budget']['eur_per_usd'], 0.9)

    def test_invalid_policy_refuses(self) -> None:
        with self.assertRaises(PolicyError):
            validate_policy({'schema_version': 999})
        with self.assertRaises(PolicyError):
            validate_policy({**load_policy(), 'budget': {'monthly_eur': -1}})
        bad = load_policy()
        bad['tickets']['digest_hour'] = 'huit'
        with self.assertRaises(PolicyError):
            validate_policy(bad)
        pire = load_policy()
        pire['standing'] = dict(pire['standing'])
        pire['standing']['capital_max'] = 0.05
        with self.assertRaises(PolicyError):
            validate_policy(pire)

    def test_chaque_reglage_est_lu_par_un_programme(self) -> None:
        """Un réglage que rien ne lit ment dans Mission Control (Q68)."""
        # raccourci : on cherche le nom du réglage (son dernier mot) dans le
        # code ; un nom repris ailleurs (« timezone ») peut passer à tort.
        sources = [
            p.read_text(encoding='utf-8')
            for dossier in ('serge', 'kit')
            for p in (ROOT / dossier).rglob('*')
            if p.suffix in {'.py', '.js'} and p not in NE_LISENT_PAS
        ]
        orphelins = [
            chemin
            for chemin in _feuilles(load_policy())
            if chemin != 'schema_version'
            and not any(
                re.search(rf'\b{re.escape(chemin.split(".")[-1])}\b', s)
                for s in sources
            )
        ]
        self.assertEqual(orphelins, [])

    def test_un_reglage_retire_disparait_d_un_ancien_snapshot(self) -> None:
        ancien = load_policy()
        ancien['quotas']['llm_outil_tours_max'] = 12
        ancien['cooldowns'] = {'inbound_silence_days': 7}
        ancien['budget']['llm_daily_eur'] = 9.0
        fusion = fusionner_semence(ancien)
        self.assertNotIn('llm_outil_tours_max', fusion['quotas'])
        self.assertNotIn('cooldowns', fusion)
        # Une valeur changée dans Mission Control est gardée.
        self.assertEqual(fusion['budget']['llm_daily_eur'], 9.0)


if __name__ == '__main__':
    unittest.main()
