#!/usr/bin/env python3
"""Remplir la base : les liens, les déclencheurs, et ce qui est retiré.

Voir ``serge/pipeline_seed.py``. Un objet retiré du pipeline de départ est
listé dans la section ``deleted`` de ``config/pipeline.yaml`` : il est
marqué supprimé en base (``deleted_at``) sur une instance existante, parce
que retirer une ligne du fichier ne l'efface jamais.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.seed_base import (
    PipelineSeedError,
    condition_columns,
    exists,
    insert,
    list_of,
    seed_params,
)

LANES = ('', 'real', 'trial')


def _lane(raw: Any, quoi: str) -> str:
    """Le couloir d'un lien ou d'un déclencheur : vide (les deux), ``real``
    (le vrai pipeline seulement) ou ``trial`` (l'essai seulement ; pour un
    bouton : il démarre un essai)."""
    lane = str(raw or '')
    if lane not in LANES:
        raise PipelineSeedError(f'{quoi} : couloir inconnu {lane!r}')
    return lane


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


def seed_links(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    for link in list_of(data, 'links'):
        ident = str(link['id'])
        if exists(conn, 'links', 'id', ident):
            continue
        origin = str(link['from'])
        cond = condition_columns(link.get('condition'), f'lien {ident}')
        for end in (origin, str(link['to'])):
            if not exists(conn, 'invocations', 'id', end):
                raise PipelineSeedError(
                    f'lien {ident} : invocation {end} inconnue'
                )
        insert(
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
            delay_min_setting=str((link.get('delay') or {}).get('min', '')),
            delay_max_setting=str((link.get('delay') or {}).get('max', '')),
            condition_field=cond[0],
            condition_op=cond[1],
            condition_value=cond[2],
            lane=_lane(link.get('lane'), f'lien {ident}'),
        )
        seed_params(
            conn, 'link_params', {'link_id': ident}, link.get('params'), ident
        )


def seed_triggers(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    from serge.interpreter.schedule import schedule_error

    for trig in list_of(data, 'triggers'):
        ident = str(trig['id'])
        if exists(conn, 'triggers', 'id', ident):
            continue
        if not exists(conn, 'invocations', 'id', str(trig['invocation'])):
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
        insert(
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
            confirm_text=str(trig.get('confirm', '')).strip(),
            origin='code',
            updated_by='pipeline.yaml',
            lane=_lane(trig.get('lane'), f'déclencheur {ident}'),
        )
        _seed_row_conditions(conn, ident, trig.get('only_if_rows'))
        for quota in trig.get('only_if_room_in') or []:
            if not exists(conn, 'table_quotas', 'id', str(quota)):
                raise PipelineSeedError(
                    f'déclencheur {ident} : quota {quota} inconnu'
                )
            insert(
                conn,
                'trigger_conditions',
                trigger_id=ident,
                quota_id=str(quota),
            )
        seed_params(
            conn,
            'trigger_params',
            {'trigger_id': ident},
            trig.get('params'),
            ident,
        )


def _seed_row_conditions(
    conn: sqlite3.Connection, trigger: str, raw: Any
) -> None:
    """Les conditions « nombre de lignes » d'un déclencheur.

    Format : ``[{table, column, values, at_most | at_least, description}]``.
    Exemple : ``{table: ventures, column: lifecycle, values:
    [SMOKE_RUNNING], at_most: 0, description: Business en test}``.
    """
    for position, cond in enumerate(raw or []):
        op = 'at_most' if 'at_most' in cond else 'at_least'
        if op not in cond:
            raise PipelineSeedError(
                f'déclencheur {trigger} : at_most ou at_least attendu'
            )
        insert(
            conn,
            'trigger_row_conditions',
            trigger_id=trigger,
            position=position,
            table_name=str(cond['table']),
            column_name=str(cond['column']),
            counted_values=', '.join(str(v) for v in cond['values']),
            op=op,
            n=int(cond[op]),
            description=str(cond.get('description', '')).strip(),
        )


def _delete_tool(conn: sqlite3.Connection, tool_id: str) -> None:
    for table in (
        'tool_db_tables',
        'tool_db_columns',
        'tool_db_filters',
        'tool_db_filter_values',
        'tool_db_joins',
        'tool_db_params',
        'tool_db_param_enums',
        # Un point d'entrée d'une API décrite en base (lot 10).
        'api_endpoint_params',
        'api_endpoints',
    ):
        conn.execute(f'DELETE FROM {table} WHERE tool_id=?', (tool_id,))
    conn.execute(
        'DELETE FROM invocation_tool_params WHERE invocation_tool_id IN'
        ' (SELECT id FROM invocation_tools WHERE tool_id=?)',
        (tool_id,),
    )
    conn.execute('DELETE FROM invocation_tools WHERE tool_id=?', (tool_id,))
    conn.execute('DELETE FROM tools WHERE id=?', (tool_id,))


def seed_deleted(conn: sqlite3.Connection, data: Mapping[str, Any]) -> None:
    """Ce qui a été retiré du pipeline de départ, retiré aussi de la base.

    Format : ``{invocations: [...], links: [...], triggers: [...],
    tools: [...], quotas: [...], serge_texts: [...], api_services: [...],
    settings: [{invocation, name}]}``.
    Les invocations, liens et déclencheurs sont marqués supprimés
    (``deleted_at``) ; les outils, les quotas, les textes de Serge, les
    services d'API et les réglages d'invocation, qui n'ont pas cette
    colonne, sont effacés.
    """
    from serge.horloge import iso_utc

    raw = data.get('deleted') or {}
    if not isinstance(raw, Mapping):
        raise PipelineSeedError('deleted : un objet est attendu')
    now = iso_utc()
    for key, table in (
        ('invocations', 'invocations'),
        ('links', 'links'),
        ('triggers', 'triggers'),
    ):
        for ident in raw.get(key) or []:
            conn.execute(
                f"UPDATE {table} SET deleted_at=?, updated_by='pipeline.yaml'"
                " WHERE id=? AND deleted_at=''",
                (now, str(ident)),
            )
    # Les tâches encore en attente d'une invocation retirée ne partiront
    # jamais : elles sont annulées, pour ne pas encombrer la file.
    for ident in raw.get('invocations') or []:
        conn.execute(
            "UPDATE tasks SET status='cancelled', finished_at=?,"
            " last_error='invocation retirée du pipeline'"
            " WHERE invocation_id=? AND status='ready'",
            (now, str(ident)),
        )
    for ident in raw.get('tools') or []:
        _delete_tool(conn, str(ident))
    for ident in raw.get('quotas') or []:
        conn.execute(
            'DELETE FROM trigger_conditions WHERE quota_id=?', (str(ident),)
        )
        conn.execute('DELETE FROM table_quotas WHERE id=?', (str(ident),))
    for ident in raw.get('serge_texts') or []:
        conn.execute('DELETE FROM serge_texts WHERE id=?', (str(ident),))
    # Un réglage que plus rien ne lit : ``{invocation, name}``.
    for setting in raw.get('settings') or []:
        conn.execute(
            'DELETE FROM invocation_settings WHERE invocation_id=? AND name=?',
            (str(setting['invocation']), str(setting['name'])),
        )
    for ident in raw.get('api_services') or []:
        conn.execute('DELETE FROM api_services WHERE id=?', (str(ident),))
