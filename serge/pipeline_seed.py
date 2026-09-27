#!/usr/bin/env python3
"""Remplir la base avec le pipeline de départ (``config/pipeline.yaml``).

Ce fichier ne sert qu'à remplir la base d'une nouvelle instance, et à
ajouter sur une instance existante les objets nouveaux. Après
l'initialisation, la base est la seule source de vérité :

1. un objet déjà en base n'est jamais modifié, même si le fichier change ;
2. un objet supprimé dans Mission Control (``deleted_at`` rempli) n'est
   jamais recréé ;
3. un objet est ajouté en entier (une invocation avec ses outils, ses
   champs de réponse et ses règles d'écriture), ou pas du tout.

Exemple : Julien change dans Mission Control le prompt d'une invocation ;
un développeur change ensuite le prompt dans le fichier ; au démarrage,
l'instance de Julien garde son prompt, une nouvelle instance reçoit celui
du fichier.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
FILENAME = 'pipeline.yaml'


class PipelineSeedError(ValueError):
    """Le fichier du pipeline de départ est mal formé."""


def _list(data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = data.get(key) or []
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise PipelineSeedError(f'{key} : une liste d’objets est attendue')
    return value


def _params(raw: Any, where: str) -> list[tuple[str, str, str]]:
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


def _exists(
    conn: sqlite3.Connection, table: str, column: str, value: str
) -> bool:
    return (
        conn.execute(
            f'SELECT 1 FROM {table} WHERE {column}=?', (value,)
        ).fetchone()
        is not None
    )


def _seed_simple(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for queue in _list(data, 'queues'):
        conn.execute(
            'INSERT OR IGNORE INTO queues(id, title) VALUES(?,?)',
            (str(queue['id']), str(queue.get('title', ''))),
        )
    for model in _list(data, 'llm_models'):
        conn.execute(
            'INSERT OR IGNORE INTO llm_models(tier, provider, model)'
            ' VALUES(?,?,?)',
            (
                str(model['tier']),
                str(model.get('provider', '')),
                str(model.get('model', '')),
            ),
        )
    for text in _list(data, 'serge_texts'):
        conn.execute(
            'INSERT OR IGNORE INTO serge_texts(id, body, updated_at)'
            ' VALUES(?,?,?)',
            (str(text['id']), str(text.get('body', '')).strip(), ''),
        )


def _seed_rules(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for table in _list(data, 'writable_tables'):
        name = str(table['table'])
        if _exists(conn, 'writable_tables', 'table_name', name):
            continue
        conn.execute(
            'INSERT INTO writable_tables(table_name, can_insert, can_update,'
            ' description) VALUES(?,?,?,?)',
            (
                name,
                int(bool(table.get('insert'))),
                int(bool(table.get('update'))),
                str(table.get('description', '')),
            ),
        )
        for column in _list(table, 'columns'):
            conn.execute(
                'INSERT INTO writable_columns(table_name, column_name,'
                ' description) VALUES(?,?,?)',
                (
                    name,
                    str(column['name']),
                    str(column.get('description', '')),
                ),
            )
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for rule in _list(data, 'status_transitions'):
        key = (str(rule['table']), str(rule['column']))
        groups.setdefault(key, []).append(rule)
    for (table, column), rules in groups.items():
        if conn.execute(
            'SELECT 1 FROM status_transitions WHERE table_name=?'
            ' AND column_name=?',
            (table, column),
        ).fetchone():
            continue
        for rule in rules:
            conn.execute(
                'INSERT INTO status_transitions(table_name, column_name,'
                ' from_value, to_value) VALUES(?,?,?,?)',
                (table, column, str(rule.get('from', '')), str(rule['to'])),
            )
    for rule in _list(data, 'dedup_rules'):
        ident = str(rule['id'])
        if _exists(conn, 'dedup_rules', 'id', ident):
            continue
        conn.execute(
            'INSERT INTO dedup_rules(id, table_name, method, threshold,'
            ' on_duplicate) VALUES(?,?,?,?,?)',
            (
                ident,
                str(rule['table']),
                str(rule['method']),
                int(rule.get('threshold', 100)),
                str(rule.get('on_duplicate', 'skip')),
            ),
        )
        for column in rule.get('columns') or []:
            conn.execute(
                'INSERT INTO dedup_rule_columns(rule_id, column_name)'
                ' VALUES(?,?)',
                (ident, str(column)),
            )


def _seed_invocation(conn: sqlite3.Connection, inv: Mapping[str, Any]) -> None:
    ident = str(inv['id'])
    kind = str(inv.get('type', 'llm'))
    conn.execute(
        'INSERT INTO invocations(id, title, role, step_id, type, enabled,'
        ' queue_id, priority, model_tier, prompt, gets_serge_intro,'
        ' default_max_rows, max_tool_turns, capability_id, origin,'
        ' updated_by) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            ident,
            str(inv.get('title', '')),
            str(inv.get('role', '')).strip(),
            str(inv.get('step', '')),
            kind,
            int(bool(inv.get('enabled', True))),
            str(inv.get('queue', 'works')),
            int(inv.get('priority', 10)),
            str(inv.get('model_tier', 'mid' if kind == 'llm' else '')),
            str(inv.get('prompt', '')).strip(),
            int(bool(inv.get('gets_serge_intro', False))),
            int(inv.get('default_max_rows', 50)),
            int(inv.get('max_tool_turns', 12)),
            str(inv.get('capability', '')),
            'code',
            'pipeline.yaml',
        ),
    )
    for name, source, value in _params(inv.get('params'), ident):
        conn.execute(
            'INSERT INTO invocation_tool_params(invocation_id,'
            ' invocation_tool_id, param_name, source, value)'
            ' VALUES(?,0,?,?,?)',
            (ident, name, source, value),
        )
    for position, tool in enumerate(_list(inv, 'tools')):
        cursor = conn.execute(
            'INSERT INTO invocation_tools(invocation_id, tool_id, mode, label,'
            ' max_rows, position) VALUES(?,?,?,?,?,?)',
            (
                ident,
                str(tool['tool']),
                str(tool.get('mode', 'callable')),
                str(tool.get('label', '')),
                int(tool.get('max_rows', 0)),
                position,
            ),
        )
        for name, source, value in _params(tool.get('params'), ident):
            conn.execute(
                'INSERT INTO invocation_tool_params(invocation_id,'
                ' invocation_tool_id, param_name, source, value)'
                ' VALUES(?,?,?,?,?)',
                (ident, cursor.lastrowid, name, source, value),
            )
    for position, out in enumerate(_list(inv, 'output')):
        conn.execute(
            'INSERT INTO invocation_output_fields(invocation_id, path, type,'
            ' choices, required, description, position)'
            ' VALUES(?,?,?,?,?,?,?)',
            (
                ident,
                str(out['path']),
                str(out['type']),
                ', '.join(str(c) for c in out.get('choices') or []),
                int(bool(out.get('required', True))),
                str(out.get('description', '')),
                position,
            ),
        )
    write_ids: list[int] = []
    for position, write in enumerate(_list(inv, 'writes')):
        parent = write.get('parent')
        parent_id = 0
        if parent is not None:
            if not isinstance(parent, int) or not 0 <= parent < position:
                raise PipelineSeedError(
                    f'{ident}.writes[{position}] : parent doit désigner une'
                    ' écriture précédente'
                )
            parent_id = write_ids[parent]
        key = write.get('key') or {}
        cursor = conn.execute(
            'INSERT INTO invocation_writes(invocation_id, position,'
            ' table_name, operation, for_each, parent_write_id, key_column,'
            ' key_source, key_value) VALUES(?,?,?,?,?,?,?,?,?)',
            (
                ident,
                position,
                str(write['table']),
                str(write['operation']),
                str(write.get('for_each', '')),
                parent_id,
                str(key.get('column', '')),
                str(key.get('source', '')),
                str(key.get('value', '')),
            ),
        )
        write_id = int(cursor.lastrowid or 0)
        write_ids.append(write_id)
        for column, source, value in _params(write.get('values'), ident):
            conn.execute(
                'INSERT INTO invocation_write_values(write_id, column_name,'
                ' source, value) VALUES(?,?,?,?)',
                (write_id, column, source, value),
            )


def _write_id(conn: sqlite3.Connection, invocation: str, position: Any) -> int:
    if position is None:
        return 0
    row = conn.execute(
        'SELECT id FROM invocation_writes WHERE invocation_id=?'
        ' AND position=?',
        (invocation, int(position)),
    ).fetchone()
    if row is None:
        raise PipelineSeedError(
            f'lien depuis {invocation} : écriture {position} introuvable'
        )
    return int(row[0])


def _seed_links(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for link in _list(data, 'links'):
        ident = str(link['id'])
        if _exists(conn, 'links', 'id', ident):
            continue
        origin = str(link['from'])
        for end in (origin, str(link['to'])):
            if not _exists(conn, 'invocations', 'id', end):
                raise PipelineSeedError(
                    f'lien {ident} : invocation {end} inconnue'
                )
        conn.execute(
            'INSERT INTO links(id, title, from_invocation_id,'
            ' to_invocation_id, mode, write_id, auto, enabled, origin,'
            ' updated_by) VALUES(?,?,?,?,?,?,?,?,?,?)',
            (
                ident,
                str(link.get('title', '')),
                origin,
                str(link['to']),
                str(link.get('mode', 'on_finish')),
                _write_id(conn, origin, link.get('write')),
                int(bool(link.get('auto', True))),
                int(bool(link.get('enabled', True))),
                'code',
                'pipeline.yaml',
            ),
        )
        for name, source, value in _params(link.get('params'), ident):
            conn.execute(
                'INSERT INTO link_params(link_id, param_name, source, value)'
                ' VALUES(?,?,?,?)',
                (ident, name, source, value),
            )


def _seed_triggers(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for trig in _list(data, 'triggers'):
        ident = str(trig['id'])
        if _exists(conn, 'triggers', 'id', ident):
            continue
        if not _exists(conn, 'invocations', 'id', str(trig['invocation'])):
            raise PipelineSeedError(
                f'déclencheur {ident} : invocation {trig["invocation"]} inconnue'
            )
        conn.execute(
            'INSERT INTO triggers(id, title, invocation_id, event, table_name,'
            ' filter_column, filter_value, every_minutes, at_time, at_days,'
            ' enabled, origin, updated_by)'
            ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                ident,
                str(trig.get('title', '')),
                str(trig['invocation']),
                str(trig['event']),
                str(trig.get('table', '')),
                str(trig.get('filter_column', '')),
                str(trig.get('filter_value', '')),
                int(trig.get('every_minutes', 0)),
                str(trig.get('at_time', '')),
                str(trig.get('at_days', '')),
                int(bool(trig.get('enabled', True))),
                'code',
                'pipeline.yaml',
            ),
        )
        for name, source, value in _params(trig.get('params'), ident):
            conn.execute(
                'INSERT INTO trigger_params(trigger_id, param_name, source,'
                ' value) VALUES(?,?,?,?)',
                (ident, name, source, value),
            )


def seed_pipeline(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    """Ajoute en base ce que décrit ``data``, sans rien écraser.

    Args:
        conn: Canon (commit par l'appelant).
        data: Le contenu de ``pipeline.yaml``.

    Raises:
        PipelineSeedError: Fichier mal formé.
    """
    if data.get('schema_version') != SCHEMA_VERSION:
        raise PipelineSeedError('schema_version doit valoir 1')
    _seed_simple(conn, data)
    _seed_rules(conn, data)
    for inv in _list(data, 'invocations'):
        if not _exists(conn, 'invocations', 'id', str(inv['id'])):
            _seed_invocation(conn, inv)
    _seed_links(conn, data)
    _seed_triggers(conn, data)


def ensure_pipeline(
    conn: sqlite3.Connection, directory: Path | None = None
) -> None:
    """Lit ``pipeline.yaml`` et remplit la base (appelé au démarrage).

    Sans fichier (un dossier de config de test, par exemple), il n'y a
    rien à ajouter.

    Args:
        conn: Canon (commit par l'appelant).
        directory: Dossier de config (défaut : celui du dépôt).
    """
    from serge.policy import config_dir, read_yaml_file

    path = (directory or config_dir()) / FILENAME
    if path.is_file():
        seed_pipeline(conn, read_yaml_file(path))
