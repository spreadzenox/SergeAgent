#!/usr/bin/env python3
"""Voice policy gate: legal hours, mandate bits, runtime state. Fail-closed.

Les jours et heures d'appel du pays sont des réglages de la page Policy
(« Pays et appels ») ; les jours fériés français sont calculés.

No SIP here. voice_bridge.py originates only what this policy allowed, and
only with the locked CLI. Inbound answering needs no consent (answering is
not prospection) but is still mandate-gated.
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from serge.db.store import open_db
from serge.paths import system_root
from serge.policy_store import policy_en_vigueur

PARIS_TZ = 'Europe/Paris'
# Les jours de la semaine, dans l'ordre de ``datetime.weekday()``.
DAYS = ('lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim')


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


@dataclass(frozen=True)
class CallHours:
    """Les jours et heures d'appel d'un pays (page Policy).

    Exemple pour la France : du lundi au vendredi, 10 h – 13 h et
    14 h – 20 h (``[[10, 0, 13, 0], [14, 0, 20, 0]]``).
    """

    days: frozenset[int]
    windows: tuple[tuple[int, int, int, int], ...]


def call_hours(pol: Mapping[str, Any]) -> CallHours:
    """Les jours et heures d'appel du pays par défaut."""
    zones = pol['calling_zones']
    zone = zones[zones['default']]
    return CallHours(
        days=frozenset(DAYS.index(str(d)) for d in zone['call_days']),
        windows=tuple(
            (int(a), int(b), int(c), int(d))
            for a, b, c, d in zone['call_windows']
        ),
    )


def within_legal_hours(moment: datetime, hours: CallHours) -> bool:
    """Un jour et une heure d'appel (heure de Paris), jamais un jour férié."""
    if moment.weekday() not in hours.days:
        return False
    if moment.date() in french_holidays(moment.year):
        return False
    current = (moment.hour, moment.minute)
    for start_h, start_m, end_h, end_m in hours.windows:
        if (start_h, start_m) <= current < (end_h, end_m):
            return True
    return False


def next_legal_moment(moment: datetime, hours: CallHours) -> datetime:
    """Le prochain moment d'appel permis (``moment`` lui-même s'il l'est).

    Exemple : un samedi à 9 h, c'est le lundi suivant à 10 h. Cherché sur
    les 30 jours qui viennent ; sans aucun créneau, dans 30 jours.

    Raises:
        VoiceBrokerDenied: ``moment`` sans fuseau.
    """
    if moment.tzinfo is None:
        raise VoiceBrokerDenied('moment sans fuseau')
    if within_legal_hours(moment, hours):
        return moment
    for offset in range(31):
        day = moment + timedelta(days=offset)
        if day.weekday() not in hours.days:
            continue
        if day.date() in french_holidays(day.year):
            continue
        for start_h, start_m, _end_h, _end_m in sorted(hours.windows):
            start = day.replace(
                hour=start_h, minute=start_m, second=0, microsecond=0
            )
            if start > moment:
                return start
    return moment + timedelta(days=30)


@dataclass(frozen=True)
class VoicePolicy:
    mode: str
    mandate_outbound_allowed: bool
    mandate_inbound_allowed: bool
    external_actions: bool
    cli_expected: str


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
        cli_expected=str(identity.get('phone_voice_number') or ''),
    )


def default_ledger_path(root: Path | None = None) -> Path:
    base = root or system_root()
    return base / 'state/voice/voice.db'


def call_limits(canon_path: Path) -> tuple[int, int, CallHours]:
    """Appels par jour, appels à une même personne sur 30 jours, et les
    jours et heures d'appel.

    Lus dans les réglages en vigueur (page Policy) : « Appels passés au
    plus, par jour » (famille « Canaux »), et, pour le pays par défaut,
    « Prises de contact au plus, par personne, sur 30 jours » et ses jours
    et heures d'appel. Une seule valeur, en base : pas de réglage en double
    (Q78).
    """
    with closing(open_db(canon_path)) as canon:
        pol = policy_en_vigueur(canon)
    zones = pol['calling_zones']
    return (
        int(pol['channels']['voice']['max_per_day']),
        int(zones[zones['default']]['contact_per_30d']),
        call_hours(pol),
    )
