#!/usr/bin/env python3
"""Ce qu'il faut pour appeler un modèle : le modèle, la clé, le budget.

L'appel lui-même est fait par l'interpréteur (``serge/interpreter/``), le
même pour toutes les invocations. Ce fichier ne connaît aucune invocation.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kit.openrouter import RECOMMENDED_TIERS
from serge.paths import config_root
from serge.secrets import read_secret_file

TIER_TO_SLOT = {'T1': 'CHEAP', 'T2': 'DEFAULT', 'T3': 'SMART'}


def _slots_path(root: Path | None) -> Path:
    base = root or config_root()
    return base / 'llm/slots.json'


def resolve_model(
    tier: str, root: Path | None = None, referer_out: dict | None = None
) -> tuple[str, str]:
    """Le modèle choisi à l'installation pour ce niveau.

    Args:
        tier: T1 | T2 | T3.
        root: Dossier de l'instance (défaut : celui de l'instance).
        referer_out: Dict rempli avec le referer si fourni.

    Returns:
        Tuple (identifiant du modèle, referer).
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
    """Clé OpenRouter de l'instance (jamais écrite au journal).

    Args:
        root: Dossier de l'instance (défaut : celui de l'instance).

    Returns:
        La clé, ou '' si absente.
    """
    base = root or config_root()
    return read_secret_file(base / 'secrets/openrouter-api-key')


def daily_tokens(
    conn: sqlite3.Connection, day: str | None = None
) -> tuple[int, int]:
    """Tokens consommés dans la journée, par tous les appels réussis.

    Args:
        conn: Connexion à la base (lecture).
        day: Préfixe AAAA-MM-JJ (défaut : aujourd'hui UTC).

    Returns:
        Tuple (tokens_in, tokens_out).
    """
    prefix = day or datetime.now(UTC).strftime('%Y-%m-%d')
    row = conn.execute(
        'SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0)'
        " FROM llm_usage WHERE verdict IN ('ok', 'format_invalide')"
        ' AND created_at LIKE ?',
        (f'{prefix}%',),
    ).fetchone()
    return int(row[0]), int(row[1])


def budget_spent(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    day: str | None = None,
) -> bool:
    """Vrai si le plafond de dépense LLM du jour est atteint.

    Exemple : avec un plafond de 5 € et 0,004 € pour 1 000 tokens, le
    plafond est atteint à 1 250 000 tokens dans la journée.

    Args:
        conn: Connexion à la base (lecture).
        policy: Policy en vigueur (``budget.llm_daily_eur`` et
            ``budget.llm_eur_per_1k_tokens``).
        day: Jour UTC AAAA-MM-JJ (défaut : aujourd'hui).
    """
    budget = policy.get('budget') or {}
    cap = float(budget.get('llm_daily_eur', 0) or 0)
    rate = float(budget.get('llm_eur_per_1k_tokens', 0) or 0)
    spent_in, spent_out = daily_tokens(conn, day)
    return rate > 0 and (spent_in + spent_out) / 1000 * rate >= cap > 0
