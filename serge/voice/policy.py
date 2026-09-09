#!/usr/bin/env python3
"""Voice policy gate: legal hours, mandate bits, runtime state. Fail-closed.

No SIP here. voice_bridge.py originates only what this policy allowed, and
only with the locked CLI. Inbound answering needs no consent (answering is
not prospection) but is still mandate-gated.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from serge.paths import system_root

PARIS_TZ = 'Europe/Paris'
# Legal cold-call windows, lunch break excluded, Monday-Friday only.
CALL_WINDOWS = ((10, 0, 13, 0), (14, 0, 20, 0))


class VoiceBrokerDenied(ValueError):
    pass


def paris_now(now: datetime | None = None) -> datetime:
    """Current time in Europe/Paris. Fail-closed when tzdata is missing."""
    try:
        paris = ZoneInfo(PARIS_TZ)
    except ZoneInfoNotFoundError as exc:
        raise VoiceBrokerDenied('timezone Europe/Paris unavailable') from exc
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(paris)


def easter_sunday(year: int) -> date:
    """Meeus/Jones/Butcher Gregorian Easter. Needed for movable holidays."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    weekday = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * weekday) // 451
    month, day = divmod(h + weekday - 7 * m + 114, 31)
    return date(year, month, day + 1)


def french_holidays(year: int) -> set[date]:
    easter = easter_sunday(year)
    fixed = {
        date(year, 1, 1),
        date(year, 5, 1),
        date(year, 5, 8),
        date(year, 7, 14),
        date(year, 8, 15),
        date(year, 11, 1),
        date(year, 11, 11),
        date(year, 12, 25),
    }
    movable = {
        easter + timedelta(days=1),  # Easter Monday
        easter + timedelta(days=39),  # Ascension
        easter + timedelta(days=50),  # Whit Monday
    }
    return fixed | movable


def within_legal_hours(moment: datetime) -> bool:
    """Mon-Fri, 10h-13h / 14h-20h Paris time, public holidays excluded."""
    if moment.weekday() >= 5:
        return False
    if moment.date() in french_holidays(moment.year):
        return False
    current = (moment.hour, moment.minute)
    for start_h, start_m, end_h, end_m in CALL_WINDOWS:
        if (start_h, start_m) <= current < (end_h, end_m):
            return True
    return False


def kill_switch_active(system_root: Path) -> bool:
    return (system_root / 'orchestrator/runtime/KILL_SWITCH').exists() or (
        system_root / 'state/KILL_SWITCH'
    ).exists()


@dataclass(frozen=True)
class VoicePolicy:
    mode: str
    mandate_outbound_allowed: bool
    mandate_inbound_allowed: bool
    external_actions: bool
    kill_switch: bool
    cli_expected: str
    max_calls_per_day: int


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise VoiceBrokerDenied(f'instance file unreadable: {path}') from exc


def resolve_policy(
    root: Path | None = None,
    *,
    instance_file: Path | None = None,
    mandate_path: Path | None = None,
) -> VoicePolicy:
    """Build the outbound policy from instance file + mandate + runtime state."""
    base = root or system_root()
    toml_path = instance_file or Path(
        os.environ.get('SERGE_INSTANCE_FILE', '')
    )
    if not str(toml_path):
        raise VoiceBrokerDenied('SERGE_INSTANCE_FILE is required')
    data = _read_toml(Path(toml_path))
    features = data.get('features') or {}
    if not features.get('phone_voice'):
        raise VoiceBrokerDenied('features.phone_voice is off')
    identity = data.get('identity') or {}
    phone = data.get('phone_voice') or {}
    try:
        max_calls = int(phone.get('max_calls_per_day', 50))
    except (TypeError, ValueError):
        max_calls = 50
    policy_path = mandate_path or Path(
        os.environ.get('SERGE_MANDATE_PATH', '')
    )
    outbound = inbound = False
    if str(policy_path):
        try:
            mandate = yaml.safe_load(
                Path(policy_path).read_text(encoding='utf-8')
            )
        except (OSError, yaml.YAMLError) as exc:
            raise VoiceBrokerDenied('mandate unreadable') from exc
        if isinstance(mandate, dict):
            sales = (mandate.get('governance') or {}).get('sales') or {}
            outbound = (
                sales.get('may_place_commercial_calls') is True
                and 'place_bounded_commercial_calls_via_voice_broker'
                in (mandate.get('autonomous_actions') or [])
            )
            inbound = sales.get(
                'may_answer_voice_calls'
            ) is True and 'answer_inbound_voice_calls' in (
                mandate.get('autonomous_actions') or []
            )
    runtime_file = base / 'orchestrator/runtime/runtime-policy.json'
    external = False
    if runtime_file.is_file():
        try:
            runtime = json.loads(runtime_file.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            runtime = {}
        external = runtime.get('external_actions_enabled') is True
    return VoicePolicy(
        mode=str(data.get('mode') or 'sandbox'),
        mandate_outbound_allowed=outbound,
        mandate_inbound_allowed=inbound,
        external_actions=external,
        kill_switch=kill_switch_active(base),
        cli_expected=str(identity.get('phone_voice_number') or ''),
        max_calls_per_day=max(1, max_calls),
    )


def default_ledger_path(root: Path | None = None) -> Path:
    base = root or system_root()
    return base / 'state/voice/voice.db'
