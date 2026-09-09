#!/usr/bin/env python3
"""Points H1/H2/H3 : rendu FR (R) + intent owner (1) + conséquence (1).

H1 : contexte ticket (IDs backend strippés dét). H2 : intent + confiance
(ambigu → clarification par l'appelant). H3 : conséquence OUI/NON sur
5 critères (doute → confirmation ; §14.1a dét après, par l'appelant).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json

ID_RE = re.compile(r'\b[twe]_[0-9a-f]{12}\b')
INTENTS = frozenset(
    {'APPROVE', 'REJECT', 'DISCUSS', 'ASK', 'ORDER', 'ESCALATE', 'OTHER'}
)
CRITERES = frozenset(
    {'irreversible', 'financier', 'visible', 'volume', 'juridique'}
)

RENDER_SYSTEM = """Tu présentes un ticket à son owner (français, embed court).
Réponds UNIQUEMENT un objet JSON : {"titre": "...", "ou": "...", "enjeu": "...", "attente": "..."}.
ou = où on en est (1 phrase) ; enjeu = pourquoi ça compte ; attente = ce que l'owner doit faire ("" si FYI). Jamais d'ID technique, jamais de PII/secrets."""

INTENT_SYSTEM = """Tu classes un message d'owner (français).
Réponds UNIQUEMENT un objet JSON : {"intent": "APPROVE|REJECT|DISCUSS|ASK|ORDER|ESCALATE|OTHER", "confiance": 0.0-1.0, "cible": "..."}.
APPROVE/REJECT = valide/refuse la proposition courante ; DISCUSS = commente ; ASK = question ; ORDER = ordre d'action ; ESCALATE = urgence/alerte ; OTHER = inclassable. cible = objet visé ("" si aucun)."""

CONSEQ_SYSTEM = """Tu juges si un ordre a des conséquences (français).
5 critères : irreversible (pas d'annulation), financier (coût/transaction), visible (public/prospect), volume (N personnes), juridique (contrat/données).
Réponds UNIQUEMENT un objet JSON : {"consequence": "OUI|NON", "criteres": [{"nom": "...", "touche": true|false}], "confiance": 0.0-1.0}.
Doute = OUI (conservateur)."""


def strip_ids(text: str) -> str:
    """Retire les IDs backend opaques (affichage owner).

    Args:
        text: Texte à nettoyer.

    Returns:
        Texte sans t_/w_/e_ hexadécimaux.
    """
    return ID_RE.sub('', text)


def _valid_render(data: dict[str, Any]) -> bool:
    for key in ('titre', 'ou', 'enjeu'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            return False
    return isinstance(data.get('attente'), str)


def render_context_fr(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    ticket_text: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """H1 : contexte ticket FR (lecture seule, IDs strippés).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        ticket_text: Ticket + thread + état (tronqué 1500c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict titre/ou/enjeu/attente/fallback (repli = brut).
    """
    messages = [
        {'role': 'system', 'content': RENDER_SYSTEM},
        {'role': 'user', 'content': ticket_text[:1500]},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 400}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'render_context_fr', messages, _valid_render, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'titre': ticket_text[:120],
            'ou': '',
            'enjeu': '',
            'attente': '',
            'fallback': reason or 'parse',
        }
    return {
        'titre': strip_ids(str(data['titre'])),
        'ou': strip_ids(str(data['ou'])),
        'enjeu': strip_ids(str(data['enjeu'])),
        'attente': strip_ids(str(data.get('attente') or '')),
        'fallback': '',
    }


def _valid_intent(data: dict[str, Any]) -> bool:
    if data.get('intent') not in INTENTS:
        return False
    try:
        confiance = float(data.get('confiance', -1))
    except (TypeError, ValueError):
        return False
    return 0.0 <= confiance <= 1.0


def classify_owner_intent(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    message: str,
    thread_text: str = '',
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """H2 : intent owner (ambigu → clarification par l'appelant).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        message: Message owner.
        thread_text: Thread courant (tronqué 1000c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict intent/confiance/cible/needs_clarify/fallback.
    """
    messages = [
        {'role': 'system', 'content': INTENT_SYSTEM},
        {
            'role': 'user',
            'content': f'Message : {message[:800]}\nThread : {thread_text[:1000]}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'classify_owner_intent',
        messages,
        _valid_intent,
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'intent': 'OTHER',
            'confiance': 0.0,
            'cible': '',
            'needs_clarify': True,
            'fallback': reason or 'parse',
        }
    confiance = float(data['confiance'])
    return {
        'intent': str(data['intent']),
        'confiance': confiance,
        'cible': str(data.get('cible') or ''),
        'needs_clarify': confiance < 0.6,
        'fallback': '',
    }


def _valid_conseq(data: dict[str, Any]) -> bool:
    if data.get('consequence') not in {'OUI', 'NON'}:
        return False
    criteres = data.get('criteres')
    if not isinstance(criteres, list):
        return False
    for item in criteres:
        if not isinstance(item, dict):
            return False
        if item.get('nom') not in CRITERES:
            return False
        if not isinstance(item.get('touche'), bool):
            return False
    try:
        confiance = float(data.get('confiance', -1))
    except (TypeError, ValueError):
        return False
    return 0.0 <= confiance <= 1.0


def judge_consequence(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    ordre_text: str,
    contexte_text: str = '',
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """H3 : conséquence OUI/NON (doute → confirmation ; §14.1a après).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        ordre_text: Ordre owner.
        contexte_text: Cible/montants/portée (tronqué 1500c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict consequence/criteres/confiance/needs_confirmation/fallback.
    """
    messages = [
        {'role': 'system', 'content': CONSEQ_SYSTEM},
        {
            'role': 'user',
            'content': f'Ordre : {ordre_text[:800]}\nContexte : {contexte_text[:1500]}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 300}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'judge_consequence', messages, _valid_conseq, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'consequence': 'OUI',
            'criteres': [],
            'confiance': 0.0,
            'needs_confirmation': True,
            'fallback': reason or 'parse',
        }
    consequence = str(data['consequence'])
    confiance = float(data['confiance'])
    return {
        'consequence': consequence,
        'criteres': [
            {'nom': str(item['nom']), 'touche': bool(item['touche'])}
            for item in data['criteres']
        ],
        'confiance': confiance,
        'needs_confirmation': consequence == 'OUI' or confiance < 0.7,
        'fallback': '',
    }
