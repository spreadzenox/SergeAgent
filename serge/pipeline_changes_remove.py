#!/usr/bin/env python3
"""Retirer une pièce d'un objet déjà en base, une seule fois.

Les sortes de modification ``remove_*`` de la section ``changes`` de
``config/pipeline.yaml`` (voir ``serge/pipeline_changes.py``) : un champ de
la réponse d'une invocation, une valeur d'une de ses écritures, une
colonne lue par un outil de lecture, un outil d'une invocation, ou une
condition d'un déclencheur. Exemple : le navigateur du constructeur, quand
seul le relecteur essaie le produit (lot 11).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.seed_base import PipelineSeedError


def invocation_absente(conn: sqlite3.Connection, invocation: str) -> bool:
    return not conn.execute(
        'SELECT 1 FROM invocations WHERE id=?', (invocation,)
    ).fetchone()


def _textes(raw: Any, quoi: str) -> list[str]:
    if not isinstance(raw, list) or not all(
        isinstance(x, str) and x for x in raw
    ):
        raise PipelineSeedError(f'changes : {quoi}, une liste de noms')
    return list(raw)


def remove_outputs(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Retire des champs de la réponse d'une invocation déjà en base, avec
    leurs sous-champs (``faq`` retire aussi ``faq.question``)."""
    paths = _textes(raw, 'remove_outputs')
    if invocation_absente(conn, invocation):
        return 'objet absent'
    parts = []
    for path in paths:
        retires = conn.execute(
            'DELETE FROM invocation_output_fields WHERE invocation_id=?'
            ' AND (path=? OR path LIKE ?)',
            (invocation, path, f'{path}.%'),
        ).rowcount
        parts.append(f'{path} retiré' if retires else f'{path} déjà absent')
    return ' ; '.join(parts)


def remove_write_values(
    conn: sqlite3.Connection, invocation: str, write: Any, raw: Any
) -> str:
    """Retire des valeurs d'une écriture d'une invocation déjà en base (son
    rang ``write``) : la colonne n'est plus écrite."""
    columns = _textes(raw, 'remove_write_values')
    if not isinstance(write, int):
        raise PipelineSeedError('changes : remove_write_values, un rang write')
    if invocation_absente(conn, invocation):
        return 'objet absent'
    row = conn.execute(
        'SELECT id FROM invocation_writes WHERE invocation_id=? AND position=?',
        (invocation, write),
    ).fetchone()
    if row is None:
        return 'écriture absente'
    parts = []
    for column in columns:
        retires = conn.execute(
            'DELETE FROM invocation_write_values WHERE write_id=?'
            ' AND column_name=?',
            (row[0], column),
        ).rowcount
        parts.append(
            f'{column} retiré' if retires else f'{column} déjà absent'
        )
    return ' ; '.join(parts)


def remove_tool_columns(conn: sqlite3.Connection, tool: str, raw: Any) -> str:
    """Retire des colonnes lues par un outil de lecture déjà en base."""
    if not isinstance(raw, list) or not all(
        isinstance(c, Mapping) and c.get('table') and c.get('name')
        for c in raw
    ):
        raise PipelineSeedError(
            'changes : remove_tool_columns, une liste de {table, name}'
        )
    if not conn.execute('SELECT 1 FROM tools WHERE id=?', (tool,)).fetchone():
        return 'objet absent'
    parts = []
    for col in raw:
        retires = conn.execute(
            'DELETE FROM tool_db_columns WHERE tool_id=? AND table_name=?'
            ' AND column_name=?',
            (tool, str(col['table']), str(col['name'])),
        ).rowcount
        nom = f'{col["table"]}.{col["name"]}'
        parts.append(f'{nom} retiré' if retires else f'{nom} déjà absent')
    return ' ; '.join(parts)


def remove_tools(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Retire des outils d'une invocation déjà en base, avec leurs
    paramètres figés. Exemple : le navigateur du constructeur, quand seul
    le relecteur essaie le produit."""
    outils = _textes(raw, 'remove_tools')
    if invocation_absente(conn, invocation):
        return 'objet absent'
    parts = []
    for tool in outils:
        liens = [
            r[0]
            for r in conn.execute(
                'SELECT id FROM invocation_tools WHERE invocation_id=?'
                ' AND tool_id=?',
                (invocation, tool),
            ).fetchall()
        ]
        for lien in liens:
            conn.execute(
                'DELETE FROM invocation_tool_params WHERE invocation_tool_id=?',
                (lien,),
            )
            conn.execute('DELETE FROM invocation_tools WHERE id=?', (lien,))
        parts.append(f'{tool} retiré' if liens else f'{tool} déjà absent')
    return ' ; '.join(parts)


def remove_trigger_conditions(
    conn: sqlite3.Connection, trigger: str, raw: Any
) -> str:
    """Retire des conditions d'un déclencheur déjà en base (les quotas dont
    il dépendait). Exemple : un bouton d'essai ne dépend plus des places
    de test (lot 12)."""
    quotas = _textes(raw, 'remove_trigger_conditions')
    if not conn.execute(
        'SELECT 1 FROM triggers WHERE id=?', (trigger,)
    ).fetchone():
        return 'objet absent'
    parts = []
    for quota in quotas:
        retires = conn.execute(
            'DELETE FROM trigger_conditions WHERE trigger_id=? AND quota_id=?',
            (trigger, quota),
        ).rowcount
        parts.append(f'{quota} retiré' if retires else f'{quota} déjà absent')
    return ' ; '.join(parts)
