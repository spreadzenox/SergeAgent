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
from kit.units import units_to_enable
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


def is_active(runner: Runner, unit: str) -> bool:
    return systemctl_user(runner, 'is-active', '--quiet', unit).returncode == 0


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


def restart_active(runner: Runner, names: Sequence[str]) -> list[str]:
    reload = systemctl_user(runner, 'daemon-reload')
    if reload.returncode != 0:
        detail = (reload.stderr or reload.stdout or '')[-300:]
        raise BuilderError(f'daemon-reload a échoué : {detail}')
    restarted: list[str] = []
    for name in names:
        if not is_active(runner, name):
            continue
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
    names = units_to_enable(loaded['features'])
    enabled = enable_now(runner, names)
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
    names = units_to_enable(loaded['features'])
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
    receipt['units_restarted'] = restarted
    receipt['status'] = 'updated'
    return receipt
