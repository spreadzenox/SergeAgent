#!/usr/bin/env python3
"""Lecteurs DB fermés et permissions runtime des points LLM."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from serge.horloge import iso_utc
from serge.policy import config_dir, read_yaml_file

READER_SEED: tuple[tuple[str, str, str, str], ...] = (
    (
        'current_listen_cycle',
        'Cycle d’écoute courant',
        'Lit les paramètres du cycle d’écoute actif.',
        'serge/listen/memory.py',
    ),
    (
        'listen_cycle_documents',
        'Documents du cycle d’écoute',
        'Lit uniquement les documents attribués au cycle courant.',
        'serge/listen/memory.py',
    ),
    (
        'known_business_candidates',
        'Business déjà trouvés',
        'Lit les business candidats déjà présents pour éviter les doublons.',
        'serge/listen/memory.py',
    ),
    (
        'eligible_poc_candidates',
        'Business éligibles au POC',
        'Lit les candidats non sélectionnés et leur état POC.',
        'serge/listen/memory.py',
    ),
)


def ensure_db_readers(conn: sqlite3.Connection) -> None:
    """Sème les lecteurs et projette les permissions déclarées dans le YAML.

    Args:
        conn: Canon (commit par l'appelant).

    Raises:
        ValueError: Si un point réclame un lecteur inconnu ou mal formé.
    """
    for reader_id, title, doc, code_path in READER_SEED:
        conn.execute(
            'INSERT OR IGNORE INTO db_readers'
            '(id, titre, doc_md, code_path, etat) VALUES(?,?,?,?,?)',
            (reader_id, title, doc, code_path, 'branche'),
        )
    known_readers = {item[0] for item in READER_SEED}
    permissions: dict[str, tuple[str, ...]] = {}
    root = config_dir()
    path = root / 'llm-points.yaml'
    if not path.is_file():
        path = Path(__file__).resolve().parents[1] / 'config/llm-points.yaml'
    raw_points = read_yaml_file(path).get('points')
    if not isinstance(raw_points, dict):
        raise ValueError('llm-points.yaml : points manquants')
    for point_id, spec in raw_points.items():
        if not isinstance(spec, dict):
            raise ValueError(f'llm-points.{point_id} invalide')
        context = spec.get('context') or {}
        if not isinstance(context, dict):
            raise ValueError(f'llm-points.{point_id}.context invalide')
        raw_readers = context.get('db_readers') or []
        if not isinstance(raw_readers, list) or any(
            not isinstance(reader, str) or not reader for reader in raw_readers
        ):
            raise ValueError(
                f'llm-points.{point_id}.context.db_readers invalide'
            )
        unknown = set(raw_readers) - known_readers
        if unknown:
            names = ', '.join(sorted(unknown))
            raise ValueError(
                f'llm-points.{point_id}.context.db_readers inconnus: {names}'
            )
        permissions[point_id] = tuple(raw_readers)

    conn.execute('DELETE FROM llm_point_readers')
    now = iso_utc()
    for point_id, reader_ids in permissions.items():
        for reader_id in reader_ids:
            conn.execute(
                'INSERT OR IGNORE INTO llm_point_readers'
                '(point_id, reader_id, usage, enabled, updated_at, updated_by)'
                'VALUES(?,?,?,?,?,?)',
                (point_id, reader_id, 'autorise', 1, now, 'boot'),
            )


def readers_du_point(
    conn: sqlite3.Connection, point_id: str
) -> list[dict[str, Any]]:
    """Retourne les lecteurs autorisés et leur état pour un point."""
    rows = conn.execute(
        'SELECT r.id, r.titre, r.doc_md, j.usage, j.enabled '
        'FROM llm_point_readers j JOIN db_readers r ON r.id=j.reader_id '
        'WHERE j.point_id=? ORDER BY r.id',
        (point_id,),
    ).fetchall()
    return [
        {
            'id': str(row[0]),
            'titre': str(row[1]),
            'doc_md': str(row[2]),
            'usage': str(row[3]),
            'enabled': bool(row[4]),
        }
        for row in rows
    ]


def reader_allowed(
    conn: sqlite3.Connection, point_id: str, reader_id: str
) -> bool:
    """Vérifie en DB l’autorisation effective d’un lecteur."""
    row = conn.execute(
        'SELECT 1 FROM llm_point_readers '
        "WHERE point_id=? AND reader_id=? AND enabled=1 AND usage='autorise'",
        (point_id, reader_id),
    ).fetchone()
    return row is not None


def reader_ids_for_point(
    conn: sqlite3.Connection, point_id: str
) -> tuple[str, ...]:
    """Retourne les ids actifs injectables dans le contrat de l’agent."""
    return tuple(
        item['id']
        for item in readers_du_point(conn, point_id)
        if item['enabled'] and item['usage'] == 'autorise'
    )


def reader_contract(conn: sqlite3.Connection, point_id: str) -> dict[str, Any]:
    """Construit le contrat DB visible par l’agent au moment de l’appel."""
    return {
        'allowed': list(reader_ids_for_point(conn, point_id)),
        'permission_source': 'sqlite',
    }


def tool_ids_for_point(
    conn: sqlite3.Connection, point_id: str
) -> tuple[str, ...]:
    """Retourne les tools actifs selon la jonction canonique."""
    rows = conn.execute(
        'SELECT tool_id FROM llm_point_tools '
        "WHERE point_id=? AND usage IN ('autorise', 'declare') ORDER BY tool_id",
        (point_id,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)
