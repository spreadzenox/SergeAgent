#!/usr/bin/env python3
"""Projecteurs P5 Policy : les réglages généraux, et ceux des invocations."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.policy_store import section_lock, settings


def _precedent(at: str, by: str, value: Any) -> dict[str, Any] | None:
    """La valeur précédente d'un réglage (qui, quand), ou ``None``."""
    if not at:
        return None
    return {'valeur': value, 'par': by, 'le': at}


def settings_sections(conn: sqlite3.Connection, page: str) -> list[dict]:
    """Les familles de réglages généraux d'une page (``policy`` ou
    ``pipeline``), telles qu'elles sont en base.

    Chaque réglage arrive avec sa description (titre, aide, sorte, bornes,
    choix), sa valeur, et sa valeur précédente : la page n'a aucun
    catalogue à elle. Une famille verrouillée dit pourquoi (exemple : un
    essai tourne).
    """
    previous = {
        str(r[0]): _precedent(str(r[2]), str(r[3]), json.loads(r[1] or 'null'))
        for r in conn.execute(
            'SELECT id, previous_json, previous_at, previous_by'
            ' FROM policy_settings'
        )
    }
    reglages: dict[str, list[dict[str, Any]]] = {}
    for s in settings(conn):
        reglages.setdefault(s.section_id, []).append(
            {
                'id': s.id,
                'titre': s.title,
                'aide': s.help,
                'widget': s.kind,
                'min': s.min,
                'max': s.max,
                'pas': s.step,
                'choix': list(s.choices),
                'valeur': s.value,
                'precedent': previous.get(s.id),
            }
        )
    sections = [
        {
            'id': str(row[0]),
            'titre': str(row[1]),
            'pourquoi': str(row[2]),
            'verrou': section_lock(conn, str(row[0])),
            'reglages': reglages[str(row[0])],
        }
        for row in conn.execute(
            'SELECT id, title, why FROM policy_sections WHERE page=?'
            ' ORDER BY position',
            (page,),
        ).fetchall()
        if str(row[0]) in reglages
    ]
    return sections


def project_politique_active(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les familles de réglages de la page Policy (P5).

    Returns:
        ``{sections: [{id, titre, pourquoi, verrou, reglages: [...]}]}``.
    """
    _ = (policy, now)
    return {'sections': settings_sections(conn, 'policy')}


def project_reglages(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les réglages d'invocation et les quotas marqués « policy » (P5).

    Ils sont rangés avec l'invocation ou la table qui s'en sert, pas dans
    la policy générale ; la page Policy les montre ici, par étape puis par
    invocation, modifiables en direct, avec leur valeur précédente.

    Returns:
        ``{invocations: [{invocation_id, titre, etape, reglages}],
        quotas: [...]}``.
    """
    _ = (policy, now)
    groupes: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        'SELECT s.invocation_id, i.title, COALESCE(st.titre, i.step_id),'
        ' s.name, s.type, s.value, s.min_value, s.max_value, s.description,'
        ' s.previous_value, s.previous_at, s.previous_by'
        ' FROM invocation_settings s JOIN invocations i ON i.id=s.invocation_id'
        ' LEFT JOIN pipeline_steps st ON st.id=i.step_id'
        " WHERE s.policy=1 AND i.deleted_at=''"
        ' ORDER BY COALESCE(st.rang, 99), s.invocation_id, s.name'
    ).fetchall():
        groupe = groupes.setdefault(
            str(row[0]),
            {
                'invocation_id': str(row[0]),
                'titre': str(row[1] or row[0]),
                'etape': str(row[2] or ''),
                'reglages': [],
            },
        )
        groupe['reglages'].append(
            {
                'name': str(row[3]),
                'type': str(row[4]),
                'value': str(row[5]),
                'min': str(row[6]),
                'max': str(row[7]),
                'description': str(row[8]),
                'precedent': _precedent(str(row[10]), str(row[11]), row[9]),
            }
        )
    quotas = [
        {
            'id': str(r[0]),
            'table': str(r[1]),
            'column': str(r[2]),
            'values': str(r[3]),
            'max': int(r[4]),
            'description': str(r[5]),
            'precedent': _precedent(str(r[7]), str(r[8]), r[6]),
        }
        for r in conn.execute(
            'SELECT id, table_name, column_name, counted_values, max_value,'
            ' description, previous_value, previous_at, previous_by'
            ' FROM table_quotas WHERE policy=1 ORDER BY id'
        ).fetchall()
    ]
    return {'invocations': list(groupes.values()), 'quotas': quotas}
