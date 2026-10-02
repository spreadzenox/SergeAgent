#!/usr/bin/env python3
"""Ce qu'une invocation apprend sur elle-même : sa place, et ses leçons.

Le bloc « Qui est Serge » est fabriqué à chaque appel, à partir de la
base : la présentation de Serge (``serge_texts``), la chaîne des 8 étapes
(``pipeline_steps``), l'étape de l'invocation, et ce qui vient juste avant
et juste après elle, lu dans les liens et les déclencheurs. Il est donc
toujours à jour, sans rien d'écrit pour une invocation en particulier.

Les leçons sont celles rattachées à l'invocation (portée
``invocation:<id>``), puis à son étape (``etape:<id>``), puis à tout Serge
(``global``), les plus fiables d'abord. Une leçon dépassée ou expirée
n'est jamais donnée.
"""

from __future__ import annotations

import sqlite3

from serge.horloge import iso_utc


def _titles(conn: sqlite3.Connection, sql: str, args: tuple) -> list[str]:
    return [
        f'« {title or other} »' + (f' (« {link} »)' if link else '')
        for title, other, link in conn.execute(sql, args).fetchall()
    ]


def serge_text(conn: sqlite3.Connection, ident: str, **values: object) -> str:
    """Un texte envoyé au modèle, tel qu'il est en base (page Pipeline).

    Ses repères sont remplacés par ``values``. Exemple :
    ``serge_text(conn, 'format_retry', erreurs='champ manquant')``
    remplace ``{erreurs}``. Un texte vide ou absent rend ``''`` : il n'est
    pas envoyé.
    """
    row = conn.execute(
        'SELECT body FROM serge_texts WHERE id=?', (ident,)
    ).fetchone()
    body = str(row[0]).strip() if row else ''
    for name, value in values.items():
        body = body.replace('{' + name + '}', str(value))
    return body


def serge_intro(
    conn: sqlite3.Connection, invocation_id: str, title: str, step_id: str
) -> str:
    """Le bloc « Qui est Serge » et « Ta place » d'une invocation."""
    parts: list[str] = []
    intro = serge_text(conn, 'presentation')
    steps = conn.execute(
        'SELECT id, titre FROM pipeline_steps ORDER BY rang'
    ).fetchall()
    chain = ' → '.join(
        f'{n}. {titre or ident}' for n, (ident, titre) in enumerate(steps, 1)
    )
    if chain:
        intro += f'\n\nLa chaîne : {chain}.'
    if intro.strip():
        parts.append(f'# Qui est Serge\n{intro.strip()}')
    place = f'Tu es « {title} »'
    for n, (ident, titre) in enumerate(steps, 1):
        if ident == step_id:
            place += f', dans l’étape {n} « {titre or ident} »'
    lines = [place + '.']
    before = _titles(
        conn,
        'SELECT i.title, i.id, l.title FROM links l'
        ' JOIN invocations i ON i.id=l.from_invocation_id'
        " WHERE l.to_invocation_id=? AND l.enabled=1 AND l.deleted_at=''"
        " AND i.deleted_at='' ORDER BY l.id",
        (invocation_id,),
    )
    before += [
        f'le déclencheur « {t} »'
        for (t,) in conn.execute(
            'SELECT title FROM triggers WHERE invocation_id=? AND enabled=1'
            " AND deleted_at='' ORDER BY id",
            (invocation_id,),
        ).fetchall()
    ]
    if before:
        lines.append('Avant toi : ' + ' ; '.join(before) + '.')
    after = _titles(
        conn,
        'SELECT i.title, i.id, l.title FROM links l'
        ' JOIN invocations i ON i.id=l.to_invocation_id'
        " WHERE l.from_invocation_id=? AND l.enabled=1 AND l.deleted_at=''"
        " AND i.deleted_at='' ORDER BY l.id",
        (invocation_id,),
    )
    lines.append(
        'Après toi : ' + ' ; '.join(after) + '.'
        if after
        else 'Après toi : rien ; ta réponse est écrite en base.'
    )
    parts.append('# Ta place\n' + '\n'.join(lines))
    return '\n\n'.join(parts)


PORTEES = {
    'invocation': 'pour toi',
    'etape': 'pour ton étape',
    'global': 'pour tout Serge',
}


def lessons_for(
    conn: sqlite3.Connection, invocation_id: str, step_id: str, limit: int
) -> tuple[list[tuple[str, float, str]], int]:
    """Ses leçons, les plus fiables d'abord, et leur nombre total.

    Returns:
        ``([(énoncé, fiabilité, portée)], total)`` ; la portée vaut
        ``invocation``, ``etape`` ou ``global``.
    """
    scopes = (f'invocation:{invocation_id}', f'etape:{step_id}', 'global')
    where = (
        " FROM lessons WHERE status<>'deprecated'"
        " AND (expires_at='' OR expires_at>?) AND scope IN (?,?,?)"
    )
    args = (iso_utc(), *scopes)
    rows = conn.execute(
        'SELECT statement, confidence, scope' + where + ' ORDER BY CASE scope'
        ' WHEN ? THEN 0 WHEN ? THEN 1 ELSE 2 END, confidence DESC, id'
        ' LIMIT ?',
        (*args, scopes[0], scopes[1], limit),
    ).fetchall()
    total = int(conn.execute('SELECT COUNT(*)' + where, args).fetchone()[0])
    return [
        (str(s), float(c), str(scope).split(':')[0]) for s, c, scope in rows
    ], total


def lessons_block(
    conn: sqlite3.Connection,
    invocation_id: str,
    step_id: str,
    task_id: str,
    limit: int,
) -> str:
    """Ses leçons, données d'office, les plus fiables d'abord.

    Le nombre de leçons données et laissées de côté est noté dans
    ``task_seen_tables`` (table ``lessons``), pour la fiche de la tâche.
    """
    rows, total = lessons_for(conn, invocation_id, step_id, limit)
    if not total:
        return ''
    left = max(0, total - len(rows))
    conn.execute(
        'INSERT OR REPLACE INTO task_seen_tables(task_id, table_name,'
        " rows_given, rows_left_out) VALUES(?, 'lessons', ?, ?)",
        (task_id, len(rows), left),
    )
    lines = [
        f'- {statement} ({PORTEES[scope]}, fiabilité {confidence:.1f})'
        for statement, confidence, scope in rows
    ]
    if left:
        lines.append(f'({left} autres leçons ne sont pas montrées.)')
    return '## Tes leçons (les plus fiables d’abord)\n' + '\n'.join(lines)
