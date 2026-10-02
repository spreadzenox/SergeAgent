#!/usr/bin/env python3
"""Le catalogue des modèles d'OpenRouter.

La note d'intelligence de chaque modèle est l'indice d'Artificial Analysis,
que ``/models`` donne avec le modèle (``benchmarks``) : pas de clé, pas de
second appel, pas d'identifiants à rapprocher. Le catalogue est lu sur
OpenRouter à chaque ouverture de la page Pipeline (environ une demi-seconde) :
il est donc toujours à jour. Si OpenRouter ne répond pas, on garde le dernier
catalogue lu, et on le dit.
"""

from __future__ import annotations

import copy
import sqlite3
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from kit.openrouter import OpenRouterError, fetch_models
from serge.llm.recommendation import (
    DAY_S,
    DEFERRED_VARIANT,
    effective_price,
    recommend,
)
from serge.llm.runtime import read_api_key, tokens_since
from serge.policy_store import policy_en_vigueur

TIMEOUT_S = 10.0
SCORES_SOURCE = (
    'indice d’intelligence d’Artificial Analysis, donné par OpenRouter'
)

# raccourci : le dernier catalogue lu vit dans la mémoire du programme, sans
# verrou ; un seul propriétaire ouvre la page, et un mélange de deux lectures
# ne donnerait qu'un catalogue un peu plus vieux.
_last: dict[str, Any] = {'models': [], 'at': 0.0, 'error': ''}


def clear_cache() -> None:
    """Oublie le dernier catalogue lu (tests)."""
    _last.update(models=[], at=0.0, error='')


def catalog(
    root: Path | None = None,
    *,
    fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Le catalogue OpenRouter, lu maintenant : ``{models, at, error}``.

    Args:
        root: Dossier de l'instance (pour la clé OpenRouter, facultative).
        fetcher: Remplace l'appel à OpenRouter (tests).
        now: Heure en secondes (défaut : maintenant).

    Returns:
        ``models`` est vide si OpenRouter n'a jamais répondu ; ``error``
        dit pourquoi la dernière lecture a échoué (vide si elle a réussi).
        Après un échec, ``models`` est le dernier catalogue lu.
    """
    try:
        models = (fetcher or _read_openrouter)(read_api_key(root))
    except OpenRouterError as exc:
        _last['error'] = str(exc)
    else:
        _last.update(
            models=models,
            at=time.time() if now is None else now,
            error='',
        )
    return copy.deepcopy(_last)


def _read_openrouter(api_key: str) -> list[dict[str, Any]]:
    return fetch_models(api_key, timeout=TIMEOUT_S)


def tier_settings(conn: sqlite3.Connection) -> dict[str, dict[str, float]]:
    """Le prix maximum et la tolérance de chaque niveau, lus en base."""
    return {
        str(tier): {'max_price': float(price), 'tolerance': int(pct) / 100}
        for tier, price, pct in conn.execute(
            'SELECT tier, max_price_usd, tolerance_pct FROM llm_models'
        )
    }


def usage_mix(conn: sqlite3.Connection, now: float | None = None) -> dict:
    """Le mélange de jetons lus et écrits de Serge, mesuré sur les derniers
    jours (réglages « Recommandation de modèle », page Pipeline). Sous le
    nombre de jetons mesurés réglé, on suppose la part de jetons lus réglée.

    Returns:
        ``{input_share, tokens, measured}`` : la part de jetons lus, le
        nombre de jetons mesurés, et si la mesure suffit (sinon la part est
        celle par défaut).
    """
    choice = policy_en_vigueur(conn)['model_choice']
    moment = time.time() if now is None else now
    days = int(choice['mix_days'])
    since = datetime.fromtimestamp(moment - days * DAY_S, UTC).isoformat()
    read, written = tokens_since(conn, since)
    total = read + written
    if total < int(choice['min_measured_tokens']):
        return {
            'input_share': float(choice['default_read_share']),
            'tokens': total,
            'measured': False,
        }
    return {'input_share': read / total, 'tokens': total, 'measured': True}


def for_page(
    tiers: dict[str, dict[str, float]],
    mix: dict,
    choice: dict[str, Any],
    root: Path | None = None,
    *,
    fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Ce que la page Pipeline affiche : modèles, notes, recommandations."""
    cat = catalog(root, fetcher=fetcher, now=now)
    share = float(mix['input_share'])
    models: list[dict[str, Any]] = [
        {
            'id': m['id'],
            'name': m['name'],
            'context': m['context_length'],
            'input': m['prompt_usd'],
            'cache_read': m.get('cache_read_usd'),
            'cache_write': m.get('cache_write_usd'),
            'output': m['completion_usd'],
            'price': effective_price(m, share),
            'tools': m.get('tools'),
            'score': m.get('intelligence'),
        }
        for m in cat['models']
    ]
    at = cat['at']
    return {
        'models': sorted(models, key=lambda m: str(m['id'])),
        'recommendations': recommend(
            cat['models'], tiers, share, choice=choice, now=now
        ),
        'mix': mix,
        'loaded_at': (
            datetime.fromtimestamp(at, UTC).isoformat(timespec='seconds')
            if at
            else ''
        ),
        'error': cat['error'],
        'scored': sum(1 for m in models if m['score']),
        'scores_source': SCORES_SOURCE,
    }


def check_model(
    model: str,
    root: Path | None = None,
    *,
    fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
) -> tuple[str, str]:
    """Le modèle existe-t-il chez OpenRouter, et convient-il à Serge ?

    Returns:
        ``('ok', '')``, ``('unknown', message)`` (l'identifiant n'est pas
        dans le catalogue), ``('unverified', message)`` (catalogue
        injoignable), ``('deferred', message)`` (variante ``:batch``) ou
        ``('no_tools', message)``.
    """
    cat = catalog(root, fetcher=fetcher)
    if not cat['models'] or cat['error']:
        return (
            'unverified',
            'Catalogue OpenRouter injoignable : identifiant non vérifié.',
        )
    found = next((m for m in cat['models'] if m['id'] == model), None)
    if found is None:
        return 'unknown', f'« {model} » n’existe pas chez OpenRouter.'
    if model.endswith(DEFERRED_VARIANT):
        return (
            'deferred',
            'Variante Batch d’OpenRouter : pensée pour des traitements'
            ' différés (réponse sous 24 h), pas pour les appels directs de'
            ' Serge. Choisis plutôt le modèle sans « :batch ».',
        )
    if found.get('tools') is False:
        return (
            'no_tools',
            'Ce modèle ne sait pas appeler d’outils : les invocations qui'
            ' en ont besoin échoueront.',
        )
    return 'ok', ''
