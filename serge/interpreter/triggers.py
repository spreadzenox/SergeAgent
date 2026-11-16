#!/usr/bin/env python3
"""Les déclencheurs : ce qui crée une tâche sans qu'une autre finisse.

Un **déclencheur** crée une tâche quand une ligne est écrite dans une table
(``row_written``), à intervalle régulier (``every``), à une heure fixe
certains jours (``at``), ou quand on clique sur un bouton (``button``).
Un déclencheur horaire qui vise une table crée une tâche par ligne de cette
table (exemple : lire chaque flux actif toutes les 6 heures).

Ses conditions, toutes en base :
- des quotas qui ont de la place (``trigger_conditions``) : ne lancer un
  cycle que s'il reste une place de test ;
- des nombres de lignes (``trigger_row_conditions``) : ne choisir le
  business principal que si plus aucun test ne tourne (au plus 0 business
  en test) et qu'un test retenu attend (au moins 1).

**Le couloir d'essai** (``serge/trial.py``) : la tâche est du couloir de
la ligne qui la déclenche, sinon de la tâche qui a écrit cette ligne. Un
déclencheur peut n'exister que dans un couloir (``lane``) ; un bouton
dont le couloir est ``trial`` démarre un essai, qui remplace le précédent.
Les conditions comptent les lignes du couloir de la tâche à créer ; un
quota qui ne compte que les vraies lignes ne refuse jamais un essai.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from serge.db.store import utcnow
from serge.interpreter.flow import alive, lane_ok, params_from, ref
from serge.interpreter.rules import quota_usage, safe_name
from serge.interpreter.schedule import due_slot
from serge.interpreter.tasks import SELF, enqueue_task, task_lane
from serge.interpreter.writer import Written
from serge.trial import current_task, lane_clause, run_for_row
from serge.trial_run import begin_trial, stop_trial


def trigger_refusal(
    conn: sqlite3.Connection, trigger_id: str, trial: bool = False
) -> str:
    """Pourquoi ce déclencheur ne peut pas créer de tâche, ou ``''``.

    Exemples : « Places de test occupées : 3 sur 3 » ; « Business en test :
    1, au plus 0 ». ``trial`` : la tâche à créer serait d'un essai.
    """
    for (quota_id,) in conn.execute(
        'SELECT quota_id FROM trigger_conditions WHERE trigger_id=?'
        ' ORDER BY quota_id',
        (trigger_id,),
    ).fetchall():
        if trial and _real_only(conn, str(quota_id)):
            continue
        usage = quota_usage(conn, str(quota_id))
        if usage is not None and usage[0] >= usage[1]:
            return f'{usage[2]} : {usage[0]} sur {usage[1]}'
    for table, column, counted, op, n, description in conn.execute(
        'SELECT table_name, column_name, counted_values, op, n, description'
        ' FROM trigger_row_conditions WHERE trigger_id=? ORDER BY position',
        (trigger_id,),
    ).fetchall():
        values = [v.strip() for v in str(counted).split(',') if v.strip()]
        clause = lane_clause(conn, str(table), trial=trial)
        found = conn.execute(
            f'SELECT COUNT(*) FROM "{safe_name(str(table))}"'
            f' WHERE "{safe_name(str(column))}"'
            f' IN ({", ".join("?" * len(values))})'
            + (f' AND {clause}' if clause else ''),
            values,
        ).fetchone()
        count = int(found[0])
        if (op == 'at_most' and count > int(n)) or (
            op == 'at_least' and count < int(n)
        ):
            word = 'au plus' if op == 'at_most' else 'au moins'
            return f'{description or table} : {count}, {word} {n}'
    return ''


def _real_only(conn: sqlite3.Connection, quota_id: str) -> bool:
    """Ce quota ne compte-t-il que les vraies lignes (``trial`` à 0) ?"""
    row = conn.execute(
        'SELECT where_column, where_value FROM table_quotas WHERE id=?',
        (quota_id,),
    ).fetchone()
    return bool(row) and str(row[0]) == 'trial' and str(row[1]) == '0'


def fire_row_triggers(
    conn: sqlite3.Connection,
    written: Mapping[int, Written],
    task_id: str = '',
) -> None:
    """Déclencheurs « une ligne est écrite dans telle table ».

    ``task_id`` : la tâche qui a écrit ces lignes (vide : un programme qui
    reçoit de l'extérieur, voir ``notify_rows_written``).
    """
    trial_run, rerun = task_lane(conn, task_id) if task_id else ('', '')
    for done in written.values():
        if not done.rows:
            continue
        for trig_id, inv, column, value, lane in conn.execute(
            'SELECT id, invocation_id, filter_column, filter_value, lane'
            " FROM triggers WHERE event='row_written' AND table_name=?"
            " AND enabled=1 AND deleted_at=''",
            (done.table,),
        ).fetchall():
            rows = _trigger_param_rows(conn, str(trig_id))
            for row in done.rows:
                if column and str(row.get(str(column), '')) != str(value):
                    continue
                run = run_for_row(conn, row, trial_run)
                if not lane_ok(str(lane), run) or not alive(conn, run):
                    continue
                if trigger_refusal(conn, str(trig_id), bool(run)):
                    continue
                enqueue_task(
                    conn,
                    str(inv),
                    params_from(rows, row=row),
                    origin='trigger',
                    origin_ref=ref(
                        f'{trig_id}:{done.table}:{row.get("id", "")}', rerun
                    ),
                    trial_run=run,
                    parent=task_id,
                    rerun=rerun,
                )


def notify_rows_written(
    conn: sqlite3.Connection,
    table: str,
    row_ids: list[str],
    from_task: str = '',
) -> None:
    """Prévient les déclencheurs « une ligne est écrite » pour des lignes
    écrites hors de l'interpréteur.

    Un programme qui reçoit de l'extérieur (un appel, un SMS, un paiement)
    écrit sa ligne, puis appelle cette fonction : le pipeline se réveille
    comme après l'écriture d'une invocation. Exemple : le résumé d'un appel
    reçu, écrit dans ``inbound_events``, lance « Traiter une réponse ».
    La tâche créée est la suite de ``from_task`` (la tâche qui a ouvert le
    ticket auquel on répond), sinon de la tâche en cours.
    """
    cursor = conn.execute(
        f'SELECT * FROM "{safe_name(table)}" WHERE id IN'
        f' ({",".join("?" * len(row_ids))})',
        row_ids,
    )
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
    fire_row_triggers(
        conn, {0: Written(table, rows=rows)}, from_task or current_task()
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
    """Déclencheurs horaires : à intervalle régulier ou à heure fixe.

    Sans table, la tâche est du vrai pipeline. Avec une table, chaque
    ligne donne une tâche de son couloir : la campagne d'un essai est
    suivie par une tâche d'essai.
    """
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
        lane,
    ) in conn.execute(
        'SELECT id, invocation_id, event, every_minutes, at_time, at_days,'
        ' last_fired_at, table_name, filter_column, filter_value, lane'
        ' FROM triggers'
        " WHERE event IN ('every', 'at') AND enabled=1 AND deleted_at=''"
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
        rows = _trigger_param_rows(conn, str(trig_id))
        for suffix, row in _target_rows(
            conn, str(table), str(column), str(value)
        ):
            run = run_for_row(conn, row, '')
            if not lane_ok(str(lane), run) or not alive(conn, run):
                continue
            if trigger_refusal(conn, str(trig_id), bool(run)):
                continue
            enqueue_task(
                conn,
                str(inv),
                params_from(rows, row=row),
                origin='trigger',
                origin_ref=f'{trig_id}:{slot}{suffix}',
                trial_run=run,
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
    """Un bouton de Mission Control : crée la tâche avec le formulaire.

    Un bouton du couloir d'essai démarre un essai : le précédent est
    arrêté, et la tâche créée donne son numéro au nouveau. Un bouton qui
    porte un business (son formulaire a ``venture_id``) est du couloir de
    ce business : « Supprimer de Stripe » sur la calculatrice d'un essai
    lance une tâche d'essai.
    """
    row = conn.execute(
        'SELECT invocation_id, lane FROM triggers WHERE id=?'
        " AND event='button' AND enabled=1 AND deleted_at=''",
        (trigger_id,),
    ).fetchone()
    if row is None:
        return None
    starts_trial = str(row[1] or '') == 'trial'
    run = SELF if starts_trial else run_for_row(conn, dict(form), '')
    if trigger_refusal(conn, trigger_id, bool(run)):
        return None
    if starts_trial:
        stop_trial(conn, 'remplacé par un nouvel essai')
    task_id = enqueue_task(
        conn,
        str(row[0]),
        params_from(_trigger_param_rows(conn, trigger_id), form=form),
        origin='button',
        origin_ref=f'{trigger_id}:{utcnow()}',
        trial_run=run,
    )
    if starts_trial and task_id:
        begin_trial(conn, task_id)
    return task_id
