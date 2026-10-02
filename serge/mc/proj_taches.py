#!/usr/bin/env python3
"""Mission Control : les deux files de tâches (``tasks``), lues en base.

Une tâche lance une invocation avec ses paramètres. Chaque file
(``conversations``, ``works``) prend sa tâche prête la plus prioritaire.
Les formats JSON rendus ici sont ceux que lit la page En direct : ``kind``
porte le titre de l'invocation, ``venture_id`` le paramètre du même nom
s'il existe.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.interpreter.tasks import next_task
from serge.llm.runtime import budget_reached
from serge.mc.proj_objet_base import _champs, _liens, _row
from serge.policy_store import policy_en_vigueur

ETATS_TACHE = {
    'ready': 'Prête',
    'running': 'En cours',
    'done': 'Terminée',
    'failed': 'Échouée',
    'cancelled': 'Annulée',
}

# id, titre, business, depuis, file, état, priorité, pas avant, créée,
# essais, nom du business, invocation allumée, invocation supprimée le,
# étape allumée, sorte d'invocation
_SELECT = (
    "SELECT t.id, COALESCE(NULLIF(i.title, ''), t.invocation_id),"
    " COALESCE(p.value, ''), t.started_at, t.queue_id, t.status,"
    ' t.priority, t.not_before, t.created_at, t.attempts,'
    " COALESCE(v.name, ''), COALESCE(i.enabled, 0),"
    " COALESCE(i.deleted_at, 'absente'), COALESCE(s.enabled, 1),"
    " COALESCE(i.type, '')"
    ' FROM tasks t LEFT JOIN invocations i ON i.id=t.invocation_id'
    ' LEFT JOIN pipeline_steps s ON s.id=i.step_id'
    " LEFT JOIN task_params p ON p.task_id=t.id AND p.name='venture_id'"
    ' LEFT JOIN ventures v ON v.id=p.value'
)


def _bloquee(row: Any, plafond: str = '') -> str:
    """Pourquoi une tâche prête ne partira pas, ou pas maintenant, ou ``''``.

    La file saute les tâches d'une invocation supprimée ou éteinte, d'une
    étape coupée, et les tâches LLM quand le plafond de dépense du jour ou
    du mois est atteint (``plafond``) : elles ne doivent pas avoir l'air
    d'attendre leur tour.
    """
    if row[5] != 'ready':
        return ''
    if row[12]:
        return 'Ne partira pas : invocation supprimée'
    if not row[11]:
        return 'En attente : invocation éteinte'
    if not row[13]:
        return 'En attente : étape coupée'
    if plafond and row[14] == 'llm':
        return f'En attente : plafond du {plafond} atteint'
    return ''


def _resume(row: Any) -> dict[str, Any]:
    return {
        'id': str(row[0]),
        'kind': str(row[1]),
        'venture_id': str(row[2]),
        'since': str(row[3] or ''),
        'file': str(row[4]),
    }


def _files(conn: sqlite3.Connection) -> list[str]:
    return [
        str(r[0]) for r in conn.execute('SELECT id FROM queues ORDER BY id')
    ]


def plafond_atteint(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> str:
    """Le plafond de dépense atteint (``'jour'``, ``'mois'``) ou ``''`` :
    la file saute alors les tâches LLM jusqu'au lendemain ou jusqu'au mois
    suivant (comme ``serge/interpreter/queue.py``).
    """
    return budget_reached(conn, policy, now[:10])


def _attente(conn: sqlite3.Connection, plafond: str) -> str:
    """Pourquoi des tâches prêtes attendent, en une phrase, ou ``''``."""
    if not plafond:
        return ''
    row = conn.execute(
        'SELECT COUNT(*) FROM tasks t JOIN invocations i'
        " ON i.id=t.invocation_id WHERE t.status='ready'"
        " AND i.type='llm' AND i.deleted_at=''"
    ).fetchone()
    n = int(row[0]) if row else 0
    if not n:
        return ''
    quand = 'demain' if plafond == 'jour' else 'le mois prochain'
    return (
        f'Plafond du {plafond} atteint : {n} tâche(s) LLM attendent {quand},'
        ' ou un plafond plus haut (page Policy).'
    )


def prochaines(
    conn: sqlite3.Connection, now: str, *, llm: bool = True
) -> dict[str, str]:
    """La prochaine tâche de chaque file : ``{file: id de tâche}``.

    Avec ``llm`` faux (plafond du jour ou du mois atteint), les tâches LLM sont
    sautées, comme le fait la file.
    """
    out: dict[str, str] = {}
    for queue in _files(conn):
        found = next_task(conn, queue, now, llm=llm)
        if found:
            out[queue] = found
    return out


def _prochaine(
    conn: sqlite3.Connection, now: str, *, llm: bool = True
) -> dict[str, Any] | None:
    """La plus prioritaire des prochaines tâches, toutes files confondues."""
    ids = list(prochaines(conn, now, llm=llm).values())
    if not ids:
        return None
    row = conn.execute(
        _SELECT + f' WHERE t.id IN ({",".join("?" * len(ids))})'
        ' ORDER BY t.priority DESC, t.created_at LIMIT 1',
        ids,
    ).fetchone()
    return _resume(row) if row else None


def _compte(conn: sqlite3.Connection, status: str) -> int:
    """Les tâches dans cet état, sauf celles d'une invocation supprimée,
    qui ne partiront jamais (une invocation éteinte, elle, attend)."""
    row = conn.execute(
        'SELECT COUNT(*) FROM tasks t JOIN invocations i'
        " ON i.id=t.invocation_id WHERE t.status=? AND i.deleted_at=''",
        (status,),
    ).fetchone()
    return int(row[0]) if row else 0


def _en_cours(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    return [
        _resume(row)
        for row in conn.execute(
            _SELECT + " WHERE t.status='running'"
            ' ORDER BY t.started_at DESC LIMIT ?',
            (limit,),
        ).fetchall()
    ]


def tache_en_cours(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """La tâche en cours la plus récente, ou None."""
    running = _en_cours(conn, 1)
    return running[0] if running else None


def project_hero(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Ce qui tourne, combien attendent, et la prochaine tâche.

    Returns:
        ``{running, ready, next, attente}`` ; ``attente`` dit pourquoi des
        tâches prêtes ne partent pas (le plafond du jour ou du mois), ou
        ``''``.
    """
    plafond = plafond_atteint(conn, policy, now)
    return {
        'running': tache_en_cours(conn),
        'ready': _compte(conn, 'ready'),
        'next': _prochaine(conn, now, llm=not plafond),
        'attente': _attente(conn, plafond),
    }


def project_file(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les tâches en cours (10 au plus), le nombre de prêtes, la prochaine.

    Returns:
        ``{running, ready_count, next, attente}``.
    """
    plafond = plafond_atteint(conn, policy, now)
    return {
        'running': _en_cours(conn, 10),
        'ready_count': _compte(conn, 'ready'),
        'next': _prochaine(conn, now, llm=not plafond),
        'attente': _attente(conn, plafond),
    }


def project_scheduler(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Page Système : la prochaine tâche et les compteurs des files.

    Returns:
        ``{next, ready, running, bloques, attente}`` ; ``bloques`` compte
        les tâches prêtes dont la date « pas avant » n'est pas encore
        passée.
    """
    plafond = plafond_atteint(conn, policy, now)
    row = conn.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='ready' AND not_before>?",
        (now,),
    ).fetchone()
    return {
        'next': _prochaine(conn, now, llm=not plafond),
        'ready': _compte(conn, 'ready'),
        'running': _compte(conn, 'running'),
        'bloques': int(row[0]) if row else 0,
        'attente': _attente(conn, plafond),
    }


def project_file_detail(conn: sqlite3.Connection, now: str) -> dict[str, Any]:
    """Les deux files en entier : en cours, puis prêtes par priorité."""
    plafond = plafond_atteint(conn, policy_en_vigueur(conn), now)
    suivantes = set(prochaines(conn, now, llm=not plafond).values())
    rows = conn.execute(
        _SELECT + " WHERE t.status IN ('ready', 'running')"
        " ORDER BY t.queue_id, CASE t.status WHEN 'running' THEN 0 ELSE 1"
        ' END, t.priority DESC, t.created_at'
    ).fetchall()
    # Les tâches qui ne partiront pas viennent en dernier, sans rang.
    rows = sorted(rows, key=lambda r: bool(_bloquee(r, plafond)))
    lignes = []
    enfants = []
    rang = 0
    for row in rows:
        ident, titre = str(row[0]), str(row[1])
        etat = ETATS_TACHE.get(str(row[5]), str(row[5]))
        pause = str(row[7] or '')
        bloquee = _bloquee(row, plafond)
        if not bloquee:
            rang += 1
        if bloquee:
            etat = bloquee
        elif ident in suivantes:
            etat = 'Prochaine'
        elif row[5] == 'ready' and pause > now:
            etat = 'En pause'
        lignes.append(
            {
                'id': ident,
                'type': 'task',
                'cellules': [
                    '—' if bloquee else str(rang),
                    titre,
                    str(row[4]),
                    etat,
                    str(row[6]),
                    str(row[10] or row[2] or '—'),
                    pause if pause > now else '—',
                    str(row[8] or '—'),
                    str(row[9]),
                ],
            }
        )
        enfants.append(
            {
                'type': 'task',
                'id': ident,
                'titre': f'{titre} ({bloquee})'
                if bloquee
                else f'{rang}. {titre}',
            }
        )
    return {
        'type': 'file',
        'id': 'canon',
        'titre': 'Files de tâches',
        'pourquoi': (
            'Deux files tournent en même temps : les conversations (tâches'
            ' courtes) et les travaux (tâches longues). Chacune prend sa'
            ' tâche prête la plus prioritaire, la plus ancienne d’abord.'
        ),
        'champs': [
            {
                'k': 'Prêtes',
                'v': str(
                    sum(1 for r in rows if r[5] == 'ready' and not r[12])
                ),
            },
            {
                'k': 'En cours',
                'v': str(sum(1 for r in rows if r[5] == 'running')),
            },
        ],
        'tableau': {
            'colonnes': [
                'Rang',
                'Invocation',
                'File',
                'État',
                'Priorité',
                'Business',
                'Pas avant',
                'Créée',
                'Essais',
            ],
            'lignes': lignes,
        },
        'enfants': enfants,
        'preuve': '',
    }


def fiche_tache(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """La fiche d'une tâche : son invocation, ses paramètres, ce qu'elle a reçu."""
    row = _row(conn, 'SELECT * FROM tasks WHERE id=?', (ident,))
    if row is None:
        return None
    inv = _row(
        conn,
        'SELECT title FROM invocations WHERE id=?',
        (row['invocation_id'],),
    )
    titre = str((inv['title'] if inv else '') or row['invocation_id'])
    params = conn.execute(
        'SELECT name, value FROM task_params WHERE task_id=? ORDER BY name',
        (ident,),
    ).fetchall()
    recus = conn.execute(
        "SELECT COALESCE(NULLIF(it.label, ''), it.tool_id), ti.rows_given,"
        ' ti.rows_left_out FROM task_inputs ti'
        ' LEFT JOIN invocation_tools it ON it.id=ti.invocation_tool_id'
        ' WHERE ti.task_id=? ORDER BY it.position',
        (ident,),
    ).fetchall()
    champs = [
        ('Invocation', titre),
        ('File', row['queue_id']),
        ('État', ETATS_TACHE.get(row['status'], row['status'])),
        ('Priorité', row['priority']),
        ('Essais', row['attempts']),
        ('Lancée par', row['origin'] or '—'),
        ('Créée', row['created_at']),
        ('Commencée', row['started_at'] or '—'),
        ('Finie', row['finished_at'] or '—'),
    ]
    if row['not_before']:
        champs.append(('Pas avant', row['not_before']))
    if row['last_error']:
        champs.append(('Erreur', row['last_error']))
    champs += [(f'Paramètre {p[0]}', p[1]) for p in params]
    champs += [
        (f'Lu d’office : {r[0]}', f'{r[1]} lignes, {r[2]} laissées de côté')
        for r in recus
    ]
    for titre_vue, table, donnees, laissees in conn.execute(
        "SELECT COALESCE(NULLIF(v.title, ''), s.table_name), s.table_name,"
        ' s.rows_given, s.rows_left_out FROM task_seen_tables s'
        ' LEFT JOIN table_views v ON v.table_name=s.table_name'
        ' WHERE s.task_id=? ORDER BY s.table_name',
        (ident,),
    ).fetchall():
        champs.append(
            ('Ses leçons', f'{donnees} leçons, {laissees} laissées de côté')
            if table == 'lessons'
            else (
                f'Pour comparer : {titre_vue}',
                f'{donnees} lignes, {laissees} laissées de côté',
            )
        )
    actions = []
    if row['status'] == 'ready':
        actions.append(
            {
                'libelle': 'Annuler la tâche',
                'route': '/owner/api/tache/annuler',
                'charge': {'task_id': ident},
                'confirmer': 'La tâche est retirée de sa file et ne partira'
                ' pas. Ce qu’elle aurait lancé ensuite ne partira pas non'
                ' plus.',
            }
        )
    if row['status'] == 'failed':
        actions.append(
            {
                'libelle': 'Relancer la tâche',
                'route': '/owner/api/tache/relancer',
                'charge': {'task_id': ident},
                'confirmer': 'La tâche repart de zéro dans sa file, au'
                ' prochain tour, si Serge est démarré.',
            }
        )
    return {
        'type': 'task',
        'id': ident,
        'titre': titre,
        'actions': actions,
        'pourquoi': (
            'Une tâche lance une invocation avec ses paramètres. Elle est'
            ' enregistrée en base dès qu’elle est finie.'
        ),
        'champs': _champs(champs),
        'enfants': _liens(
            [('llm', str(row['invocation_id']), 'Invocation')]
            + [
                ('venture', str(p[1]), 'Business')
                for p in params
                if p[0] == 'venture_id' and p[1]
            ]
        ),
        'preuve': json.dumps(
            {
                'parametres': {str(p[0]): str(p[1]) for p in params},
                'erreur': row['last_error'],
            },
            ensure_ascii=False,
            indent=2,
        ),
    }
