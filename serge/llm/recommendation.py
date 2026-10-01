#!/usr/bin/env python3
"""Quel modèle recommander pour chaque niveau : le rapport note / prix.

La note d'intelligence de chaque modèle (l'indice d'Artificial Analysis) et
son prix viennent d'OpenRouter, le mélange de jetons lus et écrits est
mesuré dans ``llm_usage`` ; le prix maximum et la tolérance de chaque
niveau viennent de ``llm_models``. Pour un niveau :

1. on ne garde que les modèles utilisables (outils, contexte, récents, pas
   gratuits, pas en variante ``:batch``) et au plus au prix maximum ;
2. la meilleure note parmi eux donne la référence ;
3. on garde ceux qui ont au moins ``tolerance`` fois cette note ;
4. on recommande celui dont le rapport note / prix est le meilleur.

Sans note, rien n'est recommandé : le prix seul ne dit rien de
l'intelligence.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

# raccourci : ces deux seuils sont en dur ; en faire des réglages d'un niveau
# si l'un d'eux doit changer.
MIN_CONTEXT = 128_000  # jetons : les historiques d'outils sont longs
MAX_AGE_DAYS = 365
# Le Batch API d'OpenRouter répond sous 24 h : Serge fait des appels directs.
DEFERRED_VARIANT = ':batch'
DAY_S = 86400
# raccourci : tant que Serge n'a pas assez d'appels enregistrés pour mesurer
# son mélange, on suppose trois jetons lus pour un écrit.
DEFAULT_INPUT_SHARE = 0.75


def dollars(value: float) -> str:
    """``0,30 $/M`` : dollars par million de jetons, à la française."""
    return f'{value:.2f} $/M'.replace('.', ',')


def effective_price(model: Mapping[str, Any], input_share: float) -> float:
    """Dollars par million de jetons, pour ``input_share`` de jetons lus.

    Les jetons lus sont comptés au prix de la lecture normale, pas à celui
    du cache : c'est le prix sans remise, qui dit le pire.
    """
    return input_share * float(model.get('prompt_usd') or 0) + (
        1 - input_share
    ) * float(model.get('completion_usd') or 0)


def usable(model: Mapping[str, Any], now: float) -> bool:
    """Le modèle peut-il servir à Serge (outils, contexte, récent, payant) ?"""
    if str(model['id']).endswith(DEFERRED_VARIANT):
        return False
    if model.get('tools') is not True or model.get('text_out') is False:
        return False
    if int(model.get('context_length') or 0) < MIN_CONTEXT:
        return False
    if not (model.get('prompt_usd') or model.get('completion_usd')):
        return False
    created = int(model.get('created') or 0)
    if created and now - created > MAX_AGE_DAYS * DAY_S:
        return False
    end = str(model.get('expires') or '')[:10]
    return not end or end > time.strftime('%Y-%m-%d', time.gmtime(now))


def _pick(
    candidates: list[Mapping[str, Any]],
    tier: Mapping[str, float],
    input_share: float,
) -> dict[str, Any]:
    max_price = float(tier['max_price'])
    if max_price <= 0:
        return {'id': '', 'reason': 'Prix maximum non réglé pour ce niveau.'}
    scored = [m for m in candidates if m.get('intelligence')]
    if not scored:
        return {
            'id': '',
            'reason': (
                f'Aucun modèle noté et utilisable sous {dollars(max_price)}.'
            ),
        }
    best = max(float(m['intelligence']) for m in scored)
    threshold = float(tier['tolerance']) * best
    chosen = min(
        (m for m in scored if float(m['intelligence']) >= threshold),
        key=lambda m: (
            -float(m['intelligence']) / effective_price(m, input_share),
            -float(m['intelligence']),
            m['id'],
        ),
    )
    score = float(chosen['intelligence'])
    price = effective_price(chosen, input_share)
    return {
        'id': chosen['id'],
        'score': score,
        'price': price,
        'reason': (
            f'Note {score:g} pour {dollars(price)} ; la meilleure note sous'
            f' {dollars(max_price)} est {best:g}.'
        ),
    }


def recommend(
    models: list[Mapping[str, Any]],
    tiers: Mapping[str, Mapping[str, float]],
    input_share: float = DEFAULT_INPUT_SHARE,
    now: float | None = None,
) -> dict[str, dict[str, Any]]:
    """Le modèle recommandé par niveau : ``{tier: {id, reason, ...}}``.

    Args:
        models: Le catalogue OpenRouter (``kit.openrouter.fetch_models``).
        tiers: Les réglages de chaque niveau, ``{tier: {max_price,
            tolerance}}`` (prix maximum en $/M, tolérance entre 0 et 1).
        now: Heure en secondes (défaut : maintenant).

    Returns:
        Par niveau, ``id`` vaut ``''`` quand rien ne peut être recommandé ;
        ``max_price`` rappelle le plafond du niveau.
    """
    moment = time.time() if now is None else now
    pool = [m for m in models if usable(m, moment)]
    out = {}
    for tier, settings in tiers.items():
        under = [
            m
            for m in pool
            if effective_price(m, input_share) <= float(settings['max_price'])
        ]
        out[tier] = {
            **_pick(under, settings, input_share),
            'max_price': float(settings['max_price']),
        }
    return out
