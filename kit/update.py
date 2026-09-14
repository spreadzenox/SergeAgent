#!/usr/bin/env python3
"""Overlay git archive dans un system_root déjà instancié. Ne recrée pas le canon."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from kit.builder.guards import BuilderError, assert_instance_paths_safe
from kit.builder.install import write_units
from kit.builder.seed import dest_is_empty, git_archive_into, resolve_git_sha
from kit.builder.telephony import write_asterisk, write_asterisk_conf
from kit.instance_file import (
    InstanceError,
    load_secret_map,
    load_toml,
    validate_toml,
)
from kit.units import host_facts_from_instance

PRESERVE_TOP = frozenset({'state', 'queue', 'logs', 'reports', 'evidence'})


def loaded_from_instance(instance_file: Path) -> dict[str, Any]:
    """Charge le TOML sans déchiffrer le sidecar (update code seulement)."""
    data = validate_toml(load_toml(instance_file))
    home = Path(str(data['paths']['home']))
    config_root = Path(
        str(data['paths'].get('config_root') or (home / '.config/serge'))
    )
    return {
        **data,
        'instance_file': str(instance_file.resolve()),
        'paths': {
            **data['paths'],
            'config_root': str(config_root),
        },
    }


def _secrets_for_update(loaded: dict[str, Any]) -> dict[str, str] | None:
    """Déchiffre le sidecar si age/dotenv est là ; sinon None (pjsip intact)."""
    instance = Path(str(loaded['instance_file']))
    name = Path(
        str(
            (loaded.get('paths') or {}).get('secrets_age')
            or 'serge.secrets.age'
        )
    ).name
    sidecar = instance.parent / name
    if (
        not os.environ.get('SERGE_SECRETS_DOTENV', '').strip()
        and not sidecar.is_file()
    ):
        return None
    try:
        return load_secret_map(sidecar)
    except InstanceError:
        return None


def _preserved(rel: Path) -> bool:
    return bool(rel.parts) and rel.parts[0] in PRESERVE_TOP


def overlay_tree(source_tree: Path, dest: Path) -> list[str]:
    """Copie l’archive par-dessus dest, sans toucher state/queue/logs/…"""
    copied: list[str] = []
    for src in source_tree.rglob('*'):
        if not src.is_file():
            continue
        rel = src.relative_to(source_tree)
        if _preserved(rel):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(str(rel))
    return copied


def overlay_git_archive(
    source_repo: Path,
    sha: str,
    dest: Path,
) -> list[str]:
    resolved = resolve_git_sha(source_repo, sha)
    with tempfile.TemporaryDirectory() as raw:
        tree = Path(raw) / 'tree'
        git_archive_into(source_repo, resolved, tree)
        return overlay_tree(tree, dest)


def update_instance(
    *,
    instance_file: Path,
    source_repo: Path,
    git_sha: str = 'HEAD',
    confirm_live_id: str = '',
    kit_root: Path | None = None,
    systemd_user_dir: Path | None = None,
    uid: int | None = None,
) -> dict[str, Any]:
    """Overlay le SHA, réécrit les units, laisse le canon intact."""
    loaded = loaded_from_instance(instance_file)
    assert_instance_paths_safe(loaded, confirm_live_id=confirm_live_id)
    system_root = Path(str(loaded['paths']['system_root']))
    if dest_is_empty(system_root):
        raise BuilderError(
            f'system_root vide ({system_root}) : utilise l’installeur'
        )
    copied = overlay_git_archive(source_repo, git_sha, system_root)
    home = Path(str(loaded['paths']['home']))
    user_systemd = systemd_user_dir or (home / '.config/systemd/user')
    facts = host_facts_from_instance(loaded, uid=uid)
    units = write_units(
        loaded,
        user_systemd,
        facts=facts,
        kit_root=kit_root or source_repo,
    )
    config_root = Path(str(loaded['paths']['config_root']))
    asterisk_files: list[str] = []
    asterisk_conf = ''
    if (loaded.get('features') or {}).get('phone_voice'):
        secrets = _secrets_for_update(loaded)
        if secrets:
            asterisk_files = write_asterisk(
                loaded, secrets, config_root, facts
            )
            asterisk_conf = 'asterisk.conf'
        else:
            asterisk_conf = write_asterisk_conf(loaded, config_root, facts)
    return {
        'status': 'updated',
        'instance_id': loaded['instance_id'],
        'system_root': str(system_root),
        'files_copied': len(copied),
        'units_written': sorted(units['files']),
        'units_enable': list(units['enable']),
        'asterisk_conf_written': asterisk_conf,
        'asterisk_files_written': asterisk_files,
        'canon_recreated': False,
    }
