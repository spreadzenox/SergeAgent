#!/usr/bin/env python3
"""Les types de tickets, en base (décision Q85).

Ils sont remplis au démarrage depuis ``config/ticket-types.yaml`` : un type
nouveau s'ajoute, un type déjà en base n'est jamais touché. Le délai
d'expiration, la décision par défaut annoncée et les boutons se règlent
dans Mission Control ; le reste de la déclaration (rôle, champs, couleur
et emoji de la carte…) est gardé tel quel.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from serge.horloge import iso_utc
from serge.tickets.acts import BOUTONS

# Ce que Mission Control règle ; le reste reste dans ``spec_json``.
_REGLES = ('expiry_hours', 'expiry_minutes', 'default_detail', 'buttons')


def _minutes(spec: dict[str, Any]) -> int | None:
    """Le délai d'expiration de la déclaration, en minutes (``None`` :
    jamais). Exemple : ``expiry_hours: 48`` → 2880."""
    hours = spec.get('expiry_hours')
    if hours is not None:
        return int(float(hours) * 60)
    minutes = spec.get('expiry_minutes')
    if isinstance(minutes, list):
        minutes = minutes[0] if minutes else None
    return int(minutes) if minutes is not None else None


def ensure_ticket_types(
    conn: sqlite3.Connection, directory: Path | None = None
) -> None:
    """Ajoute en base les types de tickets nouveaux du fichier de départ.

    Sans fichier (un dossier de config de test, par exemple), il n'y a rien
    à ajouter.
    """
    from serge.policy import config_dir
    from serge.registry import load_ticket_types

    if not ((directory or config_dir()) / 'ticket-types.yaml').is_file():
        return
    for name, spec in load_ticket_types(directory).items():
        if conn.execute(
            'SELECT 1 FROM ticket_types WHERE id=?', (name,)
        ).fetchone():
            continue
        reste = {k: v for k, v in spec.items() if k not in _REGLES}
        conn.execute(
            'INSERT INTO ticket_types(id, expiry_minutes, default_detail,'
            ' buttons_json, spec_json, updated_by, updated_at)'
            ' VALUES(?,?,?,?,?,?,?)',
            (
                name,
                _minutes(spec),
                str(spec.get('default_detail') or ''),
                json.dumps(list(spec.get('buttons') or [])),
                json.dumps(reste, ensure_ascii=False),
                'ticket-types.yaml',
                iso_utc(),
            ),
        )


def ticket_types(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Les types de tickets en vigueur : ``{type: déclaration}``.

    La déclaration a la forme du fichier de départ : ``expiry_minutes``
    (``None`` : jamais), ``default``, ``default_detail``, ``buttons``,
    ``fields``, ``render``…
    """
    out: dict[str, dict[str, Any]] = {}
    for ident, minutes, detail, buttons, spec in conn.execute(
        'SELECT id, expiry_minutes, default_detail, buttons_json, spec_json'
        ' FROM ticket_types ORDER BY id'
    ).fetchall():
        declaration = dict(json.loads(spec or '{}'))
        declaration['expiry_minutes'] = (
            int(minutes) if minutes is not None else None
        )
        declaration['default_detail'] = str(detail or '')
        declaration['buttons'] = list(json.loads(buttons or '[]'))
        out[str(ident)] = declaration
    return out


def set_ticket_type(
    conn: sqlite3.Connection,
    ident: str,
    by: str,
    *,
    expiry_minutes: int | None | str = '',
    default_detail: str | None = None,
    buttons: list[str] | None = None,
) -> str:
    """Change le délai, la décision par défaut annoncée ou les boutons d'un
    type ; rend ce qui ne va pas, ou ``''`` si c'est fait.

    ``expiry_minutes`` : un nombre de minutes, ``None`` pour « jamais »,
    ``''`` pour ne pas y toucher. Un nouveau délai vaut pour les tickets
    créés ensuite.
    """
    if not conn.execute(
        'SELECT 1 FROM ticket_types WHERE id=?', (ident,)
    ).fetchone():
        return f'type de ticket inconnu : {ident}'
    # Tout est vérifié avant d'écrire : un changement refusé ne laisse rien
    # à moitié fait.
    if expiry_minutes not in ('', None) and (
        isinstance(expiry_minutes, bool)
        or not isinstance(expiry_minutes, int)
        or not 1 <= expiry_minutes <= 60 * 24 * 30
    ):
        return 'délai : un nombre de minutes entre 1 et 43 200 (30 jours)'
    if buttons is not None:
        inconnus = [b for b in buttons if b not in BOUTONS]
        if inconnus:
            return f'boutons inconnus : {", ".join(inconnus)}'
        if not buttons:
            return 'au moins un bouton'
    if expiry_minutes != '':
        conn.execute(
            'UPDATE ticket_types SET expiry_minutes=? WHERE id=?',
            (expiry_minutes, ident),
        )
    if default_detail is not None:
        conn.execute(
            'UPDATE ticket_types SET default_detail=? WHERE id=?',
            (default_detail.strip(), ident),
        )
    if buttons is not None:
        conn.execute(
            'UPDATE ticket_types SET buttons_json=? WHERE id=?',
            (json.dumps(list(dict.fromkeys(buttons))), ident),
        )
    conn.execute(
        'UPDATE ticket_types SET updated_by=?, updated_at=? WHERE id=?',
        (by, iso_utc(), ident),
    )
    return ''
