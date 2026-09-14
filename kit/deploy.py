#!/usr/bin/env python3
"""Déploiement VPS : install vierge ou update + units. Pas de denylist."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from kit.builder.guards import BuilderError
from kit.builder.seed import dest_is_empty
from kit.units import system_units_to_enable, units_to_enable
from kit.update import loaded_from_instance, update_instance

Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run(
    runner: Runner,
    argv: Sequence[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = runner(
        list(argv),
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    return completed


def systemctl_user(
    runner: Runner,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    return _run(runner, ['systemctl', '--user', *args])


RESTART_STATES = frozenset(
    {'active', 'activating', 'failed', 'reloading', 'deactivating'}
)


def unit_active_state(runner: Runner, unit: str) -> str:
    completed = systemctl_user(
        runner, 'show', '-p', 'ActiveState', '--value', unit
    )
    return (completed.stdout or '').strip()


def enable_now(runner: Runner, names: Sequence[str]) -> list[str]:
    reload = systemctl_user(runner, 'daemon-reload')
    if reload.returncode != 0:
        detail = (reload.stderr or reload.stdout or '')[-300:]
        raise BuilderError(f'daemon-reload a échoué : {detail}')
    enabled: list[str] = []
    errors: list[str] = []
    for name in names:
        completed = systemctl_user(runner, 'enable', '--now', name)
        if completed.returncode == 0:
            enabled.append(name)
        else:
            errors.append(name)
    if errors:
        raise BuilderError('systemctl enable failed: ' + ', '.join(errors))
    return enabled


def _listen(loaded: dict[str, Any]) -> str:
    raw = (
        loaded.get('ingress')
        if isinstance(loaded.get('ingress'), dict)
        else {}
    )
    listen = str((raw or {}).get('listen') or 'loopback')
    return listen if listen in {'loopback', 'privileged'} else 'loopback'


def _system_unit_dir(loaded: dict[str, Any]) -> Path:
    home = Path(str(loaded['paths']['home']))
    return home / '.config/systemd/system-units'


def enable_system_now(
    runner: Runner, names: Sequence[str], source_dir: Path
) -> list[str]:
    """Pose les units privileged sous /etc/systemd/system (sudo -n)."""
    enabled: list[str] = []
    for name in names:
        src = source_dir / name
        dest = Path('/etc/systemd/system') / name
        if not src.is_file():
            raise BuilderError(f'unit system manquante : {src}')
        copied = _run(runner, ['sudo', '-n', 'cp', str(src), str(dest)])
        if copied.returncode != 0:
            detail = (copied.stderr or copied.stdout or '')[-300:]
            raise BuilderError(f'sudo cp {name} a échoué : {detail}')
        reload = _run(runner, ['sudo', '-n', 'systemctl', 'daemon-reload'])
        if reload.returncode != 0:
            raise BuilderError('sudo daemon-reload a échoué')
        completed = _run(
            runner, ['sudo', '-n', 'systemctl', 'enable', '--now', name]
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or '')[-300:]
            raise BuilderError(f'sudo enable {name} a échoué : {detail}')
        enabled.append(name)
    return enabled


def restart_system_active(runner: Runner, names: Sequence[str]) -> list[str]:
    restarted: list[str] = []
    reload = _run(runner, ['sudo', '-n', 'systemctl', 'daemon-reload'])
    if reload.returncode != 0:
        raise BuilderError('sudo daemon-reload a échoué')
    for name in names:
        active = _run(
            runner, ['sudo', '-n', 'systemctl', 'is-active', '--quiet', name]
        )
        if active.returncode != 0:
            continue
        completed = _run(runner, ['sudo', '-n', 'systemctl', 'restart', name])
        if completed.returncode != 0:
            raise BuilderError(f'sudo restart failed: {name}')
        restarted.append(name)
    return restarted


def restart_active(runner: Runner, names: Sequence[str]) -> list[str]:
    reload = systemctl_user(runner, 'daemon-reload')
    if reload.returncode != 0:
        detail = (reload.stderr or reload.stdout or '')[-300:]
        raise BuilderError(f'daemon-reload a échoué : {detail}')
    restarted: list[str] = []
    for name in names:
        state = unit_active_state(runner, name)
        if state not in RESTART_STATES:
            continue
        if state in {'failed', 'activating'}:
            systemctl_user(runner, 'reset-failed', name)
        completed = systemctl_user(runner, 'restart', name)
        if completed.returncode != 0:
            raise BuilderError(f'restart failed: {name}')
        restarted.append(name)
    return restarted


def _install_fresh(
    *,
    instance_file: Path,
    mandate: Path,
    source_repo: Path,
    git_sha: str,
    confirm_live_id: str,
    runner: Runner,
    python: str,
    kit_root: Path,
) -> dict[str, Any]:
    argv = [
        python,
        str(kit_root / 'scripts/serge-install.py'),
        '--instance-file',
        str(instance_file),
        '--mandate',
        str(mandate),
        '--source-repo',
        str(source_repo),
        '--git-sha',
        git_sha,
        '--no-enable-units',
        '--non-interactive',
    ]
    if confirm_live_id:
        argv.extend(['--confirm-live-instance-id', confirm_live_id])
    env = os.environ.copy()
    completed = _run(runner, argv, env=env)
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr)[-500:]
        raise BuilderError(f'install a échoué : {detail}')
    loaded = loaded_from_instance(instance_file)
    listen = _listen(loaded)
    names = units_to_enable(loaded['features'], listen)
    enabled = enable_now(runner, names)
    enabled.extend(
        enable_system_now(
            runner,
            system_units_to_enable(loaded['features'], listen),
            _system_unit_dir(loaded),
        )
    )
    return {
        'status': 'installed',
        'instance_id': loaded['instance_id'],
        'system_root': str(loaded['paths']['system_root']),
        'units_enabled': enabled,
        'canon_recreated': True,
    }


def deploy_instance(
    *,
    instance_file: Path,
    mandate: Path,
    source_repo: Path,
    git_sha: str = 'HEAD',
    confirm_live_id: str = '',
    kit_root: Path | None = None,
    runner: Runner | None = None,
    python: str | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    """Racine vide → install + enable tout. Sinon update + restart des actives."""
    root = kit_root or source_repo
    run = runner or subprocess.run
    exe = python or sys.executable
    loaded = loaded_from_instance(instance_file)
    system_root = Path(str(loaded['paths']['system_root']))
    listen = _listen(loaded)
    names = units_to_enable(loaded['features'], listen)
    system_names = system_units_to_enable(loaded['features'], listen)
    if dest_is_empty(system_root):
        return _install_fresh(
            instance_file=instance_file,
            mandate=mandate,
            source_repo=source_repo,
            git_sha=git_sha,
            confirm_live_id=confirm_live_id,
            runner=run,
            python=exe,
            kit_root=root,
        )
    receipt = update_instance(
        instance_file=instance_file,
        source_repo=source_repo,
        git_sha=git_sha,
        confirm_live_id=confirm_live_id,
        kit_root=root,
        uid=uid,
    )
    restarted = restart_active(run, names)
    restarted.extend(restart_system_active(run, system_names))
    receipt['units_restarted'] = restarted
    receipt['status'] = 'updated'
    return receipt
