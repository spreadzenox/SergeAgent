#!/usr/bin/env python3
"""Les réglages généraux en base : les remplir, les lire, les changer.

Un réglage est une ligne de ``policy_settings`` (décision Q68). Exemple :
``budget.monthly_eur`` vaut 50, titre « Plafond du mois », sorte ``eur``,
de 0 à 500. Il est changé dans Mission Control, page Policy ; il garde
sa valeur précédente (qui l'a remplacée, quand) pour « Remettre la valeur
précédente ».

Le remplissage (au démarrage) suit la même règle que le pipeline : il
n'écrase jamais une valeur en base. Un réglage nouveau de
``config/policy.yaml`` s'ajoute ; un réglage repris de l'ancienne policy
(migration v33, sans titre) reçoit sa description du fichier, ou est
effacé si le fichier ne le connaît plus ; un réglage listé dans
``deleted`` est effacé.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.horloge import iso_utc
from serge.policy import (
    Relation,
    Setting,
    check_relations,
    check_value,
    load_policy_seed,
    nest,
)

_COLUMNS = (
    's.id, s.section_id, s.position, s.title, s.help, s.kind, s.value_json,'
    ' s.min_value, s.max_value, s.step, s.choices_json'
)


def _setting(row: Any) -> Setting:
    return Setting(
        id=str(row[0]),
        section_id=str(row[1]),
        position=int(row[2]),
        title=str(row[3]),
        help=str(row[4]),
        kind=str(row[5]),
        value=json.loads(row[6]),
        min=row[7],
        max=row[8],
        step=row[9],
        choices=tuple(json.loads(row[10] or '[]')),
    )


def _describe(conn: sqlite3.Connection, setting: Setting) -> None:
    """Écrit le titre, l'aide, la sorte et les bornes d'un réglage."""
    conn.execute(
        'UPDATE policy_settings SET section_id=?, position=?, title=?,'
        ' help=?, kind=?, min_value=?, max_value=?, step=?, choices_json=?'
        ' WHERE id=?',
        (
            setting.section_id,
            setting.position,
            setting.title,
            setting.help,
            setting.kind,
            setting.min,
            setting.max,
            setting.step,
            json.dumps(list(setting.choices), ensure_ascii=False),
            setting.id,
        ),
    )


def _seed_sections(conn: sqlite3.Connection, sections: list) -> None:
    for position, section in enumerate(sections):
        lock = section.get('locked_while') or {}
        conn.execute(
            'INSERT OR IGNORE INTO policy_sections(id, position, page, title,'
            ' why, lock_table, lock_column, lock_value, lock_reason)'
            ' VALUES(?,?,?,?,?,?,?,?,?)',
            (
                str(section['id']),
                position,
                str(section.get('page') or 'policy'),
                str(section.get('title') or ''),
                str(section.get('why') or ''),
                str(lock.get('table') or ''),
                str(lock.get('column') or ''),
                str(lock.get('value') or ''),
                str(lock.get('reason') or ''),
            ),
        )


def _seed_settings(conn: sqlite3.Connection, settings: list[Setting]) -> None:
    known = {s.id: s for s in settings}
    imported = {
        str(r[0]): json.loads(r[1])
        for r in conn.execute(
            "SELECT id, value_json FROM policy_settings WHERE title=''"
        )
    }
    for ident, value in imported.items():
        setting = known.get(ident)
        if setting is None:
            # Repris de l'ancienne policy, mais plus rien ne le lit.
            conn.execute('DELETE FROM policy_settings WHERE id=?', (ident,))
            continue
        _describe(conn, setting)
        if check_value(setting, value):
            conn.execute(
                'UPDATE policy_settings SET value_json=?,'
                " updated_by='policy.yaml' WHERE id=?",
                (json.dumps(setting.value), ident),
            )
    now = iso_utc()
    for setting in settings:
        if conn.execute(
            'SELECT 1 FROM policy_settings WHERE id=?', (setting.id,)
        ).fetchone():
            continue
        conn.execute(
            'INSERT INTO policy_settings(id, value_json, updated_at,'
            " updated_by) VALUES(?,?,?,'policy.yaml')",
            (setting.id, json.dumps(setting.value), now),
        )
        _describe(conn, setting)


def _rename(
    conn: sqlite3.Connection,
    renamed: list[tuple[str, str]],
    known: dict[str, Setting],
) -> None:
    """Un réglage renommé garde sa valeur et sa valeur précédente, et reçoit
    la description de son nouveau nom."""
    for old, new in renamed:
        if (
            new not in known
            or conn.execute(
                'SELECT 1 FROM policy_settings WHERE id=?', (new,)
            ).fetchone()
        ):
            continue
        if conn.execute(
            'UPDATE policy_settings SET id=? WHERE id=?', (new, old)
        ).rowcount:
            _describe(conn, known[new])
            for column in ('lower_id', 'upper_id'):
                conn.execute(
                    f'UPDATE policy_relations SET {column}=? WHERE {column}=?',
                    (new, old),
                )


def ensure_policy(conn: sqlite3.Connection) -> None:
    """Remplit les réglages généraux depuis ``policy.yaml`` (au démarrage).

    Raises:
        PolicyError: Fichier mal formé (voir ``load_policy_seed``).
    """
    from serge.pipeline_changes import apply_changes
    from serge.policy import config_dir

    # Sans fichier (un dossier de config de test), rien à ajouter, comme
    # pour pipeline.yaml.
    if not (config_dir() / 'policy.yaml').is_file():
        return
    seed = load_policy_seed()
    _seed_sections(conn, seed['sections'])
    _rename(conn, seed['renamed'], {s.id: s for s in seed['settings']})
    _seed_settings(conn, seed['settings'])
    for rel in seed['relations']:
        conn.execute(
            'INSERT OR IGNORE INTO policy_relations(lower_id, upper_id,'
            ' strict) VALUES(?,?,?)',
            (rel.lower, rel.upper, int(rel.strict)),
        )
    apply_changes(conn, seed['changes'])
    for ident in seed['deleted']:
        conn.execute('DELETE FROM policy_settings WHERE id=?', (ident,))
        conn.execute(
            'DELETE FROM policy_relations WHERE lower_id=? OR upper_id=?',
            (ident, ident),
        )


def settings(conn: sqlite3.Connection) -> list[Setting]:
    """Tous les réglages, dans l'ordre de la page Policy."""
    return [
        _setting(r)
        for r in conn.execute(
            f'SELECT {_COLUMNS} FROM policy_settings s LEFT JOIN'
            ' policy_sections p ON p.id=s.section_id'
            ' ORDER BY p.position, s.position, s.id'
        )
    ]


def relations(conn: sqlite3.Connection) -> list[Relation]:
    return [
        Relation(str(r[0]), str(r[1]), bool(r[2]))
        for r in conn.execute(
            'SELECT lower_id, upper_id, strict FROM policy_relations'
        )
    ]


def policy_en_vigueur(conn: sqlite3.Connection) -> dict[str, Any]:
    """Les réglages en vigueur, rangés par section.

    Exemple : ``policy_en_vigueur(conn)['budget']['monthly_eur']``.
    """
    return nest(
        {
            str(r[0]): json.loads(r[1])
            for r in conn.execute('SELECT id, value_json FROM policy_settings')
        }
    )


def section_lock(conn: sqlite3.Connection, section_id: str) -> str:
    """Pourquoi une section ne peut pas changer maintenant, ou ``''``.

    Exemple : la taille des essais ne change pas pendant qu'un essai tourne
    (une ligne de ``campaigns`` a ``state`` = ``RUNNING``).
    """
    from serge.interpreter.rules import safe_name

    row = conn.execute(
        'SELECT lock_table, lock_column, lock_value, lock_reason'
        ' FROM policy_sections WHERE id=?',
        (section_id,),
    ).fetchone()
    if row is None or not row[0]:
        return ''
    table, column = safe_name(str(row[0])), safe_name(str(row[1]))
    busy = conn.execute(
        f'SELECT 1 FROM "{table}" WHERE "{column}"=? LIMIT 1', (str(row[2]),)
    ).fetchone()
    return str(row[3]) if busy else ''


def setting_lock(conn: sqlite3.Connection, ident: str) -> str:
    """Le verrou de la famille d'un réglage (voir ``section_lock``)."""
    row = conn.execute(
        'SELECT section_id FROM policy_settings WHERE id=?', (ident,)
    ).fetchone()
    return section_lock(conn, str(row[0])) if row else ''


def set_setting(
    conn: sqlite3.Connection, ident: str, value: Any, by: str
) -> str:
    """Change un réglage ; rend ce qui ne va pas, ou ``''`` si c'est fait.

    La valeur est vérifiée (sorte, bornes, choix), puis les relations
    (« le plancher ne dépasse pas le plafond ») et le verrou de la section.
    L'ancienne valeur devient la valeur précédente, avec qui l'a remplacée
    et quand. Le journal est écrit
    par l'appelant (Mission Control) : ce module est lu au démarrage, avant
    le journal.
    """
    found = [s for s in settings(conn) if s.id == ident]
    if not found:
        return 'réglage inconnu'
    setting = found[0]
    problem = (
        check_value(setting, value)
        or check_relations(
            {
                **{s.id: s.value for s in settings(conn)},
                ident: value,
            },
            relations(conn),
        )
        or section_lock(conn, setting.section_id)
    )
    if problem:
        return problem
    now = iso_utc()
    conn.execute(
        'UPDATE policy_settings SET previous_json=value_json,'
        ' previous_at=?, previous_by=?, value_json=?, updated_at=?,'
        ' updated_by=? WHERE id=?',
        (now, by, json.dumps(value), now, by, ident),
    )
    return ''


def previous_value(conn: sqlite3.Connection, ident: str) -> tuple[bool, Any]:
    """``(True, valeur)`` si le réglage a une valeur précédente."""
    row = conn.execute(
        'SELECT previous_json, previous_at FROM policy_settings WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None or not row[1]:
        return False, None
    return True, json.loads(row[0])
