#!/usr/bin/env python3
"""Runtime points LLM : kill-switch, budget dur, metering, dérive.

run_point() est le seul chemin d'appel LLM runtime. Ordre : kill-switch
→ budget journalier (estimation EUR) → appel → metering + alerte dérive
vs enveloppe. Tout échec = fallback signalé (jamais d'exception métier),
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
from serge.db.store import append_event, utcnow
from serge.llm.client import ChatResult, LlmError, chat
from serge.paths import config_root
from serge.registry import load_llm_points, runtime_allows
from serge.secrets import read_secret_file

TIER_TO_SLOT = {'T1': 'CHEAP', 'T2': 'DEFAULT', 'T3': 'SMART'}
TEMPERATURES = {
    'LLM-1': 0.1,
    'LLM-B': 0.3,
    'LLM-L': 0.7,
    'LLM-R': 0.2,
    'HYB': 0.3,
}
DRIFT_RATIO = 2.0


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


def run_point(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    spec: Mapping[str, Any],
    point_name: str,
    messages: list[dict[str, Any]],
    *,
    root: Path | None = None,
    caller: Callable[..., ChatResult] = chat,
    max_tokens: int = 800,
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
        caller: Fonction d'appel (injectable en test).
        max_tokens: Cap réponse.
        day: Jour UTC YYYY-MM-DD (défaut : aujourd'hui).

    Returns:
        RunResult (ok ou fallback killed/budget/error).
    """
    tier = str(spec.get('tier') or 'T1')
    verdict_kind = str(spec.get('verdict') or 'LLM-1')
    if not runtime_allows(conn, point_name):
        _record(conn, point_name, tier, '', 0, 0, 0, 'killed')
        return RunResult(False, '', 'killed', 0, 0, '', 0)
    if spec.get('enabled') is not True:
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
    if not key or not model:
        _record(conn, point_name, tier, model, 0, 0, 0, 'error')
        return RunResult(False, '', 'error', 0, 0, model, 0)
    try:
        result = caller(
            key,
            model,
            messages,
            referer=referer,
            max_tokens=max_tokens,
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
    envelope = 0
    context = spec.get('context')
    if isinstance(context, dict):
        raw = context.get('envelope_tokens', 0)
        envelope = (
            raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
        )
    if envelope > 0 and result.tokens_in > envelope * DRIFT_RATIO:
        append_event(
            conn,
            actor='llm',
            type='alert.llm_envelope_drift',
            payload={
                'point': point_name,
                'tokens_in': result.tokens_in,
                'envelope': envelope,
            },
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
        kwargs: Transmis à run_point (root, caller, max_tokens...).

    Returns:
        RunResult (point inconnu = fallback killed).
    """
    try:
        points = load_llm_points()
    except ValueError:
        points = {}
    spec = points.get(point_name)
    if not isinstance(spec, dict):
        _record(conn, point_name, 'T1', '', 0, 0, 0, 'killed')
        return RunResult(False, '', 'killed', 0, 0, '', 0)
    return run_point(conn, policy, spec, point_name, messages, **kwargs)
