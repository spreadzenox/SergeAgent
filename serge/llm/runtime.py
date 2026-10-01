#!/usr/bin/env python3
"""Ce qu'il faut pour appeler un modèle : le modèle, la clé, le budget.

L'appel lui-même est fait par l'interpréteur (``serge/interpreter/``), le
même pour toutes les invocations. Ce fichier ne connaît aucune invocation.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
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


# Les appels qui ont eu une réponse, donc des jetons (tours d'outils
# compris) ; un appel raté (« erreur ») n'a rien coûté.
_COMPTES = "('ok', 'format_invalide', 'outil')"


@dataclass(frozen=True)
class LlmSpend:
    """Ce que les appels au modèle ont coûté, en euros.

    ``eur`` est le coût réel donné par OpenRouter (``usage.cost``), converti
    en euros. Il n'est jamais estimé : un appel dont le coût n'est pas connu
    n'y compte pas, et ses jetons sont comptés à part (``unknown_tokens``).
    """

    eur: float
    tokens: int
    unknown_tokens: int


def llm_spend(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    day: str | None = None,
) -> LlmSpend:
    """La dépense des appels au modèle, un jour, un mois ou depuis le début.

    Args:
        conn: Connexion à la base (lecture).
        policy: Policy en vigueur (``budget.eur_per_usd`` pour convertir le
            coût réel en euros).
        day: Jour UTC AAAA-MM-JJ, ou mois UTC AAAA-MM ; ``''`` pour tout
            l'historique ; ``None`` pour aujourd'hui.
    """
    prefix = datetime.now(UTC).strftime('%Y-%m-%d') if day is None else day
    eur_per_usd = float(
        (policy.get('budget') or {}).get('eur_per_usd', 0) or 0
    )
    row = conn.execute(
        'SELECT COALESCE(SUM(cost_usd), 0), COALESCE(SUM(CASE WHEN cost_usd'
        ' IS NULL THEN tokens_in + tokens_out ELSE 0 END), 0),'
        ' COALESCE(SUM(tokens_in + tokens_out), 0) FROM llm_usage'
        f' WHERE verdict IN {_COMPTES} AND created_at LIKE ?',
        (f'{prefix}%',),
    ).fetchone()
    return LlmSpend(float(row[0]) * eur_per_usd, int(row[2]), int(row[1]))


def daily_tokens(
    conn: sqlite3.Connection, day: str | None = None
) -> tuple[int, int]:
    """Tokens consommés dans la journée, par tous les appels qui ont eu
    une réponse (tours d'outils compris).

    Args:
        conn: Connexion à la base (lecture).
        day: Préfixe AAAA-MM-JJ (défaut : aujourd'hui UTC).

    Returns:
        Tuple (tokens_in, tokens_out).
    """
    prefix = day or datetime.now(UTC).strftime('%Y-%m-%d')
    row = conn.execute(
        'SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0)'
        f' FROM llm_usage WHERE verdict IN {_COMPTES} AND created_at LIKE ?',
        (f'{prefix}%',),
    ).fetchone()
    return int(row[0]), int(row[1])


def tokens_since(conn: sqlite3.Connection, since: str) -> tuple[int, int]:
    """Jetons lus et écrits par les appels qui ont eu une réponse, depuis
    l'instant ISO ``since`` (tours d'outils compris).
    """
    row = conn.execute(
        'SELECT COALESCE(SUM(tokens_in),0), COALESCE(SUM(tokens_out),0)'
        f' FROM llm_usage WHERE verdict IN {_COMPTES} AND created_at >= ?',
        (since,),
    ).fetchone()
    return int(row[0]), int(row[1])


def budget_reached(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    day: str | None = None,
) -> str:
    """Le plafond de dépense atteint : ``'jour'``, ``'mois'``, ou ``''``.

    Deux plafonds de la policy (page Policy) : ``budget.llm_daily_eur`` pour
    le jour, et ``budget.monthly_eur`` pour le mois, c'est-à-dire ce que
    Serge nous coûte en IA (décision Q68). Les achats de Serge pour ses
    business n'y comptent pas. La dépense est le coût réel donné par
    OpenRouter, converti en euros (voir ``llm_spend``). Un plafond à 0 ne
    bloque rien.

    Args:
        conn: Connexion à la base (lecture).
        policy: Policy en vigueur.
        day: Jour UTC AAAA-MM-JJ (défaut : aujourd'hui) ; son mois compte
            pour le plafond du mois.
    """
    today = day or datetime.now(UTC).strftime('%Y-%m-%d')
    budget = policy.get('budget') or {}
    for period, key, prefix in (
        ('jour', 'llm_daily_eur', today),
        ('mois', 'monthly_eur', today[:7]),
    ):
        cap = float(budget.get(key, 0) or 0)
        if cap > 0 and llm_spend(conn, policy, prefix).eur >= cap:
            return period
    return ''
