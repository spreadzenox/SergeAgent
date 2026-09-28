#!/usr/bin/env python3
"""Ce que voit une invocation pour comparer, et les outils pour lire le reste.

Le deuxième cercle d'une invocation, ce sont les tables qu'elle voit en
version courte : les tables où elle écrit, plus ou moins les ajustements
réglés dans Mission Control (``invocation_compare_tables``). Seules les
tables décrites dans ``table_views`` peuvent être vues, et seulement par
leurs colonnes lisibles (``table_view_columns``).

Exemple : « Formuler des idées » écrit des business ; elle reçoit donc
d'office leur numéro et leur nom, les plus récents d'abord. Avec « Lire
les tables que je vois », elle peut demander la fiche complète du
business n° 12, ou tous les business au statut ``CANDIDATE`` ; avec
« Lire l'historique », ce qui est arrivé à ce business. Rien de tout cela
n'est propre à une invocation : les deux outils sont construits à chaque
appel à partir de ce que la base dit d'elle.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any

from serge.interpreter.rules import safe_name, table_columns


class ViewSeedError(ValueError):
    """Une vue de table de ``pipeline.yaml`` est invalide."""


def _write_tables(conn: sqlite3.Connection, invocation_id: str) -> list[str]:
    tables: list[str] = []
    for (table,) in conn.execute(
        'SELECT table_name FROM invocation_writes WHERE invocation_id=?'
        ' ORDER BY position',
        (invocation_id,),
    ).fetchall():
        if str(table) not in tables:
            tables.append(str(table))
    return tables


def compare_tables(
    conn: sqlite3.Connection, invocation_id: str
) -> list[tuple[str, str]]:
    """Chaque table de son deuxième cercle, et pourquoi.

    Returns:
        ``(table, raison)`` ; raison vaut ``ecrit`` (elle y écrit),
        ``ajoutee`` (ajoutée dans MC) ou ``retiree`` (elle y écrit, mais
        on l'a retirée : elle ne la voit pas).
    """
    overrides = {
        str(table): bool(included)
        for table, included in conn.execute(
            'SELECT table_name, included FROM invocation_compare_tables'
            ' WHERE invocation_id=? ORDER BY table_name',
            (invocation_id,),
        ).fetchall()
    }
    views = {
        str(r[0]) for r in conn.execute('SELECT table_name FROM table_views')
    }
    out: list[tuple[str, str]] = []
    writes = _write_tables(conn, invocation_id)
    for table in writes:
        if table in views:
            out.append(
                (table, 'ecrit' if overrides.get(table, True) else 'retiree')
            )
    for table, included in overrides.items():
        if included and table not in writes and table in views:
            out.append((table, 'ajoutee'))
    return out


def seen_tables(conn: sqlite3.Connection, invocation_id: str) -> list[str]:
    """Les tables que l'invocation voit en version courte."""
    return [
        t for t, why in compare_tables(conn, invocation_id) if why != 'retiree'
    ]


def history_tables(conn: sqlite3.Connection, invocation_id: str) -> list[str]:
    """Les tables dont elle peut lire l'historique d'une ligne.

    Ce sont celles qu'elle voit en version courte, et celles qu'elle
    reçoit d'office par ses lectures (ce qu'elle doit traiter).
    """
    tables = seen_tables(conn, invocation_id)
    for (table,) in conn.execute(
        'SELECT DISTINCT d.table_name FROM invocation_tools it'
        ' JOIN tool_db_tables d ON d.tool_id=it.tool_id'
        " WHERE it.invocation_id=? AND it.mode='given' ORDER BY d.table_name",
        (invocation_id,),
    ).fetchall():
        if str(table) not in tables:
            tables.append(str(table))
    return tables


def view_columns(
    conn: sqlite3.Connection, table: str, *, short: bool = False
) -> list[str]:
    """Les colonnes lisibles d'une table (ou celles de sa version courte)."""
    real = table_columns(conn, table)
    return [
        str(name)
        for (name,) in conn.execute(
            'SELECT column_name FROM table_view_columns WHERE table_name=?'
            f'{" AND short=1" if short else ""} ORDER BY position, column_name',
            (table,),
        ).fetchall()
        if str(name) in real
    ]


def _title(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        'SELECT title FROM table_views WHERE table_name=?', (table,)
    ).fetchone()
    return str(row[0]) if row and str(row[0]) else table


def _order(conn: sqlite3.Connection, table: str) -> str:
    row = conn.execute(
        'SELECT order_column FROM table_views WHERE table_name=?', (table,)
    ).fetchone()
    column = str(row[0]) if row else ''
    if column and column in table_columns(conn, table):
        return f' ORDER BY "{safe_name(column)}" DESC, rowid DESC'
    return ' ORDER BY rowid DESC'


def _select(
    conn: sqlite3.Connection,
    table: str,
    columns: list[str],
    where: tuple[str, Any] | None,
    limit: int,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """Les lignes demandées, les plus récentes d'abord, et leur nombre exact."""
    name = safe_name(table)
    clause, bound = '', []
    if where is not None:
        clause = f' WHERE "{safe_name(where[0])}"=?'
        bound = [where[1]]
    cols = ', '.join(f'"{safe_name(c)}"' for c in columns)
    rows = conn.execute(
        f'SELECT {cols} FROM "{name}"{clause}{_order(conn, table)}'
        ' LIMIT ? OFFSET ?',
        [*bound, limit, offset],
    ).fetchall()
    total = conn.execute(
        f'SELECT COUNT(*) FROM "{name}"{clause}', bound
    ).fetchone()
    return [dict(zip(columns, row, strict=True)) for row in rows], int(
        total[0]
    )


def short_blocks(
    conn: sqlite3.Connection, invocation_id: str, task_id: str, limit: int
) -> list[str]:
    """La version courte de chaque table à comparer, donnée d'office.

    Au plus ``limit`` lignes par table, les plus récentes d'abord, suivies
    du nombre exact de lignes laissées de côté. Chaque compte est noté dans
    ``task_seen_tables`` pour la fiche de la tâche.
    """
    blocks: list[str] = []
    for table in seen_tables(conn, invocation_id):
        columns = view_columns(conn, table, short=True)
        if not columns:
            continue
        rows, total = _select(conn, table, columns, None, limit)
        left = max(0, total - len(rows))
        body = json.dumps(rows, ensure_ascii=False, default=str)
        if left:
            body += (
                f'\n({left} autres lignes ne sont pas montrées ; « Lire les'
                ' tables que je vois » les donne.)'
            )
        conn.execute(
            'INSERT OR REPLACE INTO task_seen_tables(task_id, table_name,'
            ' rows_given, rows_left_out) VALUES(?,?,?,?)',
            (task_id, table, len(rows), left),
        )
        blocks.append(
            f'## {_title(conn, table)} (version courte, pour comparer)\n{body}'
        )
    return blocks


def _page_size(conn: sqlite3.Connection, invocation_id: str) -> int:
    row = conn.execute(
        'SELECT default_max_rows FROM invocations WHERE id=?', (invocation_id,)
    ).fetchone()
    return max(1, int(row[0])) if row else 50


def _page(args: Mapping[str, Any]) -> int:
    try:
        return max(1, int(args.get('page') or 1))
    except (TypeError, ValueError):
        return 1


def read_seen_table(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """« Lire les tables que je vois » : toutes les colonnes lisibles.

    Le modèle choisit une table de son deuxième cercle, et peut filtrer
    sur une colonne lisible égale à une valeur (``id`` pour une seule
    ligne). Les lignes viennent page par page.
    """
    table = str(args.get('table') or '')
    tables = seen_tables(conn, inv)
    if table not in tables:
        return {'ok': False, 'code': 'table_non_vue', 'tables': tables}
    columns = view_columns(conn, table)
    column = str(args.get('column') or '')
    where = None
    if column:
        if column not in columns:
            return {
                'ok': False,
                'code': 'colonne_non_lisible',
                'colonnes': columns,
            }
        value = args.get('value')
        where = (
            column,
            value if isinstance(value, int | float) else str(value or ''),
        )
    size, page = _page_size(conn, inv), _page(args)
    rows, total = _select(conn, table, columns, where, size, (page - 1) * size)
    return {
        'ok': True,
        'table': table,
        'rows': rows,
        'page': page,
        'pages': max(1, -(-total // size)),
        'total': total,
    }


def row_history(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """« Lire l'historique » d'une ligne : ses événements, du plus récent."""
    table = str(args.get('table') or '')
    tables = history_tables(conn, inv)
    if table not in tables:
        return {'ok': False, 'code': 'table_non_vue', 'tables': tables}
    row_id = str(args.get('id') or '')
    if not row_id:
        return {'ok': False, 'code': 'id_manquant'}
    size, page = _page_size(conn, inv), _page(args)
    events = [
        {
            'quand': str(ts),
            'qui': str(actor),
            'quoi': str(kind),
            'detail': json.loads(payload or '{}'),
        }
        for ts, actor, kind, payload in conn.execute(
            'SELECT e.ts, e.actor, e.type, e.payload_json FROM event_rows r'
            ' JOIN events e ON e.id=r.event_id'
            ' WHERE r.table_name=? AND r.row_id=?'
            ' ORDER BY e.id DESC LIMIT ? OFFSET ?',
            (table, row_id, size, (page - 1) * size),
        ).fetchall()
    ]
    total = conn.execute(
        'SELECT COUNT(*) FROM event_rows WHERE table_name=? AND row_id=?',
        (table, row_id),
    ).fetchone()
    return {
        'ok': True,
        'table': table,
        'id': row_id,
        'rows': events,
        'page': page,
        'total': int(total[0]),
    }


def _describe(conn: sqlite3.Connection, tables: list[str], short: bool) -> str:
    lines = []
    for table in tables:
        row = conn.execute(
            'SELECT description FROM table_views WHERE table_name=?', (table,)
        ).fetchone()
        what = str(row[0]) if row and str(row[0]) else _title(conn, table)
        cols = ', '.join(view_columns(conn, table, short=short))
        lines.append(f'{table} : {what} Colonnes : {cols}.')
    return ' '.join(lines)


def _read_choices(
    conn: sqlite3.Connection, inv: str
) -> tuple[dict[str, list[str]], str] | None:
    tables = seen_tables(conn, inv)
    if not tables:
        return None
    return {'table': tables}, _describe(conn, tables, short=False)


def _history_choices(
    conn: sqlite3.Connection, inv: str
) -> tuple[dict[str, list[str]], str] | None:
    tables = history_tables(conn, inv)
    if not tables:
        return None
    return {'table': tables}, 'Tables : ' + ', '.join(tables) + '.'


# Ce que le schéma d'un outil propose au modèle dépend de l'invocation qui
# l'appelle : les tables qu'elle voit. ``None`` : l'outil ne lui sert pas.
Choices = Callable[
    [sqlite3.Connection, str], tuple[dict[str, list[str]], str] | None
]
CHOICES: dict[str, Choices] = {
    'seen_table_read': _read_choices,
    'row_history': _history_choices,
}


def seed_table_views(conn: sqlite3.Connection, raw: Any) -> None:
    """Range les vues des tables de ``pipeline.yaml``, sans rien écraser.

    Format : ``[{table, title, description, order, columns: [{name, short,
    description}]}]``. Une vue déjà en base garde ses réglages ; seules
    ses colonnes nouvelles s'ajoutent (exemple : la famille d'un business,
    ajoutée au lot 7).

    Raises:
        ViewSeedError: Table ou colonne absente de la base.
    """
    for view in raw or []:
        table = str(view['table'])
        real = table_columns(conn, table)
        if not real:
            raise ViewSeedError(f'table_views : table absente {table}')
        order = str(view.get('order', ''))
        if order and order not in real:
            raise ViewSeedError(
                f'table_views.{table} : colonne absente {order}'
            )
        conn.execute(
            'INSERT OR IGNORE INTO table_views(table_name, title, description,'
            ' order_column, updated_by) VALUES(?,?,?,?,?)',
            (
                table,
                str(view.get('title', '')),
                str(view.get('description', '')).strip(),
                order,
                'pipeline.yaml',
            ),
        )
        for position, column in enumerate(view.get('columns') or []):
            name = str(column['name'])
            if name not in real:
                raise ViewSeedError(
                    f'table_views.{table} : colonne absente {name}'
                )
            conn.execute(
                'INSERT OR IGNORE INTO table_view_columns(table_name,'
                ' column_name, short, description, position)'
                ' VALUES(?,?,?,?,?)',
                (
                    table,
                    name,
                    int(bool(column.get('short', False))),
                    str(column.get('description', '')),
                    position,
                ),
            )
