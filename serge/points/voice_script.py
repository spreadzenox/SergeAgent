#!/usr/bin/env python3
"""Point P4 : voice_script (LLM-B, T2). Script + disclosure + durée dét.

Checkers : disclosure en tête (obligatoire), jamais de passing humain,
durée estimée <= policy, chiffres sourcés, ton. Repli : script pinné
(précédent validé) ; sans pinné = pas de script (appel interdit).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from serge.points.checkers import check_aggressivity, fold
from serge.points.jsonio import run_json
from serge.points.reply import invented_numbers
from serge.policy import PolicyError

DISCLOSURE_PATTERNS = (
    'assistant vocal',
    'agent vocal',
    'intelligence artificielle',
    'je suis serge',
    'serge, l',
)
HUMAN_PASSING = (
    'vraie personne',
    'vrai humain',
    'humain comme vous',
    'pas un robot',
    'pas une machine',
    'en chair et en os',
)
CHARS_PER_SECOND = 13
MAX_BLOCS = 8

SCRIPT_SYSTEM = """Tu rédiges un script d'appel commercial (français) en blocs courts.
Règles dures : le PREMIER bloc contient la disclosure ("je suis Serge, un assistant vocal IA") ; jamais se faire passer pour un humain ; phrases courtes orales (≤ 25 mots) ; proposer le rappel humain (touche 1) ; sans markdown.
Réponds UNIQUEMENT un objet JSON : {"blocs": [{"nom": "accroche|pitch|objections|cloture", "texte": "..."}]}."""


def _valid_script(data: dict[str, Any]) -> bool:
    blocs = data.get('blocs')
    if not isinstance(blocs, list) or not 1 <= len(blocs) <= MAX_BLOCS:
        return False
    for bloc in blocs:
        if not isinstance(bloc, dict):
            return False
        if not bloc.get('nom') or not str(bloc.get('texte') or '').strip():
            return False
    return True


def estimate_duration_s(blocs: Sequence[Mapping[str, Any]]) -> int:
    """Durée orale estimée (13 car/s, FR).

    Args:
        blocs: Blocs {nom, texte}.

    Returns:
        Secondes estimées (arrondi).
    """
    chars = sum(len(str(bloc.get('texte') or '')) for bloc in blocs)
    return max(1, round(chars / CHARS_PER_SECOND))


def check_disclosure(blocs: Sequence[Mapping[str, Any]]) -> str:
    """Disclosure IA en tête (obligatoire, anti-passing humain).

    Returns:
        Code défaut ('' si OK).
    """
    if not blocs:
        return 'vide'
    head = fold(str(blocs[0].get('texte') or ''))
    if not any(pattern in head for pattern in DISCLOSURE_PATTERNS):
        return 'disclosure_manquante'
    full = fold(' '.join(str(bloc.get('texte') or '') for bloc in blocs))
    for pattern in HUMAN_PASSING:
        if pattern in full:
            return f'passing_humain:{pattern}'
    return ''


def draft_voice_script(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    fiche_text: str,
    objections_text: str = '',
    pitfalls_text: str = '',
    *,
    offer_text: str = '',
    pinned: list[dict[str, str]] | None = None,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P4 : script d'appel (checkers dét, repli pinné).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (voice.script_max_seconds).
        fiche_text: Fiche prospect (tronquée 600c).
        objections_text: Objections segment (tronqué 1000c).
        pitfalls_text: Pièges voix (tronqué 400c).
        offer_text: Offre (source chiffres).
        pinned: Script validé précédent (repli).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict blocs/duree_totale_s/action (propose|pinned)/reason/fallback.
    """
    try:
        max_s = int((policy.get('voice') or {}).get('script_max_seconds', 120))
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.script_max_seconds invalide') from exc

    def _pinned(reason: str) -> dict[str, Any]:
        kept = pinned or []
        return {
            'blocs': kept,
            'duree_totale_s': estimate_duration_s(kept) if kept else 0,
            'action': 'pinned',
            'reason': reason,
            'fallback': reason,
        }

    messages = [
        {'role': 'system', 'content': SCRIPT_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'Fiche : {fiche_text[:600]}'
                f'\nObjections : {objections_text[:1000]}'
                f'\nPièges : {pitfalls_text[:400]}'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 900}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'voice_script', messages, _valid_script, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return _pinned(reason or 'parse')
    blocs = [
        {'nom': str(bloc['nom']), 'texte': str(bloc['texte']).strip()}
        for bloc in data['blocs']
    ]
    defect = check_disclosure(blocs)
    if not defect:
        aggr = check_aggressivity(' '.join(bloc['texte'] for bloc in blocs))
        if aggr:
            defect = f'agressif:{aggr}'
    if not defect:
        suspects = invented_numbers(
            ' '.join(bloc['texte'] for bloc in blocs),
            f'{offer_text}\n{fiche_text}',
        )
        if suspects:
            defect = f'nombres:{",".join(suspects[:3])}'
    if not defect and estimate_duration_s(blocs) > max_s:
        defect = f'trop_long:{estimate_duration_s(blocs)}s'
    if defect:
        return _pinned(defect)
    return {
        'blocs': blocs,
        'duree_totale_s': estimate_duration_s(blocs),
        'action': 'propose',
        'reason': '',
        'fallback': '',
    }
