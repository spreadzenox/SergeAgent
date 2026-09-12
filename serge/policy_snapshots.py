#!/usr/bin/env python3
"""Gestion des snapshots de politique (E2, R-c).

Invariant B4 : l'écriture de snapshot appartient à la policy.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from serge.db.store import utcnow
from serge.policy import PolicyError, load_policy, validate_policy


def snapshot_policy(
    conn: sqlite3.Connection,
    policy_dict: dict[str, Any],
    applied_by: str = 'owner',
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Valide et enregistre un snapshot de politique (append-only).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy_dict: Données de politique brutes ou validées.
        applied_by: Auteur de la modification.
        now_iso: Horodatage ISO (défaut : maintenant).

    Returns:
        Dict {id, content_hash, version, applied_by, active_from}.
    """
    valide = validate_policy(policy_dict)
    content_json = json.dumps(valide, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(content_json.encode('utf-8')).hexdigest()[
        :16
    ]
    moment = now_iso or utcnow()

    cur = conn.execute(
        'INSERT INTO policy_snapshots(content_hash, content_json, applied_by, active_from)'
        ' VALUES(?, ?, ?, ?)',
        (content_hash, content_json, applied_by, moment),
    )
    return {
        'id': cur.lastrowid,
        'content_hash': content_hash,
        'applied_by': applied_by,
        'active_from': moment,
    }


def list_snapshots(
    conn: sqlite3.Connection, limit: int = 20
) -> list[dict[str, Any]]:
    """Historique des snapshots récents.

    Args:
        conn: Connexion canon (lecture).
        limit: Nombre max de snapshots.

    Returns:
        Liste de dicts [{id, content_hash, applied_by, active_from}].
    """
    rows = conn.execute(
        'SELECT id, content_hash, applied_by, active_from FROM policy_snapshots'
        ' ORDER BY id DESC LIMIT ?',
        (limit,),
    ).fetchall()
    return [
        {
            'id': row[0],
            'content_hash': str(row[1]),
            'applied_by': str(row[2]),
            'active_from': str(row[3]),
        }
        for row in rows
    ]


def get_snapshot(
    conn: sqlite3.Connection, snapshot_id: int
) -> dict[str, Any] | None:
    """Récupère un snapshot par ID pour comparaison ou rollback.

    Args:
        conn: Connexion canon (lecture).
        snapshot_id: ID du snapshot.

    Returns:
        Dict ou None.
    """
    row = conn.execute(
        'SELECT id, content_hash, content_json, applied_by, active_from'
        ' FROM policy_snapshots WHERE id=?',
        (snapshot_id,),
    ).fetchone()
    if not row:
        return None
    try:
        content = json.loads(str(row[2]))
    except ValueError:
        content = {}
    return {
        'id': row[0],
        'content_hash': str(row[1]),
        'content': content,
        'applied_by': str(row[3]),
        'active_from': str(row[4]),
    }


def latest_policy(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Dernier snapshot validé, ou None si le canon n’en a pas.

    Args:
        conn: Connexion canon (lecture).

    Returns:
        Policy validée, ou None.

    Raises:
        PolicyError: Snapshot présent mais illisible ou invalide.
    """
    row = conn.execute(
        'SELECT content_json FROM policy_snapshots ORDER BY id DESC LIMIT 1'
    ).fetchone()
    if row is None:
        return None
    try:
        data = json.loads(row[0] or '{}')
    except ValueError as exc:
        raise PolicyError('snapshot policy illisible') from exc
    if not isinstance(data, dict):
        raise PolicyError('snapshot policy invalide')
    return validate_policy(data)


def policy_en_vigueur(
    conn: sqlite3.Connection, directory: Path | None = None
) -> dict[str, Any]:
    """Policy runtime : dernier snapshot, sinon semence YAML puis snapshot.

    Une source : le canon. `config/policy.yaml` n’est que la graine.

    Args:
        conn: Connexion canon (écriture si semence).
        directory: Dossier YAML (défaut : config du repo).

    Returns:
        Policy validée en vigueur.
    """
    found = latest_policy(conn)
    if found is not None:
        return _avec_testing(conn, found)
    seed = _avec_testing(conn, load_policy(directory), ecrire=True)
    return seed


def _avec_testing(
    conn: sqlite3.Connection,
    policy: dict[str, Any],
    *,
    ecrire: bool = False,
) -> dict[str, Any]:
    """Garantit un bloc testing dans la policy (semence si manquant)."""
    from kit.instance_file import _validate_testing

    bloc = policy.get('testing')
    raw: dict[str, Any] = bloc if isinstance(bloc, dict) else {}
    propre = _validate_testing(raw)
    if policy.get('testing') == propre and not ecrire:
        return policy
    complete = dict(policy)
    complete['testing'] = propre
    snapshot_policy(conn, complete, applied_by='seed')
    return complete
