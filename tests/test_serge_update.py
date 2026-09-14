#!/usr/bin/env python3
"""Update overlay : code neuf, canon et state intacts."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.builder.guards import BuilderError  # noqa: E402
from kit.update import update_instance  # noqa: E402


def _toml(home: Path, system_root: Path) -> str:
    return (
        'schema_version = 1\n'
        'instance_id = "alice-laptop"\n'
        'mode = "sandbox"\n'
        '[identity]\n'
        'hostname = "localhost"\n'
        '[paths]\n'
        f'home = "{home}"\n'
        f'system_root = "{system_root}"\n'
        f'policy = "{home}/.config/serge/mandate.yaml"\n'
        f'config_root = "{home}/.config/serge"\n'
        '[features]\n'
        'ingress = false\n'
        'stripe = false\n'
        'voice = false\n'
        'metagrok = false\n'
        'gmail = false\n'
        'mailbox = false\n'
        'discord = false\n'
        'owner_ui = false\n'
        'payments_live = false\n'
        'phone_sms = false\n'
        'phone_voice = false\n'
        '[llm]\n'
        'provider = "openrouter"\n'
    )


def _git_seed(path: Path, body: str = 'hello\n') -> str:
    path.mkdir(parents=True)
    (path / 'README').write_text(body, encoding='utf-8')
    (path / 'scripts').mkdir()
    (path / 'scripts/marker.txt').write_text('new\n', encoding='utf-8')
    subprocess.run(['git', 'init'], cwd=path, check=True, capture_output=True)
    subprocess.run(
        ['git', 'add', '.'], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        [
            'git',
            '-c',
            'user.email=update@example.com',
            '-c',
            'user.name=Update',
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


class SergeUpdateTests(unittest.TestCase):
    def test_overlay_keeps_state_and_skips_empty_root(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _git_seed(source, 'v2\n')
            dest = tmp / 'dest'
            dest.mkdir()
            (dest / 'state').mkdir()
            (dest / 'state/serge.db').write_text('CANON\n', encoding='utf-8')
            (dest / 'queue/pending').mkdir(parents=True)
            (dest / 'queue/pending/old.json').write_text(
                '{}\n', encoding='utf-8'
            )
            (dest / 'old.txt').write_text('stale\n', encoding='utf-8')
            home = tmp / 'home'
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml(home, dest), encoding='utf-8')
            units = home / '.config/systemd/user'
            receipt = update_instance(
                instance_file=instance,
                source_repo=source,
                git_sha=sha,
                kit_root=ROOT,
                systemd_user_dir=units,
            )
            self.assertEqual(receipt['status'], 'updated')
            self.assertFalse(receipt['canon_recreated'])
            self.assertEqual((dest / 'state/serge.db').read_text(), 'CANON\n')
            self.assertTrue((dest / 'queue/pending/old.json').is_file())
            self.assertEqual((dest / 'README').read_text(), 'v2\n')
            self.assertEqual(
                (dest / 'scripts/marker.txt').read_text(), 'new\n'
            )
            self.assertTrue((units / 'serge-pipeline.timer').is_file())
            empty = tmp / 'empty'
            instance2 = tmp / 'empty.toml'
            instance2.write_text(_toml(home, empty), encoding='utf-8')
            with self.assertRaises(BuilderError):
                update_instance(
                    instance_file=instance2,
                    source_repo=source,
                    git_sha=sha,
                    kit_root=ROOT,
                    systemd_user_dir=units,
                )

    def test_live_paths_need_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _git_seed(source)
            dest = tmp / 'dest'
            dest.mkdir()
            (dest / 'keep').write_text('x\n', encoding='utf-8')
            home = tmp / 'home'
            instance = tmp / 'serge.instance.toml'
            instance.write_text(
                _toml(home, dest)
                .replace(
                    'instance_id = "alice-laptop"',
                    'instance_id = "julien-vps"',
                )
                .replace(
                    f'system_root = "{dest}"',
                    'system_root = "/home/serge/serge-system"',
                ),
                encoding='utf-8',
            )
            with self.assertRaises(BuilderError):
                update_instance(
                    instance_file=instance,
                    source_repo=source,
                    git_sha=sha,
                    kit_root=ROOT,
                    systemd_user_dir=tmp / 'units',
                )

    def test_phone_voice_rewrites_asterisk_conf_not_pjsip(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            source = tmp / 'source'
            sha = _git_seed(source)
            dest = tmp / 'dest'
            dest.mkdir()
            (dest / 'keep').write_text('x\n', encoding='utf-8')
            home = tmp / 'home'
            config = home / '.config/serge/asterisk'
            config.mkdir(parents=True)
            (config / 'asterisk.conf').write_text(
                '[directories](!)\nastdatadir => /wrong\n',
                encoding='utf-8',
            )
            (config / 'pjsip.conf').write_text('SECRET\n', encoding='utf-8')
            text = (
                _toml(home, dest)
                .replace('ingress = false\n', 'ingress = true\n')
                .replace('voice = false\n', 'voice = true\n')
                .replace('phone_sms = false\n', 'phone_sms = true\n')
                .replace('phone_voice = false\n', 'phone_voice = true\n')
                .replace(
                    'hostname = "localhost"\n',
                    'hostname = "localhost"\n'
                    'public_hostname = "serge-kit-test.example.net"\n'
                    'phone_sms_number = "+33600000001"\n'
                    'phone_voice_number = "+33162000001"\n',
                )
                + '\n[phone_voice]\n'
                'sip_server = "sip.example.com"\n'
                'sip_username = "trunk"\n'
                'sip_transport = "tls"\n'
                'max_calls_per_day = 50\n'
            )
            instance = tmp / 'serge.instance.toml'
            instance.write_text(text, encoding='utf-8')
            receipt = update_instance(
                instance_file=instance,
                source_repo=source,
                git_sha=sha,
                kit_root=ROOT,
                systemd_user_dir=home / '.config/systemd/user',
            )
            conf = (config / 'asterisk.conf').read_text(encoding='utf-8')
            self.assertEqual(receipt['asterisk_conf_written'], 'asterisk.conf')
            self.assertIn('[directories]', conf)
            self.assertNotIn('[directories](!)', conf)
            self.assertIn('astdatadir => /var/lib/asterisk', conf)
            self.assertEqual(
                (config / 'pjsip.conf').read_text(encoding='utf-8'),
                'SECRET\n',
            )


if __name__ == '__main__':
    unittest.main()
