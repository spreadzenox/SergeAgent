#!/usr/bin/env python3
"""Builder install: couple, mandate, units into the virgin instance."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from kit.builder.guards import BuilderError, live_mandate_markers
from kit.mandate import MandateError, validate_mandate
from kit.units import render_units


def install_couple(
    instance_src: Path,
    loaded: Mapping[str, Any],
    config_root: Path,
) -> Path:
    config_root.mkdir(parents=True, exist_ok=True)
    dest_toml = config_root / 'serge.instance.toml'
    dest_toml.write_text(
        instance_src.read_text(encoding='utf-8'), encoding='utf-8'
    )
    sidecar_src = Path(loaded['paths']['secrets_age'])
    if sidecar_src.is_file():
        dest_side = config_root / sidecar_src.name
        dest_side.write_bytes(sidecar_src.read_bytes())
        dest_side.chmod(0o600)
    return dest_toml


def install_mandate(source: Path, dest: Path, *, instance_id: str) -> None:
    text = source.read_text(encoding='utf-8')
    if instance_id != 'julien-vps':
        for marker in live_mandate_markers():
            if marker in text:
                raise BuilderError(
                    'refusing live owner mandate for a non julien-vps instance'
                )
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BuilderError('mandate unreadable') from exc
    try:
        validate_mandate(payload if isinstance(payload, dict) else {})
    except MandateError as exc:
        raise BuilderError(str(exc)) from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding='utf-8')
    dest.chmod(0o600)


def write_units(
    loaded: Mapping[str, Any],
    systemd_user_dir: Path,
    *,
    facts: Mapping[str, str] | None = None,
    kit_root: Path | None = None,
) -> dict[str, Any]:
    rendered = render_units(loaded, facts, root=kit_root)
    for rel, text in rendered['files'].items():
        if rendered['scope'].get(rel) == 'system':
            dest = systemd_user_dir.parent / 'system-units' / Path(rel).name
        else:
            dest = systemd_user_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')
        dest.chmod(0o644)
    return rendered


def session_systemd_user_dir() -> Path:
    return Path.home() / '.config/systemd/user'


def can_enable_in_session(systemd_user_dir: Path) -> bool:
    try:
        return (
            systemd_user_dir.resolve() == session_systemd_user_dir().resolve()
        )
    except OSError:
        return False


def enable_units(names: list[str]) -> dict[str, Any]:
    reload = subprocess.run(
        ['systemctl', '--user', 'daemon-reload'],
        check=False,
        capture_output=True,
        text=True,
    )
    enabled: list[str] = []
    errors: list[str] = []
    if reload.returncode != 0:
        errors.append('daemon-reload failed')
    for name in names:
        completed = subprocess.run(
            ['systemctl', '--user', 'enable', '--now', name],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            enabled.append(name)
        else:
            errors.append(name)
    if errors:
        raise BuilderError('systemctl enable failed: ' + ', '.join(errors))
    return {'enabled': enabled}
