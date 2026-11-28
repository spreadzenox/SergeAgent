#!/usr/bin/env python3
"""Les petites fonctions communes au remplissage du pipeline de départ.

Voir ``serge/pipeline_seed.py`` : ce fichier ne fait que ranger en base ce
que décrit ``config/pipeline.yaml``, sans rien écraser.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any


class PipelineSeedError(ValueError):
    """Le fichier du pipeline de départ est mal formé."""


def list_of(data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = data.get(key) or []
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise PipelineSeedError(f'{key} : une liste d’objets est attendue')
    return value


def params_of(raw: Any, where: str) -> list[tuple[str, str, str]]:
    """``{nom: {source, value}}`` → ``[(nom, source, value)]``."""
    if raw in (None, {}):
        return []
    if not isinstance(raw, Mapping):
        raise PipelineSeedError(f'{where} : params doit être un objet')
    out = []
    for name, spec in raw.items():
        if not isinstance(spec, Mapping) or 'source' not in spec:
            raise PipelineSeedError(f'{where}.{name} : source manquante')
        out.append(
            (str(name), str(spec['source']), str(spec.get('value', '')))
        )
    return out


def exists(
    conn: sqlite3.Connection, table: str, column: str, value: str
) -> bool:
    return (
        conn.execute(
            f'SELECT 1 FROM {table} WHERE {column}=?', (value,)
        ).fetchone()
        is not None
    )


def insert(
    conn: sqlite3.Connection, table: str, *, ignore: bool = False, **values
) -> int:
    """Ajoute une ligne ; rend son ``rowid``. Les noms viennent du code."""
    verb = 'INSERT OR IGNORE' if ignore else 'INSERT'
    cursor = conn.execute(
        f'{verb} INTO {table}({", ".join(values)})'
        f' VALUES({", ".join("?" for _ in values)})',
        tuple(values.values()),
    )
    return int(cursor.lastrowid or 0)


def seed_params(
    conn: sqlite3.Connection,
    table: str,
    owner: Mapping[str, Any],
    raw: Any,
    where: str,
    name_column: str = 'param_name',
) -> None:
    """Range des paramètres ``{nom: {source, value}}`` dans ``table``."""
    for name, source, value in params_of(raw, where):
        insert(
            conn,
            table,
            **owner,
            **{name_column: name},
            source=source,
            value=value,
        )


def seed_tool_link(
    conn: sqlite3.Connection,
    invocation_id: str,
    tool: Mapping[str, Any],
    position: int,
) -> None:
    """Un outil d'une invocation, avec ses paramètres.

    Format de ``tool`` : ``{tool, mode, label, max_rows, batch_size,
    max_calls, params}``, comme dans ``pipeline.yaml``.
    """
    link_id = insert(
        conn,
        'invocation_tools',
        invocation_id=invocation_id,
        tool_id=str(tool['tool']),
        mode=str(tool.get('mode', 'callable')),
        label=str(tool.get('label', '')),
        max_rows=int(tool.get('max_rows', 0)),
        batch_size=str(tool.get('batch_size', '')),
        max_calls=str(tool.get('max_calls', '')),
        position=position,
    )
    seed_params(
        conn,
        'invocation_tool_params',
        {'invocation_id': invocation_id, 'invocation_tool_id': link_id},
        tool.get('params'),
        invocation_id,
    )


# Les opérateurs d'une condition sur un lien ou une écriture.
CONDITION_OPS = frozenset({'=', '!=', 'non_vide'})


def condition_columns(raw: Any, where: str) -> tuple[str, str, str]:
    """Le champ, l'opérateur et la valeur d'une condition (YAML ``condition``).

    Exemple : ``condition: {field: reaction, op: '=', value: refus}``.

    Raises:
        PipelineSeedError: Opérateur inconnu.
    """
    cond = raw or {}
    op = str(cond.get('op', '=' if cond else ''))
    if cond and op not in CONDITION_OPS:
        raise PipelineSeedError(f'{where} : condition {op} inconnue')
    return str(cond.get('field', '')), op, str(cond.get('value', ''))


def seed_write(
    conn: sqlite3.Connection,
    ident: str,
    position: int,
    write: Mapping[str, Any],
) -> int:
    """Pose une règle d'écriture d'une invocation, à son rang ; rend son
    numéro. ``parent`` désigne le rang d'une écriture précédente."""
    where = f'{ident}.writes[{position}]'
    parent = write.get('parent')
    parent_id = 0
    if parent is not None:
        row = None
        if isinstance(parent, int) and 0 <= parent < position:
            row = conn.execute(
                'SELECT id FROM invocation_writes WHERE invocation_id=?'
                ' AND position=?',
                (ident, parent),
            ).fetchone()
        if row is None:
            raise PipelineSeedError(
                f'{where} : parent doit désigner une écriture précédente'
            )
        parent_id = int(row[0])
    key = write.get('key') or {}
    cond = condition_columns(write.get('condition'), where)
    write_id = insert(
        conn,
        'invocation_writes',
        invocation_id=ident,
        position=position,
        table_name=str(write['table']),
        operation=str(write['operation']),
        for_each=str(write.get('for_each', '')),
        parent_write_id=parent_id,
        key_column=str(key.get('column', '')),
        key_source=str(key.get('source', '')),
        key_value=str(key.get('value', '')),
        max_rows=str(write.get('max_rows', '')),
        condition_field=cond[0],
        condition_op=cond[1],
        condition_value=cond[2],
        skip_dedup=int(write.get('dedup', True) is False),
    )
    seed_params(
        conn,
        'invocation_write_values',
        {'write_id': write_id},
        write.get('values'),
        ident,
        'column_name',
    )
    return write_id
