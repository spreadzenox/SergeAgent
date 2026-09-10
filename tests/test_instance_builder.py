#!/usr/bin/env python3
"""Builder instantiates a virgin tree; never writes the live VPS."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'orchestrator'))

from kit.builder import (  # noqa: E402
    BuilderError,
    build_instance,
    secret_destination,
    secret_file_body,
)
from kit.instance_wizard import (  # noqa: E402
    default_answers,
    empty_features,
    write_couple,
)
from kit.mandate import build_mandate, render_yaml  # noqa: E402

LIVE_SENTINELS = (
    '/home/serge/serge-system',
    'live-owner.example.net',
    'live-owner@example.com',
    '999988887777666001',
)


def _answers(base: Path, **feature_overrides):
    home = base / 'home'
    answers = default_answers()
    answers['instance_id'] = 'alice-laptop'
    answers['paths'] = {
        'home': str(home),
        'system_root': str(base / 'dest'),
        'policy': str(home / '.config/serge/mandate.yaml'),
        'config_root': str(home / '.config/serge'),
        'secrets_age': 'serge.secrets',
    }
    answers['features'] = empty_features()
    answers['features'].update(feature_overrides)
    answers['secrets'] = {'openrouter_api_key': 'test-openrouter'}
    if feature_overrides.get('stripe'):
        answers['secrets']['stripe_test_key'] = 'sk_test_dummy'
        answers['secrets']['stripe_webhook_test_key'] = 'whsec_dummy'
    answers['mandate'] = {
        'policy_owner': 'alice',
        'email': 'alice@example.com',
    }
    return answers


def _write_mandate(path: Path, **overrides) -> Path:
    answers = {
        'policy_owner': 'alice',
        'email': 'alice@example.com',
        'mode': 'sandbox',
    }
    answers.update(overrides)
    path.write_text(render_yaml(build_mandate(answers)), encoding='utf-8')
    return path


STUB_WEB_INGRESS = '''\
"""Minimal test double: upsert one route + default tenant, no Caddy."""
import argparse
import json
import os
import tomllib
from pathlib import Path

root = Path(os.environ['SERGE_SYSTEM_ROOT'])
args = argparse.ArgumentParser()
args.add_argument('command')
args.add_argument('--hostname', default='')
args.add_argument('--upstream', default='')
args.add_argument('--venture-id', default='')
args.add_argument('--health-url', default='')
args.add_argument('--allow-unhealthy', action='store_true')
ns = args.parse_args()
assert ns.command == 'upsert', ns.command
data = tomllib.loads(Path(os.environ['SERGE_INSTANCE_FILE']).read_text())
public = str((data.get('identity') or {}).get('public_hostname') or '')
routes = [
    {
        'hostname': public,
        'upstream': '127.0.0.1:8790',
        'venture_id': 'serge-owner-mission-control',
    },
    {
        'hostname': ns.hostname,
        'upstream': ns.upstream,
        'venture_id': ns.venture_id,
    },
]
dest = root / 'state/web-ingress/inventory.json'
dest.parent.mkdir(parents=True, exist_ok=True)
dest.write_text(json.dumps({'routes': routes}), encoding='utf-8')
print(json.dumps({'status': 'ok'}))
'''


def _seed_repo(path: Path, *, with_ingress: bool = False) -> str:
    path.mkdir(parents=True)
    (path / 'README').write_text('virgin seed\n', encoding='utf-8')
    if with_ingress:
        vendor = path / 'orchestrator'
        vendor.mkdir(parents=True)
        (vendor / 'web_ingress.py').write_text(STUB_WEB_INGRESS)
    poison = path / 'state'
    poison.mkdir()
    (poison / 'poison.db').write_text('JULIEN-MEMORY\n', encoding='utf-8')
    leftover = path / 'queue/pending'
    leftover.mkdir(parents=True)
    (leftover / 'leftover.json').write_text('{}\n', encoding='utf-8')
    subprocess.run(['git', 'init'], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ['git', 'add', '.'], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        [
            'git',
            '-c',
            'user.email=builder@example.com',
            '-c',
            'user.name=Builder',
            'commit',
            '-m',
            'seed',
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ['git', 'rev-parse', 'HEAD'],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    return sha.stdout.strip()


class InstanceBuilderTests(unittest.TestCase):
    def test_secret_destination_leaves_live_catalogue(self) -> None:
        dest = secret_destination(
            '/home/serge/.config/serge/secrets/openrouter-api-key',
            home=Path('/tmp/alice'),
            config_root=Path('/tmp/alice/.config/serge'),
        )
        self.assertEqual(
            dest, Path('/tmp/alice/.config/serge/secrets/openrouter-api-key')
        )
        gog = secret_destination(
            '/home/serge/.config/openclaw/gog.env',
            home=Path('/tmp/alice'),
            config_root=Path('/tmp/alice/.config/serge'),
        )
        self.assertEqual(gog, Path('/tmp/alice/.config/openclaw/gog.env'))

    def test_refuses_live_system_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            answers = _answers(tmp)
            answers['paths']['system_root'] = '/home/serge/serge-system'
            couple = tmp / 'couple'
            write_couple(answers, couple, allow_plaintext=True)
            mandate = _write_mandate(tmp / 'mandate.yaml')
            with self.assertRaises(BuilderError):
                build_instance(
                    instance_file=couple / 'serge.instance.toml',
                    mandate=mandate,
                    source_repo=tmp,
                    kit_root=ROOT,
                )

    def test_refuses_live_mandate_for_other_instance(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            couple = tmp / 'couple'
            write_couple(_answers(tmp), couple, allow_plaintext=True)
            mandate = tmp / 'mandate.yaml'
            mandate.write_text(
                'version: 2\nidentity:\n  email: live-owner@example.com\n',
                encoding='utf-8',
            )
            with mock.patch.dict(
                os.environ,
                {'SERGE_LIVE_MANDATE_MARKERS': 'live-owner@example.com'},
            ):
                with self.assertRaises(BuilderError):
                    build_instance(
                        instance_file=couple / 'serge.instance.toml',
                        mandate=mandate,
                        source_repo=tmp,
                        kit_root=ROOT,
                    )

    def test_refuses_metagrok_without_host_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            couple = tmp / 'couple'
            write_couple(
                _answers(tmp, metagrok=True), couple, allow_plaintext=True
            )
            mandate = _write_mandate(tmp / 'mandate.yaml')
            with self.assertRaises(BuilderError):
                build_instance(
                    instance_file=couple / 'serge.instance.toml',
                    mandate=mandate,
                    source_repo=tmp,
                    kit_root=ROOT,
                )

    def test_sandbox_smoke_archive_empty_canon_units(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _seed_repo(source)
            couple = tmp / 'couple'
            write_couple(
                _answers(tmp, stripe=True), couple, allow_plaintext=True
            )
            mandate = _write_mandate(tmp / 'mandate.yaml')
            receipt = build_instance(
                instance_file=couple / 'serge.instance.toml',
                mandate=mandate,
                source_repo=source,
                git_sha=sha,
                kit_root=ROOT,
                uid=1000,
            )
            dest = Path(receipt['system_root'])
            self.assertTrue((dest / 'README').is_file())
            self.assertFalse((dest / 'state/poison.db').exists())
            self.assertFalse((dest / 'queue/pending/leftover.json').exists())
            db = dest / 'state/serge.db'
            self.assertTrue(db.is_file())
            self.assertEqual(oct(db.stat().st_mode & 0o777), '0o600')
            connection = sqlite3.connect(db)
            try:
                tables = connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            finally:
                connection.close()
            self.assertEqual(tables, [])
            secret = (
                Path(receipt['instance_file']).parent
                / 'secrets/openrouter-api-key'
            )
            self.assertTrue(secret.is_file())
            self.assertEqual(oct(secret.stat().st_mode & 0o777), '0o600')
            self.assertEqual(
                secret.read_text(encoding='utf-8').strip(), 'test-openrouter'
            )
            self.assertNotIn('/home/serge', str(secret))
            stripe = secret.parent / 'stripe-test.key'
            self.assertTrue(stripe.is_file())
            pipeline = tmp / 'home/.config/systemd/user/serge-pipeline.service'
            text = pipeline.read_text(encoding='utf-8')
            self.assertIn('SERGE_INSTANCE_FILE=', text)
            self.assertIn(
                str(tmp / 'home/.config/serge/serge.instance.toml'), text
            )
            self.assertNotIn('Wants=openclaw-gateway.service', text)
            for marker in LIVE_SENTINELS:
                self.assertNotIn(marker, text)
            self.assertEqual(receipt['units_enabled'], [])
            self.assertEqual(
                receipt['units_enable_skipped'],
                'systemd_user_dir is not this user session',
            )
            self.assertFalse(receipt['secret_values_included'])
            self.assertNotIn('test-openrouter', json.dumps(receipt))
            self.assertTrue((dest / 'state/instance-build.json').is_file())

    def test_phone_full_stack_builds_units_asterisk_and_sms_route(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _seed_repo(source, with_ingress=True)
            answers = _answers(
                tmp,
                ingress=True,
                voice=True,
                owner_ui=True,
                phone_sms=True,
                phone_voice=True,
            )
            answers['identity'] = {
                'hostname': 'phone-test',
                'public_hostname': 'serge-kit-test.example.net',
                'phone_sms_number': '+33600000001',
                'phone_voice_number': '+33162000001',
            }
            answers['phone_voice'] = {
                'sip_server': 'sip.example.com',
                'sip_username': 'trunk',
                'sip_transport': 'tls',
                'max_calls_per_day': 50,
            }
            answers['secrets'] = {
                'openrouter_api_key': 'test-openrouter',
                'xai_api_key': 'xai-dummy',
                'cloudflare_infra_key': 'infra',
                'cloudflare_registrar_key': 'registrar',
                'owner_dashboard_token': 'owner-token',
                'sms_gateway_token': 'sms-secret-value',
                'sip_trunk_password': 'sip-secret-value',
            }
            couple = tmp / 'couple'
            write_couple(answers, couple, allow_plaintext=True)
            mandate = _write_mandate(tmp / 'mandate.yaml')
            receipt = build_instance(
                instance_file=couple / 'serge.instance.toml',
                mandate=mandate,
                source_repo=source,
                git_sha=sha,
                kit_root=ROOT,
                uid=1000,
            )
            dest = Path(receipt['system_root'])
            config = tmp / 'home/.config/serge'
            units_dir = tmp / 'home/.config/systemd/user'
            for unit in (
                'serge-sms-receiver.service',
                'serge-asterisk.service',
                'serge-voice-bridge.service',
            ):
                self.assertTrue((units_dir / unit).is_file(), unit)
                self.assertIn(unit, receipt['units_enable'])
            sms_unit = (units_dir / 'serge-sms-receiver.service').read_text()
            self.assertIn('serge/sms/receiver.py serve', sms_unit)
            asterisk_dir = config / 'asterisk'
            for name in (
                'asterisk.conf',
                'pjsip.conf',
                'extensions.conf',
                'rtp.conf',
                'modules.conf',
            ):
                self.assertTrue((asterisk_dir / name).is_file(), name)
            pjsip = asterisk_dir / 'pjsip.conf'
            self.assertEqual(oct(pjsip.stat().st_mode & 0o777), '0o600')
            self.assertIn(
                'sip-secret-value', pjsip.read_text(encoding='utf-8')
            )
            extensions = (asterisk_dir / 'extensions.conf').read_text()
            self.assertIn('+33162000001', extensions)
            self.assertIn('serge-campaign', extensions)
            token = config / 'secrets/sms-gateway.token'
            self.assertEqual(
                token.read_text(encoding='utf-8').strip(),
                'sms-secret-value',
            )
            self.assertEqual(oct(token.stat().st_mode & 0o777), '0o600')
            sip_secret = config / 'secrets/sip-trunk-password'
            self.assertTrue(sip_secret.is_file())
            inventory = json.loads(
                (dest / 'state/web-ingress/inventory.json').read_text()
            )
            hosts = [route['hostname'] for route in inventory['routes']]
            self.assertIn('sms.serge-kit-test.example.net', hosts)
            self.assertIn('serge-kit-test.example.net', hosts)
            self.assertNotIn('live-owner.example.net', hosts)
            sms_route = [
                route
                for route in inventory['routes']
                if route['hostname'] == 'sms.serge-kit-test.example.net'
            ][0]
            self.assertEqual(sms_route['upstream'], '127.0.0.1:8787')
            self.assertEqual(
                receipt['sms_route'],
                'sms.serge-kit-test.example.net',
            )
            self.assertEqual(
                sorted(receipt['asterisk_files_written']),
                [
                    'asterisk.conf',
                    'extensions.conf',
                    'modules.conf',
                    'pjsip.conf',
                    'rtp.conf',
                ],
            )
            blob = json.dumps(receipt)
            self.assertNotIn('sip-secret-value', blob)
            self.assertNotIn('sms-secret-value', blob)
            self.assertTrue((config / 'voice/README.txt').is_file())
            for marker in LIVE_SENTINELS:
                self.assertNotIn(marker, blob)

    def test_cli_builds_without_enable(self) -> None:
        script = ROOT / 'scripts/serge-builder.py'
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _seed_repo(source)
            couple = tmp / 'couple'
            write_couple(_answers(tmp), couple, allow_plaintext=True)
            mandate = _write_mandate(tmp / 'mandate.yaml')
            completed = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    '--instance-file',
                    str(couple / 'serge.instance.toml'),
                    '--mandate',
                    str(mandate),
                    '--source-repo',
                    str(source),
                    '--git-sha',
                    sha,
                    '--no-enable-units',
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload['instance_id'], 'alice-laptop')
            self.assertEqual(payload['units_enabled'], [])

    def test_gmail_build_injects_multiline_gog_env(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _seed_repo(source)
            answers = _answers(tmp, gmail=True)
            blob = 'ALPHA=un\nBETA=deux\nGAMMA=trois'
            answers['secrets']['gog_env'] = blob
            couple = tmp / 'couple'
            write_couple(answers, couple, allow_plaintext=True)
            mandate = _write_mandate(tmp / 'mandate.yaml')
            receipt = build_instance(
                instance_file=couple / 'serge.instance.toml',
                mandate=mandate,
                source_repo=source,
                git_sha=sha,
                kit_root=ROOT,
                uid=1000,
            )
            gog = tmp / 'home/.config/openclaw/gog.env'
            self.assertTrue(gog.is_file())
            self.assertEqual(gog.read_text(encoding='utf-8'), blob + '\n')
            mode = oct(gog.stat().st_mode & 0o777)
            self.assertEqual(mode, '0o600')
            self.assertIn('gog_env', receipt['secret_names_written'])

    def test_secret_file_body_prefixes_only_monoline(self) -> None:
        item = {'name': 'gog_env', 'maps_to': 'x/openclaw/gog.env'}
        self.assertEqual(
            secret_file_body('gog_env', 'ALPHA=un', item),
            'GOG_ENV=ALPHA=un\n',
        )
        self.assertEqual(
            secret_file_body('gog_env', 'ALPHA=un\nBETA=deux', item),
            'ALPHA=un\nBETA=deux\n',
        )

    def test_mailbox_build_injects_password_and_backend(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _seed_repo(source)
            answers = _answers(tmp, mailbox=True)
            answers['mailbox']['login'] = 'serge@example.net'
            answers['secrets']['mailbox_password'] = 'pw-fake-2'
            couple = tmp / 'couple'
            write_couple(answers, couple, allow_plaintext=True)
            mandate = _write_mandate(tmp / 'mandate.yaml')
            receipt = build_instance(
                instance_file=couple / 'serge.instance.toml',
                mandate=mandate,
                source_repo=source,
                git_sha=sha,
                kit_root=ROOT,
                uid=1000,
            )
            secret = tmp / 'home/.config/serge/secrets/mailbox-password'
            self.assertTrue(secret.is_file())
            self.assertEqual(secret.read_text(encoding='utf-8'), 'pw-fake-2\n')
            mode = oct(secret.stat().st_mode & 0o777)
            self.assertEqual(mode, '0o600')
            unit = tmp / 'home/.config/systemd/user/serge-pipeline.service'
            self.assertIn(
                'Environment=SERGE_EMAIL_BACKEND=smtp',
                unit.read_text(encoding='utf-8'),
            )
            self.assertIn('mailbox_password', receipt['secret_names_written'])


if __name__ == '__main__':
    unittest.main()
