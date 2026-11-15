#!/usr/bin/env python3
"""Ajouter un paramètre à un objet déjà en base, une seule fois.

Deux sortes de modification de la section ``changes`` de
``config/pipeline.yaml`` (voir ``serge/pipeline_changes.py``) :

- ``add_link_params`` (avec ``link``) : un paramètre de plus qu'un lien
  passe à l'invocation suivante. Exemple : le domaine commun des produits
  finis, de « Mettre en vente » à « Publier le produit en prod » ;
- ``add_params`` (avec ``invocation``) : un paramètre de plus d'une
  invocation sans LLM, réglé comme dans ``pipeline.yaml``. Exemple :
  ``base_domain`` de « Publier le produit en prod ».

Un paramètre déjà là est gardé : il a pu être changé dans Mission Control.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.seed_base import PipelineSeedError


def _params(raw: Any, quoi: str) -> Mapping[str, Mapping[str, Any]]:
    if not isinstance(raw, Mapping) or not all(
        isinstance(spec, Mapping) and 'source' in spec for spec in raw.values()
    ):
        raise PipelineSeedError(f'changes : {quoi}, des paramètres {{source}}')
    return raw


def add_link_params(conn: sqlite3.Connection, link: str, raw: Any) -> str:
    """Ajoute des paramètres à un lien déjà en base."""
    params = _params(raw, 'add_link_params')
    if not conn.execute('SELECT 1 FROM links WHERE id=?', (link,)).fetchone():
        return 'objet absent'
    parts = []
    for name, spec in params.items():
        if conn.execute(
            'SELECT 1 FROM link_params WHERE link_id=? AND param_name=?',
            (link, str(name)),
        ).fetchone():
            parts.append(f'{name} déjà là')
            continue
        conn.execute(
            'INSERT INTO link_params(link_id, param_name, source, value)'
            ' VALUES(?,?,?,?)',
            (link, str(name), str(spec['source']), str(spec.get('value', ''))),
        )
        parts.append(f'{name} ajouté')
    return ' ; '.join(parts)


def add_params(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Ajoute des paramètres à une invocation sans LLM déjà en base."""
    params = _params(raw, 'add_params')
    if not conn.execute(
        'SELECT 1 FROM invocations WHERE id=?', (invocation,)
    ).fetchone():
        return 'objet absent'
    parts = []
    for name, spec in params.items():
        if conn.execute(
            'SELECT 1 FROM invocation_tool_params WHERE invocation_id=?'
            ' AND invocation_tool_id=0 AND param_name=?',
            (invocation, str(name)),
        ).fetchone():
            parts.append(f'{name} déjà là')
            continue
        conn.execute(
            'INSERT INTO invocation_tool_params(invocation_id,'
            ' invocation_tool_id, param_name, source, value)'
            ' VALUES(?,0,?,?,?)',
            (
                invocation,
                str(name),
                str(spec['source']),
                str(spec.get('value', '')),
            ),
        )
        parts.append(f'{name} ajouté')
    return ' ; '.join(parts)
