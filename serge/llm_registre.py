#!/usr/bin/env python3
"""Jugements LLM en canon : table llm_points + jonction outils."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# id → (path, sha). SHA figé : fichier changé sans maj = test rouge.
# install_guide : pas encore de .py.
POINT_LOCKS: dict[str, tuple[str, str]] = {
    'draft_hypothesis_smoke': (
        'serge/points/hypotheses.py',
        'b34d4c720ab95105b15df88cbf54aaffa97a6e57916e47ef46da328847fedeb1',
    ),
    'draft_hypothesis_full': (
        'serge/points/hypotheses.py',
        'b34d4c720ab95105b15df88cbf54aaffa97a6e57916e47ef46da328847fedeb1',
    ),
    'plan_scale': (
        'serge/points/plans.py',
        '776b0307b3c74261482f81c193f28ed083ea35abf5ef4e63d08439c55b733a5b',
    ),
    'options_pivot': (
        'serge/points/plans.py',
        '776b0307b3c74261482f81c193f28ed083ea35abf5ef4e63d08439c55b733a5b',
    ),
    'resume_test': (
        'serge/points/plans.py',
        '776b0307b3c74261482f81c193f28ed083ea35abf5ef4e63d08439c55b733a5b',
    ),
    'qualify_prospect': (
        'serge/points/qualify.py',
        'd37edba69d03b070cc9738339b9c5fd4d9ea0d756ce26b0a6f6c1bfcbd4bc2b0',
    ),
    'fill_slots': (
        'serge/points/write.py',
        '636f74e2a538821b5613bb89fc38ece6cc7650511ce7250b377d88336041c758',
    ),
    'write_followup': (
        'serge/points/write.py',
        '636f74e2a538821b5613bb89fc38ece6cc7650511ce7250b377d88336041c758',
    ),
    'voice_script': (
        'serge/points/voice_script.py',
        '721287ad700622a6c945ad83c624dc80ca1afca27cd707b0d0e6560791e97643',
    ),
    'voice_dialog': (
        'serge/points/dialog.py',
        '3379d758b8295daa568e8bb3733fd4bca8d0bb8fe25de157c940dec215fdf022',
    ),
    'summarize_thread': (
        'serge/points/summaries.py',
        '1b4d49969c992ab7da2768a0e35d1ff66fe98ca2f5c8093da242922a37fe071b',
    ),
    'score_lead_departage': (
        'serge/points/qualify.py',
        'd37edba69d03b070cc9738339b9c5fd4d9ea0d756ce26b0a6f6c1bfcbd4bc2b0',
    ),
    'build_artifact': (
        'serge/points/build.py',
        '37cbf6c527bebabd7ea87fdf956ae6aec1de5aef496ed09caadd61c8f5262e6a',
    ),
    'review_build': (
        'serge/points/review.py',
        '378b7a0527dd4a77443348c6e2fa8f1bf66fd326913a75101d85b46ca40e21f4',
    ),
    'summarize_build_debt': (
        'serge/points/review.py',
        '378b7a0527dd4a77443348c6e2fa8f1bf66fd326913a75101d85b46ca40e21f4',
    ),
    'classify_reply': (
        'serge/points/classify.py',
        '96278ba360ac6fc14627e00804dc3f507b18d76c3f31e5f555cb6400140f7c00',
    ),
    'extract_meeting': (
        'serge/points/meeting.py',
        '91c3a898311a5df03e36bb41cc93a675afed18d06d0aa5489b7648bdf5c07b28',
    ),
    'reply_intent': (
        'serge/points/reply.py',
        '2a7716084b3a4e426813ea044a93dcba643d21b67c189b6a7f8581c055c932cb',
    ),
    'review_other': (
        'serge/points/other.py',
        'e59c7a5489e960dfeeee3ff9c91f70e4c75233aef42c975ffade3335a48e5988',
    ),
    'score_call': (
        'serge/points/summaries.py',
        '1b4d49969c992ab7da2768a0e35d1ff66fe98ca2f5c8093da242922a37fe071b',
    ),
    'draft_price': (
        'serge/points/price.py',
        '6e0c8e07a61b3882faa5ff12d0144823183b9eafcd0f773151d81d9354233ba2',
    ),
    'judge_allocator': (
        'serge/points/allocator.py',
        'c8a1e6052ac10427d90d7fdcbce43911a6a342b027093eccc38173775dbcf8d7',
    ),
    'consolidate': (
        'serge/points/memory_pts.py',
        '5fb337bd0a7abe00f703b9f02782c083ced4eebf43a470951458569efc6edbed',
    ),
    'edit_serge_md': (
        'serge/points/memory_pts.py',
        '5fb337bd0a7abe00f703b9f02782c083ced4eebf43a470951458569efc6edbed',
    ),
    'render_context_fr': (
        'serge/points/interact.py',
        '4742e1ed093803185483ddeebf83fe0162fbd11f5f8794ca391da40f7a567a24',
    ),
    'classify_owner_intent': (
        'serge/points/interact.py',
        '4742e1ed093803185483ddeebf83fe0162fbd11f5f8794ca391da40f7a567a24',
    ),
    'judge_consequence': (
        'serge/points/interact.py',
        '4742e1ed093803185483ddeebf83fe0162fbd11f5f8794ca391da40f7a567a24',
    ),
    'cluster_demand': (
        'serge/points/listen_pts.py',
        'c3d2cf4ae51a6ea3acd2e09e023883d590dc0c6dd7ca2947695c4783b50130b0',
    ),
    'install_guide': ('', ''),
}


def ensure_llm_points(conn: sqlite3.Connection) -> None:
    """Sème les points + jonction depuis le YAML (usage seulement).

    Args:
        conn: Canon (commit par l’appelant).
    """
    from serge.mc.libelles import LLM_ETAPE, LLM_TITRES
    from serge.mc.llm_roles import ROLES
    from serge.policy import config_dir, read_yaml_file

    path = config_dir() / 'llm-points.yaml'
    if not path.is_file():
        path = Path(__file__).resolve().parents[1] / 'config/llm-points.yaml'
    data = read_yaml_file(path)
    raw = data.get('points')
    points = raw if isinstance(raw, dict) else {}
    for name, spec in points.items():
        path, sha = POINT_LOCKS.get(name, ('', ''))
        etape = LLM_ETAPE.get(name, '')
        verdict = str(spec.get('verdict') or '')
        tier = str(spec.get('tier') or '')
        allume = 1 if spec.get('enabled') else 0
        found = conn.execute(
            'SELECT 1 FROM llm_points WHERE id=?', (name,)
        ).fetchone()
        if found:
            conn.execute(
                'UPDATE llm_points SET etape_id=?, code_path=?, code_sha=?,'
                ' verdict=?, tier=?, enabled=? WHERE id=?',
                (etape, path, sha, verdict, tier, allume, name),
            )
        else:
            role = ROLES.get(name)
            doc = str(role[0]) if role else ''
            conn.execute(
                'INSERT INTO llm_points(id, etape_id, code_path, code_sha,'
                ' verdict, tier, titre, doc_md, enabled)'
                ' VALUES(?,?,?,?,?,?,?,?,?)',
                (
                    name,
                    etape,
                    path,
                    sha,
                    verdict,
                    tier,
                    LLM_TITRES.get(name, name),
                    doc,
                    allume,
                ),
            )
    _sync_jonction(conn, points)


def outils_du_point(
    conn: sqlite3.Connection, point_id: str
) -> list[dict[str, Any]]:
    """Outils liés au jugement + ceux « partout ».

    Args:
        conn: Canon.
        point_id: Nom du point.

    Returns:
        Lignes ``{id, titre, usage}`` (usage vide si partout seulement).
    """
    from serge.outils import ensure_tools, outils_partout

    ensure_llm_points(conn)
    ensure_tools(conn)
    rows = conn.execute(
        'SELECT t.id, t.titre, j.usage FROM llm_point_tools j'
        ' JOIN tools t ON t.id=j.tool_id WHERE j.point_id=?'
        ' ORDER BY t.id',
        (point_id,),
    ).fetchall()
    vus = {str(r[0]) for r in rows}
    out = [
        {'id': str(r[0]), 'titre': str(r[1]), 'usage': str(r[2])} for r in rows
    ]
    for extra in outils_partout(conn):
        if extra['id'] not in vus:
            out.append(
                {'id': extra['id'], 'titre': extra['titre'], 'usage': ''}
            )
    return out


def point_par_id(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Une ligne llm_points, ou None."""
    ensure_llm_points(conn)
    row = conn.execute(
        'SELECT id, etape_id, code_path, code_sha, verdict, tier, titre,'
        ' doc_md, enabled FROM llm_points WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    return {
        'id': str(row[0]),
        'etape_id': str(row[1] or ''),
        'code_path': str(row[2] or ''),
        'code_sha': str(row[3] or ''),
        'verdict': str(row[4]),
        'tier': str(row[5]),
        'titre': str(row[6]),
        'doc_md': str(row[7]),
        'enabled': bool(row[8]),
    }


def _sync_jonction(conn: sqlite3.Connection, points: dict[str, dict]) -> None:
    conn.execute('DELETE FROM llm_point_tools')
    for name, spec in points.items():
        ctx = spec.get('context') if isinstance(spec, dict) else None
        if not isinstance(ctx, dict):
            continue
        couche = ctx.get('couche5') or {}
        allowed = isinstance(couche, dict) and bool(couche.get('allowed'))
        conn.execute(
            'INSERT INTO llm_point_tools(point_id, tool_id, usage)'
            ' VALUES(?,?,?)',
            (name, 'memory_search', 'autorise' if allowed else 'interdit'),
        )
        extra = ctx.get('tools') or []
        if isinstance(extra, list):
            for tool in extra:
                ident = str(tool or '')
                if not ident or ident == 'memory_search':
                    continue
                conn.execute(
                    'INSERT OR IGNORE INTO llm_point_tools'
                    '(point_id, tool_id, usage) VALUES(?,?,?)',
                    (name, ident, 'declare'),
                )
