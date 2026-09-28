#!/usr/bin/env python3
"""Les réglages d'une invocation, et les endroits où ils servent.

Un réglage est une valeur nommée, rangée avec l'invocation
(``invocation_settings``). Exemple : « nombre_idees = 2 » pour « Formuler
des idées ». Le même réglage sert dans le prompt (« Propose
{nombre_idees} idées »), dans le format de la réponse (une liste
d'exactement ``nombre_idees`` éléments), dans l'écriture (au plus N
lignes, ou une colonne qui reçoit la valeur) et dans les paramètres des
outils et des liens. Quand Julien change la valeur dans Mission Control,
tout suit au prochain appel.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from typing import Any


class SettingError(ValueError):
    """Un réglage manque, ou sa valeur ne convient pas."""


_REPERE = re.compile(r'\{([a-z][a-z0-9_]*)\}')


def load_settings(
    conn: sqlite3.Connection, invocation_id: str
) -> dict[str, str]:
    """Les réglages d'une invocation : ``{nom: valeur}``."""
    return {
        str(name): str(value)
        for name, value in conn.execute(
            'SELECT name, value FROM invocation_settings WHERE invocation_id=?',
            (invocation_id,),
        ).fetchall()
    }


def fill_prompt(text: str, settings: dict[str, str]) -> str:
    """Remplace ``{nom}`` par la valeur du réglage.

    Un repère qui ne désigne aucun réglage est laissé tel quel : un prompt
    peut contenir des accolades pour d'autres raisons (un exemple JSON).
    """
    return _REPERE.sub(lambda m: settings.get(m.group(1), m.group(0)), text)


def resolve_count(text: str, settings: dict[str, str]) -> int | None:
    """Un nombre écrit tel quel, ou le nom d'un réglage ; vide = aucun.

    Exemples : ``'3'`` donne 3 ; ``'nombre_idees'`` donne la valeur du
    réglage ; ``''`` donne ``None`` (pas de limite).

    Raises:
        SettingError: Réglage inconnu, ou valeur qui n'est pas un nombre
            entier positif ou nul.
    """
    raw = text.strip()
    if not raw:
        return None
    value = raw if raw.isdigit() else settings.get(raw)
    if value is None:
        raise SettingError(f'réglage inconnu : {raw}')
    if not str(value).strip().isdigit():
        raise SettingError(f'{raw} doit être un nombre entier : {value!r}')
    return int(str(value).strip())


def check_setting(
    kind: str, value: str, min_value: str, max_value: str
) -> str:
    """Ce qui ne va pas dans la valeur d'un réglage, ou ``''``.

    Exemple : « 12 » pour un nombre entre 1 et 10 est refusé.
    """
    if kind == 'bool':
        return '' if value in ('0', '1') else 'oui/non attendu (0 ou 1)'
    if kind != 'number':
        return ''
    try:
        number = float(value)
    except ValueError:
        return f'nombre attendu : {value!r}'
    if min_value and number < float(min_value):
        return f'au moins {min_value}'
    if max_value and number > float(max_value):
        return f'au plus {max_value}'
    return ''


def seed_settings(
    conn: sqlite3.Connection, invocation_id: str, raw: Any
) -> None:
    """Range les réglages de départ d'une invocation (``pipeline.yaml``).

    Format : ``{nom: {type, value, min, max, description, policy}}``.
    Exemple : ``nombre_idees: {value: 2, min: 1, max: 10, policy: true}``.

    Raises:
        SettingError: Format invalide, ou valeur hors de ses bornes.
    """
    if raw in (None, {}):
        return
    if not isinstance(raw, Mapping):
        raise SettingError(f'{invocation_id}.settings doit être un objet')
    for name, spec in raw.items():
        where = f'{invocation_id}.settings.{name}'
        if not isinstance(spec, Mapping) or 'value' not in spec:
            raise SettingError(f'{where} : value manquant')
        kind = str(spec.get('type', 'number'))
        value = str(spec['value'])
        low, high = str(spec.get('min', '')), str(spec.get('max', ''))
        probleme = check_setting(kind, value, low, high)
        if probleme:
            raise SettingError(f'{where} : {probleme}')
        conn.execute(
            'INSERT INTO invocation_settings(invocation_id, name, type, value,'
            ' min_value, max_value, description, policy, updated_by)'
            ' VALUES(?,?,?,?,?,?,?,?,?)',
            (
                invocation_id,
                str(name),
                kind,
                value,
                low,
                high,
                str(spec.get('description', '')).strip(),
                int(bool(spec.get('policy', False))),
                'pipeline.yaml',
            ),
        )
