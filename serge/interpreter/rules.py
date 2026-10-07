#!/usr/bin/env python3
"""Les protections de l'écriture, toutes réglées en base.

1. Le catalogue (``writable_tables``, ``writable_columns``) : une table ou
   une colonne absente ne peut jamais être écrite par une invocation.
2. Les changements de statut permis (``status_transitions``) : dès qu'une
   colonne a des lignes ici, seuls ces changements passent. Exemple :
   ``CANDIDATE`` → ``POC_SELECTED`` est permis ; comme rien ne permet
   ``SMOKE_RUNNING`` → ``POC_SELECTED``, un business déjà en test est
   refusé.
3. Les doublons (``dedup_rules``) : ``exact`` compare les textes sans
   majuscules, accents ni espaces en trop ; ``shared_words`` compare la
   part de mots en commun, par exemple 72 %.
4. Les quotas (``table_quotas``) : « au plus N lignes dont telle colonne
   vaut l'une de ces valeurs ». Exemple : au plus 3 business au statut
   ``POC_SELECTED`` ; le quatrième est refusé, quelle que soit
   l'invocation qui écrit.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Mapping
from typing import Any


class WriteConfigError(ValueError):
    """La règle d'écriture vise une table ou une colonne interdite."""


_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def safe_name(name: str) -> str:
    """Un nom de table ou de colonne, refusé s'il n'est pas un simple nom.

    Raises:
        WriteConfigError: Nom invalide.
    """
    if not _IDENT.match(name):
        raise WriteConfigError(f'nom invalide : {name!r}')
    return name


def check_catalogue(
    conn: sqlite3.Connection, table: str, operation: str, columns: list[str]
) -> None:
    """Refuse une écriture hors du catalogue.

    Raises:
        WriteConfigError: Table, opération ou colonne non autorisée.
    """
    row = conn.execute(
        'SELECT can_insert, can_update, can_delete FROM writable_tables'
        ' WHERE table_name=?',
        (table,),
    ).fetchone()
    if row is None:
        raise WriteConfigError(f'table non inscriptible : {table}')
    allowed = {'insert': row[0], 'update': row[1], 'delete': row[2]}.get(
        operation
    )
    if not allowed:
        raise WriteConfigError(f'{operation} interdit sur {table}')
    permitted = {
        str(r[0])
        for r in conn.execute(
            'SELECT column_name FROM writable_columns WHERE table_name=?',
            (table,),
        ).fetchall()
    }
    for column in columns:
        if column not in permitted:
            raise WriteConfigError(
                f'colonne non inscriptible : {table}.{column}'
            )


def transition_refusal(
    conn: sqlite3.Connection,
    table: str,
    values: Mapping[str, Any],
    current: Mapping[str, Any] | None,
) -> str:
    """La raison du refus d'un changement de statut, ou ``''``.

    ``current`` vaut ``None`` pour une ligne nouvelle : la valeur de départ
    est alors vide.
    """
    for column, value in values.items():
        rules = conn.execute(
            'SELECT from_value, to_value FROM status_transitions'
            ' WHERE table_name=? AND column_name=?',
            (table, column),
        ).fetchall()
        if not rules:
            continue
        before = '' if current is None else str(current.get(column) or '')
        after = str(value)
        if current is not None and before == after:
            continue
        if (before, after) not in {(str(a), str(b)) for a, b in rules}:
            shown = before or '(création)'
            return (
                f'{table}.{column} : passage de {shown} à {after} non permis'
            )
    return ''


def _normal(text: str) -> str:
    folded = unicodedata.normalize('NFKD', text.casefold())
    bare = ''.join(ch for ch in folded if not unicodedata.combining(ch))
    return ' '.join(bare.split())


def find_duplicate(
    conn: sqlite3.Connection, table: str, values: Mapping[str, Any]
) -> tuple[str, str, str] | None:
    """Une ligne existante trop proche : ``(règle, clé, action)``, ou ``None``.

    La clé est l'``id`` de la ligne existante (ou son ``rowid``).
    """
    for rule_id, method, threshold, action in conn.execute(
        'SELECT id, method, threshold, on_duplicate FROM dedup_rules'
        ' WHERE table_name=? ORDER BY id',
        (table,),
    ).fetchall():
        columns = [
            str(r[0])
            for r in conn.execute(
                'SELECT column_name FROM dedup_rule_columns WHERE rule_id=?'
                ' ORDER BY column_name',
                (rule_id,),
            ).fetchall()
        ]
        if not columns:
            continue
        safe_name(table)
        for column in columns:
            safe_name(column)
        wanted = _normal(' '.join(str(values.get(c) or '') for c in columns))
        if not wanted:
            continue
        key = 'id' if _has_column(conn, table, 'id') else 'rowid'
        select = ', '.join(f'"{c}"' for c in columns)
        for row in conn.execute(
            f'SELECT {key}, {select} FROM "{table}"'
        ).fetchall():
            existing = _normal(' '.join(str(v or '') for v in row[1:]))
            if method == 'exact':
                same = existing == wanted
            else:
                a, b = set(wanted.split()), set(existing.split())
                same = bool(a | b) and len(a & b) * 100 >= threshold * len(
                    a | b
                )
            if same:
                return str(rule_id), str(row[0]), str(action)
    return None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in table_columns(conn, table)


def table_columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    """Les colonnes réelles d'une table : type, obligatoire, clé."""
    return {
        str(r[1]): {
            'type': str(r[2]).upper(),
            'notnull': bool(r[3]),
            'default': r[4],
            'pk': bool(r[5]),
        }
        for r in conn.execute(f'PRAGMA table_info("{safe_name(table)}")')
    }


def quota_refusal(
    conn: sqlite3.Connection,
    table: str,
    values: Mapping[str, Any],
    current: Mapping[str, Any] | None,
) -> str:
    """La raison du refus d'une ligne qui dépasserait un quota, ou ``''``.

    Une ligne ne compte que si elle entre dans le quota : un business déjà
    ``POC_SELECTED`` qu'on modifie ne prend pas une place de plus.
    """
    for quota_id, column, counted, maximum in conn.execute(
        'SELECT id, column_name, counted_values, max_value FROM table_quotas'
        ' WHERE table_name=? ORDER BY id',
        (table,),
    ).fetchall():
        column = safe_name(str(column))
        if column not in values:
            continue
        compte = [v.strip() for v in str(counted).split(',') if v.strip()]
        if str(values[column]) not in compte:
            continue
        if current is not None and str(current.get(column) or '') in compte:
            continue
        marques = ', '.join('?' for _ in compte)
        row = conn.execute(
            f'SELECT COUNT(*) FROM "{safe_name(table)}"'
            f' WHERE "{column}" IN ({marques})',
            compte,
        ).fetchone()
        if int(row[0]) >= int(maximum):
            return (
                f'quota {quota_id} : au plus {maximum} ligne(s) de {table}'
                f' avec {column} parmi {", ".join(compte)}'
            )
    return ''


def quota_usage(
    conn: sqlite3.Connection, quota_id: str
) -> tuple[int, int, str] | None:
    """Où en est un quota : ``(lignes comptées, maximum, description)``.

    Exemple : ``(2, 3, 'Au plus 3 business en test')``. ``None`` si le
    quota n'existe pas.
    """
    row = conn.execute(
        'SELECT table_name, column_name, counted_values, max_value,'
        ' description FROM table_quotas WHERE id=?',
        (quota_id,),
    ).fetchone()
    if row is None:
        return None
    table, column, counted, maximum, description = row
    compte = [v.strip() for v in str(counted).split(',') if v.strip()]
    marques = ', '.join('?' for _ in compte) or "''"
    used = conn.execute(
        f'SELECT COUNT(*) FROM "{safe_name(str(table))}"'
        f' WHERE "{safe_name(str(column))}" IN ({marques})',
        compte,
    ).fetchone()
    return int(used[0]), int(maximum), str(description or quota_id)


def cancel_tasks_on_change(
    conn: sqlite3.Connection,
    table: str,
    row_ids: list[Any],
    values: Mapping[str, Any],
    now: str,
) -> int:
    """Annule les tâches en attente des lignes qui viennent de changer.

    Les règles sont réglées sur la table (``task_cancel_rules``). Exemple :
    un cycle d'écoute qui passe à ``ABANDONED`` annule ses tâches en
    attente (celles dont le paramètre ``cycle_id`` vaut son numéro).

    Returns:
        Le nombre de tâches annulées.
    """
    total = 0
    for column, value, param in conn.execute(
        'SELECT column_name, value, param_name FROM task_cancel_rules'
        ' WHERE table_name=? ORDER BY column_name, param_name',
        (table,),
    ).fetchall():
        if column not in values or str(values[column]) != str(value):
            continue
        for row_id in row_ids:
            cursor = conn.execute(
                "UPDATE tasks SET status='cancelled', finished_at=?,"
                " last_error=? WHERE status='ready' AND id IN"
                ' (SELECT task_id FROM task_params WHERE name=? AND value=?)',
                (
                    now,
                    f'{table} {row_id} : {column} = {value}',
                    param,
                    str(row_id),
                ),
            )
            total += cursor.rowcount
    return total


def condition_met(value: Any, op: str, expected: str) -> bool:
    """Une condition d'un lien ou d'une écriture est-elle remplie ?

    ``op`` : ``=`` (égal à ``expected``), ``!=`` (différent), ``non_vide``,
    ou vide (pas de condition). Exemple : ``condition_met('refus', '=',
    'refus')`` est vrai ; ``condition_met('', 'non_vide', '')`` est faux.

    Raises:
        ValueError: Opérateur inconnu.
    """
    if not op:
        return True
    text = '' if value is None else str(value)
    if op == '=':
        return text == expected
    if op == '!=':
        return text != expected
    if op == 'non_vide':
        return bool(text.strip())
    raise ValueError(f'condition inconnue : {op}')
