#!/usr/bin/env python3
"""Registres versionnés: points LLM (C), tickets (H), séquences (B §2.6)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from serge.db.store import append_event, utcnow
from serge.policy import (
    SCHEMA_VERSION,
    PolicyError,
    config_dir,
    read_yaml_file,
)
from serge.tickets.lifecycle import create_ticket

VERDICTS = frozenset({'LLM-1', 'LLM-B', 'LLM-L', 'LLM-R', 'HYB'})
TIERS = frozenset({'T1', 'T2', 'T3'})


def _load_registry(filename: str, directory: Path | None = None) -> dict:
    root = directory or config_dir()
    data = read_yaml_file(root / filename)
    if data.get('schema_version') != SCHEMA_VERSION:
        raise PolicyError(f'{filename} : schema_version doit valoir 1')
    return data


def load_llm_points(directory: Path | None = None) -> dict[str, dict]:
    """Charge et valide le registre des points LLM (matrice C).

    Args:
        directory: Dossier config (défaut : config du repo).

    Returns:
        Mapping nom de point → déclaration validée.

    Raises:
        PolicyError: Si point incomplet (verdict/tier/contrat/garde-fou).
    """
    data = _load_registry('llm-points.yaml', directory)
    points = data.get('points')
    if not isinstance(points, dict) or not points:
        raise PolicyError('llm-points.yaml : points manquants')
    for name, point in points.items():
        if not isinstance(point, dict):
            raise PolicyError(f'llm-points.{name} invalide')
        if point.get('verdict') not in VERDICTS:
            raise PolicyError(f'llm-points.{name}.verdict invalide')
        if point.get('tier') not in TIERS:
            raise PolicyError(f'llm-points.{name}.tier invalide')
        context = point.get('context')
        if not isinstance(context, dict):
            raise PolicyError(f'llm-points.{name}.context manquant')
        for key in ('fixed', 'retrieved', 'couche5', 'forbidden'):
            if key not in context:
                raise PolicyError(f'llm-points.{name}.context.{key} manquant')
        envelope = context.get('envelope_tokens', 0)
        if isinstance(envelope, bool) or not isinstance(envelope, int):
            raise PolicyError(f'llm-points.{name}.envelope_tokens invalide')
        if not isinstance(point.get('enabled'), bool):
            raise PolicyError(f'llm-points.{name}.enabled doit être booléen')
        for key in ('checklist', 'garde_fou', 'repli'):
            if not point.get(key):
                raise PolicyError(f'llm-points.{name}.{key} manquant')
    return points


def llm_enabled(
    name: str,
    conn: sqlite3.Connection | None = None,
    directory: Path | None = None,
    now_iso: str | None = None,
) -> bool:
    """Kill-switch par point (matrice C §0 + override runtime M8).

    Args:
        name: Nom du point (ex. qualify_prospect).
        conn: Connexion canon (None = YAML seul, legacy).
        directory: Dossier config (défaut : config du repo).
        now_iso: Maintenant ISO (défaut : horloge canon).

    Returns:
        True si activé (ni kill runtime ni enabled=false), else False.
    """
    if conn is not None and not runtime_allows(conn, name, now_iso=now_iso):
        return False
    try:
        points = load_llm_points(directory)
    except PolicyError:
        return False
    point = points.get(name)
    return bool(isinstance(point, dict) and point.get('enabled') is True)


class KillError(ValueError):
    """Kill M8 refusé (point inconnu, raison vide, pas de kill actif)."""


def _flag_nom(point: str) -> str:
    return f'llm.{point}'


def runtime_allows(
    conn: sqlite3.Connection, point: str, now_iso: str | None = None
) -> bool:
    """Kill à chaud actif ? True = autorisé (sans flag, expiré, détourné).

    Args:
        conn: Connexion canon (schema assuré).
        point: Nom du point registre.
        now_iso: Maintenant ISO (défaut : horloge canon).

    Returns:
        False uniquement si flag 'kill' présent et non expiré.
    """
    moment = now_iso or utcnow()
    row = conn.execute(
        'SELECT value, expires_at FROM runtime_flags WHERE name=?',
        (_flag_nom(point),),
    ).fetchone()
    if row is None:
        return True
    if str(row[1]) and str(row[1]) <= moment:
        return True
    return str(row[0]) != 'kill'


def _decision_connue(conn: sqlite3.Connection, decision_id: str) -> bool:
    for row in conn.execute(
        "SELECT payload_json FROM events WHERE type='mc_act'"
        ' ORDER BY id DESC LIMIT 50'
    ).fetchall():
        try:
            payload = json.loads(row[0] or '{}')
        except ValueError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get('decision_id') == decision_id
        ):
            return True
    return False


def poser_kill(
    conn: sqlite3.Connection,
    point: str,
    raison: str,
    auteur: str = 'owner',
    ttl_h: int = 24,
    decision_id: str = '',
    now_iso: str | None = None,
) -> dict[str, str]:
    """Pose un kill à chaud + ticket POLICY + audit (M8, commit appelant).

    Args:
        conn: Connexion canon.
        point: Nom du point registre.
        raison: Raison (requise, traçabilité).
        auteur: Acteur (défaut owner).
        ttl_h: Durée du flag en heures (défaut 24).
        decision_id: Idempotence (double-clic = 1 acte).
        now_iso: Maintenant ISO (défaut : horloge canon).

    Returns:
        Dict {ticket_id, expires_at} (ou {duplicata} si rejoué).

    Raises:
        KillError: Si raison vide ou point inconnu au registre.
    """
    moment = now_iso or utcnow()
    if decision_id and _decision_connue(conn, decision_id):
        return {'duplicata': 'true'}
    if not raison.strip():
        raise KillError('raison requise')
    try:
        points = load_llm_points()
    except PolicyError:
        points = {}
    if point not in points:
        raise KillError(f'point inconnu : {point}')
    expires = (
        datetime.fromisoformat(moment) + timedelta(hours=ttl_h)
    ).isoformat()
    conn.execute(
        'INSERT OR REPLACE INTO runtime_flags(name, value, set_by, set_at,'
        ' expires_at, reason) VALUES(?,?,?,?,?,?)',
        (_flag_nom(point), 'kill', auteur, moment, expires, raison),
    )
    ticket_id = create_ticket(
        conn,
        load_ticket_types(),
        'POLICY',
        f'Persister le kill du point {point}',
        {'point': point, 'raison': raison, 'expires_at': expires},
        creator=auteur,
        now=moment,
    )
    append_event(
        conn,
        actor=auteur,
        type='mc_act',
        payload={
            'acte': 'kill',
            'point': point,
            'raison': raison,
            'expires_at': expires,
            'ticket_id': ticket_id,
            'decision_id': decision_id,
        },
    )
    return {'ticket_id': ticket_id, 'expires_at': expires}


def retirer_kill(
    conn: sqlite3.Connection,
    point: str,
    auteur: str = 'owner',
    decision_id: str = '',
) -> dict[str, str]:
    """Retire un kill à chaud + audit (M8 off, commit appelant).

    Args:
        conn: Connexion canon.
        point: Nom du point (flag existant requis, registre non vérifié
            pour permettre le nettoyage des orphelins).
        auteur: Acteur (défaut owner).
        decision_id: Idempotence.

    Returns:
        Dict {retire} (ou {duplicata} si rejoué).

    Raises:
        KillError: Si aucun flag pour ce point.
    """
    if decision_id and _decision_connue(conn, decision_id):
        return {'duplicata': 'true'}
    row = conn.execute(
        'SELECT value FROM runtime_flags WHERE name=?', (_flag_nom(point),)
    ).fetchone()
    if row is None:
        raise KillError(f'pas de kill actif : {point}')
    conn.execute('DELETE FROM runtime_flags WHERE name=?', (_flag_nom(point),))
    append_event(
        conn,
        actor=auteur,
        type='mc_act',
        payload={'acte': 'unkill', 'point': point, 'decision_id': decision_id},
    )
    return {'retire': 'true'}


def load_ticket_types(directory: Path | None = None) -> dict[str, dict]:
    """Charge et valide la taxonomie des tickets (H §0, §7).

    Args:
        directory: Dossier config (défaut : config du repo).

    Returns:
        Mapping type de ticket → déclaration validée.

    Raises:
        PolicyError: Si type incomplet.
    """
    data = _load_registry('ticket-types.yaml', directory)
    types = data.get('types')
    if not isinstance(types, dict) or not types:
        raise PolicyError('ticket-types.yaml : types manquants')
    for name, spec in types.items():
        if not isinstance(spec, dict):
            raise PolicyError(f'ticket-types.{name} invalide')
        for key in ('role', 'urgency', 'default', 'fields', 'buttons'):
            if key not in spec:
                raise PolicyError(f'ticket-types.{name}.{key} manquant')
        if 'expiry_hours' not in spec and 'expiry_minutes' not in spec:
            raise PolicyError(f'ticket-types.{name} : expiry manquante')
        render = spec.get('render')
        if render is not None:
            if not isinstance(render, dict):
                raise PolicyError(f'ticket-types.{name}.render invalide')
            color = render.get('color')
            if (
                isinstance(color, bool)
                or not isinstance(color, int)
                or not 0 <= color <= 0xFFFFFF
            ):
                raise PolicyError(f'ticket-types.{name}.render.color invalide')
            if not render.get('emoji') or not isinstance(
                render.get('emoji'), str
            ):
                raise PolicyError(f'ticket-types.{name}.render.emoji invalide')
    return types


def load_sequences(directory: Path | None = None) -> dict[str, list]:
    """Charge et valide les séquences de prospection (B §2.6).

    Args:
        directory: Dossier config (défaut : config du repo).

    Returns:
        Mapping nom → étapes [{channel, delay_days}].

    Raises:
        PolicyError: Si étape incomplète.
    """
    data = _load_registry('sequences.yaml', directory)
    sequences = data.get('sequences')
    if not isinstance(sequences, dict) or not sequences:
        raise PolicyError('sequences.yaml : sequences manquantes')
    for name, steps in sequences.items():
        if not isinstance(steps, list) or not steps:
            raise PolicyError(f'sequences.{name} invalide')
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise PolicyError(f'sequences.{name}[{index}] invalide')
            channel = step.get('channel')
            delay = step.get('delay_days')
            if not channel or not isinstance(channel, str):
                raise PolicyError(f'sequences.{name}[{index}].channel requis')
            if isinstance(delay, bool) or not isinstance(delay, int):
                raise PolicyError(
                    f'sequences.{name}[{index}].delay_days doit être entier'
                )
            if delay < 0:
                raise PolicyError(f'sequences.{name}[{index}].delay_days >= 0')
    return sequences
