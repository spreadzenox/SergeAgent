#!/usr/bin/env python3
"""L'horaire d'un déclencheur : le vérifier, et savoir s'il est l'heure.

Un déclencheur ``every`` part toutes les N minutes ; un déclencheur ``at``
part à une heure fixe, certains jours. Ce fichier ne lit pas la base : il
sert au remplissage de la base (vérifier) et aux files (déclencher).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Les jours d'un déclencheur « à heure fixe », dans l'ordre de la semaine.
# Exemple : « lun,jeu » à 08:30 = chaque lundi et chaque jeudi à 8 h 30.
# Aucun jour = tous les jours.
DAYS = ('lun', 'mar', 'mer', 'jeu', 'ven', 'sam', 'dim')
_HEURE = re.compile(r'^([01][0-9]|2[0-3]):[0-5][0-9]$')


def schedule_error(event: str, every: int, at_time: str, at_days: str) -> str:
    """Ce qui ne va pas dans l'horaire d'un déclencheur, ou ``''``.

    Exemple : ``at`` à « 8h30 » est refusé (« 08:30 » est attendu), et le
    jour « mon » aussi (« lun » est attendu).
    """
    if event == 'every' and every <= 0:
        return 'every_minutes doit être un nombre de minutes positif'
    if event != 'at':
        return ''
    if not _HEURE.match(at_time):
        return f'heure « {at_time} » invalide (attendu : 08:30)'
    for day in (d.strip() for d in at_days.split(',') if d.strip()):
        if day not in DAYS:
            return f'jour « {day} » inconnu (attendu : {", ".join(DAYS)})'
    return ''


def due_slot(
    event: str,
    every: int,
    at_time: str,
    at_days: str,
    last: str,
    now: datetime,
    zone: ZoneInfo,
) -> str:
    """Le créneau à déclencher maintenant, ou ``''``."""
    if event == 'every':
        if every <= 0:
            return ''
        if last and now - datetime.fromisoformat(last) < timedelta(
            minutes=every
        ):
            return ''
        return now.isoformat(timespec='minutes')
    local = now.astimezone(zone)
    days = {d.strip() for d in at_days.split(',') if d.strip()}
    if days and DAYS[local.weekday()] not in days:
        return ''
    try:
        hour, minute = (int(x) for x in at_time.split(':'))
    except ValueError:
        return ''
    target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local < target:
        return ''
    slot = target.isoformat(timespec='minutes')
    if last and datetime.fromisoformat(last) >= target:
        return ''
    return slot
