#!/usr/bin/env python3
"""Passer la main : les liens entre invocations.

Un **lien** part d'une invocation qui vient de finir. En mode
``on_finish``, il crée une tâche ; en mode ``per_row``, une tâche par ligne
écrite par l'une de ses règles d'écriture. Un même résultat n'est jamais
transmis deux fois (``link_passages``). Un lien dont ``auto`` vaut 0 note
le passage avec ses paramètres (``link_passage_params``) et attend le clic
« Passer à la suite » dans Mission Control. Les déclencheurs sont dans
``triggers.py``.

**Le couloir d'essai** (``serge/trial.py``) : une tâche créée par un lien
est du couloir de la ligne qu'il passe, sinon de la tâche qui l'a créée.
Un lien peut n'exister que dans un couloir (``lane`` : ``real`` ou
``trial``). La suite d'un essai arrêté ne part pas. La marque d'un
redémarrage (``tasks.rerun``) suit la chaîne : la suite d'une tâche
rejouée repasse par ses liens.
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import utcnow
from serge.interpreter.rules import condition_met
from serge.interpreter.settings import load_settings
from serge.interpreter.tasks import (
    enqueue_task,
    task_key,
    task_lane,
    task_params,
)
from serge.interpreter.writer import Written
from serge.policy_store import setting_value
from serge.tickets.passage import clore_ticket_de_passage, ticket_de_passage
from serge.trial import NO_RUN, active_run, run_for_row


def lane_ok(lane: str, trial_run: str) -> bool:
    """Ce lien ou ce déclencheur existe-t-il dans ce couloir ?"""
    return not lane or (lane == 'trial') == bool(trial_run)


def alive(conn: sqlite3.Connection, trial_run: str) -> bool:
    """La suite d'un essai arrêté ou remplacé ne part pas."""
    return trial_run in ('', NO_RUN) or trial_run == active_run(conn)


def ref(base: str, rerun: str) -> str:
    """La référence d'un passage ou d'un déclenchement, propre à un
    redémarrage : la suite d'une tâche rejouée repasse par ses liens."""
    return f'{base}#{rerun}' if rerun else base


def params_from(
    rows: list[tuple[str, str, str]],
    *,
    row: Mapping[str, Any] | None = None,
    task: Mapping[str, str] | None = None,
    form: Mapping[str, Any] | None = None,
    settings: Mapping[str, str] | None = None,
    answer: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {}
    for name, source, value in rows:
        if source == 'fixed':
            out[name] = value
        elif source == 'field':
            # Un champ de la réponse de l'invocation qui vient de finir.
            # Exemple : le tour suivant rendu par « Compter les tours ».
            found = (answer or {}).get(value)
            out[name] = '' if found is None else str(found)
        elif source == 'setting':
            out[name] = str((settings or {}).get(value, ''))
        elif source == 'row':
            out[name] = str((row or {}).get(value, '') or '')
        elif source == 'task':
            out[name] = str((task or {}).get(value, '') or '')
        elif source == 'form':
            out[name] = str((form or {}).get(value, '') or '')
        elif source == 'form_case':
            # Une case du formulaire : cochée, 1 ; sinon 0.
            coche = str((form or {}).get(value, '') or '').lower()
            out[name] = '1' if coche in {'1', 'true', 'on', 'oui'} else '0'
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
    *,
    from_task: str = '',
    trial_run: str = '',
) -> None:
    if not alive(conn, trial_run):
        return
    cursor = conn.execute(
        'INSERT OR IGNORE INTO link_passages(link_id, source_ref, created_at,'
        ' from_task) VALUES(?,?,?,?)',
        (link_id, source_ref, utcnow(), from_task),
    )
    if cursor.rowcount != 1:
        return
    if not auto:
        conn.executemany(
            'INSERT OR REPLACE INTO link_passage_params(link_id, source_ref,'
            ' name, value) VALUES(?,?,?,?)',
            [(link_id, source_ref, k, v) for k, v in sorted(params.items())],
        )
        ticket_de_passage(conn, link_id, source_ref, params)
        return
    _mark_passed(
        conn,
        link_id,
        source_ref,
        to_invocation,
        params,
        not_before,
        from_task=from_task,
        trial_run=trial_run,
    )


def _mark_passed(
    conn: sqlite3.Connection,
    link_id: str,
    source_ref: str,
    to_invocation: str,
    params: Mapping[str, str],
    not_before: str = '',
    *,
    from_task: str = '',
    trial_run: str = '',
) -> str | None:
    # Une tâche par passage : deux résultats différents qui passent le
    # même lien avec les mêmes paramètres donnent deux tâches. Exemple :
    # « Suivre une campagne » relance « Trouver des prospects » une
    # deuxième fois, pour la même campagne.
    task_id = enqueue_task(
        conn,
        to_invocation,
        params,
        origin='link',
        origin_ref=link_id,
        not_before=not_before,
        key=task_key(
            to_invocation, 'link', f'{link_id}:{source_ref}', dict(params)
        ),
        trial_run=trial_run,
        parent=from_task,
        rerun=task_lane(conn, from_task)[1] if from_task else '',
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
        'SELECT l.to_invocation_id, p.from_task FROM link_passages p'
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
    origine = str(row[1] or '')
    task = _mark_passed(
        conn,
        link_id,
        source_ref,
        str(row[0]),
        params,
        from_task=origine,
        trial_run=task_lane(conn, origine)[0] if origine else '',
    )
    clore_ticket_de_passage(conn, link_id, source_ref)
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

    Un réglage peut être une liste d'attentes, une par tour d'une boucle :
    ``nom[{tour}]`` prend celle du tour (la première sans tour, la dernière
    au-delà de la liste). Exemple : ``web_accounts.contact_waits_minutes
    [{rappel}]`` fait attendre 5 minutes avant le premier rappel, 1 heure
    avant le deuxième.
    """
    if not min_setting:
        return ''

    def minutes(name: str) -> float:
        for key, value in source.items():
            name = name.replace('{' + str(key) + '}', str(value or ''))
        name, _, rang = name.partition('[')
        valeur = setting_value(conn, name)
        if isinstance(valeur, list):
            chiffres = rang.rstrip(']').strip()
            tour = int(chiffres) if chiffres.isdigit() else 1
            valeur = (
                valeur[min(max(tour, 1), len(valeur)) - 1] if valeur else 0
            )
        return float(valeur or 0)

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
    ``on_finish`` ; sinon dans les paramètres de la tâche, quand la réponse
    n'a pas ce champ) ou dans la ligne écrite (lien ``per_row``), et un
    délai (voir ``_delay``).
    """
    task = task_params(conn, task_id)
    trial_run, rerun = task_lane(conn, task_id)
    settings = load_settings(conn, invocation_id)
    reponse = answer if isinstance(answer, Mapping) else {}
    for link in conn.execute(
        'SELECT id, to_invocation_id, mode, write_id, auto, condition_field,'
        ' condition_op, condition_value, delay_min_setting,'
        ' delay_max_setting, lane FROM links'
        " WHERE from_invocation_id=? AND enabled=1 AND deleted_at=''",
        (invocation_id,),
    ).fetchall():
        link_id, to_inv, mode, write_id, auto = (str(x) for x in link[:5])
        field, op, expected, low, high, lane = (str(x or '') for x in link[5:])
        rows = _link_param_rows(conn, link_id)
        if mode == 'on_finish':
            value = reponse[field] if field in reponse else task.get(field)
            if lane_ok(lane, trial_run) and condition_met(value, op, expected):
                _pass(
                    conn,
                    link_id,
                    to_inv,
                    auto == '1',
                    ref(f'task:{task_id}', rerun),
                    params_from(
                        rows, task=task, settings=settings, answer=reponse
                    ),
                    _delay(conn, low, high, task),
                    from_task=task_id,
                    trial_run=trial_run,
                )
            continue
        done = written.get(int(write_id))
        if done is None:
            continue
        for row in done.rows:
            run = run_for_row(conn, row, trial_run)
            if not lane_ok(lane, run):
                continue
            if not condition_met(row.get(field), op, expected):
                continue
            _pass(
                conn,
                link_id,
                to_inv,
                auto == '1',
                ref(f'{done.table}:{row.get("id", "")}', rerun),
                params_from(
                    rows, row=row, task=task, settings=settings, answer=reponse
                ),
                _delay(conn, low, high, {**task, **row}),
                from_task=task_id,
                trial_run=run,
            )
