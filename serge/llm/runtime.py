#!/usr/bin/env python3
"""Runtime points LLM : kill-switch, budget dur et metering.

run_point() est le seul chemin d'appel LLM runtime. Ordre : kill-switch
→ budget journalier (estimation EUR) → appel → metering. Tout échec =
fallback signalé (jamais d'exception métier),
usage enregistré avec verdict (ok/killed/budget/error).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kit.openrouter import RECOMMENDED_TIERS
from serge.db.store import utcnow
from serge.llm.boucle import executer_boucle
from serge.llm.client import ChatResult, LlmError, chat
from serge.paths import config_root
from serge.registry import runtime_allows
from serge.secrets import read_secret_file

TIER_TO_SLOT = {'T1': 'CHEAP', 'T2': 'DEFAULT', 'T3': 'SMART'}
TEMPERATURES = {
    'LLM-1': 0.1,
    'LLM-B': 0.3,
    'LLM-L': 0.7,
    'LLM-R': 0.2,
    'HYB': 0.3,
}


@dataclass(frozen=True)
class RunResult:
    ok: bool
    text: str
    fallback: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int


def _slots_path(root: Path | None) -> Path:
    base = root or config_root()
    return base / 'llm/slots.json'


def resolve_model(
    tier: str, root: Path | None = None, referer_out: dict | None = None
) -> tuple[str, str]:
    """Modèle OpenRouter du tier (slots.json, fallback recommandations).

    Args:
        tier: T1 | T2 | T3.
        root: config_root (défaut : instance).
        referer_out: Dict rempli avec le referer si fourni.

    Returns:
        Tuple (model_id, referer).
    """
    model = RECOMMENDED_TIERS.get(tier.lower(), '')
    referer = ''
    try:
        payload = json.loads(_slots_path(root).read_text(encoding='utf-8'))
        slot = (payload.get('slots') or {}).get(TIER_TO_SLOT.get(tier, ''))
        if isinstance(slot, dict) and slot.get('openrouter_id'):
            model = str(slot['openrouter_id'])
        referer = str(payload.get('referer') or '')
    except (OSError, ValueError):
        pass
    if referer_out is not None:
        referer_out['referer'] = referer
    return model, referer


def read_api_key(root: Path | None = None) -> str:
    """Clé OpenRouter instance (jamais loguée).

    Args:
        root: config_root (défaut : instance).

    Returns:
        La clé ou '' si absente.
    """
    base = root or config_root()
    return read_secret_file(base / 'secrets/openrouter-api-key')


def daily_tokens(
    conn: sqlite3.Connection, day: str | None = None
) -> tuple[int, int]:
    """Tokens LLM du jour (metering, tous points, verdict ok uniquement).

    Args:
        conn: Connexion canon (lecture).
        day: Préfixe YYYY-MM-DD (défaut : aujourd'hui UTC).

    Returns:
        Tuple (tokens_in, tokens_out).
    """
    prefix = day or datetime.now(UTC).strftime('%Y-%m-%d')
    row = conn.execute(
        'SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0)'
        " FROM llm_usage WHERE verdict='ok' AND created_at LIKE ?",
        (f'{prefix}%',),
    ).fetchone()
    return int(row[0]), int(row[1])


def _record(
    conn: sqlite3.Connection,
    point: str,
    tier: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    verdict: str,
) -> None:
    conn.execute(
        'INSERT INTO llm_usage(point, tier, model, tokens_in, tokens_out,'
        ' latency_ms, verdict, created_at) VALUES(?,?,?,?,?,?,?,?)',
        (
            point,
            tier,
            model,
            tokens_in,
            tokens_out,
            latency_ms,
            verdict,
            utcnow(),
        ),
    )


def _db_point_metadata(
    conn: sqlite3.Connection, point_name: str
) -> tuple[str, str, bool] | None:
    """Lit les métadonnées runtime sans réintroduire de registre JSON."""
    try:
        row = conn.execute(
            'SELECT prompt, output_mode, external_info FROM llm_points'
            ' WHERE id=?',
            (point_name,),
        ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return str(row[0] or ''), str(row[1] or 'text'), bool(row[2])


def _replace_system_prompt(
    messages: list[dict[str, Any]], prompt: str
) -> list[dict[str, Any]]:
    """Remplace uniquement le premier message system fourni par le point."""
    result = [dict(item) for item in messages]
    for item in result:
        if item.get('role') == 'system':
            item['content'] = prompt
            return result
    result.insert(0, {'role': 'system', 'content': prompt})
    return result


def run_point(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    spec: Mapping[str, Any],
    point_name: str,
    messages: list[dict[str, Any]],
    *,
    root: Path | None = None,
    caller: Callable[..., ChatResult] = chat,
    day: str | None = None,
) -> RunResult:
    """Exécute un point LLM déclaré (kill-switch, budget, metering).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (budget.llm_daily_eur + llm_eur_per_1k_tokens).
        spec: Déclaration du point (registre, avec tier/verdict/enabled).
        point_name: Nom du point (metering).
        messages: Messages chat.
        root: config_root (défaut : instance).
        caller: Fonction d'appel (injectable en test ; alors pas de clé).
        day: Jour UTC YYYY-MM-DD (défaut : aujourd'hui).

    Returns:
        RunResult (ok ou fallback killed/budget/error).
    """
    runtime_spec = dict(spec)
    metadata = _db_point_metadata(conn, point_name)
    runtime_messages = messages
    if metadata is not None:
        prompt, output_mode, external_info = metadata
        runtime_spec['output_mode'] = output_mode
        runtime_spec['external_info'] = external_info
        if prompt:
            runtime_messages = _replace_system_prompt(messages, prompt)
    tier = str(runtime_spec.get('tier') or 'T1')
    verdict_kind = str(runtime_spec.get('verdict') or 'LLM-1')
    if not runtime_allows(conn, point_name):
        _record(conn, point_name, tier, '', 0, 0, 0, 'killed')
        return RunResult(False, '', 'killed', 0, 0, '', 0)
    if runtime_spec.get('enabled') is not True:
        _record(conn, point_name, tier, '', 0, 0, 0, 'killed')
        return RunResult(False, '', 'killed', 0, 0, '', 0)
    budget = policy.get('budget') or {}
    cap = float(budget.get('llm_daily_eur', 0) or 0)
    rate = float(budget.get('llm_eur_per_1k_tokens', 0) or 0)
    spent_in, spent_out = daily_tokens(conn, day)
    if rate > 0 and (spent_in + spent_out) / 1000 * rate >= cap > 0:
        _record(conn, point_name, tier, '', 0, 0, 0, 'budget')
        return RunResult(False, '', 'budget', 0, 0, '', 0)
    model, referer = resolve_model(tier, root)
    key = read_api_key(root)
    # Client réel : clé + modèle. Caller injecté (tests) : pas de secret.
    if caller is chat and (not key or not model):
        _record(conn, point_name, tier, model, 0, 0, 0, 'error')
        return RunResult(False, '', 'error', 0, 0, model, 0)
    try:
        result = executer_boucle(
            caller,
            key,
            model,
            runtime_messages,
            spec=runtime_spec,
            policy=policy,
            conn=conn,
            point_name=point_name,
            referer=referer,
            temperature=TEMPERATURES.get(verdict_kind, 0.3),
        )
    except LlmError:
        _record(conn, point_name, tier, model, 0, 0, 0, 'error')
        return RunResult(False, '', 'error', 0, 0, model, 0)
    _record(
        conn,
        point_name,
        tier,
        result.model,
        result.tokens_in,
        result.tokens_out,
        result.latency_ms,
        'ok',
    )
    return RunResult(
        True,
        result.text,
        '',
        result.tokens_in,
        result.tokens_out,
        result.model,
        result.latency_ms,
    )


def run_registered_point(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    point_name: str,
    messages: list[dict[str, Any]],
    **kwargs: Any,
) -> RunResult:
    """run_point() avec spec chargée du registre (kill-switch versionné).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy.
        point_name: Nom registre (matrice C).
        messages: Messages chat.
        kwargs: Transmis à run_point (root, caller...).

    Returns:
        RunResult (point inconnu = fallback killed).
    """
    from serge.llm_registre import point_par_id

    spec = point_par_id(conn, point_name)
    if spec is None:
        _record(conn, point_name, 'T1', '', 0, 0, 0, 'killed')
        return RunResult(False, '', 'killed', 0, 0, '', 0)
    runtime_spec = dict(spec)
    from serge.db_readers import tool_ids_for_point

    runtime_spec['db_tools'] = list(tool_ids_for_point(conn, point_name))
    return run_point(
        conn, policy, runtime_spec, point_name, messages, **kwargs
    )
