#!/usr/bin/env python3
"""Instance file loader + boot gate. No secret values leaked."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.instance_file import (  # noqa: E402
    InstanceError,
    apply_env,
    command_requires_instance,
    default_features,
    escape_sidecar_value,
    load_instance,
    multiline_secret_names,
    parse_dotenv,
    require_instance,
    required_secret_names,
    validate_toml,
)

MINIMAL_TOML = """
schema_version = 1
instance_id = "example-sandbox"
mode = "sandbox"

[identity]
hostname = "localhost"
{identity_extra}
[paths]
home = "/home/owner"
system_root = "{system_root}"
policy = "/home/owner/.config/serge/mandate.yaml"
secrets_age = "serge.secrets.age"

[features]
ingress = {ingress}
stripe = {stripe}
voice = {voice}
metagrok = false
gmail = false
discord = {discord}
openclaw = false
owner_ui = false
payments_live = false
phone_sms = {phone_sms}
phone_voice = {phone_voice}

[llm]
provider = "openrouter"

[phone_voice]
{phone_extra}
{discord_extra}"""


class InstanceFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = {
            key: os.environ.get(key)
            for key in (
                'SERGE_INSTANCE_FILE',
                'SERGE_SECRETS_DOTENV',
                'SERGE_AGE_IDENTITY',
                'SERGE_INSTANCE_ALLOW_PLAINTEXT_SECRETS',
                'SERGE_HOME',
                'SERGE_SYSTEM_ROOT',
                'SERGE_MANDATE_PATH',
                'SERGE_POLICY_PATH',
            )
        }

    def tearDown(self) -> None:
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _write_pair(
        self,
        tmp: Path,
        *,
        secrets: str = 'openrouter_api_key=test-openrouter\n',
        stripe: bool = False,
        voice: bool = False,
        ingress: bool = False,
        phone_sms: bool = False,
        phone_voice: bool = False,
        discord: bool = False,
        identity_extra: str = '',
        phone_extra: str = '',
        discord_extra: str = '',
    ) -> Path:
        toml_path = tmp / 'serge.instance.toml'
        toml_path.write_text(
            MINIMAL_TOML.format(
                system_root=ROOT,
                ingress='true' if ingress else 'false',
                stripe='true' if stripe else 'false',
                voice='true' if voice else 'false',
                phone_sms='true' if phone_sms else 'false',
                phone_voice='true' if phone_voice else 'false',
                discord='true' if discord else 'false',
                identity_extra=identity_extra,
                phone_extra=phone_extra,
                discord_extra=discord_extra,
            ),
            encoding='utf-8',
        )
        dotenv = tmp / 'secrets.env'
        dotenv.write_text(secrets, encoding='utf-8')
        os.environ['SERGE_SECRETS_DOTENV'] = str(dotenv)
        return toml_path

    def test_missing_env_refuses_boot(self) -> None:
        os.environ.pop('SERGE_INSTANCE_FILE', None)
        with self.assertRaises(InstanceError) as ctx:
            require_instance()
        self.assertIn('SERGE_INSTANCE_FILE', str(ctx.exception))

    def test_missing_file_refuses_boot(self) -> None:
        os.environ['SERGE_INSTANCE_FILE'] = '/tmp/serge-does-not-exist.toml'
        with self.assertRaises(InstanceError):
            require_instance()

    def test_sandbox_with_openrouter_only_boots(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(tmp)
            os.environ['SERGE_INSTANCE_FILE'] = str(toml_path)
            loaded = require_instance()
        self.assertEqual(loaded['instance_id'], 'example-sandbox')
        self.assertEqual(loaded['mode'], 'sandbox')
        self.assertFalse(loaded['features']['stripe'])
        self.assertFalse(loaded['secret_values_included'])
        self.assertNotIn('secret_values', loaded)
        self.assertEqual(os.environ['SERGE_HOME'], '/home/owner')
        self.assertEqual(os.environ['SERGE_SYSTEM_ROOT'], str(ROOT))
        self.assertEqual(
            os.environ['SERGE_MANDATE_PATH'],
            '/home/owner/.config/serge/mandate.yaml',
        )
        blob = str(loaded)
        self.assertNotIn('test-openrouter', blob)

    def test_stripe_on_without_keys_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(tmp, stripe=True)
            os.environ['SERGE_INSTANCE_FILE'] = str(toml_path)
            with self.assertRaises(InstanceError) as ctx:
                require_instance()
        self.assertIn('stripe_test_key', str(ctx.exception))

    def test_discord_on_without_ids_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(tmp, discord=True)
            os.environ['SERGE_INSTANCE_FILE'] = str(toml_path)
            with self.assertRaises(InstanceError) as ctx:
                require_instance()
        self.assertIn('discord.guild_id', str(ctx.exception))

    def test_discord_on_without_token_refuses(self) -> None:
        extra = (
            '[discord]\n'
            'guild_id = "123456789012345678"\n'
            'forum_channel_id = "123456789012345679"\n'
            'urgent_channel_id = "123456789012345680"\n'
            'digest_channel_id = "123456789012345681"\n'
            'owner_user_id = "999988887777666555"\n'
        )
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(
                tmp, discord=True, discord_extra=extra
            )
            os.environ['SERGE_INSTANCE_FILE'] = str(toml_path)
            with self.assertRaises(InstanceError) as ctx:
                require_instance()
        self.assertIn('discord_bot_token', str(ctx.exception))

    def test_discord_on_with_ids_and_token_boots(self) -> None:
        extra = (
            '[discord]\n'
            'guild_id = "123456789012345678"\n'
            'forum_channel_id = "123456789012345679"\n'
            'urgent_channel_id = "123456789012345680"\n'
            'digest_channel_id = "123456789012345681"\n'
            'owner_user_id = "999988887777666555"\n'
        )
        secrets = (
            'openrouter_api_key=test-openrouter\n'
            'discord_bot_token=fake-discord-token\n'
        )
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(
                tmp, secrets=secrets, discord=True, discord_extra=extra
            )
            os.environ['SERGE_INSTANCE_FILE'] = str(toml_path)
            loaded = require_instance()
        self.assertTrue(loaded['features']['discord'])
        self.assertIn('discord_bot_token', loaded['secret_names_present'])

    def test_stripe_on_with_keys_boots(self) -> None:
        secrets = (
            'openrouter_api_key=test-openrouter\n'
            'stripe_test_key=sk_test_dummy\n'
            'stripe_webhook_test_key=whsec_dummy\n'
        )
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(tmp, secrets=secrets, stripe=True)
            os.environ['SERGE_INSTANCE_FILE'] = str(toml_path)
            loaded = require_instance()
        self.assertTrue(loaded['features']['stripe'])
        self.assertIn('stripe_test_key', loaded['secret_names_present'])

    def test_voice_accepts_xai_or_openai(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(
                tmp,
                secrets='openrouter_api_key=k\nxai_api_key=xai-dummy\n',
                voice=True,
            )
            loaded = load_instance(toml_path)
        self.assertIn('xai_api_key', loaded['secret_names_present'])

        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(
                tmp,
                secrets='openrouter_api_key=k\nopenai_api_key=oai-dummy\n',
                voice=True,
            )
            loaded = load_instance(toml_path)
        self.assertIn('openai_api_key', loaded['secret_names_present'])

    def test_voice_without_either_key_refuses(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(tmp, voice=True)
            with self.assertRaises(InstanceError) as ctx:
                load_instance(toml_path)
        self.assertIn('xai_api_key', str(ctx.exception))

    def test_validate_toml_rejects_bad_mode(self) -> None:
        with self.assertRaises(InstanceError):
            validate_toml(
                {
                    'schema_version': 1,
                    'instance_id': 'x',
                    'mode': 'prod',
                    'paths': {
                        'home': '/h',
                        'system_root': '/s',
                        'policy': '/p',
                    },
                }
            )

    def test_default_features_are_all_or_nothing(self) -> None:
        features = default_features()
        self.assertTrue(features['owner_ui'])
        self.assertTrue(features['ingress'])
        self.assertTrue(features['openclaw'])
        self.assertTrue(features['payments_live'])
        self.assertTrue(features['phone_sms'])
        self.assertTrue(features['phone_voice'])
        self.assertFalse(features['metagrok'])

    def test_phone_voice_requires_sms_and_voice(self) -> None:
        base = {
            'schema_version': 1,
            'instance_id': 'x',
            'mode': 'sandbox',
            'paths': {'home': '/h', 'system_root': '/s', 'policy': '/p'},
        }
        with self.assertRaises(InstanceError) as ctx:
            validate_toml(
                {
                    **base,
                    'features': {'phone_voice': True, 'phone_sms': False},
                }
            )
        self.assertIn('phone_sms', str(ctx.exception))
        with self.assertRaises(InstanceError) as ctx:
            validate_toml(
                {
                    **base,
                    'identity': {
                        'public_hostname': 'example.net',
                        'phone_sms_number': '+33600000001',
                    },
                    'features': {
                        'ingress': True,
                        'phone_sms': True,
                        'phone_voice': True,
                        'voice': False,
                    },
                }
            )
        self.assertIn('voice', str(ctx.exception))

    def test_phone_sms_requires_ingress_hostname_and_number(self) -> None:
        base = {
            'schema_version': 1,
            'instance_id': 'x',
            'mode': 'sandbox',
            'paths': {'home': '/h', 'system_root': '/s', 'policy': '/p'},
            'features': {'phone_sms': True},
        }
        with self.assertRaises(InstanceError) as ctx:
            validate_toml(base)
        self.assertIn('ingress', str(ctx.exception))
        with self.assertRaises(InstanceError):
            validate_toml(
                {
                    **base,
                    'features': {'ingress': True, 'phone_sms': True},
                }
            )
        with self.assertRaises(InstanceError) as ctx:
            validate_toml(
                {
                    **base,
                    'identity': {'public_hostname': 'example.net'},
                    'features': {'ingress': True, 'phone_sms': True},
                }
            )
        self.assertIn('phone_sms_number', str(ctx.exception))
        with self.assertRaises(InstanceError):
            validate_toml(
                {
                    **base,
                    'identity': {
                        'public_hostname': 'example.net',
                        'phone_sms_number': 'not-a-number',
                    },
                    'features': {'ingress': True, 'phone_sms': True},
                }
            )

    def test_phone_voice_requires_sip_and_npv(self) -> None:
        base = {
            'schema_version': 1,
            'instance_id': 'x',
            'mode': 'sandbox',
            'paths': {'home': '/h', 'system_root': '/s', 'policy': '/p'},
            'identity': {
                'public_hostname': 'example.net',
                'phone_sms_number': '+33600000001',
            },
            'features': {
                'ingress': True,
                'voice': True,
                'phone_sms': True,
                'phone_voice': True,
            },
        }
        with self.assertRaises(InstanceError) as ctx:
            validate_toml(base)
        self.assertIn('phone_voice_number', str(ctx.exception))
        identity = dict(base['identity'])
        identity['phone_voice_number'] = '+33162000001'
        with self.assertRaises(InstanceError) as ctx:
            validate_toml({**base, 'identity': identity})
        self.assertIn('sip_server', str(ctx.exception))
        valid = validate_toml(
            {
                **base,
                'identity': identity,
                'phone_voice': {
                    'sip_server': 'sip.example.com',
                    'sip_username': 'trunk',
                    'sip_transport': 'tls',
                    'max_calls_per_day': 50,
                },
            }
        )
        self.assertEqual(valid['phone_voice']['sip_transport'], 'tls')

    def test_phone_sms_without_token_refuses(self) -> None:
        identity_extra = (
            'public_hostname = "example.net"\n'
            'phone_sms_number = "+33600000001"\n'
        )
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(
                tmp,
                ingress=True,
                phone_sms=True,
                identity_extra=identity_extra,
                secrets=(
                    'openrouter_api_key=k\n'
                    'cloudflare_infra_key=a\ncloudflare_registrar_key=b\n'
                ),
            )
            os.environ['SERGE_INSTANCE_FILE'] = str(toml_path)
            with self.assertRaises(InstanceError) as ctx:
                require_instance()
        self.assertIn('sms_gateway_token', str(ctx.exception))

    def test_phone_full_stack_with_keys_boots(self) -> None:
        identity_extra = (
            'public_hostname = "example.net"\n'
            'phone_sms_number = "+33600000001"\n'
            'phone_voice_number = "+33162000001"\n'
        )
        phone_extra = (
            'sip_server = "sip.example.com"\nsip_username = "trunk"\n'
        )
        secrets = (
            'openrouter_api_key=k\nxai_api_key=x\n'
            'cloudflare_infra_key=a\ncloudflare_registrar_key=b\n'
            'sms_gateway_token=t\nsip_trunk_password=p\n'
        )
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            toml_path = self._write_pair(
                tmp,
                ingress=True,
                voice=True,
                phone_sms=True,
                phone_voice=True,
                secrets=secrets,
                identity_extra=identity_extra,
                phone_extra=phone_extra,
            )
            loaded = load_instance(toml_path)
        self.assertIn('sms_gateway_token', loaded['secret_names_present'])
        self.assertIn('sip_trunk_password', loaded['secret_names_present'])
        self.assertEqual(
            loaded['phone_voice']['sip_server'],
            'sip.example.com',
        )

    def test_required_secrets_ignore_disabled_features(self) -> None:
        names = required_secret_names(
            {
                'ingress': False,
                'stripe': False,
                'voice': False,
                'metagrok': False,
                'gmail': False,
                'discord': False,
                'openclaw': False,
                'owner_ui': False,
                'payments_live': False,
            }
        )
        self.assertEqual(names, ['openrouter_api_key'])

    def test_apply_env_does_not_export_secrets(self) -> None:
        exported = apply_env(
            {
                'instance_file': '/tmp/serge.instance.toml',
                'paths': {
                    'home': '/home/owner',
                    'system_root': '/home/owner/serge-system',
                    'policy': '/tmp/mandate.yaml',
                },
            }
        )
        self.assertEqual(
            set(exported),
            {
                'SERGE_INSTANCE_FILE',
                'SERGE_HOME',
                'SERGE_SYSTEM_ROOT',
                'SERGE_MANDATE_PATH',
                'SERGE_POLICY_PATH',
            },
        )

    def test_sergectl_boot_commands_are_gated(self) -> None:
        for command in (
            'run-once',
            'doctor',
            'activate',
            'shadow-run',
            'live-preflight',
            'burn-in',
            'monitor',
        ):
            self.assertTrue(command_requires_instance(command))
        self.assertFalse(command_requires_instance('status'))
        self.assertFalse(command_requires_instance('kill'))

    def test_testing_defaults_when_absent(self) -> None:
        data = validate_toml(
            {
                'schema_version': 1,
                'instance_id': 'x',
                'mode': 'sandbox',
                'paths': {
                    'home': '/h',
                    'system_root': '/s',
                    'policy': '/p',
                },
            }
        )
        self.assertEqual(
            data['testing'],
            {
                'n_smoke_min': 30,
                'n_smoke_max': 50,
                'n_full_min': 150,
                'n_full_target': 200,
                'kill_max_positives': 1,
                'scale_min_positives': 5,
                'scale_min_meetings': 2,
                'extend_max': 1,
            },
        )

    def test_testing_invalid_ranges_refuse(self) -> None:
        base: dict[str, Any] = {
            'schema_version': 1,
            'instance_id': 'x',
            'mode': 'sandbox',
            'paths': {'home': '/h', 'system_root': '/s', 'policy': '/p'},
        }
        for testing in (
            {'n_smoke_min': 50, 'n_smoke_max': 30},
            {'n_full_min': 200, 'n_full_target': 150},
            {'kill_max_positives': 5, 'scale_min_positives': 5},
            {'extend_max': 0},
            {'n_smoke_min': 'beaucoup'},
        ):
            with self.assertRaises(InstanceError, msg=testing):
                validate_toml({**base, 'testing': testing})


class SidecarMultilineTests(unittest.TestCase):
    def test_escape_then_parse_restores_multiline(self) -> None:
        blob = 'ALPHA=un\nBETA=deux\nGAMMA=trois'
        # Marqueur en littéral : verrouille le contrat inter-versions.
        text = (
            '# serge-sidecar v2 (multiline \\n-escaped)\n'
            f'gog_env={escape_sidecar_value(blob)}\n'
            f'plain={escape_sidecar_value("a\\b")}\n'
            f'tricky={escape_sidecar_value("x\\ny")}\n'
        )
        back = parse_dotenv(text)
        self.assertEqual(back['gog_env'], blob)
        self.assertEqual(back['plain'], 'a\\b')
        self.assertEqual(back['tricky'], 'x\\ny')

    def test_parse_legacy_keeps_raw_text(self) -> None:
        back = parse_dotenv('k=v\nXKEY=\nodd=a\\nb\n')
        self.assertEqual(back, {'k': 'v', 'XKEY': '', 'odd': 'a\\nb'})

    def test_multiline_names_follow_feature(self) -> None:
        features = default_features()
        self.assertIn('gog_env', multiline_secret_names(features))
        features['gmail'] = False
        self.assertNotIn('gog_env', multiline_secret_names(features))


if __name__ == '__main__':
    unittest.main()
