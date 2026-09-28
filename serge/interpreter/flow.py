#!/usr/bin/env python3
"""Passer la main : les liens entre invocations et les déclencheurs.

Un **lien** part d'une invocation qui vient de finir. En mode
``on_finish``, il crée une tâche ; en mode ``per_row``, une tâche par ligne
écrite par l'une de ses règles d'écriture. Un même résultat n'est jamais
transmis deux fois (``link_passages``). Un lien dont ``auto`` vaut 0 note
le passage avec ses paramètres (``link_passage_params``) et attend le clic
« Passer à la suite » dans Mission Control.

Un **déclencheur** crée une tâche quand une ligne est écrite dans une table
(``row_written``), à intervalle régulier (``every``), à une heure fixe
certains jours (``at``), ou quand on clique sur un bouton (``button``).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from serge.db.store import utcnow
from serge.interpreter.schedule import due_slot
from serge.interpreter.settings import load_settings
from serge.interpreter.tasks import enqueue_task, task_params
from serge.interpreter.writer import Written


def _params(
    rows: list[tuple[str, str, str]],
    *,
    row: Mapping[str, Any] | None = None,
    task: Mapping[str, str] | None = None,
    form: Mapping[str, Any] | None = None,
    settings: Mapping[str, str] | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, source, value in rows:
        if source == 'fixed':
            out[name] = value
        elif source == 'setting':
            out[name] = str((settings or {}).get(value, ''))
        elif source == 'row':
            out[name] = str((row or {}).get(value, '') or '')
        elif source == 'task':
            out[name] = str((task or {}).get(value, '') or '')
        elif source == 'form':
            out[name] = str((form or {}).get(value, '') or '')
    return out


def _link_param_rows(conn: sqlite3.Connection, link_id: str) -> list:
    return [
        (str(a), str(b), str(c))
        for a, b, c in conn.execute(
            'SELECT param_name, source, value FROM link_params WHERE link_id=?',
            (link_id,),
        ).fetchall()
    ]


def _pass(
    conn: sqlite3.Connection,
    link_id: str,
    to_invocation: str,
    auto: bool,
    source_ref: str,
    params: dict[str, str],
) -> None:
    cursor = conn.execute(
        'INSERT OR IGNORE INTO link_passages(link_id, source_ref, created_at)'
        ' VALUES(?,?,?)',
        (link_id, source_ref, utcnow()),
    )
    if cursor.rowcount != 1:
        return
    if not auto:
        conn.executemany(
            'INSERT OR REPLACE INTO link_passage_params(link_id, source_ref,'
            ' name, value) VALUES(?,?,?,?)',
            [(link_id, source_ref, k, v) for k, v in sorted(params.items())],
        )
        return
    _mark_passed(conn, link_id, source_ref, to_invocation, params)


def _mark_passed(
    conn: sqlite3.Connection,
    link_id: str,
    source_ref: str,
    to_invocation: str,
    params: Mapping[str, str],
) -> str | None:
    task_id = enqueue_task(
        conn, to_invocation, params, origin='link', origin_ref=link_id
    )
    conn.execute(
        'UPDATE link_passages SET task_id=?, passed_at=?'
        ' WHERE link_id=? AND source_ref=?',
        (task_id or '', utcnow(), link_id, source_ref),
    )
    return task_id


def pass_waiting(
    conn: sqlite3.Connection, link_id: str, source_ref: str
) -> str | None:
    """« Passer à la suite » : lance un passage qui attendait un clic.

    L'invocation suivante reçoit les paramètres gardés au moment du
    passage. Exemple : ``venture_id = 12`` pour le business choisi.

    Returns:
        L'id de la tâche créée, ou ``None`` si rien n'attend (déjà passé,
        lien éteint ou supprimé, invocation suivante éteinte).
    """
    row = conn.execute(
        'SELECT l.to_invocation_id FROM link_passages p'
        ' JOIN links l ON l.id=p.link_id'
        " WHERE p.link_id=? AND p.source_ref=? AND p.passed_at=''"
        " AND l.enabled=1 AND l.deleted_at=''",
        (link_id, source_ref),
    ).fetchone()
    if row is None:
        return None
    params = {
        str(name): str(value)
        for name, value in conn.execute(
            'SELECT name, value FROM link_passage_params'
            ' WHERE link_id=? AND source_ref=?',
            (link_id, source_ref),
        ).fetchall()
    }
    if not conn.execute(
        "SELECT 1 FROM invocations WHERE id=? AND enabled=1 AND deleted_at=''",
        (str(row[0]),),
    ).fetchone():
        return None
    return _mark_passed(conn, link_id, source_ref, str(row[0]), params)


def set_link_auto(conn: sqlite3.Connection, link_id: str, auto: bool) -> bool:
    """L'interrupteur « passage automatique » d'un lien.

    Il ne vaut que pour les passages suivants : ce qui attend déjà un clic
    continue d'attendre.
    """
    cursor = conn.execute(
        "UPDATE links SET auto=?, updated_at=?, updated_by='owner'"
        " WHERE id=? AND deleted_at=''",
        (int(auto), utcnow(), link_id),
    )
    return cursor.rowcount == 1


def pass_links(
    conn: sqlite3.Connection,
    invocation_id: str,
    task_id: str,
    written: Mapping[int, Written],
) -> None:
    """Lance les invocations suivantes, selon les liens de celle-ci."""
    task = task_params(conn, task_id)
    settings = load_settings(conn, invocation_id)
    for link_id, to_inv, mode, write_id, auto in conn.execute(
        'SELECT id, to_invocation_id, mode, write_id, auto FROM links'
        " WHERE from_invocation_id=? AND enabled=1 AND deleted_at=''",
        (invocation_id,),
    ).fetchall():
        rows = _link_param_rows(conn, str(link_id))
        if mode == 'on_finish':
            _pass(
                conn,
                str(link_id),
                str(to_inv),
                bool(auto),
                f'task:{task_id}',
                _params(rows, task=task, settings=settings),
            )
            continue
        done = written.get(int(write_id))
        if done is None:
            continue
        for row in done.rows:
            ref = f'{done.table}:{row.get("id", "")}'
            _pass(
                conn,
                str(link_id),
                str(to_inv),
                bool(auto),
                ref,
                _params(rows, row=row, task=task, settings=settings),
            )


def fire_row_triggers(
    conn: sqlite3.Connection, written: Mapping[int, Written]
) -> None:
    """Déclencheurs « une ligne est écrite dans telle table »."""
    for done in written.values():
        if not done.rows:
            continue
        for trig_id, inv, column, value in conn.execute(
            'SELECT id, invocation_id, filter_column, filter_value FROM triggers'
            " WHERE event='row_written' AND table_name=? AND enabled=1"
            " AND deleted_at=''",
            (done.table,),
        ).fetchall():
            rows = _trigger_param_rows(conn, str(trig_id))
            for row in done.rows:
                if column and str(row.get(str(column), '')) != str(value):
                    continue
                enqueue_task(
                    conn,
                    str(inv),
                    _params(rows, row=row),
                    origin='trigger',
                    origin_ref=f'{trig_id}:{done.table}:{row.get("id", "")}',
                )


def _trigger_param_rows(conn: sqlite3.Connection, trigger_id: str) -> list:
    return [
        (str(a), str(b), str(c))
        for a, b, c in conn.execute(
            'SELECT param_name, source, value FROM trigger_params'
            ' WHERE trigger_id=?',
            (trigger_id,),
        ).fetchall()
    ]


def fire_due_triggers(
    conn: sqlite3.Connection, now: str, timezone: str = 'Europe/Paris'
) -> None:
    """Déclencheurs horaires : à intervalle régulier ou à heure fixe."""
    moment = datetime.fromisoformat(now)
    zone = ZoneInfo(timezone)
    for trig_id, inv, event, every, at_time, at_days, last in conn.execute(
        'SELECT id, invocation_id, event, every_minutes, at_time, at_days,'
        " last_fired_at FROM triggers WHERE event IN ('every', 'at')"
        " AND enabled=1 AND deleted_at=''"
    ).fetchall():
        slot = due_slot(
            str(event),
            int(every),
            str(at_time),
            str(at_days),
            str(last),
            moment,
            zone,
        )
        if not slot:
            continue
        enqueue_task(
            conn,
            str(inv),
            _params(_trigger_param_rows(conn, str(trig_id))),
            origin='trigger',
            origin_ref=f'{trig_id}:{slot}',
        )
        conn.execute(
            'UPDATE triggers SET last_fired_at=? WHERE id=?', (now, trig_id)
        )


def fire_button(
    conn: sqlite3.Connection, trigger_id: str, form: Mapping[str, Any]
) -> str | None:
    """Un bouton de Mission Control : crée la tâche avec le formulaire."""
    row = conn.execute(
        "SELECT invocation_id FROM triggers WHERE id=? AND event='button'"
        " AND enabled=1 AND deleted_at=''",
        (trigger_id,),
    ).fetchone()
    if row is None:
        return None
    params = _params(_trigger_param_rows(conn, trigger_id), form=form)
    return enqueue_task(
        conn,
        str(row[0]),
        params,
        origin='button',
        origin_ref=f'{trigger_id}:{utcnow()}',
    )
