#!/usr/bin/env python3
"""Render portable systemd units from instance paths. Does not install."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kit.instance_file import FEATURE_KEYS, as_table

PLACEHOLDER = re.compile(r'__[A-Z][A-Z0-9_]*__')
CORE_UNIT_FILES = (
    'serge-pipeline.service',
    'serge-pipeline.timer',
    'serge-pipeline.timer.d/production-continuous.conf',
    'serge-daily-report.service',
    'serge-daily-report.timer',
)
ALWAYS_ENABLE = (
    'serge-pipeline.timer',
    'serge-daily-report.timer',
)


class UnitError(ValueError):
    pass


def _repo_root() -> Path:
    env = os.environ.get('SERGE_SYSTEM_ROOT', '').strip()
    if env and (Path(env) / 'systemd/templates').is_dir():
        return Path(env)
    return Path(__file__).resolve().parents[1]


def template_dir(root: Path | None = None) -> Path:
    return (root or _repo_root()) / 'systemd/templates'


def _read_template(name: str, root: Path | None = None) -> str:
    path = template_dir(root) / f'{name}.in'
    try:
        return path.read_text(encoding='utf-8')
    except OSError as exc:
        raise UnitError(f'unit template missing: {path}') from exc


def render_template(text: str, mapping: Mapping[str, str]) -> str:
    out = text
    for key, value in mapping.items():
        out = out.replace(f'__{key}__', value)
    leftover = PLACEHOLDER.findall(out)
    if leftover:
        raise UnitError(
            'unreplaced placeholders: ' + ', '.join(sorted(set(leftover)))
        )
    return out


def host_facts_from_instance(
    loaded: Mapping[str, Any],
    *,
    uid: int | None = None,
    python: str = '/usr/bin/python3',
    user: str | None = None,
) -> dict[str, str]:
    home = Path(str(loaded['paths']['home']))
    unix_user = user or home.name or 'owner'
    caddy = str(home / '.local/bin/caddy')
    return {
        'user': unix_user,
        'uid': str(uid if uid is not None else os.getuid()),
        'python': python,
        'caddy': caddy,
    }


def substitutions(
    loaded: Mapping[str, Any],
    facts: Mapping[str, str],
) -> dict[str, str]:
    paths = loaded['paths']
    features = loaded.get('features') or {}
    openclaw = bool(features.get('openclaw'))
    gmail = bool(features.get('gmail'))
    listen = 'unprivileged'
    ingress = as_table(loaded.get('ingress'))
    if str(ingress.get('listen') or '') == 'privileged':
        listen = 'privileged'
    elif str(ingress.get('listen') or '') == 'loopback':
        listen = 'loopback'
    return {
        'HOME': str(paths['home']),
        'USER': str(facts['user']),
        'UID': str(facts['uid']),
        'SYSTEM_ROOT': str(paths['system_root']),
        'CONFIG_ROOT': str(
            paths.get('config_root') or Path(paths['home']) / '.config/serge'
        ),
        'POLICY': str(paths['policy']),
        'INSTANCE_FILE': str(loaded['instance_file']),
        'PYTHON': str(facts.get('python') or '/usr/bin/python3'),
        'CADDY': str(
            facts.get('caddy') or Path(paths['home']) / '.local/bin/caddy'
        ),
        'INGRESS_LISTEN': listen,
        'AGENT_RUNTIME': 'openclaw' if openclaw else 'direct_llm',
        'OPENCLAW_ADAPTER': '1' if openclaw else '0',
        'OPENCLAW_UNIT_LINES': (
            'Wants=openclaw-gateway.service\nAfter=openclaw-gateway.service\n'
            if openclaw
            else ''
        ),
        'OPENCLAW_RW': (f'{paths["home"]}/.openclaw ' if openclaw else ''),
        # Miroir kit/builder/secrets.py::secret_destination (cas gog) :
        # l'import direct ferait un cycle units<->builder.
        'GMAIL_UNIT_LINES': (
            f'EnvironmentFile=-{paths["home"]}/.config/openclaw/gog.env\n'
            if gmail
            else ''
        ),
    }


def selected_units(
    features: Mapping[str, bool],
    mode: str,
    listen: str = 'loopback',
) -> list[tuple[str, str, str]]:
    """Return (dest_relpath, template_stem, scope)."""
    chosen: list[tuple[str, str, str]] = [
        ('serge-pipeline.service', 'serge-pipeline.service', 'user'),
        ('serge-pipeline.timer', 'serge-pipeline.timer', 'user'),
        (
            'serge-pipeline.timer.d/production-continuous.conf',
            'serge-pipeline.timer.d/production-continuous.conf',
            'user',
        ),
        ('serge-daily-report.service', 'serge-daily-report.service', 'user'),
        ('serge-daily-report.timer', 'serge-daily-report.timer', 'user'),
    ]
    if features.get('ingress'):
        privileged = listen == 'privileged'
        chosen.append(
            (
                'serge-web-ingress.service',
                'serge-web-ingress.system.service'
                if privileged
                else 'serge-web-ingress.user.service',
                'system' if privileged else 'user',
            )
        )
    if features.get('owner_ui'):
        chosen.append(
            (
                'serge-public-dashboard.service',
                'serge-public-dashboard.service',
                'user',
            )
        )
    if features.get('phone_sms'):
        chosen.append(
            (
                'serge-sms-receiver.service',
                'serge-sms-receiver.service',
                'user',
            )
        )
    if features.get('discord'):
        chosen.append(
            (
                'serge-discord-bot.service',
                'serge-discord-bot.service',
                'user',
            )
        )
    if features.get('phone_voice'):
        chosen.append(
            (
                'serge-asterisk.service',
                'serge-asterisk.service',
                'user',
            )
        )
        chosen.append(
            (
                'serge-voice-bridge.service',
                'serge-voice-bridge.service',
                'user',
            )
        )
    if mode == 'sandbox':
        chosen.append(
            (
                'serge-burn-in-failure.service',
                'serge-burn-in-failure.service',
                'user',
            )
        )
    return chosen


def units_to_enable(
    features: Mapping[str, bool], listen: str = 'loopback'
) -> list[str]:
    enable = list(ALWAYS_ENABLE)
    if features.get('ingress'):
        enable.append('serge-web-ingress.service')
    if features.get('owner_ui'):
        enable.append('serge-public-dashboard.service')
    if features.get('phone_sms'):
        enable.append('serge-sms-receiver.service')
    if features.get('discord'):
        enable.append('serge-discord-bot.service')
    if features.get('phone_voice'):
        enable.append('serge-asterisk.service')
        enable.append('serge-voice-bridge.service')
    return enable


def render_units(
    loaded: Mapping[str, Any],
    facts: Mapping[str, str] | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    features = {
        key: bool((loaded.get('features') or {}).get(key))
        for key in FEATURE_KEYS
    }
    if features.get('metagrok'):
        # Host-local bridge only. Kit never emits Meta-Grok units.
        pass
    ingress = as_table(loaded.get('ingress'))
    listen = str(ingress.get('listen') or 'loopback')
    mapping = substitutions(loaded, facts or host_facts_from_instance(loaded))
    files: dict[str, str] = {}
    scopes: dict[str, str] = {}
    for dest, template, scope in selected_units(
        features,
        str(loaded.get('mode') or 'sandbox'),
        listen,
    ):
        files[dest] = render_template(_read_template(template, root), mapping)
        scopes[dest] = scope
    return {
        'files': files,
        'enable': units_to_enable(features, listen),
        'scope': scopes,
        'installed': False,
        'metagrok_units_included': False,
    }
