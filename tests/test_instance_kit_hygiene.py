#!/usr/bin/env python3
"""Kit seed stays virgin: no secrets, no Julien instance memory."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / 'schemas/serge.instance.example.toml'
EXCLUSIONS = ROOT / 'schemas/serge.kit-exclusions.yaml'
MANIFEST = ROOT / 'schemas/serge.secrets.manifest.yaml'
INVENTORY = ROOT / 'docs/instance-inventory.yaml'
TEMPLATES = ROOT / 'systemd/templates'

LIVE_SENTINELS = (
    'live-owner.example.net',
    'live-owner@example.com',
    '999988887777666001',
    'live-owner.example.com',
)
PERSONAL_MAIL_RE = (
    r'@(gmail|hotmail|outlook|yahoo|icloud|protonmail|free|orange|sfr'
    r'|laposte|gmx|aol)\.[a-z]{2,}'
)


class InstanceKitHygieneTests(unittest.TestCase):
    def test_example_toml_is_virgin_sandbox(self) -> None:
        text = EXAMPLE.read_text(encoding='utf-8')
        self.assertIn('instance_id = "example-sandbox"', text)
        self.assertIn('mode = "sandbox"', text)
        self.assertIn('owner_ui = true', text)
        self.assertIn('payments_live = true', text)
        self.assertIn('phone_sms = true', text)
        self.assertIn('phone_voice = true', text)
        self.assertIn('[phone_voice]', text)
        self.assertIn('metagrok = false', text)
        self.assertNotIn('julien-vps', text)
        for marker in LIVE_SENTINELS:
            self.assertNotIn(marker, text)
        self.assertNotIn('/home/serge', text)
        self.assertNotIn('openrouter_api_key', text)
        self.assertNotIn('sk_', text)

    def test_kit_exclusions_cover_memory_and_secrets(self) -> None:
        payload = yaml.safe_load(EXCLUSIONS.read_text(encoding='utf-8'))
        self.assertIs(payload['secret_values_included'], False)
        never = set(payload['never_copy'])
        for required in (
            'state/',
            'serge.secrets.age',
            'projects/',
            'evidence/',
            'logs/',
            '~/.config/serge/',
            '~/.openclaw/',
            '~/.meta-grok/',
        ):
            self.assertIn(required, never)

    def test_tracked_kit_schemas_have_no_secret_values(self) -> None:
        tracked = [EXAMPLE, EXCLUSIONS, MANIFEST, INVENTORY]
        tracked.extend(TEMPLATES.rglob('*.in'))
        blob = '\n'.join(path.read_text(encoding='utf-8') for path in tracked)
        self.assertIsNone(re.search(r'sk_live_[A-Za-z0-9]{10,}', blob))
        self.assertIsNone(re.search(r'whsec_[A-Za-z0-9]{8,}', blob))
        self.assertNotIn('-----BEGIN ', blob)

    def test_example_toml_avoids_live_identity(self) -> None:
        text = EXAMPLE.read_text(encoding='utf-8')
        for marker in LIVE_SENTINELS:
            self.assertNotIn(marker, text)

    def test_kit_seed_has_no_personal_data(self) -> None:
        tracked = [EXAMPLE, EXCLUSIONS, MANIFEST, INVENTORY]
        tracked.extend(TEMPLATES.rglob('*.in'))
        blob = '\n'.join(path.read_text(encoding='utf-8') for path in tracked)
        self.assertIsNone(re.search(PERSONAL_MAIL_RE, blob))
        self.assertIsNone(re.search(r'\b[0-9]{17,20}\b', blob))


if __name__ == '__main__':
    unittest.main()
