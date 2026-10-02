#!/usr/bin/env python3
"""Le format de la réponse d'une invocation : le décrire, puis le vérifier.

Le format est lu dans ``invocation_output_fields``. Un champ contenu dans
une liste a un chemin avec un point : ``fiches`` est une liste,
``fiches.title`` le titre de chaque fiche. Une liste sans champ déclaré
à l'intérieur est une liste de textes, par exemple ``fiches.pages``.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from typing import Any

from serge.interpreter.settings import load_settings, resolve_count


@dataclass(frozen=True)
class Field:
    path: str
    type: str
    choices: tuple[str, ...]
    required: bool
    description: str
    min_items: int | None = None
    max_items: int | None = None

    @property
    def parent(self) -> str:
        return self.path.rpartition('.')[0]

    @property
    def name(self) -> str:
        return self.path.rpartition('.')[2]


def load_fields(conn: sqlite3.Connection, invocation_id: str) -> list[Field]:
    """Les champs attendus, dans l'ordre déclaré.

    Le nombre d'éléments d'une liste est un nombre, ou le nom d'un réglage
    de l'invocation, lu à chaque appel.
    """
    settings = load_settings(conn, invocation_id)
    return [
        Field(
            str(path),
            str(kind),
            tuple(c.strip() for c in str(choices).split(',') if c.strip()),
            bool(required),
            str(description),
            resolve_count(str(low), settings),
            resolve_count(str(high), settings),
        )
        for path, kind, choices, required, description, low, high in (
            conn.execute(
                'SELECT path, type, choices, required, description,'
                ' min_items, max_items FROM invocation_output_fields'
                ' WHERE invocation_id=? ORDER BY position',
                (invocation_id,),
            ).fetchall()
        )
    ]


def _count_text(field: Field) -> str:
    """« exactement 2 éléments », « au plus 3 éléments »…, ou ``''``."""
    low, high = field.min_items, field.max_items
    if low is not None and low == high:
        return f'exactement {low} élément(s)'
    if low is not None and high is not None:
        return f'entre {low} et {high} éléments'
    if low is not None:
        return f'au moins {low} élément(s)'
    if high is not None:
        return f'au plus {high} élément(s)'
    return ''


_EXEMPLES = {'text': '"…"', 'number': '0', 'bool': 'true', 'choice': '"…"'}


def _example(fields: list[Field], parent: str) -> str:
    parts = []
    for field in (f for f in fields if f.parent == parent):
        if field.type == 'list':
            inner = [f for f in fields if f.parent == field.path]
            item = _example(fields, field.path) if inner else '"…"'
            parts.append(f'"{field.name}": [{item}]')
        else:
            parts.append(f'"{field.name}": {_EXEMPLES[field.type]}')
    return '{' + ', '.join(parts) + '}'


def describe_format(fields: list[Field], intro: str) -> str:
    """Le texte qui explique au modèle ce qu'il doit rendre.

    ``intro`` est la première phrase, réglée sur la page Pipeline
    (« Ta réponse finale est un seul objet JSON… ») ; vide, elle n'est pas
    envoyée.
    """
    if not fields:
        return ''
    lines = [
        *([intro] if intro else []),
        _example(fields, ''),
        'Les champs :',
    ]
    for field in fields:
        detail = field.description or ''
        if field.choices:
            detail += f' Valeurs permises : {", ".join(field.choices)}.'
        if _count_text(field):
            detail += f' Liste de {_count_text(field)}.'
        need = 'obligatoire' if field.required else 'facultatif'
        lines.append(
            f'- {field.path} ({field.type}, {need}) : {detail}'.rstrip()
        )
    return '\n'.join(lines)


def parse_answer(text: str) -> Any:
    """Lit l'objet JSON de la réponse, même entouré de ```json … ```."""
    cleaned = text.strip()
    fenced = re.search(r'```(?:json)?\s*(.*?)```', cleaned, re.S)
    if fenced:
        cleaned = fenced.group(1).strip()
    return json.loads(cleaned)


def _check_value(field: Field, value: Any, where: str) -> list[str]:
    ok = {
        'text': isinstance(value, str),
        'number': isinstance(value, (int, float))
        and not isinstance(value, bool),
        'bool': isinstance(value, bool),
        'list': isinstance(value, list),
        'choice': isinstance(value, str) and value in field.choices,
    }[field.type]
    if ok:
        return []
    if field.type == 'choice':
        return [f'{where} doit valoir l’une de : {", ".join(field.choices)}']
    return [f'{where} doit être de type {field.type}']


def _check_object(
    fields: list[Field], parent: str, obj: Any, where: str
) -> list[str]:
    if not isinstance(obj, dict):
        return [f'{where or "la réponse"} doit être un objet JSON']
    errors: list[str] = []
    for field in (f for f in fields if f.parent == parent):
        label = f'{where}.{field.name}' if where else field.name
        if field.name not in obj or obj[field.name] is None:
            if field.required:
                errors.append(f'{label} manque')
            continue
        value = obj[field.name]
        errors.extend(_check_value(field, value, label))
        if field.type == 'list' and isinstance(value, list):
            low, high = field.min_items, field.max_items
            if (low is not None and len(value) < low) or (
                high is not None and len(value) > high
            ):
                errors.append(
                    f'{label} doit contenir {_count_text(field)}'
                    f' (reçu : {len(value)})'
                )
            inner = [f for f in fields if f.parent == field.path]
            for index, item in enumerate(value):
                if inner:
                    errors.extend(
                        _check_object(
                            fields, field.path, item, f'{label}[{index}]'
                        )
                    )
                elif not isinstance(item, (str, int, float)):
                    errors.append(f'{label}[{index}] doit être un texte')
    return errors


def check_answer(fields: list[Field], answer: Any) -> list[str]:
    """Les écarts entre la réponse et le format ; vide si tout va bien."""
    return _check_object(fields, '', answer, '')
