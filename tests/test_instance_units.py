#!/usr/bin/env python3
"""Parameterized unit templates stay portable and instance-driven."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.instance_file import FEATURE_KEYS  # noqa: E402
from kit.units import (  # noqa: E402
    UnitError,
    render_template,
    render_units,
    system_units_to_enable,
)

LIVE_SENTINELS = (
    '/home/serge',
    '1002',
    'julien-vps',
    'live-owner.example.net',
    'live-owner',
    '999988887777666001',
)


def _loaded(**overrides):
    features = {key: False for key in FEATURE_KEYS}
    features.update(overrides.pop('features', {}))
    payload = {
        'instance_file': '/home/owner/.config/serge/serge.instance.toml',
        'instance_id': 'example-sandbox',
        'mode': 'sandbox',
        'paths': {
            'home': '/home/owner',
            'system_root': '/home/owner/serge-system',
            'policy': '/home/owner/.config/serge/mandate.yaml',
            'config_root': '/home/owner/.config/serge',
        },
        'features': features,
        'ingress': {'listen': 'loopback', 'aliases': []},
    }
    payload.update(overrides)
    return payload


class InstanceUnitTests(unittest.TestCase):
    def test_templates_have_no_live_host_memory(self) -> None:
        templates = ROOT / 'systemd/templates'
        blob = '\n'.join(
            path.read_text(encoding='utf-8')
            for path in templates.rglob('*.in')
        )
        for marker in LIVE_SENTINELS:
            self.assertNotIn(marker, blob)
        self.assertIn('__INSTANCE_FILE__', blob)
        self.assertIn('__SYSTEM_ROOT__', blob)

    def test_core_units_for_sandbox_without_optional_features(self) -> None:
        rendered = render_units(_loaded(), {'user': 'owner', 'uid': '1000'})
        files = rendered['files']
        self.assertIn('serge-pipeline.service', files)
        self.assertIn('serge-pipeline.timer', files)
        self.assertNotIn('serge-daily-report.service', files)
        self.assertNotIn('serge-burn-in-failure.service', files)
        self.assertNotIn('serge-web-ingress.service', files)
        self.assertNotIn('serge-public-dashboard.service', files)
        self.assertFalse(rendered['installed'])
        self.assertFalse(rendered['metagrok_units_included'])
        pipeline = files['serge-pipeline.service']
        self.assertIn(
            'SERGE_INSTANCE_FILE=/home/owner/.config/serge/serge.instance.toml',
            pipeline,
        )
        self.assertIn('SERGE_AGENT_RUNTIME=direct_llm', pipeline)
        self.assertIn('scripts/serge-runner.py --once', pipeline)
        self.assertIn('state/pipeline.lock', pipeline)
        self.assertNotIn('orchestrator/sergectl.py', pipeline)
        self.assertNotIn('openclaw-gateway', pipeline)
        self.assertNotIn('SERGE_OPENCLAW', pipeline)
        self.assertNotIn('/home/serge', pipeline)
        self.assertNotIn('/run/user/1002', pipeline)
        self.assertIn('/run/user/1000', pipeline)
        self.assertEqual(rendered['enable'], ['serge-pipeline.timer'])

    def test_ingress_and_owner_ui_are_feature_gated(self) -> None:
        rendered = render_units(
            _loaded(features={'ingress': True, 'owner_ui': True})
        )
        self.assertIn('serge-web-ingress.service', rendered['files'])
        self.assertIn('serge-public-dashboard.service', rendered['files'])
        self.assertEqual(
            rendered['scope']['serge-web-ingress.service'], 'user'
        )
        self.assertIn('serge-web-ingress.service', rendered['enable'])
        self.assertIn('serge-public-dashboard.service', rendered['enable'])
        ingress = rendered['files']['serge-web-ingress.service']
        self.assertIn('serge/ingress/caddy.py render', ingress)
        self.assertNotIn('orchestrator/web_ingress.py', ingress)

    def test_privileged_ingress_uses_system_scope(self) -> None:
        rendered = render_units(
            _loaded(
                features={'ingress': True},
                ingress={'listen': 'privileged', 'aliases': []},
            )
        )
        unit = rendered['files']['serge-web-ingress.service']
        self.assertEqual(
            rendered['scope']['serge-web-ingress.service'], 'system'
        )
        self.assertIn('CAP_NET_BIND_SERVICE', unit)
        self.assertIn('SERGE_INGRESS_LISTEN=privileged', unit)
        self.assertNotIn('serge-web-ingress.service', rendered['enable'])
        self.assertEqual(
            system_units_to_enable({'ingress': True}, 'privileged'),
            ['serge-web-ingress.service'],
        )

    def test_dead_units_are_never_rendered(self) -> None:
        for mode in ('sandbox', 'live'):
            rendered = render_units(_loaded(mode=mode))
            self.assertNotIn(
                'serge-burn-in-failure.service', rendered['files']
            )
            self.assertNotIn('serge-daily-report.service', rendered['files'])
            self.assertNotIn('serge-daily-report.timer', rendered['files'])
            self.assertEqual(rendered['enable'], ['serge-pipeline.timer'])

    def test_phone_units_are_feature_gated(self) -> None:
        rendered = render_units(_loaded(features={'phone_sms': True}))
        self.assertIn('serge-sms-receiver.service', rendered['files'])
        self.assertNotIn('serge-asterisk.service', rendered['files'])
        self.assertNotIn('serge-voice-bridge.service', rendered['files'])
        self.assertIn('serge-sms-receiver.service', rendered['enable'])
        full = render_units(
            _loaded(
                features={
                    'phone_sms': True,
                    'phone_voice': True,
                }
            )
        )
        self.assertIn('serge-asterisk.service', full['files'])
        self.assertIn('serge-voice-bridge.service', full['files'])
        self.assertIn('serge-asterisk.service', full['enable'])
        self.assertIn('serge-voice-bridge.service', full['enable'])
        asterisk = full['files']['serge-asterisk.service']
        self.assertIn('/usr/sbin/asterisk', asterisk)
        self.assertIn(
            '/home/owner/.config/serge/asterisk/asterisk.conf',
            asterisk,
        )
        bridge = full['files']['serge-voice-bridge.service']
        self.assertIn('serge/voice/bridge.py serve', bridge)
        self.assertIn('127.0.0.1:8791', bridge)

    def test_stripe_receiver_is_feature_gated(self) -> None:
        rendered = render_units(_loaded(features={'stripe': True}))
        self.assertIn('serge-stripe-receiver.service', rendered['files'])
        self.assertIn('serge-stripe-receiver.service', rendered['enable'])
        unit = rendered['files']['serge-stripe-receiver.service']
        self.assertIn('serge/collect/receiver.py serve', unit)
        self.assertNotIn(
            'serge-stripe-receiver.service',
            render_units(_loaded())['files'],
        )

    def test_discord_bot_is_feature_gated(self) -> None:
        rendered = render_units(_loaded(features={'discord': True}))
        self.assertIn('serge-discord-bot.service', rendered['files'])
        self.assertIn('serge-discord-bot.service', rendered['enable'])
        bot = rendered['files']['serge-discord-bot.service']
        self.assertIn('serge/discord/cli.py serve', bot)
        self.assertNotIn(
            'serge-discord-bot.service',
            render_units(_loaded())['files'],
        )

    def test_unreplaced_placeholder_fails(self) -> None:
        with self.assertRaises(UnitError):
            render_template('WorkingDirectory=__SYSTEM_ROOT__\n', {})

    def test_every_service_exports_instance_file(self) -> None:
        rendered = render_units(
            _loaded(
                features={
                    'ingress': True,
                    'owner_ui': True,
                    'phone_sms': True,
                    'phone_voice': True,
                },
            )
        )
        for name, text in rendered['files'].items():
            if name.endswith('.timer') or name.endswith('.conf'):
                continue
            self.assertIn('SERGE_INSTANCE_FILE=', text, name)

    def test_pipeline_gmail_environment_file(self) -> None:
        with_gmail = render_units(_loaded(features={'gmail': True}))
        pipeline = with_gmail['files']['serge-pipeline.service']
        self.assertIn(
            'EnvironmentFile=-/home/owner/.config/serge/secrets/gog.env',
            pipeline,
        )
        without = render_units(_loaded())['files']['serge-pipeline.service']
        self.assertNotIn('EnvironmentFile', without)
        self.assertNotIn('GMAIL_UNIT_LINES', pipeline + without)

    def test_pipeline_mailbox_backend(self) -> None:
        with_box = render_units(_loaded(features={'mailbox': True}))
        pipeline = with_box['files']['serge-pipeline.service']
        self.assertIn('SERGE_EMAIL_BACKEND=smtp', pipeline)
        without = render_units(_loaded())['files']['serge-pipeline.service']
        self.assertNotIn('SERGE_EMAIL_BACKEND', without)
        self.assertNotIn('EMAIL_BACKEND_LINES', pipeline + without)

    def test_units_use_given_python(self) -> None:
        facts = {
            'user': 'owner',
            'uid': '1000',
            'python': '/x/py',
            'caddy': '/x/caddy',
        }
        rendered = render_units(_loaded(features={'discord': True}), facts)
        pipeline = rendered['files']['serge-pipeline.service']
        self.assertIn('/x/py ', pipeline)
        bot = rendered['files']['serge-discord-bot.service']
        self.assertIn('ExecStart=/x/py ', bot)
        self.assertNotIn('/usr/bin/python3', pipeline + bot)

    def test_shims_use_path_python(self) -> None:
        for shim in sorted((ROOT / 'bin').iterdir()):
            if not shim.is_file():
                continue
            text = shim.read_text(encoding='utf-8')
            self.assertNotIn('/usr/bin/python3', text, shim.name)
            self.assertIn('exec python3', text, shim.name)


if __name__ == '__main__':
    unittest.main()
