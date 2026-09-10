#!/usr/bin/env python3
"""Builder secrets: sidecar values to 0600 instance files. No values logged."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kit.instance_file import assert_secrets_complete, load_manifest


def secret_destination(
    maps_to: str,
    *,
    home: Path,
    config_root: Path,
) -> Path:
    catalogue = Path(maps_to)
    if catalogue.name == 'gog.env' or 'openclaw/gog.env' in maps_to.replace(
        '\\', '/'
    ):
        return home / '.config/openclaw' / catalogue.name
    return config_root / 'secrets' / catalogue.name


def secret_file_body(name: str, value: str, item: Mapping[str, Any]) -> str:
    env_name = str(item.get('env_name_inside_file') or '').strip()
    dest_name = Path(str(item.get('maps_to') or name)).name
    if '\n' in value.rstrip('\n'):
        return value if value.endswith('\n') else f'{value}\n'
    if env_name:
        return f'{env_name}={value}\n'
    if dest_name.endswith('.env'):
        return f'{name.upper()}={value}\n'
    return value if value.endswith('\n') else f'{value}\n'


def inject_secrets(
    secrets: Mapping[str, str],
    features: Mapping[str, bool],
    *,
    home: Path,
    config_root: Path,
    manifest: Mapping[str, Any] | None = None,
) -> list[str]:
    payload = manifest or load_manifest()
    present = assert_secrets_complete(features, secrets, payload)
    written: list[str] = []
    by_name = {
        str(item.get('name')): item
        for item in (payload.get('keys') or [])
        if isinstance(item, dict) and item.get('name')
    }
    secrets_dir = config_root / 'secrets'
    secrets_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir.chmod(0o700)
    for name in present:
        value = str(secrets.get(name) or '').strip()
        if not value:
            continue
        item = by_name.get(name) or {'name': name, 'maps_to': f'{name}'}
        dest = secret_destination(
            str(item.get('maps_to') or name),
            home=home,
            config_root=config_root,
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(secret_file_body(name, value, item), encoding='utf-8')
        dest.chmod(0o600)
        written.append(name)
    return written
