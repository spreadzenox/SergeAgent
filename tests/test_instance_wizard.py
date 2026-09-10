#!/usr/bin/env python3
"""Instance wizard writes a complete virgin couple, never Julien memory."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import yaml

from kit.instance_file import (
    InstanceError,
    default_features,  # noqa: E402
    load_instance,  # noqa: E402
    load_secret_map,
)
from kit.instance_wizard import (  # noqa: E402
    WizardError,
    default_answers,
    empty_features,
    render_dotenv,
    render_toml,
    write_couple,
)
from kit.mandate import validate_mandate  # noqa: E402

LIVE_SENTINELS = (
    'julien-vps',
    'live-owner.example.net',
    'live-owner@example.com',
    '999988887777666001',
    '/home/serge',
)


def _answers(**overrides):
    answers = default_answers()
    answers['instance_id'] = 'alice-laptop'
    answers['features'] = empty_features()
    answers['secrets'] = {'openrouter_api_key': 'test-openrouter'}
    answers.update(overrides)
    if 'features' in overrides:
        answers['features'] = {**empty_features(), **overrides['features']}
    return answers


class InstanceWizardTests(unittest.TestCase):
    def test_defaults_are_all_or_nothing(self) -> None:
        features = default_answers()['features']
        expected = default_features()
        self.assertEqual(features, expected)
        self.assertTrue(features['owner_ui'])
        self.assertTrue(features['stripe'])
        self.assertTrue(features['payments_live'])
        self.assertTrue(features['phone_sms'])
        self.assertTrue(features['phone_voice'])
        self.assertFalse(features['metagrok'])

    def test_phone_couple_renders_and_loads(self) -> None:
        answers = _answers(
            features={
                'ingress': True,
                'voice': True,
                'phone_sms': True,
                'phone_voice': True,
            }
        )
        answers['identity']['public_hostname'] = 'example.net'
        answers['identity']['phone_sms_number'] = '+33600000001'
        answers['identity']['phone_voice_number'] = '+33162000001'
        answers['phone_voice']['sip_server'] = 'sip.example.com'
        answers['phone_voice']['sip_username'] = 'trunk'
        answers['secrets'] = {
            'openrouter_api_key': 'test-openrouter',
            'xai_api_key': 'xai-dummy',
            'cloudflare_infra_key': 'infra',
            'cloudflare_registrar_key': 'registrar',
            'sms_gateway_token': 'sms-secret',
            'sip_trunk_password': 'sip-secret',
        }
        text = render_toml(answers)
        self.assertIn('phone_sms = true', text)
        self.assertIn('phone_voice = true', text)
        self.assertIn('[phone_voice]', text)
        self.assertIn('[testing]', text)
        self.assertIn('n_full_target = 200', text)
        self.assertIn('phone_sms_number = "+33600000001"', text)
        self.assertNotIn('sms-secret', text)
        self.assertNotIn('sip-secret', text)
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            written = write_couple(answers, dest, allow_plaintext=True)
            loaded = load_instance(Path(written['instance']))
        self.assertIn('sms_gateway_token', loaded['secret_names_present'])
        self.assertIn('sip_trunk_password', loaded['secret_names_present'])

    def test_phone_voice_without_sms_refuses_and_writes_nothing(self) -> None:
        answers = _answers(features={'phone_voice': True})
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            with self.assertRaises(WizardError):
                write_couple(answers, dest, allow_plaintext=True)
            self.assertEqual(list(dest.iterdir()), [])

    def test_discord_section_renders_and_validates(self) -> None:
        answers = _answers(features={'discord': True})
        answers['discord'] = {
            key: '123456789012345678' for key in answers['discord']
        }
        answers['secrets']['discord_bot_token'] = 'fake-discord-token'
        text = render_toml(answers)
        self.assertIn('[discord]', text)
        self.assertIn('owner_user_id = "123456789012345678"', text)
        self.assertNotIn('fake-discord-token', text)
        with tempfile.TemporaryDirectory() as raw:
            written = write_couple(answers, Path(raw), allow_plaintext=True)
            self.assertTrue(Path(written['instance']).is_file())

    def test_discord_without_ids_refuses(self) -> None:
        answers = _answers(features={'discord': True})
        answers['secrets']['discord_bot_token'] = 'fake-discord-token'
        with self.assertRaises(InstanceError) as ctx:
            render_toml(answers)
        self.assertIn('discord.guild_id', str(ctx.exception))

    def test_toml_has_no_secrets_or_live_markers(self) -> None:
        text = render_toml(_answers())
        self.assertIn('instance_id = "alice-laptop"', text)
        self.assertNotIn('openrouter_api_key', text)
        self.assertNotIn('test-openrouter', text)
        for marker in LIVE_SENTINELS:
            self.assertNotIn(marker, text)

    def test_full_defaults_without_tokens_refuse(self) -> None:
        answers = default_answers()
        answers['discord'] = {
            key: '123456789012345678' for key in answers['discord']
        }
        answers['mailbox']['login'] = 'serge@example.net'
        answers['secrets'] = {'openrouter_api_key': 'test-openrouter'}
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            with self.assertRaises(WizardError) as ctx:
                write_couple(answers, dest, allow_plaintext=True)
            self.assertIn('secrets incomplete', str(ctx.exception))
            self.assertEqual(list(dest.iterdir()), [])

    def test_incomplete_stripe_refuses_and_writes_nothing(self) -> None:
        answers = _answers()
        answers['features']['stripe'] = True
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            with self.assertRaises(WizardError):
                write_couple(answers, dest, allow_plaintext=True)
            self.assertEqual(list(dest.iterdir()), [])

    def test_plaintext_couple_loads(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            written = write_couple(_answers(), dest, allow_plaintext=True)
            toml_path = Path(written['instance'])
            loaded = load_instance(toml_path)
            toml_text = toml_path.read_text(encoding='utf-8')
        self.assertEqual(loaded['instance_id'], 'alice-laptop')
        self.assertFalse(loaded['secret_values_included'])
        self.assertNotIn('test-openrouter', toml_text)

    def test_also_mandate_writes_sandbox_file(self) -> None:
        answers = _answers()
        answers['mandate'] = {
            'policy_owner': 'alice',
            'email': 'alice@example.com',
        }
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            mandate_out = dest / 'mandate.yaml'
            written = write_couple(
                answers,
                dest,
                allow_plaintext=True,
                also_mandate=True,
                mandate_out=mandate_out,
            )
            loaded = yaml.safe_load(
                Path(written['mandate']).read_text(encoding='utf-8')
            )
            validate_mandate(loaded)
            text = mandate_out.read_text(encoding='utf-8')
        self.assertEqual(loaded['policy_owner'], 'alice')
        for marker in LIVE_SENTINELS:
            self.assertNotIn(marker, text)

    def test_cli_writes_couple(self) -> None:
        script = ROOT / 'scripts' / 'serge-instance-wizard.py'
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw)
            answers = dest / 'answers.json'
            answers.write_text(json.dumps(_answers()), encoding='utf-8')
            import subprocess

            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    '--answers',
                    str(answers),
                    '--out-dir',
                    str(dest),
                    '--allow-plaintext-secrets',
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue((dest / 'serge.instance.toml').is_file())
            self.assertTrue((dest / 'serge.secrets').is_file())
            mode = oct((dest / 'serge.secrets').stat().st_mode & 0o777)
            self.assertEqual(mode, '0o600')

    def test_render_dotenv_marks_and_escapes(self) -> None:
        blob = 'ALPHA=un\nBETA=deux'
        text = render_dotenv({'plain': 'tok', 'gog_env': blob})
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith('# serge-sidecar v2'))
        self.assertIn('gog_env=ALPHA=un\\nBETA=deux', lines)
        self.assertIn('plain=tok', lines)

    def test_gmail_couple_round_trip_multiline(self) -> None:
        answers = _answers(features={'gmail': True})
        blob = 'ALPHA=un\nBETA=deux\nGAMMA=trois'
        answers['secrets'] = {
            'openrouter_api_key': 'test-openrouter',
            'gog_env': blob,
        }
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / 'couple'
            written = write_couple(answers, dest, allow_plaintext=True)
            back = load_secret_map(Path(written['secrets']))
            self.assertEqual(back['gog_env'], blob)
            toml = Path(written['instance']).read_text(encoding='utf-8')
            self.assertNotIn('ALPHA=un', toml)

    def test_mailbox_section_renders_and_round_trip(self) -> None:
        answers = _answers(features={'mailbox': True})
        answers['mailbox']['login'] = 'serge@example.net'
        answers['secrets'] = {
            'openrouter_api_key': 'test-openrouter',
            'mailbox_password': 'pw-fake-2',
        }
        text = render_toml(answers)
        self.assertIn('[mailbox]', text)
        self.assertIn('preset = "infomaniak"', text)
        self.assertIn('login = "serge@example.net"', text)
        self.assertNotIn('pw-fake-2', text)
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / 'couple'
            written = write_couple(answers, dest, allow_plaintext=True)
            back = load_secret_map(Path(written['secrets']))
            self.assertEqual(back['mailbox_password'], 'pw-fake-2')

    def test_mailbox_incomplete_refuses(self) -> None:
        missing_secret = _answers(features={'mailbox': True})
        missing_secret['mailbox']['login'] = 'serge@example.net'
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(WizardError):
                write_couple(missing_secret, Path(raw) / 'c1')
        missing_login = _answers(features={'mailbox': True})
        missing_login['secrets'] = {
            'openrouter_api_key': 'test-openrouter',
            'mailbox_password': 'pw-fake-2',
        }
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaises(WizardError):
                write_couple(missing_login, Path(raw) / 'c2')


def _load_interactive_wizard():
    spec = importlib.util.spec_from_file_location(
        'serge_instance_wizard',
        str(ROOT / 'scripts' / 'serge-instance-wizard.py'),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class InteractiveWizardTests(unittest.TestCase):
    def test_multiline_secret_reads_until_blank(self) -> None:
        wizard = _load_interactive_wizard()
        with mock.patch.object(
            wizard.getpass, 'getpass', side_effect=['L1', 'L2', '']
        ):
            self.assertEqual(wizard._read_multiline_secret('Blob'), 'L1\nL2')


if __name__ == '__main__':
    unittest.main()
