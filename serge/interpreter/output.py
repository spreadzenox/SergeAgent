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


@dataclass(frozen=True)
class Field:
    path: str
    type: str
    choices: tuple[str, ...]
    required: bool
    description: str

    @property
    def parent(self) -> str:
        return self.path.rpartition('.')[0]

    @property
    def name(self) -> str:
        return self.path.rpartition('.')[2]


def load_fields(conn: sqlite3.Connection, invocation_id: str) -> list[Field]:
    """Les champs attendus, dans l'ordre déclaré."""
    return [
        Field(
            str(path),
            str(kind),
            tuple(c.strip() for c in str(choices).split(',') if c.strip()),
            bool(required),
            str(description),
        )
        for path, kind, choices, required, description in conn.execute(
            'SELECT path, type, choices, required, description'
            ' FROM invocation_output_fields WHERE invocation_id=?'
            ' ORDER BY position',
            (invocation_id,),
        ).fetchall()
    ]


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


def describe_format(fields: list[Field]) -> str:
    """Le texte qui explique au modèle ce qu'il doit rendre."""
    if not fields:
        return ''
    lines = [
        'Ta réponse finale est un seul objet JSON, sans texte autour, de'
        ' cette forme :',
        _example(fields, ''),
        'Les champs :',
    ]
    for field in fields:
        detail = field.description or ''
        if field.choices:
            detail += f' Valeurs permises : {", ".join(field.choices)}.'
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
