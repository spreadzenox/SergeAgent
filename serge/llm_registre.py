#!/usr/bin/env python3
"""Invocations LLM en canon : table llm_points + jonction outils."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# id → fichier Python qui porte l'invocation (empreinte calculée au boot).
# install_guide : pas encore de .py.
POINT_PATHS: dict[str, str] = {
    'draft_hypothesis_smoke': 'serge/points/hypotheses.py',
    'draft_hypothesis_full': 'serge/points/hypotheses.py',
    'plan_scale': 'serge/points/plans.py',
    'options_pivot': 'serge/points/plans.py',
    'resume_test': 'serge/points/plans.py',
    'fill_slots': 'serge/points/write.py',
    'write_followup': 'serge/points/write.py',
    'voice_script': 'serge/points/voice_script.py',
    'voice_dialog': 'serge/points/dialog.py',
    'summarize_thread': 'serge/points/summaries.py',
    'score_lead_departage': 'serge/points/score_lead.py',
    'build_artifact': 'serge/points/build.py',
    'review_build': 'serge/points/review.py',
    'summarize_build_debt': 'serge/points/review.py',
    'classify_reply': 'serge/points/classify.py',
    'extract_meeting': 'serge/points/meeting.py',
    'reply_intent': 'serge/points/reply.py',
    'review_other': 'serge/points/other.py',
    'score_call': 'serge/points/summaries.py',
    'judge_allocator': 'serge/points/allocator.py',
    'consolidate': 'serge/points/memory_pts.py',
    'render_context_fr': 'serge/points/interact.py',
    'classify_owner_intent': 'serge/points/interact.py',
    'judge_consequence': 'serge/points/interact.py',
    'listen_discover_needs_a': 'serge/points/listen_pts.py',
    'listen_discover_needs_b': 'serge/points/listen_pts.py',
    'listen_choose_poc': 'serge/points/listen_pts.py',
    'discover_contacts': 'serge/points/discover_contacts.py',
    'install_guide': '',
}

LISTEN_POINT_DOCS = {
    'listen_discover_needs_a': 'Explore le corpus du cycle et propose des besoins prouvés.',
    'listen_discover_needs_b': 'Explore le même corpus indépendamment du premier agent.',
    'listen_choose_poc': 'Choisit des candidats éligibles, avec veto déterministe du POC.',
    'discover_contacts': 'Prépare des références de contact fournies par le contexte.',
}

# Les textes sont référencés par module plutôt que recopiés dans le YAML. Le
# YAML reste la source de seed des autres propriétés, jamais de la valeur
# runtime éditée en base.
POINT_PROMPT_SEEDS: dict[str, tuple[str, str]] = {
    'draft_hypothesis_smoke': ('serge.points.hypotheses', 'SMOKE_SYSTEM'),
    'draft_hypothesis_full': ('serge.points.hypotheses', 'FULL_SYSTEM'),
    'plan_scale': ('serge.points.plans', 'SCALE_SYSTEM'),
    'options_pivot': ('serge.points.plans', 'PIVOT_SYSTEM'),
    'resume_test': ('serge.points.plans', 'RESUME_SYSTEM'),
    'fill_slots': ('serge.points.write', 'SLOTS_SYSTEM'),
    'write_followup': ('serge.points.write', 'FOLLOWUP_SYSTEM'),
    'voice_script': ('serge.points.voice_script', 'SCRIPT_SYSTEM'),
    'voice_dialog': ('serge.points.dialog', 'DIALOG_SYSTEM'),
    'summarize_thread': ('serge.points.summaries', 'THREAD_SYSTEM'),
    'score_lead_departage': ('serge.points.score_lead', 'DEPARTAGE_SYSTEM'),
    'build_artifact': ('serge.points.build', 'BUILD_SYSTEM'),
    'review_build': ('serge.points.review', 'REVIEW_SYSTEM'),
    'summarize_build_debt': ('serge.points.review', 'DEBT_SYSTEM'),
    'classify_reply': ('serge.points.classify', 'CLASSIFY_SYSTEM'),
    'extract_meeting': ('serge.points.meeting', 'MEETING_SYSTEM'),
    'reply_intent': ('serge.points.reply', 'REPLY_SYSTEM'),
    'review_other': ('serge.points.other', 'OTHER_SYSTEM'),
    'score_call': ('serge.points.summaries', 'SCORE_SYSTEM'),
    'judge_allocator': ('serge.points.allocator', 'JUDGE_SYSTEM'),
    'consolidate': ('serge.points.memory_pts', 'CONSOLIDATE_SYSTEM'),
    'render_context_fr': ('serge.points.interact', 'RENDER_SYSTEM'),
    'classify_owner_intent': ('serge.points.interact', 'INTENT_SYSTEM'),
    'judge_consequence': ('serge.points.interact', 'CONSEQ_SYSTEM'),
    'listen_discover_needs_a': ('serge.points.listen_pts', 'DISCOVERY_SYSTEM'),
    'listen_discover_needs_b': ('serge.points.listen_pts', 'DISCOVERY_SYSTEM'),
    'listen_choose_poc': ('serge.points.listen_pts', 'CHOICE_SYSTEM'),
    'discover_contacts': (
        'serge.points.discover_contacts',
        'DISCOVER_SYSTEM',
    ),
    'install_guide': ('kit.guide', 'SYSTEM_PROMPT'),
}

# Permissions initiales lisibles et versionnables. Après le boot, les tables
# ``llm_point_tools`` et ``llm_point_readers`` sont l'autorité, pas ce seed.
POINT_TOOL_SEEDS: dict[str, tuple[str, ...]] = {
    'draft_hypothesis_smoke': ('memory_search',),
    'draft_hypothesis_full': ('memory_search',),
    'plan_scale': ('memory_search',),
    'options_pivot': ('memory_search',),
    'fill_slots': ('memory_search',),
    'write_followup': ('memory_search',),
    'voice_dialog': ('agenda', 'catalogue', 'fiches', 'identity_basique'),
    'build_artifact': ('memory_search',),
    'classify_reply': ('memory_search',),
    'reply_intent': ('memory_search',),
    'review_other': ('memory_search',),
    'judge_allocator': ('memory_search',),
    'consolidate': ('memory_search',),
    'judge_consequence': ('memory_search',),
    'listen_discover_needs_a': ('memory_search', 'web_search'),
    'listen_discover_needs_b': ('memory_search', 'web_search'),
    'discover_contacts': ('contact_upsert',),
}

POINT_CAPSULE_SEEDS: dict[str, tuple[str, ...]] = {
    'listen_discover_needs_a': (
        'current_listen_cycle',
        'listen_cycle_documents',
        'known_business_candidates',
    ),
    'listen_discover_needs_b': (
        'current_listen_cycle',
        'listen_cycle_documents',
        'known_business_candidates',
    ),
    'listen_choose_poc': ('current_listen_cycle', 'eligible_poc_candidates'),
}


def _prompt_seed(point_id: str) -> str:
    """Charge le prompt constant d'un point, ou ``''`` pour un point externe."""
    reference = POINT_PROMPT_SEEDS.get(point_id)
    if reference is None:
        return ''
    module_name, constant = reference
    from importlib import import_module

    value = getattr(import_module(module_name), constant, '')
    return str(value) if isinstance(value, str) else ''


def _metadata_seed(
    point_id: str, spec: dict[str, Any]
) -> tuple[str, str, int]:
    output_mode = str(spec.get('output_mode') or 'text')
    if output_mode not in {'structured', 'text'}:
        output_mode = 'text'
    return (
        _prompt_seed(point_id),
        output_mode,
        1 if spec.get('external_info') is True else 0,
    )


def ensure_llm_points(conn: sqlite3.Connection) -> None:
    """Sème les points et les métadonnées initiales sans écraser la DB.

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
    noms = list(dict.fromkeys([*points, *POINT_PATHS]))
    for name in noms:
        raw_spec = points.get(name)
        spec = raw_spec if isinstance(raw_spec, dict) else {}
        path = POINT_PATHS.get(name, '')
        etape = LLM_ETAPE.get(name, '')
        verdict = str(spec.get('verdict') or '')
        tier = str(spec.get('tier') or '')
        allume = 1 if spec.get('enabled') else 0
        prompt, output_mode, external_info = _metadata_seed(name, spec)
        found = conn.execute(
            'SELECT prompt, output_mode, external_info, updated_at'
            ' FROM llm_points WHERE id=?',
            (name,),
        ).fetchone()
        if found:
            conn.execute(
                'UPDATE llm_points SET etape_id=?, code_path=?,'
                ' titre=? WHERE id=?',
                (etape, path, LLM_TITRES.get(name, name), name),
            )
            # v020 vide updated_at pour demander une seule passe de seed. Les
            # éditions ultérieures, y compris vers les valeurs par défaut,
            # conservent leur timestamp et restent donc intactes.
            if (
                not str(found[0] or '')
                and str(found[1] or 'text') == 'text'
                and int(found[2] or 0) == 0
                and not str(found[3] or '')
            ):
                conn.execute(
                    'UPDATE llm_points SET prompt=?, output_mode=?, '
                    'external_info=? WHERE id=?',
                    (prompt, output_mode, external_info, name),
                )
        else:
            role = ROLES.get(name)
            doc = str(role[0]) if role else LISTEN_POINT_DOCS.get(name, '')
            conn.execute(
                'INSERT INTO llm_points(id, etape_id, code_path,'
                ' verdict, tier, titre, doc_md, enabled, prompt, output_mode,'
                ' external_info) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (
                    name,
                    etape,
                    path,
                    verdict,
                    tier,
                    LLM_TITRES.get(name, name),
                    doc,
                    allume,
                    prompt,
                    output_mode,
                    external_info,
                ),
            )
    # Une invocation retirée du code disparaît de la base (ses réglages et
    # ses tools). L’historique llm_usage reste, c’est le journal.
    trous = ','.join('?' * len(noms))
    conn.execute(f'DELETE FROM llm_points WHERE id NOT IN ({trous})', noms)
    conn.execute(
        f'DELETE FROM llm_point_tools WHERE point_id NOT IN ({trous})', noms
    )
    conn.execute(
        f'DELETE FROM llm_point_readers WHERE point_id NOT IN ({trous})', noms
    )
    _sync_jonction(conn, points)


def outils_du_point(
    conn: sqlite3.Connection, point_id: str
) -> list[dict[str, Any]]:
    """Outils liés à l’invocation + ceux « partout ».

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
        ' doc_md, enabled, prompt, output_mode, external_info, files_sha,'
        ' updated_at FROM llm_points WHERE id=?',
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
        'prompt': str(row[9] or ''),
        'output_mode': str(row[10] or 'text'),
        'external_info': bool(row[11]),
        'files_sha': str(row[12] or ''),
        'updated_at': str(row[13] or ''),
    }


def _sync_jonction(conn: sqlite3.Connection, points: dict[str, dict]) -> None:
    del points
    for name, tools in POINT_TOOL_SEEDS.items():
        for tool_id in tools:
            conn.execute(
                'INSERT OR IGNORE INTO llm_point_tools'
                '(point_id, tool_id, usage) VALUES(?,?,?)',
                (
                    name,
                    tool_id,
                    'autorise' if tool_id == 'memory_search' else 'declare',
                ),
            )
    for name, capsules in POINT_CAPSULE_SEEDS.items():
        for capsule_id in capsules:
            row = conn.execute(
                'SELECT tool_id FROM db_readers WHERE id=?', (capsule_id,)
            ).fetchone()
            if row is None or not str(row[0] or ''):
                continue
            conn.execute(
                'INSERT OR IGNORE INTO llm_point_tools'
                '(point_id, tool_id, usage) VALUES(?,?,?)',
                (name, str(row[0]), 'autorise'),
            )
