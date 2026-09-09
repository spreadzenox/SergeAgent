#!/usr/bin/env python3
"""Builder guards: never write live paths, never ship Meta-Grok blindly."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

LIVE_PREFIXES = (
    Path('/home/serge/serge-system'),
    Path('/home/serge/serge-kit'),
    Path('/home/serge/.config'),
    Path('/home/serge/.openclaw'),
    Path('/home/serge/.meta-grok'),
    Path('/opt/serge-policy'),
    Path('/opt/serge-meta-grok-v2'),
    Path('/etc/serge'),
)
LIVE_MANDATE_MARKERS_ENV = 'SERGE_LIVE_MANDATE_MARKERS'


def live_mandate_markers() -> tuple[str, ...]:
    """Marqueurs du mandat live propriétaire (email, snowflake...).

    Lus dans SERGE_LIVE_MANDATE_MARKERS (csv), configurés sur l'infra
    live uniquement — jamais en dur, jamais commités. Vide par défaut
    (installations tierces : garde inactive, pas d'erreur).
    """
    raw = os.environ.get(LIVE_MANDATE_MARKERS_ENV, '')
    return tuple(item.strip() for item in raw.split(',') if item.strip())


METAGROK_MARKERS = (
    Path('/opt/serge-meta-grok-v2/current'),
    Path('/etc/serge/meta-grok-v2/core'),
)


class BuilderError(ValueError):
    pass


def assert_not_live_path(path: Path, *, confirm_live: bool = False) -> None:
    resolved = path.resolve()
    for prefix in LIVE_PREFIXES:
        try:
            resolved.relative_to(prefix)
        except ValueError:
            continue
        if confirm_live:
            return
        raise BuilderError(
            f'refusing to write live host path {resolved} '
            '(pass --confirm-live-instance-id julien-vps only for that instance)'
        )


def assert_instance_paths_safe(
    loaded: Mapping[str, Any],
    *,
    confirm_live_id: str = '',
) -> None:
    instance_id = str(loaded.get('instance_id') or '')
    confirm = confirm_live_id == 'julien-vps' and instance_id == 'julien-vps'
    paths = loaded['paths']
    for key in ('home', 'system_root', 'policy', 'config_root'):
        raw = str(paths.get(key) or '').strip()
        if raw:
            assert_not_live_path(Path(raw), confirm_live=confirm)
    if instance_id != 'julien-vps' and confirm_live_id:
        raise BuilderError('--confirm-live-instance-id is only for julien-vps')


def assert_metagrok_ok(features: Mapping[str, bool]) -> None:
    if not features.get('metagrok'):
        return
    if os.environ.get('SERGE_METAGROK_PRESENT', '').strip() in {
        '1',
        'true',
        'TRUE',
    }:
        return
    if any(path.exists() for path in METAGROK_MARKERS):
        return
    raise BuilderError(
        'features.metagrok=true but no local Meta-Grok bridge; leave the feature false'
    )
