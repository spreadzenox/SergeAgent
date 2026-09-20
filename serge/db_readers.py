#!/usr/bin/env python3
"""Catalogue des tools DB et capsules mémoire persistées.

``db_readers`` est conservée comme nom de table historique, mais ses lignes
sont désormais des capsules : elles ajoutent un texte métier à un tool
``kind='db_read'`` et peuvent porter des paramètres fixes.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.horloge import iso_utc

CAPSULE_SEED: tuple[tuple[str, str, str, str, str], ...] = (
    (
        'current_listen_cycle',
        'Cycle d’écoute courant',
        'Lit les paramètres du cycle d’écoute actif.',
        'Le contexte du cycle courant est fourni par l’ordonnanceur.',
        'current_listen_cycle',
    ),
    (
        'listen_cycle_documents',
        'Documents du cycle d’écoute',
        'Lit uniquement les documents attribués au cycle courant.',
        'Les documents sont le corpus figé du cycle fourni par l’ordonnanceur.',
        'listen_cycle_documents',
    ),
    (
        'known_business_candidates',
        'Business déjà trouvés',
        'Lit les business candidats déjà présents pour éviter les doublons.',
        'Cette capsule donne les candidats déjà connus avant une nouvelle écoute.',
        'known_business_candidates',
    ),
    (
        'eligible_poc_candidates',
        'Business éligibles au POC',
        'Lit les candidats non sélectionnés et leur état POC.',
        'Cette capsule donne les candidats que la sélection déterministe peut encore engager.',
        'eligible_poc_candidates',
    ),
)

# Ancien nom de semence conservé pour les modules qui ne connaissent que la
# fiche historique; les lignes sont bien traitées comme des capsules ci-dessus.
READER_SEED = tuple(
    item[:3] + ('serge/db/query_builder.py',) for item in CAPSULE_SEED
)

TOOL_TABLES: tuple[tuple[str, str, int], ...] = (
    ('current_listen_cycle', 'listen_cycles', 0),
    ('listen_cycle_documents', 'listen_cycle_docs', 0),
    ('listen_cycle_documents', 'listen_docs', 1),
    ('known_business_candidates', 'business_candidates', 0),
    ('eligible_poc_candidates', 'business_candidates', 0),
)

TOOL_COLUMNS: tuple[tuple[str, str, str, str, int], ...] = (
    ('current_listen_cycle', 'listen_cycles', 'id', '', 0),
    ('current_listen_cycle', 'listen_cycles', 'guide', '', 1),
    ('current_listen_cycle', 'listen_cycles', 'needs_target', '', 2),
    ('current_listen_cycle', 'listen_cycles', 'business_target', '', 3),
    ('current_listen_cycle', 'listen_cycles', 'status', '', 4),
    ('current_listen_cycle', 'listen_cycles', 'created_at', '', 5),
    ('current_listen_cycle', 'listen_cycles', 'started_at', '', 6),
    ('current_listen_cycle', 'listen_cycles', 'finished_at', '', 7),
    ('listen_cycle_documents', 'listen_cycle_docs', 'cycle_id', '', 0),
    ('listen_cycle_documents', 'listen_cycle_docs', 'doc_id', '', 1),
    ('listen_cycle_documents', 'listen_docs', 'id', '', 2),
    ('listen_cycle_documents', 'listen_docs', 'source', '', 3),
    ('listen_cycle_documents', 'listen_docs', 'url', '', 4),
    ('listen_cycle_documents', 'listen_docs', 'title', '', 5),
    ('listen_cycle_documents', 'listen_docs', 'excerpt', '', 6),
    ('listen_cycle_documents', 'listen_docs', 'published', '', 7),
    ('known_business_candidates', 'business_candidates', 'id', '', 0),
    ('known_business_candidates', 'business_candidates', 'title', '', 1),
    ('known_business_candidates', 'business_candidates', 'content', '', 2),
    (
        'known_business_candidates',
        'business_candidates',
        'observations',
        '',
        3,
    ),
    (
        'known_business_candidates',
        'business_candidates',
        'sellable_offer',
        '',
        4,
    ),
    ('known_business_candidates', 'business_candidates', 'status', '', 5),
    ('known_business_candidates', 'business_candidates', 'created_at', '', 6),
    ('known_business_candidates', 'business_candidates', 'updated_at', '', 7),
    ('eligible_poc_candidates', 'business_candidates', 'id', '', 0),
    ('eligible_poc_candidates', 'business_candidates', 'title', '', 1),
    ('eligible_poc_candidates', 'business_candidates', 'content', '', 2),
    ('eligible_poc_candidates', 'business_candidates', 'observations', '', 3),
    (
        'eligible_poc_candidates',
        'business_candidates',
        'sellable_offer',
        '',
        4,
    ),
    ('eligible_poc_candidates', 'business_candidates', 'status', '', 5),
)

TOOL_FILTERS: tuple[tuple[str, str, str, str, str, str, str, str], ...] = (
    (
        'current_listen_cycle',
        'cycle',
        'listen_cycles',
        'id',
        '=',
        'param',
        '',
        'cycle_id',
    ),
    (
        'listen_cycle_documents',
        'cycle',
        'listen_cycle_docs',
        'cycle_id',
        '=',
        'param',
        '',
        'cycle_id',
    ),
    (
        'eligible_poc_candidates',
        'candidate_status',
        'business_candidates',
        'status',
        '=',
        'fixed',
        'CANDIDATE',
        '',
    ),
)

CAPSULE_FIXED_JOINS: tuple[tuple[str, str, str, str, str, str, int], ...] = (
    (
        'listen_cycle_documents',
        'document',
        'listen_cycle_docs',
        'doc_id',
        'listen_docs',
        'id',
        0,
    ),
)

TOOL_PARAMS: tuple[tuple[str, str, str, str, int, str, int], ...] = (
    (
        'current_listen_cycle',
        'cycle_id',
        'string',
        'Identifiant du cycle.',
        1,
        '',
        0,
    ),
    (
        'listen_cycle_documents',
        'cycle_id',
        'string',
        'Identifiant du cycle.',
        1,
        '',
        0,
    ),
    (
        'listen_cycle_documents',
        'limit',
        'integer',
        'Nombre maximal de documents.',
        0,
        '200',
        1,
    ),
    (
        'known_business_candidates',
        'limit',
        'integer',
        'Nombre maximal de candidats.',
        0,
        '200',
        0,
    ),
    (
        'eligible_poc_candidates',
        'limit',
        'integer',
        'Nombre maximal de candidats.',
        0,
        '200',
        0,
    ),
)


def _seed_tool_catalogue(conn: sqlite3.Connection) -> None:
    for tool_id, table_name, position in TOOL_TABLES:
        conn.execute(
            'INSERT OR IGNORE INTO tool_db_tables(tool_id, table_name, position)'
            ' VALUES(?,?,?)',
            (tool_id, table_name, position),
        )
    for (
        tool_id,
        table_name,
        column_name,
        output_name,
        position,
    ) in TOOL_COLUMNS:
        conn.execute(
            'INSERT OR IGNORE INTO tool_db_columns'
            '(tool_id, table_name, column_name, output_name, position)'
            ' VALUES(?,?,?,?,?)',
            (tool_id, table_name, column_name, output_name, position),
        )
    for (
        tool_id,
        filter_id,
        table_name,
        column_name,
        operator,
        value_kind,
        value_text,
        param_name,
    ) in TOOL_FILTERS:
        conn.execute(
            'INSERT OR IGNORE INTO tool_db_filters'
            '(tool_id, filter_id, table_name, column_name, operator, value_kind,'
            ' value_text, param_name) VALUES(?,?,?,?,?,?,?,?)',
            (
                tool_id,
                filter_id,
                table_name,
                column_name,
                operator,
                value_kind,
                value_text,
                param_name,
            ),
        )
    for (
        tool_id,
        name,
        kind,
        description,
        required,
        default_text,
        position,
    ) in TOOL_PARAMS:
        conn.execute(
            'INSERT OR IGNORE INTO tool_db_params'
            '(tool_id, name, type, description, required, default_text, position)'
            ' VALUES(?,?,?,?,?,?,?)',
            (
                tool_id,
                name,
                kind,
                description,
                required,
                default_text,
                position,
            ),
        )
    for (
        capsule_id,
        join_id,
        left_table,
        left_column,
        right_table,
        right_column,
        position,
    ) in CAPSULE_FIXED_JOINS:
        conn.execute(
            'INSERT OR IGNORE INTO db_reader_fixed_joins'
            '(capsule_id, join_id, left_table, left_column, right_table,'
            ' right_column, position) VALUES(?,?,?,?,?,?,?)',
            (
                capsule_id,
                join_id,
                left_table,
                left_column,
                right_table,
                right_column,
                position,
            ),
        )


def ensure_db_readers(conn: sqlite3.Connection) -> None:
    """Sème les tools/capsules et leurs affectations initiales en DB."""
    # Les bases déjà estampillées v19 peuvent précéder la table dédiée. Les
    # anciennes arêtes tool sont reprises pour la capsule homonyme, puis
    # retirées de l'ancien catalogue générique.
    conn.execute(
        """CREATE TABLE IF NOT EXISTS db_reader_fixed_joins (
            capsule_id TEXT NOT NULL,
            join_id TEXT NOT NULL,
            left_table TEXT NOT NULL,
            left_column TEXT NOT NULL,
            right_table TEXT NOT NULL,
            right_column TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (capsule_id, join_id)
        )"""
    )
    for (
        capsule_id,
        title,
        description,
        prompt_addition,
        tool_id,
    ) in CAPSULE_SEED:
        conn.execute(
            'INSERT OR IGNORE INTO db_readers'
            '(id, titre, doc_md, description, prompt_addition, tool_id, code_path, etat)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (
                capsule_id,
                title,
                description,
                description,
                prompt_addition,
                tool_id,
                'serge/db/query_builder.py',
                'branche',
            ),
        )
        conn.execute(
            'UPDATE db_readers SET titre=?, doc_md=?, description=?,'
            ' prompt_addition=?, tool_id=?, code_path=?, etat=? WHERE id=?',
            (
                title,
                description,
                description,
                prompt_addition,
                tool_id,
                'serge/db/query_builder.py',
                'branche',
                capsule_id,
            ),
        )
    conn.execute(
        'INSERT OR IGNORE INTO db_reader_fixed_joins'
        '(capsule_id, join_id, left_table, left_column, right_table,'
        ' right_column, position) SELECT r.id, j.join_id, j.left_table,'
        ' j.left_column, j.right_table, j.right_column, j.position'
        ' FROM tool_db_joins j JOIN db_readers r ON r.tool_id=j.tool_id'
    )
    conn.execute('DELETE FROM tool_db_joins')
    _seed_tool_catalogue(conn)
    from serge.llm_registre import POINT_CAPSULE_SEEDS

    now = iso_utc()
    known_capsules = {item[0] for item in CAPSULE_SEED}
    for point_id, capsule_ids in POINT_CAPSULE_SEEDS.items():
        for capsule_id in capsule_ids:
            if capsule_id not in known_capsules:
                continue
            conn.execute(
                'INSERT OR IGNORE INTO llm_point_readers'
                '(point_id, reader_id, usage, enabled, updated_at, updated_by)'
                ' VALUES(?,?,?,?,?,?)',
                (point_id, capsule_id, 'autorise', 1, now, 'boot'),
            )


def readers_du_point(
    conn: sqlite3.Connection, point_id: str
) -> list[dict[str, Any]]:
    """Retourne les capsules autorisées et leur tool sous-jacent."""
    rows = conn.execute(
        'SELECT r.id, r.titre, r.description, r.prompt_addition, r.tool_id,'
        ' j.usage, j.enabled FROM llm_point_readers j'
        ' JOIN db_readers r ON r.id=j.reader_id'
        ' WHERE j.point_id=? ORDER BY r.id',
        (point_id,),
    ).fetchall()
    return [
        {
            'id': str(row[0]),
            'titre': str(row[1]),
            'doc_md': str(row[2]),
            'description': str(row[2]),
            'prompt_addition': str(row[3]),
            'tool_id': str(row[4]),
            'usage': str(row[5]),
            'enabled': bool(row[6]),
        }
        for row in rows
    ]


def reader_allowed(
    conn: sqlite3.Connection, point_id: str, reader_id: str
) -> bool:
    """Vérifie en DB l'affectation d'une capsule à un point."""
    row = conn.execute(
        'SELECT 1 FROM llm_point_readers'
        " WHERE point_id=? AND reader_id=? AND enabled=1 AND usage='autorise'",
        (point_id, reader_id),
    ).fetchone()
    return row is not None


def reader_ids_for_point(
    conn: sqlite3.Connection, point_id: str
) -> tuple[str, ...]:
    """Retourne les ids de capsules actives injectables dans le contrat."""
    return tuple(
        item['id']
        for item in readers_du_point(conn, point_id)
        if item['enabled'] and item['usage'] == 'autorise'
    )


def reader_contract(conn: sqlite3.Connection, point_id: str) -> dict[str, Any]:
    """Construit le contrat des capsules visible par l'ordonnanceur."""
    return {
        'allowed': list(reader_ids_for_point(conn, point_id)),
        'permission_source': 'sqlite',
    }


def tool_ids_for_point(
    conn: sqlite3.Connection, point_id: str
) -> tuple[str, ...]:
    """Retourne les tools actifs selon les jonctions DB du point/capsules."""
    rows = conn.execute(
        'SELECT tool_id FROM llm_point_tools'
        " WHERE point_id=? AND usage IN ('autorise', 'declare')"
        ' UNION '
        'SELECT r.tool_id FROM llm_point_readers p'
        ' JOIN db_readers r ON r.id=p.reader_id'
        " WHERE p.point_id=? AND p.enabled=1 AND p.usage='autorise'"
        ' ORDER BY tool_id',
        (point_id, point_id),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def execute_memory_capsule(
    conn: sqlite3.Connection,
    capsule_id: str,
    runtime_params: Mapping[str, Any],
) -> dict[str, Any]:
    """Exécute une capsule avec les paramètres dynamiques du scheduler.

    La capsule ne déduit aucun identifiant métier et le LLM n'intervient pas
    dans cette résolution. Les valeurs fixes sont lues depuis SQLite.
    """
    if not isinstance(runtime_params, Mapping):
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'runtime_params objet attendu',
        }
    row = conn.execute(
        'SELECT id, titre, description, prompt_addition, tool_id'
        ' FROM db_readers WHERE id=?',
        (capsule_id,),
    ).fetchone()
    if row is None:
        return {
            'ok': False,
            'code': 'capsule_inconnue',
            'capsule_id': capsule_id,
        }
    fixed = {
        str(item[0]): str(item[1])
        for item in conn.execute(
            'SELECT param_name, value_text FROM db_reader_fixed_params'
            ' WHERE capsule_id=?',
            (capsule_id,),
        ).fetchall()
    }
    fixed_joins = [
        {
            'join_id': str(item[0]),
            'left_table': str(item[1]),
            'left_column': str(item[2]),
            'right_table': str(item[3]),
            'right_column': str(item[4]),
        }
        for item in conn.execute(
            'SELECT join_id, left_table, left_column, right_table, right_column'
            ' FROM db_reader_fixed_joins WHERE capsule_id=?'
            ' ORDER BY position, join_id',
            (capsule_id,),
        ).fetchall()
    ]
    from serge.db.query_builder import tool_catalogue

    try:
        parameters = {
            str(item['name']): item
            for item in tool_catalogue(conn, str(row[4]))['params']
        }
        typed_fixed: dict[str, Any] = {}
        for name, value in fixed.items():
            parameter = parameters.get(name)
            if parameter is None:
                return {
                    'ok': False,
                    'code': 'invalide',
                    'detail': f'paramètre fixe inconnu: {name}',
                }
            kind = str(parameter['type'])
            if kind == 'integer':
                typed_fixed[name] = int(value)
            elif kind == 'number':
                typed_fixed[name] = float(value)
            elif kind == 'boolean':
                if value not in {'true', 'false'}:
                    raise ValueError(f'booléen fixe invalide: {name}')
                typed_fixed[name] = value == 'true'
            elif kind == 'array':
                raise ValueError(f'array fixe non supporté: {name}')
            else:
                typed_fixed[name] = value
    except (TypeError, ValueError) as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}
    params = dict(typed_fixed)
    for name, value in runtime_params.items():
        if name in fixed and str(value) != fixed[name]:
            return {
                'ok': False,
                'code': 'parametre_fixe',
                'parametre': str(name),
            }
        params[str(name)] = value
    from serge.db.query_builder import execute_db_read

    try:
        result = execute_db_read(
            conn, str(row[4]), params, fixed_joins=fixed_joins
        )
    except (ValueError, sqlite3.Error) as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}
    return {
        'ok': True,
        'capsule_id': str(row[0]),
        'tool_id': str(row[4]),
        'titre': str(row[1]),
        'description': str(row[2]),
        'prompt_addition': str(row[3]),
        'data': result['data'],
    }
