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
   son catalogue de tables, colonnes et filtres), ou pas du tout ; seuls
   s'ajoutent à un objet existant ses réglages nouveaux, ses droits
   d'écriture nouveaux et les colonnes nouvelles de ses vues ;
4. une valeur d'un objet existant ne change que par la section
   ``changes`` (``serge/pipeline_changes.py``) : une seule fois, et
   seulement si elle n'a pas été changée dans Mission Control ;
5. ce qui est retiré du fichier est listé dans ``deleted``.

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

from serge.interpreter.rules import table_columns
from serge.pipeline_seed_flow import seed_deleted, seed_links, seed_triggers
from serge.seed_base import (
    PipelineSeedError,
    condition_columns,
    exists,
    insert,
    list_of,
    seed_params,
)

__all__ = ['PipelineSeedError', 'ensure_pipeline', 'seed_pipeline']

SCHEMA_VERSION = 1
FILENAME = 'pipeline.yaml'


def _seed_simple(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for queue in list_of(data, 'queues'):
        insert(
            conn,
            'queues',
            ignore=True,
            id=str(queue['id']),
            title=str(queue.get('title', '')),
        )
    for model in list_of(data, 'llm_models'):
        insert(
            conn,
            'llm_models',
            ignore=True,
            tier=str(model['tier']),
            provider=str(model.get('provider', '')),
            model=str(model.get('model', '')),
            max_price_usd=float(model.get('max_price_usd', 0)),
            tolerance_pct=int(model.get('tolerance_pct', 95)),
        )
    for text in list_of(data, 'serge_texts'):
        insert(
            conn,
            'serge_texts',
            ignore=True,
            id=str(text['id']),
            title=str(text.get('title', '')),
            help=str(text.get('help', '')).strip(),
            body=str(text.get('body', '')).strip(),
            updated_at='',
            updated_by='pipeline.yaml',
        )


def _seed_tools(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    """Les outils : une capacité réglée pour un usage précis."""
    from serge.db.query_catalogue import seed_read_catalogue

    for tool in list_of(data, 'tools'):
        ident = str(tool['id'])
        if exists(conn, 'tools', 'id', ident):
            continue
        capability = str(tool['capability'])
        read = tool.get('read')
        if (read is not None) != (capability == 'db_read'):
            raise PipelineSeedError(
                f'outil {ident} : read est obligatoire pour db_read, et'
                ' seulement pour lui'
            )
        insert(
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
    # Les droits d'écriture d'une table ne font que grandir avec le
    # pipeline : une colonne ou une opération nouvelle s'ajoute aussi sur
    # une instance existante, rien n'est jamais retiré.
    for table in list_of(data, 'writable_tables'):
        name = str(table['table'])
        insert(
            conn,
            'writable_tables',
            ignore=True,
            table_name=name,
            description=str(table.get('description', '')),
        )
        for flag, key in (
            ('can_insert', 'insert'),
            ('can_update', 'update'),
            ('can_delete', 'delete'),
        ):
            if table.get(key):
                conn.execute(
                    f'UPDATE writable_tables SET {flag}=1 WHERE table_name=?',
                    (name,),
                )
        for column in list_of(table, 'columns'):
            insert(
                conn,
                'writable_columns',
                ignore=True,
                table_name=name,
                column_name=str(column['name']),
                description=str(column.get('description', '')),
            )
    # Chaque changement permis est un objet : il s'ajoute s'il manque, même
    # sur une colonne qui en a déjà. Exemple : « création → TEST » pour le
    # business d'essai, sur une instance où les business avaient déjà leurs
    # règles. Un changement déjà en base n'est jamais touché.
    for rule in list_of(data, 'status_transitions'):
        conn.execute(
            'INSERT OR IGNORE INTO status_transitions(table_name, column_name,'
            ' from_value, to_value) VALUES(?,?,?,?)',
            (
                str(rule['table']),
                str(rule['column']),
                str(rule.get('from', '')),
                str(rule['to']),
            ),
        )
    for quota in list_of(data, 'table_quotas'):
        ident = str(quota['id'])
        if exists(conn, 'table_quotas', 'id', ident):
            continue
        insert(
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
    # Quand une ligne passe dans tel état, ses tâches en attente sont
    # annulées (exemple : un cycle abandonné arrête sa chaîne).
    for rule in list_of(data, 'task_cancel_rules'):
        table, column = str(rule['table']), str(rule['column'])
        if column not in table_columns(conn, table):
            raise PipelineSeedError(
                f'task_cancel_rules : colonne absente {table}.{column}'
            )
        insert(
            conn,
            'task_cancel_rules',
            ignore=True,
            table_name=table,
            column_name=column,
            value=str(rule['value']),
            param_name=str(rule['param']),
        )
    for rule in list_of(data, 'dedup_rules'):
        ident = str(rule['id'])
        if exists(conn, 'dedup_rules', 'id', ident):
            continue
        insert(
            conn,
            'dedup_rules',
            id=ident,
            table_name=str(rule['table']),
            method=str(rule['method']),
            threshold=int(rule.get('threshold', 100)),
            on_duplicate=str(rule.get('on_duplicate', 'skip')),
        )
        for column in rule.get('columns') or []:
            insert(
                conn,
                'dedup_rule_columns',
                rule_id=ident,
                column_name=str(column),
            )


def _seed_writes(
    conn: sqlite3.Connection, ident: str, inv: Mapping[str, Any]
) -> None:
    write_ids: list[int] = []
    for position, write in enumerate(list_of(inv, 'writes')):
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
        cond = condition_columns(
            write.get('condition'), f'{ident}.writes[{position}]'
        )
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
        )
        write_ids.append(write_id)
        seed_params(
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
    insert(
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
        single_pending_param=str(inv.get('single_pending', '')),
        capability_id=str(inv.get('capability', '')),
        origin='code',
        updated_by='pipeline.yaml',
    )
    seed_settings(conn, ident, inv.get('settings'))
    for table, included in (inv.get('compare') or {}).items():
        if not exists(conn, 'table_views', 'table_name', str(table)):
            raise PipelineSeedError(f'{ident}.compare : pas de vue {table}')
        insert(
            conn,
            'invocation_compare_tables',
            invocation_id=ident,
            table_name=str(table),
            included=int(bool(included)),
            updated_by='pipeline.yaml',
        )
    seed_params(
        conn,
        'invocation_tool_params',
        {'invocation_id': ident, 'invocation_tool_id': 0},
        inv.get('params'),
        ident,
    )
    for position, tool in enumerate(list_of(inv, 'tools')):
        link_id = insert(
            conn,
            'invocation_tools',
            invocation_id=ident,
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
            {'invocation_id': ident, 'invocation_tool_id': link_id},
            tool.get('params'),
            ident,
        )
    for position, out in enumerate(list_of(inv, 'output')):
        insert(
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


def seed_pipeline(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    """Ajoute en base ce que décrit ``data``, sans rien écraser.

    Args:
        conn: Connexion à la base (commit par l'appelant).
        data: Le contenu de ``pipeline.yaml``.

    Raises:
        PipelineSeedError: Fichier mal formé.
    """
    from serge.interpreter.seen import seed_table_views
    from serge.interpreter.settings import seed_settings
    from serge.pipeline_changes import apply_changes

    if data.get('schema_version') != SCHEMA_VERSION:
        raise PipelineSeedError('schema_version doit valoir 1')
    _seed_simple(conn, data)
    _seed_tools(conn, data)
    _seed_rules(conn, data)
    seed_table_views(conn, list_of(data, 'table_views'))
    for inv in list_of(data, 'invocations'):
        if not exists(conn, 'invocations', 'id', str(inv['id'])):
            _seed_invocation(conn, inv)
        else:
            # Un réglage nouveau s'ajoute à une invocation existante ; un
            # réglage déjà en base n'est jamais modifié.
            seed_settings(conn, str(inv['id']), inv.get('settings'))
    seed_links(conn, data)
    seed_triggers(conn, data)
    apply_changes(conn, data.get('changes'))
    seed_deleted(conn, data)


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
