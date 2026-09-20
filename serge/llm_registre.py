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
        '55e16836c32779044f8cb51f36d3c89cd2bc7e407d66c499cdcb2582d157deb6',
    ),
    'draft_hypothesis_full': (
        'serge/points/hypotheses.py',
        '55e16836c32779044f8cb51f36d3c89cd2bc7e407d66c499cdcb2582d157deb6',
    ),
    'plan_scale': (
        'serge/points/plans.py',
        '14380a2ef0eb8725e75087b5eda3e38eb66935754bde88526fff01cb1f0f994d',
    ),
    'options_pivot': (
        'serge/points/plans.py',
        '14380a2ef0eb8725e75087b5eda3e38eb66935754bde88526fff01cb1f0f994d',
    ),
    'resume_test': (
        'serge/points/plans.py',
        '14380a2ef0eb8725e75087b5eda3e38eb66935754bde88526fff01cb1f0f994d',
    ),
    'qualify_prospect': (
        'serge/points/qualify.py',
        '7b931fef460dcd036dfbfe0406be2971e3b906e304475a0f60dcd728d2ec99a5',
    ),
    'fill_slots': (
        'serge/points/write.py',
        '466eb2b34aa13456e0d85f2fb43a6cd782c4beb740c35d611f4af4c9cd749df1',
    ),
    'write_followup': (
        'serge/points/write.py',
        '466eb2b34aa13456e0d85f2fb43a6cd782c4beb740c35d611f4af4c9cd749df1',
    ),
    'voice_script': (
        'serge/points/voice_script.py',
        'd55eff88658a2323c3d94f356eb772a4c3ef5b9c472569d72bc59e2a30e6636b',
    ),
    'voice_dialog': (
        'serge/points/dialog.py',
        'bcd51c033a766578158ad681fe720efd5824bfd793328d253d92b56d3071b307',
    ),
    'summarize_thread': (
        'serge/points/summaries.py',
        '46c9b258e416038d5a5a2d4f679e665659c8f8241bc85bd4019d2fd437079236',
    ),
    'score_lead_departage': (
        'serge/points/qualify.py',
        '7b931fef460dcd036dfbfe0406be2971e3b906e304475a0f60dcd728d2ec99a5',
    ),
    'build_artifact': (
        'serge/points/build.py',
        '57facac98cf71fd6300e275ef5de73e1630040d908a46fed2bd61ea97fc78edc',
    ),
    'review_build': (
        'serge/points/review.py',
        'c4ff5b6a91be05c952f272dd6714aca67e47459f74c59f20f6952969ed89b61a',
    ),
    'summarize_build_debt': (
        'serge/points/review.py',
        'c4ff5b6a91be05c952f272dd6714aca67e47459f74c59f20f6952969ed89b61a',
    ),
    'classify_reply': (
        'serge/points/classify.py',
        '63f11a97e6b082982ec5bc50c2c00c8d215af3367590facaf496113446a6fe5a',
    ),
    'extract_meeting': (
        'serge/points/meeting.py',
        'cd8fccf3247055279939434a23ef4658bc756900fa904d2861ad9da6b83f1a2a',
    ),
    'reply_intent': (
        'serge/points/reply.py',
        '42882c22801339f0ddedc377be9f7e85bccb5fe1fd4945637b232838e8a996a7',
    ),
    'review_other': (
        'serge/points/other.py',
        'c177f12db1c734abe8958bab6fa98eefeeee7f3764e244c16c0b292963bfa019',
    ),
    'score_call': (
        'serge/points/summaries.py',
        '46c9b258e416038d5a5a2d4f679e665659c8f8241bc85bd4019d2fd437079236',
    ),
    'draft_price': (
        'serge/points/price.py',
        '1b0aadf8479fa3c2cfa098bb7f8ec4d4f6e8c5b00d39a61a5feff2adfffcd8b7',
    ),
    'judge_allocator': (
        'serge/points/allocator.py',
        '15f7d51a68cd388eda3aa92f81df6397885777f6d7f2babe4816ec94c30d9e9b',
    ),
    'consolidate': (
        'serge/points/memory_pts.py',
        '1d5d647bdca5ee980c5db93e60e5e9a9a3a5cb82a168534c5801a3b249c5c4bf',
    ),
    'edit_serge_md': (
        'serge/points/memory_pts.py',
        '1d5d647bdca5ee980c5db93e60e5e9a9a3a5cb82a168534c5801a3b249c5c4bf',
    ),
    'render_context_fr': (
        'serge/points/interact.py',
        'f3b8c25f65eb87b39094cc4a4b7a94af800a547282409cbe6661bd19de109400',
    ),
    'classify_owner_intent': (
        'serge/points/interact.py',
        'f3b8c25f65eb87b39094cc4a4b7a94af800a547282409cbe6661bd19de109400',
    ),
    'judge_consequence': (
        'serge/points/interact.py',
        'f3b8c25f65eb87b39094cc4a4b7a94af800a547282409cbe6661bd19de109400',
    ),
    'cluster_demand': (
        'serge/points/listen_pts.py',
        '6aec51bdd62319aa6c60592b26bb5743e69a16bf1c6ab4c7167a991b018767a1',
    ),
    'listen_discover_needs_a': (
        'serge/points/listen_pts.py',
        '6aec51bdd62319aa6c60592b26bb5743e69a16bf1c6ab4c7167a991b018767a1',
    ),
    'listen_discover_needs_b': (
        'serge/points/listen_pts.py',
        '6aec51bdd62319aa6c60592b26bb5743e69a16bf1c6ab4c7167a991b018767a1',
    ),
    'listen_choose_poc': (
        'serge/points/listen_pts.py',
        '6aec51bdd62319aa6c60592b26bb5743e69a16bf1c6ab4c7167a991b018767a1',
    ),
    'discover_contacts': (
        'serge/points/discover_contacts.py',
        'ca8704c8899f531f3ffae3a239f8afc2237aee731a810250d960899c1f33e913',
    ),
    'install_guide': ('', ''),
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
    'qualify_prospect': ('serge.points.qualify', 'QUALIFY_SYSTEM'),
    'fill_slots': ('serge.points.write', 'SLOTS_SYSTEM'),
    'write_followup': ('serge.points.write', 'FOLLOWUP_SYSTEM'),
    'voice_script': ('serge.points.voice_script', 'SCRIPT_SYSTEM'),
    'voice_dialog': ('serge.points.dialog', 'DIALOG_SYSTEM'),
    'summarize_thread': ('serge.points.summaries', 'THREAD_SYSTEM'),
    'score_lead_departage': ('serge.points.qualify', 'DEPARTAGE_SYSTEM'),
    'build_artifact': ('serge.points.build', 'BUILD_SYSTEM'),
    'review_build': ('serge.points.review', 'REVIEW_SYSTEM'),
    'summarize_build_debt': ('serge.points.review', 'DEBT_SYSTEM'),
    'classify_reply': ('serge.points.classify', 'CLASSIFY_SYSTEM'),
    'extract_meeting': ('serge.points.meeting', 'MEETING_SYSTEM'),
    'reply_intent': ('serge.points.reply', 'REPLY_SYSTEM'),
    'review_other': ('serge.points.other', 'OTHER_SYSTEM'),
    'score_call': ('serge.points.summaries', 'SCORE_SYSTEM'),
    'draft_price': ('serge.points.price', 'PRICE_SYSTEM'),
    'judge_allocator': ('serge.points.allocator', 'JUDGE_SYSTEM'),
    'consolidate': ('serge.points.memory_pts', 'CONSOLIDATE_SYSTEM'),
    'edit_serge_md': ('serge.points.memory_pts', 'SERGE_MD_SYSTEM'),
    'render_context_fr': ('serge.points.interact', 'RENDER_SYSTEM'),
    'classify_owner_intent': ('serge.points.interact', 'INTENT_SYSTEM'),
    'judge_consequence': ('serge.points.interact', 'CONSEQ_SYSTEM'),
    'cluster_demand': ('serge.points.listen_pts', 'CLUSTER_SYSTEM'),
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
    'draft_price': ('identity_basique', 'memory_search'),
    'judge_allocator': ('memory_search',),
    'consolidate': ('memory_search',),
    'judge_consequence': ('memory_search',),
    'cluster_demand': ('memory_search',),
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
    noms = list(dict.fromkeys([*points, *POINT_LOCKS]))
    for name in noms:
        raw_spec = points.get(name)
        spec = raw_spec if isinstance(raw_spec, dict) else {}
        path, sha = POINT_LOCKS.get(name, ('', ''))
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
                'UPDATE llm_points SET etape_id=?, code_path=?, code_sha=?,'
                ' titre=? WHERE id=?',
                (etape, path, sha, LLM_TITRES.get(name, name), name),
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
                'INSERT INTO llm_points(id, etape_id, code_path, code_sha,'
                ' verdict, tier, titre, doc_md, enabled, prompt, output_mode,'
                ' external_info) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
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
                    prompt,
                    output_mode,
                    external_info,
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
