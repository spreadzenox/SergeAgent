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
Un déclencheur horaire qui vise une table crée une tâche par ligne de cette
table (exemple : lire chaque flux actif toutes les 6 heures). Un
déclencheur peut exiger qu'un ou plusieurs quotas aient de la place
(``trigger_conditions``) : exemple, ne lancer un cycle que s'il reste une
place de test.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from serge.db.store import utcnow
from serge.interpreter.rules import condition_met, quota_usage, safe_name
from serge.interpreter.schedule import due_slot
from serge.interpreter.settings import load_settings
from serge.interpreter.tasks import enqueue_task, task_params
from serge.interpreter.writer import Written
from serge.policy_store import setting_value


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
    not_before: str = '',
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
        _ticket_de_passage(conn, link_id, source_ref, params)
        return
    _mark_passed(conn, link_id, source_ref, to_invocation, params, not_before)


# Le type de ticket d'un passage qui attend un clic, et la table dont il
# parle : un passage se désigne par « lien:source » (décision Q62).
TICKET_PASSAGE = 'PASSAGE'
REF_PASSAGE = 'link_passages'


def _ticket_de_passage(
    conn: sqlite3.Connection,
    link_id: str,
    source_ref: str,
    params: Mapping[str, str],
) -> None:
    """Un passage attend un clic : un ticket l'envoie aussi à chaque
    administrateur, à côté du bouton « Passer à la suite » de Mission
    Control (Q62). Le premier qui passe l'emporte."""
    from serge.tickets.lifecycle import create_ticket, publish
    from serge.tickets.types import ticket_types

    types = ticket_types(conn)
    if TICKET_PASSAGE not in types:
        return
    row = conn.execute(
        'SELECT title, from_invocation_id, to_invocation_id FROM links'
        ' WHERE id=?',
        (link_id,),
    ).fetchone()
    titre = str(row[0] or link_id) if row else link_id
    ticket_id = create_ticket(
        conn,
        types,
        TICKET_PASSAGE,
        f'Feu vert : {titre}',
        {
            'Le lien': f'{titre} ({row[1]} → {row[2]})' if row else titre,
            'Ce qui passe': ' · '.join(
                f'{k} = {v}' for k, v in sorted(params.items())
            )
            or '—',
        },
        creator='serge',
    )
    conn.execute(
        'UPDATE tickets SET ref_table=?, ref_id=? WHERE id=?',
        (REF_PASSAGE, f'{link_id}:{source_ref}', ticket_id),
    )
    publish(conn, ticket_id)


def _clore_ticket_de_passage(
    conn: sqlite3.Connection, link_id: str, source_ref: str
) -> None:
    """Le passage est parti (par Mission Control ou par son ticket) : son
    ticket encore ouvert est annulé chez tous."""
    from serge.tickets.lifecycle import OPENISH, cancel

    holes = ','.join('?' * len(OPENISH))
    for (ticket_id,) in conn.execute(
        f'SELECT id FROM tickets WHERE ref_table=? AND ref_id=?'
        f' AND state IN ({holes})',
        (REF_PASSAGE, f'{link_id}:{source_ref}', *sorted(OPENISH)),
    ).fetchall():
        cancel(conn, str(ticket_id), 'passage déjà parti')


def _mark_passed(
    conn: sqlite3.Connection,
    link_id: str,
    source_ref: str,
    to_invocation: str,
    params: Mapping[str, str],
    not_before: str = '',
) -> str | None:
    task_id = enqueue_task(
        conn,
        to_invocation,
        params,
        origin='link',
        origin_ref=link_id,
        not_before=not_before,
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
    task = _mark_passed(conn, link_id, source_ref, str(row[0]), params)
    _clore_ticket_de_passage(conn, link_id, source_ref)
    return task


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


def _delay(
    conn: sqlite3.Connection,
    min_setting: str,
    max_setting: str,
    source: Mapping[str, Any],
) -> str:
    """« Pas avant » : maintenant plus un délai tiré entre deux réglages.

    Les réglages sont ceux de la policy (en minutes) ; ``{channel}`` dans
    leur nom est remplacé par le canal de la ligne. Exemple :
    ``channels.{channel}.reply_delay_min_minutes`` pour une réponse par
    e-mail. Sans réglage, ou un délai de 0, la tâche part tout de suite.
    """
    if not min_setting:
        return ''

    def minutes(name: str) -> float:
        for key, value in source.items():
            name = name.replace('{' + str(key) + '}', str(value or ''))
        return float(setting_value(conn, name) or 0)

    low = minutes(min_setting)
    high = max(low, minutes(max_setting or min_setting))
    drawn = random.uniform(low, high)
    if drawn <= 0:
        return ''
    start = datetime.fromisoformat(utcnow())
    return (start + timedelta(minutes=drawn)).isoformat()


def pass_links(
    conn: sqlite3.Connection,
    invocation_id: str,
    task_id: str,
    written: Mapping[int, Written],
    answer: Any = None,
) -> None:
    """Lance les invocations suivantes, selon les liens de celle-ci.

    Un lien peut avoir une condition, lue dans la réponse (lien
    ``on_finish``) ou dans la ligne écrite (lien ``per_row``), et un délai
    (voir ``_delay``).
    """
    task = task_params(conn, task_id)
    settings = load_settings(conn, invocation_id)
    reponse = answer if isinstance(answer, Mapping) else {}
    for link in conn.execute(
        'SELECT id, to_invocation_id, mode, write_id, auto, condition_field,'
        ' condition_op, condition_value, delay_min_setting,'
        ' delay_max_setting FROM links'
        " WHERE from_invocation_id=? AND enabled=1 AND deleted_at=''",
        (invocation_id,),
    ).fetchall():
        link_id, to_inv, mode, write_id, auto = (str(x) for x in link[:5])
        field, op, expected, low, high = (str(x or '') for x in link[5:])
        rows = _link_param_rows(conn, link_id)
        if mode == 'on_finish':
            if condition_met(reponse.get(field), op, expected):
                _pass(
                    conn,
                    link_id,
                    to_inv,
                    auto == '1',
                    f'task:{task_id}',
                    _params(rows, task=task, settings=settings),
                    _delay(conn, low, high, task),
                )
            continue
        done = written.get(int(write_id))
        if done is None:
            continue
        for row in done.rows:
            if not condition_met(row.get(field), op, expected):
                continue
            _pass(
                conn,
                link_id,
                to_inv,
                auto == '1',
                f'{done.table}:{row.get("id", "")}',
                _params(rows, row=row, task=task, settings=settings),
                _delay(conn, low, high, {**task, **row}),
            )


def trigger_refusal(conn: sqlite3.Connection, trigger_id: str) -> str:
    """Pourquoi ce déclencheur ne peut pas créer de tâche, ou ``''``.

    Exemple : « Au plus 3 business en test : 3 sur 3 ».
    """
    for (quota_id,) in conn.execute(
        'SELECT quota_id FROM trigger_conditions WHERE trigger_id=?'
        ' ORDER BY quota_id',
        (trigger_id,),
    ).fetchall():
        usage = quota_usage(conn, str(quota_id))
        if usage is not None and usage[0] >= usage[1]:
            return f'{usage[2]} : {usage[0]} sur {usage[1]}'
    return ''


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
            if trigger_refusal(conn, str(trig_id)):
                continue
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


def notify_rows_written(
    conn: sqlite3.Connection, table: str, row_ids: list[str]
) -> None:
    """Prévient les déclencheurs « une ligne est écrite » pour des lignes
    écrites hors de l'interpréteur.

    Un programme qui reçoit de l'extérieur (un appel, un SMS) écrit sa
    ligne, puis appelle cette fonction : le pipeline se réveille comme
    après l'écriture d'une invocation. Exemple : le résumé d'un appel reçu,
    écrit dans ``inbound_events``, lance « Traiter une réponse ».
    """
    cursor = conn.execute(
        f'SELECT * FROM "{safe_name(table)}" WHERE id IN'
        f' ({",".join("?" * len(row_ids))})',
        row_ids,
    )
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
    fire_row_triggers(conn, {0: Written(table, rows=rows)})


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
    for (
        trig_id,
        inv,
        event,
        every,
        at_time,
        at_days,
        last,
        table,
        column,
        value,
    ) in conn.execute(
        'SELECT id, invocation_id, event, every_minutes, at_time, at_days,'
        ' last_fired_at, table_name, filter_column, filter_value FROM triggers'
        " WHERE event IN ('every', 'at') AND enabled=1 AND deleted_at=''"
    ).fetchall():
        if trigger_refusal(conn, str(trig_id)):
            continue
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
        rows = _trigger_param_rows(conn, str(trig_id))
        for ref, row in _target_rows(
            conn, str(table), str(column), str(value)
        ):
            enqueue_task(
                conn,
                str(inv),
                _params(rows, row=row),
                origin='trigger',
                origin_ref=f'{trig_id}:{slot}{ref}',
            )
        conn.execute(
            'UPDATE triggers SET last_fired_at=? WHERE id=?', (now, trig_id)
        )


def _target_rows(
    conn: sqlite3.Connection, table: str, column: str, value: str
) -> list[tuple[str, dict[str, Any]]]:
    """Les lignes visées par un déclencheur horaire, ou une seule tâche.

    Sans table, une seule tâche. Avec une table, une tâche par ligne (qui
    a ``column`` = ``value``, si le filtre est réglé).
    """
    if not table:
        return [('', {})]
    sql = f'SELECT * FROM "{safe_name(table)}"'
    args: tuple = ()
    if column:
        sql += f' WHERE "{safe_name(column)}"=?'
        args = (value,)
    cursor = conn.execute(sql, args)
    names = [d[0] for d in cursor.description]
    out = []
    for raw in cursor.fetchall():
        row = dict(zip(names, raw, strict=True))
        out.append((f':{row.get("id", "")}', row))
    return out


def fire_button(
    conn: sqlite3.Connection, trigger_id: str, form: Mapping[str, Any]
) -> str | None:
    """Un bouton de Mission Control : crée la tâche avec le formulaire."""
    row = conn.execute(
        "SELECT invocation_id FROM triggers WHERE id=? AND event='button'"
        " AND enabled=1 AND deleted_at=''",
        (trigger_id,),
    ).fetchone()
    if row is None or trigger_refusal(conn, trigger_id):
        return None
    params = _params(_trigger_param_rows(conn, trigger_id), form=form)
    return enqueue_task(
        conn,
        str(row[0]),
        params,
        origin='button',
        origin_ref=f'{trigger_id}:{utcnow()}',
    )
