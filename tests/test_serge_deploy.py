#!/usr/bin/env python3
"""Déploiement : install si racine vide, sinon update + restart des actives."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.builder.guards import BuilderError  # noqa: E402
from kit.deploy import deploy_instance  # noqa: E402


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


def _ok(*_args, **_kwargs):
    return subprocess.CompletedProcess(
        args=['systemctl'], returncode=0, stdout='', stderr=''
    )


class SergeDeployTests(unittest.TestCase):
    def test_empty_root_runs_install_then_enable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            dest = tmp / 'dest'
            home = tmp / 'home'
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml(home, dest), encoding='utf-8')
            mandate = tmp / 'mandate.yaml'
            mandate.write_text('schema_version: 1\n', encoding='utf-8')
            seen: list[list[str]] = []

            def runner(argv, **_kwargs):
                seen.append(list(argv))
                return _ok()

            receipt = deploy_instance(
                instance_file=instance,
                mandate=mandate,
                source_repo=ROOT,
                git_sha='HEAD',
                kit_root=ROOT,
                runner=runner,
                python=sys.executable,
            )
            self.assertEqual(receipt['status'], 'installed')
            self.assertTrue(receipt['canon_recreated'])
            install = next(cmd for cmd in seen if 'serge-install.py' in cmd[1])
            self.assertIn('--no-enable-units', install)
            self.assertIn('--non-interactive', install)
            enable = [
                cmd
                for cmd in seen
                if cmd[:3] == ['systemctl', '--user', 'enable']
            ]
            self.assertTrue(enable)
            self.assertIn('serge-queue@conversations.service', enable[0])

    def test_existing_root_restarts_active_units_only(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            dest = tmp / 'dest'
            dest.mkdir()
            (dest / 'state').mkdir()
            (dest / 'state/keep').write_text('1\n', encoding='utf-8')
            home = tmp / 'home'
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml(home, dest), encoding='utf-8')
            mandate = tmp / 'mandate.yaml'
            mandate.write_text('schema_version: 1\n', encoding='utf-8')
            seen: list[list[str]] = []

            def runner(argv, **_kwargs):
                seen.append(list(argv))
                if argv[:3] == ['systemctl', '--user', 'show']:
                    name = argv[-1]
                    state = (
                        'active'
                        if name == 'serge-queue@works.service'
                        else 'inactive'
                    )
                    return subprocess.CompletedProcess(
                        args=argv,
                        returncode=0,
                        stdout=f'{state}\n',
                        stderr='',
                    )
                return _ok()

            with mock.patch(
                'kit.deploy.update_instance',
                return_value={
                    'status': 'updated',
                    'instance_id': 'alice-laptop',
                    'system_root': str(dest),
                    'canon_recreated': False,
                },
            ) as patched:
                receipt = deploy_instance(
                    instance_file=instance,
                    mandate=mandate,
                    source_repo=ROOT,
                    git_sha='HEAD',
                    kit_root=ROOT,
                    runner=runner,
                )
            patched.assert_called_once()
            self.assertEqual(receipt['status'], 'updated')
            self.assertEqual(
                receipt['units_restarted'], ['serge-queue@works.service']
            )
            self.assertFalse(
                any('serge-install.py' in ' '.join(cmd) for cmd in seen)
            )

    def test_existing_root_restarts_failed_units(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            dest = tmp / 'dest'
            dest.mkdir()
            (dest / 'state').mkdir()
            home = tmp / 'home'
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml(home, dest), encoding='utf-8')
            mandate = tmp / 'mandate.yaml'
            mandate.write_text('schema_version: 1\n', encoding='utf-8')
            seen: list[list[str]] = []

            def runner(argv, **_kwargs):
                seen.append(list(argv))
                if argv[:3] == ['systemctl', '--user', 'show']:
                    name = argv[-1]
                    state = (
                        'failed'
                        if name == 'serge-queue@works.service'
                        else 'inactive'
                    )
                    return subprocess.CompletedProcess(
                        args=argv,
                        returncode=0,
                        stdout=f'{state}\n',
                        stderr='',
                    )
                return _ok()

            with mock.patch(
                'kit.deploy.update_instance',
                return_value={
                    'status': 'updated',
                    'instance_id': 'alice-laptop',
                    'system_root': str(dest),
                    'canon_recreated': False,
                },
            ):
                receipt = deploy_instance(
                    instance_file=instance,
                    mandate=mandate,
                    source_repo=ROOT,
                    git_sha='HEAD',
                    kit_root=ROOT,
                    runner=runner,
                )
            self.assertEqual(
                receipt['units_restarted'], ['serge-queue@works.service']
            )
            self.assertIn(
                [
                    'systemctl',
                    '--user',
                    'reset-failed',
                    'serge-queue@works.service',
                ],
                seen,
            )

    def test_l_ancien_timer_est_remplace_par_les_deux_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            dest = tmp / 'dest'
            dest.mkdir()
            (dest / 'state').mkdir()
            home = tmp / 'home'
            units = home / '.config/systemd/user'
            (units / 'serge-pipeline.timer.d').mkdir(parents=True)
            for rel in (
                'serge-pipeline.service',
                'serge-pipeline.timer',
                'serge-pipeline.timer.d/production-continuous.conf',
            ):
                (units / rel).write_text('[Unit]\n', encoding='utf-8')
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml(home, dest), encoding='utf-8')
            mandate = tmp / 'mandate.yaml'
            mandate.write_text('schema_version: 1\n', encoding='utf-8')
            seen: list[list[str]] = []

            def runner(argv, **_kwargs):
                seen.append(list(argv))
                if argv[:3] == ['systemctl', '--user', 'show']:
                    on = argv[-1] == 'serge-pipeline.timer'
                    return subprocess.CompletedProcess(
                        args=argv,
                        returncode=0,
                        stdout='active\n' if on else 'inactive\n',
                        stderr='',
                    )
                return _ok()

            with mock.patch(
                'kit.deploy.update_instance',
                return_value={'status': 'updated', 'canon_recreated': False},
            ):
                receipt = deploy_instance(
                    instance_file=instance,
                    mandate=mandate,
                    source_repo=ROOT,
                    git_sha='HEAD',
                    kit_root=ROOT,
                    runner=runner,
                )
            self.assertIn(
                [
                    'systemctl',
                    '--user',
                    'disable',
                    '--now',
                    'serge-pipeline.timer',
                ],
                seen,
            )
            self.assertEqual(
                receipt['units_replaced'],
                [
                    'serge-queue@conversations.service',
                    'serge-queue@works.service',
                ],
            )
            self.assertEqual(list(units.iterdir()), [])

    def test_privileged_install_enables_system_caddy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            dest = tmp / 'dest'
            home = tmp / 'home'
            unit = (
                home / '.config/systemd/system-units/serge-web-ingress.service'
            )
            unit.parent.mkdir(parents=True)
            unit.write_text('[Unit]\nDescription=test\n', encoding='utf-8')
            instance = tmp / 'serge.instance.toml'
            text = _toml(home, dest).replace(
                'ingress = false\n',
                'ingress = true\n',
            )
            text += '\n[ingress]\nlisten = "privileged"\n'
            instance.write_text(text, encoding='utf-8')
            mandate = tmp / 'mandate.yaml'
            mandate.write_text('schema_version: 1\n', encoding='utf-8')
            seen: list[list[str]] = []

            def runner(argv, **_kwargs):
                seen.append(list(argv))
                return _ok()

            receipt = deploy_instance(
                instance_file=instance,
                mandate=mandate,
                source_repo=ROOT,
                git_sha='HEAD',
                kit_root=ROOT,
                runner=runner,
                python=sys.executable,
            )
            self.assertEqual(receipt['status'], 'installed')
            self.assertIn(
                [
                    'sudo',
                    '-n',
                    'systemctl',
                    'enable',
                    '--now',
                    'serge-web-ingress.service',
                ],
                seen,
            )
            user_enable = [
                cmd
                for cmd in seen
                if cmd[:3] == ['systemctl', '--user', 'enable']
            ]
            self.assertTrue(user_enable)
            self.assertFalse(
                any('serge-web-ingress.service' in cmd for cmd in user_enable)
            )

    def test_privileged_update_recopies_system_caddy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            dest = tmp / 'dest'
            dest.mkdir()
            (dest / 'state').mkdir()
            home = tmp / 'home'
            unit = (
                home / '.config/systemd/system-units/serge-web-ingress.service'
            )
            unit.parent.mkdir(parents=True)
            unit.write_text('[Unit]\nDescription=test\n', encoding='utf-8')
            instance = tmp / 'serge.instance.toml'
            text = _toml(home, dest).replace(
                'ingress = false\n',
                'ingress = true\n',
            )
            text += '\n[ingress]\nlisten = "privileged"\n'
            instance.write_text(text, encoding='utf-8')
            mandate = tmp / 'mandate.yaml'
            mandate.write_text('schema_version: 1\n', encoding='utf-8')
            seen: list[list[str]] = []

            def runner(argv, **_kwargs):
                seen.append(list(argv))
                if argv[:3] == ['systemctl', '--user', 'show']:
                    return subprocess.CompletedProcess(
                        args=argv,
                        returncode=0,
                        stdout='inactive\n',
                        stderr='',
                    )
                return _ok()

            with mock.patch(
                'kit.deploy.update_instance',
                return_value={
                    'status': 'updated',
                    'instance_id': 'alice-laptop',
                    'system_root': str(dest),
                    'canon_recreated': False,
                },
            ):
                receipt = deploy_instance(
                    instance_file=instance,
                    mandate=mandate,
                    source_repo=ROOT,
                    git_sha='HEAD',
                    kit_root=ROOT,
                    runner=runner,
                )
            self.assertEqual(receipt['status'], 'updated')
            self.assertIn(
                [
                    'sudo',
                    '-n',
                    'cp',
                    str(unit),
                    '/etc/systemd/system/serge-web-ingress.service',
                ],
                seen,
            )
            self.assertIn(
                [
                    'sudo',
                    '-n',
                    'systemctl',
                    'restart',
                    'serge-web-ingress.service',
                ],
                seen,
            )
            self.assertFalse(
                any('serge-install.py' in ' '.join(cmd) for cmd in seen)
            )


class DependancesTests(unittest.TestCase):
    """Les dépendances du serveur, installées à chaque déploiement."""

    def _deployer(self, venv: str, pip_code: int = 0):
        raw = tempfile.TemporaryDirectory()
        self.addCleanup(raw.cleanup)
        tmp = Path(raw.name)
        dest = tmp / 'dest'
        (dest / 'state').mkdir(parents=True)
        (dest / 'state/keep').write_text('1\n', encoding='utf-8')
        self.home = tmp / 'home'
        instance = tmp / 'serge.instance.toml'
        instance.write_text(_toml(self.home, dest), encoding='utf-8')
        mandate = tmp / 'mandate.yaml'
        mandate.write_text('schema_version: 1\n', encoding='utf-8')
        self.seen: list[list[str]] = []

        def runner(argv, **_kwargs):
            self.seen.append(list(argv))
            if argv[1:2] == ['-c']:
                return subprocess.CompletedProcess(argv, 0, f'{venv}\n', '')
            if argv[1:4] == ['-m', 'pip', 'install']:
                return subprocess.CompletedProcess(
                    argv, pip_code, '', 'ERROR: No matching distribution'
                )
            return _ok()

        self.update = mock.patch(
            'kit.deploy.update_instance',
            return_value={'status': 'updated', 'canon_recreated': False},
        ).start()
        self.addCleanup(mock.patch.stopall)
        return deploy_instance(
            instance_file=instance,
            mandate=mandate,
            source_repo=ROOT,
            git_sha='HEAD',
            kit_root=ROOT,
            runner=runner,
            python='/usr/bin/python3',
        )

    def _pip(self) -> list[str]:
        return next(c for c in self.seen if c[1:4] == ['-m', 'pip', 'install'])

    def test_un_venv_recoit_les_dependances(self) -> None:
        receipt = self._deployer(venv='1')
        pip = self._pip()
        self.assertEqual(pip[0], '/usr/bin/python3')
        self.assertIn('pyyaml', pip)
        self.assertTrue(any(p.startswith('playwright') for p in pip))
        self.assertFalse(any('venv' in c for c in self.seen))
        self.assertEqual(
            self.update.call_args.kwargs['python'], '/usr/bin/python3'
        )
        self.assertFalse(receipt['dependances']['venv_cree'])

    def test_un_python_du_systeme_passe_a_l_environnement_de_serge(
        self,
    ) -> None:
        receipt = self._deployer(venv='0')
        venv = self.home / '.local/share/serge/venv'
        self.assertIn(
            [
                '/usr/bin/python3',
                '-m',
                'venv',
                '--system-site-packages',
                str(venv),
            ],
            self.seen,
        )
        self.assertEqual(self._pip()[0], str(venv / 'bin/python'))
        # Les units passent au Python de l'environnement.
        self.assertEqual(
            self.update.call_args.kwargs['python'], str(venv / 'bin/python')
        )
        self.assertTrue(receipt['dependances']['venv_cree'])

    def test_un_pip_qui_echoue_arrete_le_deploiement(self) -> None:
        with self.assertRaises(BuilderError) as refus:
            self._deployer(venv='1', pip_code=1)
        self.assertIn('No matching distribution', str(refus.exception))
        self.update.assert_not_called()
        self.assertFalse(any(c[:1] == ['systemctl'] for c in self.seen))


if __name__ == '__main__':
    unittest.main()
