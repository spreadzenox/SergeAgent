#!/usr/bin/env python3
"""Remplir la base avec le pipeline de départ (``config/pipeline.yaml``).

Ce fichier ne sert qu'à remplir la base d'une nouvelle instance, et à
ajouter sur une instance existante les objets nouveaux. Après
l'initialisation, la base est la seule source de vérité :

1. un objet déjà en base n'est jamais modifié, même si le fichier change ;
2. un objet supprimé dans Mission Control (``deleted_at`` rempli) n'est
   jamais recréé ;
3. un objet est ajouté en entier (une invocation avec ses outils, ses
   champs de réponse et ses règles d'écriture ; un outil de lecture avec
   son catalogue de tables, colonnes et filtres), ou pas du tout.

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


def _insert(
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


def _seed_simple(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for queue in _list(data, 'queues'):
        _insert(
            conn,
            'queues',
            ignore=True,
            id=str(queue['id']),
            title=str(queue.get('title', '')),
        )
    for model in _list(data, 'llm_models'):
        _insert(
            conn,
            'llm_models',
            ignore=True,
            tier=str(model['tier']),
            provider=str(model.get('provider', '')),
            model=str(model.get('model', '')),
        )
    for text in _list(data, 'serge_texts'):
        _insert(
            conn,
            'serge_texts',
            ignore=True,
            id=str(text['id']),
            body=str(text.get('body', '')).strip(),
            updated_at='',
        )


def _seed_tools(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    """Les outils : une capacité réglée pour un usage précis."""
    from serge.db.query_catalogue import seed_read_catalogue

    for tool in _list(data, 'tools'):
        ident = str(tool['id'])
        if _exists(conn, 'tools', 'id', ident):
            continue
        capability = str(tool['capability'])
        read = tool.get('read')
        if (read is not None) != (capability == 'db_read'):
            raise PipelineSeedError(
                f'outil {ident} : read est obligatoire pour db_read, et'
                ' seulement pour lui'
            )
        _insert(
            conn,
            'tools',
            id=ident,
            titre=str(tool.get('title', '')),
            doc_md=str(tool.get('doc', '')).strip(),
            capability_id=capability,
            montre_partout=int(bool(tool.get('everywhere', False))),
        )
        if isinstance(read, Mapping):
            seed_read_catalogue(conn, ident, read)


def _seed_rules(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for table in _list(data, 'writable_tables'):
        name = str(table['table'])
        if _exists(conn, 'writable_tables', 'table_name', name):
            continue
        _insert(
            conn,
            'writable_tables',
            table_name=name,
            can_insert=int(bool(table.get('insert'))),
            can_update=int(bool(table.get('update'))),
            description=str(table.get('description', '')),
        )
        for column in _list(table, 'columns'):
            _insert(
                conn,
                'writable_columns',
                table_name=name,
                column_name=str(column['name']),
                description=str(column.get('description', '')),
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
            _insert(
                conn,
                'status_transitions',
                table_name=table,
                column_name=column,
                from_value=str(rule.get('from', '')),
                to_value=str(rule['to']),
            )
    for quota in _list(data, 'table_quotas'):
        ident = str(quota['id'])
        if _exists(conn, 'table_quotas', 'id', ident):
            continue
        _insert(
            conn,
            'table_quotas',
            id=ident,
            table_name=str(quota['table']),
            column_name=str(quota['column']),
            counted_values=', '.join(str(v) for v in quota['values']),
            max_value=int(quota['max']),
            description=str(quota.get('description', '')).strip(),
            policy=int(bool(quota.get('policy', True))),
            updated_by='pipeline.yaml',
        )
    for rule in _list(data, 'dedup_rules'):
        ident = str(rule['id'])
        if _exists(conn, 'dedup_rules', 'id', ident):
            continue
        _insert(
            conn,
            'dedup_rules',
            id=ident,
            table_name=str(rule['table']),
            method=str(rule['method']),
            threshold=int(rule.get('threshold', 100)),
            on_duplicate=str(rule.get('on_duplicate', 'skip')),
        )
        for column in rule.get('columns') or []:
            _insert(
                conn,
                'dedup_rule_columns',
                rule_id=ident,
                column_name=str(column),
            )


def _seed_params(
    conn: sqlite3.Connection,
    table: str,
    owner: Mapping[str, Any],
    raw: Any,
    where: str,
    name_column: str = 'param_name',
) -> None:
    """Range des paramètres ``{nom: {source, value}}`` dans ``table``."""
    for name, source, value in _params(raw, where):
        _insert(
            conn,
            table,
            **owner,
            **{name_column: name},
            source=source,
            value=value,
        )


def _seed_writes(
    conn: sqlite3.Connection, ident: str, inv: Mapping[str, Any]
) -> None:
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
        write_id = _insert(
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
        )
        write_ids.append(write_id)
        _seed_params(
            conn,
            'invocation_write_values',
            {'write_id': write_id},
            write.get('values'),
            ident,
            'column_name',
        )


def _seed_invocation(conn: sqlite3.Connection, inv: Mapping[str, Any]) -> None:
    from serge.interpreter.settings import seed_settings

    ident = str(inv['id'])
    kind = str(inv.get('type', 'llm'))
    _insert(
        conn,
        'invocations',
        id=ident,
        title=str(inv.get('title', '')),
        role=str(inv.get('role', '')).strip(),
        step_id=str(inv.get('step', '')),
        type=kind,
        enabled=int(bool(inv.get('enabled', True))),
        queue_id=str(inv.get('queue', 'works')),
        priority=int(inv.get('priority', 10)),
        model_tier=str(inv.get('model_tier', 'mid' if kind == 'llm' else '')),
        prompt=str(inv.get('prompt', '')).strip(),
        gets_serge_intro=int(bool(inv.get('gets_serge_intro', False))),
        default_max_rows=int(inv.get('default_max_rows', 50)),
        max_tool_turns=int(inv.get('max_tool_turns', 12)),
        capability_id=str(inv.get('capability', '')),
        origin='code',
        updated_by='pipeline.yaml',
    )
    seed_settings(conn, ident, inv.get('settings'))
    _seed_params(
        conn,
        'invocation_tool_params',
        {'invocation_id': ident, 'invocation_tool_id': 0},
        inv.get('params'),
        ident,
    )
    for position, tool in enumerate(_list(inv, 'tools')):
        link_id = _insert(
            conn,
            'invocation_tools',
            invocation_id=ident,
            tool_id=str(tool['tool']),
            mode=str(tool.get('mode', 'callable')),
            label=str(tool.get('label', '')),
            max_rows=int(tool.get('max_rows', 0)),
            position=position,
        )
        _seed_params(
            conn,
            'invocation_tool_params',
            {'invocation_id': ident, 'invocation_tool_id': link_id},
            tool.get('params'),
            ident,
        )
    for position, out in enumerate(_list(inv, 'output')):
        _insert(
            conn,
            'invocation_output_fields',
            invocation_id=ident,
            path=str(out['path']),
            type=str(out['type']),
            choices=', '.join(str(c) for c in out.get('choices') or []),
            required=int(bool(out.get('required', True))),
            description=str(out.get('description', '')),
            min_items=str(out.get('min_items', '')),
            max_items=str(out.get('max_items', '')),
            position=position,
        )
    _seed_writes(conn, ident, inv)


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
        _insert(
            conn,
            'links',
            id=ident,
            title=str(link.get('title', '')),
            from_invocation_id=origin,
            to_invocation_id=str(link['to']),
            mode=str(link.get('mode', 'on_finish')),
            write_id=_write_id(conn, origin, link.get('write')),
            auto=int(bool(link.get('auto', True))),
            enabled=int(bool(link.get('enabled', True))),
            origin='code',
            updated_by='pipeline.yaml',
        )
        _seed_params(
            conn, 'link_params', {'link_id': ident}, link.get('params'), ident
        )


def _seed_triggers(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    from serge.interpreter.schedule import schedule_error

    for trig in _list(data, 'triggers'):
        ident = str(trig['id'])
        if _exists(conn, 'triggers', 'id', ident):
            continue
        if not _exists(conn, 'invocations', 'id', str(trig['invocation'])):
            raise PipelineSeedError(
                f'déclencheur {ident} : invocation {trig["invocation"]} inconnue'
            )
        horaire = schedule_error(
            str(trig['event']),
            int(trig.get('every_minutes', 0)),
            str(trig.get('at_time', '')),
            str(trig.get('at_days', '')),
        )
        if horaire:
            raise PipelineSeedError(f'déclencheur {ident} : {horaire}')
        _insert(
            conn,
            'triggers',
            id=ident,
            title=str(trig.get('title', '')),
            invocation_id=str(trig['invocation']),
            event=str(trig['event']),
            table_name=str(trig.get('table', '')),
            filter_column=str(trig.get('filter_column', '')),
            filter_value=str(trig.get('filter_value', '')),
            every_minutes=int(trig.get('every_minutes', 0)),
            at_time=str(trig.get('at_time', '')),
            at_days=str(trig.get('at_days', '')),
            enabled=int(bool(trig.get('enabled', True))),
            origin='code',
            updated_by='pipeline.yaml',
        )
        _seed_params(
            conn,
            'trigger_params',
            {'trigger_id': ident},
            trig.get('params'),
            ident,
        )


def seed_pipeline(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    """Ajoute en base ce que décrit ``data``, sans rien écraser.

    Args:
        conn: Connexion à la base (commit par l'appelant).
        data: Le contenu de ``pipeline.yaml``.

    Raises:
        PipelineSeedError: Fichier mal formé.
    """
    if data.get('schema_version') != SCHEMA_VERSION:
        raise PipelineSeedError('schema_version doit valoir 1')
    _seed_simple(conn, data)
    _seed_tools(conn, data)
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
        conn: Connexion à la base (commit par l'appelant).
        directory: Dossier de config (défaut : celui du dépôt).
    """
    from serge.policy import config_dir, read_yaml_file

    path = (directory or config_dir()) / FILENAME
    if path.is_file():
        seed_pipeline(conn, read_yaml_file(path))
