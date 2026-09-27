#!/usr/bin/env python3
"""Fiches invocation : tout ce que la base dit d'une invocation.

Rien ici ne connaît une invocation en particulier : le titre, le rôle, le
modèle, le prompt, ce qu'elle reçoit, ce qu'elle peut appeler, le format
de sa réponse, où elle écrit, ce qui la lance et ce qu'elle lance sont lus
dans les tables du pipeline (``docs/LOT6_CONCEPTION.md``).
"""

from __future__ import annotations

import sqlite3
from typing import Any

NIVEAUX = {
    'fast': 'Rapide — un réflexe (classer, extraire). Le moins cher.',
    'mid': 'Moyen — assez malin pour rédiger ou comparer.',
    'smart': 'Intelligent — plans, arbitrages. Le plus cher.',
}

SOURCES = {
    'field': 'le champ « {} » de la réponse',
    'fixed': '« {} »',
    'task': 'le paramètre « {} » de la tâche',
    'parent_row': 'la colonne « {} » de la ligne écrite juste avant',
    'row': 'la colonne « {} » de la ligne écrite',
    'form': 'le champ « {} » du formulaire',
    'now': 'la date et l’heure',
}

EVENEMENTS = {
    'row_written': 'une ligne écrite dans {table}',
    'every': 'toutes les {every} minutes',
    'at': 'à {at} ({jours})',
    'button': 'un bouton de Mission Control',
}


def _row(conn: sqlite3.Connection, sql: str, args: tuple) -> dict | None:
    cursor = conn.execute(sql, args)
    row = cursor.fetchone()
    if row is None:
        return None
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


def _source(source: str, value: str) -> str:
    return SOURCES.get(source, '{}').format(value)


def _params(conn: sqlite3.Connection, sql: str, args: tuple) -> str:
    return ' ; '.join(
        f'{name} ← {_source(str(source), str(value))}'
        for name, source, value in conn.execute(sql, args).fetchall()
    )


def _outils(
    conn: sqlite3.Connection, ident: str, mode: str
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Les outils d'un mode : liens cliquables et paramètres figés."""
    liens: list[dict[str, str]] = []
    champs: list[dict[str, str]] = []
    for link_id, tool_id, label, max_rows, titre in conn.execute(
        'SELECT it.id, it.tool_id, it.label, it.max_rows, t.titre'
        ' FROM invocation_tools it LEFT JOIN tools t ON t.id=it.tool_id'
        ' WHERE it.invocation_id=? AND it.mode=? ORDER BY it.position',
        (ident, mode),
    ).fetchall():
        nom = str(label or titre or tool_id)
        liens.append({'type': 'outil', 'id': str(tool_id), 'titre': nom})
        figes = _params(
            conn,
            'SELECT param_name, source, value FROM invocation_tool_params'
            ' WHERE invocation_id=? AND invocation_tool_id=?',
            (ident, int(link_id)),
        )
        detail = figes or 'aucun paramètre figé'
        if mode == 'given' and int(max_rows):
            detail += f' ; {int(max_rows)} lignes au plus'
        champs.append({'k': nom, 'v': detail})
    return liens, champs


def _format(conn: sqlite3.Connection, ident: str) -> list[dict[str, str]]:
    champs = []
    for path, kind, choices, required, description in conn.execute(
        'SELECT path, type, choices, required, description'
        ' FROM invocation_output_fields WHERE invocation_id=?'
        ' ORDER BY position',
        (ident,),
    ).fetchall():
        detail = f'{kind}, {"obligatoire" if required else "facultatif"}'
        if choices:
            detail += f', parmi : {choices}'
        if description:
            detail += f' — {description}'
        champs.append({'k': str(path), 'v': detail})
    return champs


def _ecritures(conn: sqlite3.Connection, ident: str) -> list[dict[str, str]]:
    champs = []
    for (
        write_id,
        table,
        operation,
        for_each,
        key_col,
        key_src,
        key_val,
    ) in conn.execute(
        'SELECT id, table_name, operation, for_each, key_column,'
        ' key_source, key_value FROM invocation_writes'
        ' WHERE invocation_id=? ORDER BY position',
        (ident,),
    ).fetchall():
        quoi = f'Ajouter dans {table}'
        if operation == 'update':
            quoi = (
                f'Modifier {table} (ligne où {key_col} ='
                f' {_source(str(key_src), str(key_val))})'
            )
        if for_each:
            quoi += f', une ligne par élément de « {for_each} »'
        valeurs = _params(
            conn,
            'SELECT column_name, source, value FROM invocation_write_values'
            ' WHERE write_id=?',
            (int(write_id),),
        )
        champs.append({'k': quoi, 'v': valeurs or '—'})
    return champs


def _enchainement(
    conn: sqlite3.Connection, ident: str
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    """Ce qui la lance (liens et déclencheurs), et ce qu'elle lance."""
    entrants, sortants, declencheurs = [], [], []
    for link_id, de, vers, titre, auto in conn.execute(
        'SELECT id, from_invocation_id, to_invocation_id, title, auto'
        " FROM links WHERE deleted_at='' AND enabled=1"
        ' AND (from_invocation_id=? OR to_invocation_id=?) ORDER BY id',
        (ident, ident),
    ).fetchall():
        manuel = '' if auto else ' (passage à la main)'
        if vers == ident:
            entrants.append(
                {
                    'type': 'llm',
                    'id': str(de),
                    'titre': f'{titre or link_id}{manuel}',
                }
            )
        if de == ident:
            sortants.append(
                {
                    'type': 'llm',
                    'id': str(vers),
                    'titre': f'{titre or link_id}{manuel}',
                }
            )
    for trig_id, titre, event, table, every, at, days in conn.execute(
        'SELECT id, title, event, table_name, every_minutes, at_time, at_days'
        " FROM triggers WHERE invocation_id=? AND deleted_at='' AND enabled=1"
        ' ORDER BY id',
        (ident,),
    ).fetchall():
        quand = EVENEMENTS.get(str(event), str(event)).format(
            table=table, every=every, at=at, jours=days or 'tous les jours'
        )
        declencheurs.append({'k': str(titre or trig_id), 'v': quand})
    return entrants, sortants, declencheurs


def _passages(conn: sqlite3.Connection, ident: str) -> list[dict[str, Any]]:
    lignes = []
    for rid, when, tin, tout, lat, verd, tier, model in conn.execute(
        'SELECT id, created_at, tokens_in, tokens_out, latency_ms,'
        ' verdict, tier, model FROM llm_usage WHERE point=?'
        ' ORDER BY id DESC LIMIT 20',
        (ident,),
    ).fetchall():
        lignes.append(
            {
                'id': f'{ident}:{rid}',
                'type': 'llm_usage',
                'cellules': [
                    when or '—',
                    {'ok': 'terminé', 'format_invalide': 'format raté'}.get(
                        str(verd), verd or '—'
                    ),
                    str(tier or '—'),
                    str(int(tin or 0) + int(tout or 0)),
                    f'{int(lat or 0)} ms',
                    model or '—',
                ],
            }
        )
    return lignes


def _champs(conn: sqlite3.Connection, inv: dict) -> list[dict[str, str]]:
    etape = _row(
        conn, 'SELECT titre FROM pipeline_steps WHERE id=?', (inv['step_id'],)
    )
    champs = [
        {
            'k': 'Sorte',
            'v': 'appel au modèle'
            if inv['type'] == 'llm'
            else f'sans modèle, capacité « {inv["capability_id"]} »',
        },
        {
            'k': 'Étape',
            'v': (etape or {}).get('titre') or inv['step_id'] or '—',
        },
        {
            'k': 'Allumée',
            'v': 'oui' if inv['enabled'] else 'non — ses tâches attendent',
        },
        {'k': 'File', 'v': inv['queue_id']},
        {'k': 'Priorité', 'v': f'{inv["priority"]} (100 = la plus urgente)'},
    ]
    if inv['type'] == 'llm':
        champs += [
            {
                'k': 'Niveau de modèle',
                'v': NIVEAUX.get(inv['model_tier'], inv['model_tier']),
            },
            {
                'k': 'Reçoit « Qui est Serge »',
                'v': 'oui' if inv['gets_serge_intro'] else 'non',
            },
            {
                'k': 'Lignes données au plus',
                'v': str(inv['default_max_rows']),
            },
            {'k': 'Appels d’outils au plus', 'v': str(inv['max_tool_turns'])},
        ]
    else:
        champs.append(
            {
                'k': 'Paramètres de la capacité',
                'v': _params(
                    conn,
                    'SELECT param_name, source, value FROM'
                    ' invocation_tool_params WHERE invocation_id=?'
                    ' AND invocation_tool_id=0',
                    (inv['id'],),
                )
                or '—',
            }
        )
    champs.append(
        {
            'k': 'Dernière modification',
            'v': f'{inv["updated_at"] or "—"} ({inv["updated_by"] or "?"})',
        }
    )
    return champs


def project_llm(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Fiche d'une invocation, lue en base."""
    inv = _row(
        conn,
        "SELECT * FROM invocations WHERE id=? AND deleted_at=''",
        (ident,),
    )
    if inv is None:
        return None
    donnes, donnes_champs = _outils(conn, ident, 'given')
    appelables, appelables_champs = _outils(conn, ident, 'callable')
    partout = [
        {'type': 'outil', 'id': str(r[0]), 'titre': f'{r[1]} (partout)'}
        for r in conn.execute(
            'SELECT id, titre FROM tools WHERE montre_partout=1 ORDER BY id'
        ).fetchall()
    ]
    entrants, sortants, declencheurs = _enchainement(conn, ident)
    cadres: list[dict[str, Any]] = [
        {'titre': 'À quoi ça sert', 'texte': inv['role'] or '—'}
    ]
    if inv['type'] == 'llm':
        cadres += [
            {
                'titre': 'Le texte qu’on lui donne (prompt)',
                'texte': inv['prompt'] or '—',
                'todo': 'Modifiable par l’API /owner/api/invocation.',
            },
            {
                'titre': 'Ce qu’elle reçoit d’office',
                'champs': donnes_champs,
                'liens': donnes,
            },
            {
                'titre': 'Ce qu’elle peut appeler',
                'champs': appelables_champs,
                'liens': appelables + partout,
            },
        ]
    cadres += [
        {'titre': 'Le format de sa réponse', 'champs': _format(conn, ident)},
        {
            'titre': 'Où sa réponse est écrite',
            'texte': 'Le modèle ne choisit jamais où écrire : c’est réglé ici.',
            'champs': _ecritures(conn, ident),
        },
        {
            'titre': 'Ce qui la lance',
            'champs': declencheurs,
            'liens': entrants,
        },
        {'titre': 'Ce qu’elle lance ensuite', 'liens': sortants},
    ]
    return {
        'type': 'llm',
        'id': ident,
        'titre': inv['title'] or ident,
        'pourquoi': inv['role'] or '',
        'champs': _champs(conn, inv),
        'cadres': cadres,
        'tableau': {
            'titre': 'Passages récents de cette invocation',
            'colonnes': [
                'Quand',
                'Résultat',
                'Niveau',
                'Jetons',
                'Durée',
                'Nom du modèle',
            ],
            'lignes': _passages(conn, ident),
        },
        'enfants': [],
        'preuve': '',
    }


def _titre(conn: sqlite3.Connection, ident: str) -> str:
    row = conn.execute(
        'SELECT title FROM invocations WHERE id=?', (ident,)
    ).fetchone()
    return str(row[0] or ident) if row else ident


def project_llm_usage(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Un passage : les compteurs d'un appel au modèle."""
    point, sep, raw = ident.partition(':')
    if not sep or not raw.isdigit():
        return None
    row = conn.execute(
        'SELECT id, point, tier, model, tokens_in, tokens_out,'
        ' latency_ms, verdict, created_at FROM llm_usage WHERE id=?',
        (int(raw),),
    ).fetchone()
    if row is None or str(row[1]) != point:
        return None
    titre = _titre(conn, point)
    return {
        'type': 'llm_usage',
        'id': ident,
        'titre': f'{titre} · passage {raw}',
        'pourquoi': 'Un appel au modèle. Les jetons et la durée sont sûrs.',
        'champs': [
            {'k': 'Invocation', 'v': titre},
            {'k': 'Quand', 'v': str(row[8] or '—')},
            {'k': 'Résultat', 'v': str(row[7] or '—')},
            {
                'k': 'Niveau de modèle',
                'v': NIVEAUX.get(str(row[2]), str(row[2] or '—')),
            },
            {'k': 'Nom du modèle', 'v': str(row[3] or '—')},
            {'k': 'Jetons lus', 'v': str(row[4] or 0)},
            {'k': 'Jetons écrits', 'v': str(row[5] or 0)},
            {'k': 'Durée', 'v': f'{int(row[6] or 0)} ms'},
        ],
        'enfants': [{'type': 'llm', 'id': point, 'titre': titre}],
        'preuve': '',
    }


def project_ecoute(
    conn: sqlite3.Connection, ident: str = ''
) -> dict[str, Any]:
    """Miroir des pages vraiment lues."""
    _ = ident
    rows = conn.execute(
        'SELECT id, source, title, excerpt, url, fetched_at FROM listen_docs'
        ' ORDER BY fetched_at DESC LIMIT 80'
    ).fetchall()
    lignes = []
    for row in rows:
        src = 'flux RSS' if row[1] == 'rss' else (row[1] or '—')
        lignes.append(
            {
                'id': row[0],
                'type': 'listen_doc',
                'cellules': [
                    src,
                    row[2] or 'sans titre',
                    (row[3] or '—')[:140],
                    row[5] or '—',
                ],
            }
        )
    todo = ''
    if not lignes:
        todo = (
            'Aucune page en base pour l’instant. Quand Serge écoute'
            ' pour de vrai, elles apparaissent ici.'
        )
    return {
        'type': 'ecoute',
        'id': 'pages',
        'titre': 'Pages vraiment lues',
        'pourquoi': (
            'C’est le miroir de ce que Serge a ramassé sur internet'
            ' pour sentir une demande. Pas une idée abstraite : des'
            ' titres, des extraits, une source. Clique une ligne.'
        ),
        'champs': [{'k': 'Pages en base', 'v': str(len(lignes))}],
        'tableau': {
            'titre': 'Miroir maintenant',
            'colonnes': ['Source', 'Titre', 'Extrait', 'Quand'],
            'lignes': lignes,
        },
        'cadres': [{'titre': 'À brancher', 'todo': todo}] if todo else [],
        'enfants': [],
        'preuve': '',
    }
