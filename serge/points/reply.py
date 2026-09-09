#!/usr/bin/env python3
"""Point O3 : reply_intent (LLM-B, T2). Brouillon + filets dét.

Filets : détecteur d'engagement contractuel (doute = ticket + accusé),
prix/délais = catalogue ou rien (tout nombre du brouillon doit matcher
une source fournie). Full auto + traçabilité post-hoc. Repli : accusé.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json

ENGAGEMENT_PATTERNS = (
    'garanti',
    'garantie',
    'promets',
    'promettons',
    'je m\u2019engage',
    'je mengage',
    'nous engageons',
    'contractuel',
    'signons',
    'rembourse',
    'dedommage',
    'assure que',
    'certifie',
    'definitif',
    'sans condition',
    'guarantee',
    'i promise',
    'we guarantee',
    'refund',
)
NUMBER_RE = re.compile(r'\d[\d\s.,]*')
MAX_DRAFT_CHARS = 2000

ACK_TEXT = (
    'Merci pour votre message, je reviens vers vous très vite avec une'
    ' réponse précise.'
)

REPLY_SYSTEM = """Tu rédiges une réponse commerciale courte à un prospect (français, ton courtois et concret).
Règles dures : jamais d'engagement contractuel (garantie, promesse, remboursement, contrat) ; jamais de prix/délai inventé (uniquement ceux fournis) ; jamais de name-drop d'autres prospects ; 1 à 2 paragraphes courts, sans markdown.
Réponds UNIQUEMENT un objet JSON : {"draft": "...", "confiance": 0.0-1.0}."""


def engagement_hit(draft: str) -> str:
    """Détecteur dét d'engagement contractuel.

    Args:
        draft: Brouillon à vérifier.

    Returns:
        Le pattern fautif, ou '' si aucun.
    """
    folded = draft.strip().lower()
    for pattern in ENGAGEMENT_PATTERNS:
        if pattern in folded:
            return pattern
    return ''


def invented_numbers(draft: str, sources: str) -> list[str]:
    """Nombres du brouillon absents des sources (prix/délais inventés).

    Args:
        draft: Brouillon à vérifier.
        sources: Textes sources autorisés (offre, catalogue, playbook).

    Returns:
        Liste des nombres suspects (normalisés, dédupliqués).
    """
    allowed = {_norm_number(item) for item in NUMBER_RE.findall(sources)}
    suspects: list[str] = []
    for raw in NUMBER_RE.findall(draft):
        norm = _norm_number(raw)
        if not norm or norm in allowed or norm in suspects:
            continue
        suspects.append(norm)
    return suspects


def _norm_number(raw: str) -> str:
    return re.sub(r'[\s.,]', '', raw).lstrip('0') or '0'


def _valid_reply(data: dict[str, Any]) -> bool:
    draft = data.get('draft')
    if not isinstance(draft, str) or not draft.strip():
        return False
    if len(draft) > MAX_DRAFT_CHARS:
        return False
    try:
        confiance = float(data.get('confiance', -1))
    except (TypeError, ValueError):
        return False
    return 0.0 <= confiance <= 1.0


def draft_intent_reply(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    history_text: str,
    classe: str,
    verbatim: str,
    *,
    offer_text: str = '',
    playbook_text: str = '',
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """O3 : brouillon de réponse intent (filets dét avant envoi).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (non lue ici, contrat uniforme).
        history_text: Historique (tronqué 2000c).
        classe: Classe O1 + confiance (texte libre court).
        verbatim: Dernier message prospect (tronqué 800c).
        offer_text: Offre/prix catalogue (source nombres autorisés).
        playbook_text: Playbook objection (tronqué 600c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict draft/confiance/action (send|ticket)/reason/fallback.
    """
    user = (
        f'Classe : {classe}\nDernier message : {verbatim[:800]}'
        f'\nHistorique : {history_text[:2000]}'
        f'\nOffre (prix autorisés) : {offer_text[:400] or "(aucun)"}'
        f'\nPlaybook : {playbook_text[:600]}'
    )
    messages = [
        {'role': 'system', 'content': REPLY_SYSTEM},
        {'role': 'user', 'content': user},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 600}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'reply_intent', messages, _valid_reply, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'draft': ACK_TEXT,
            'confiance': 0.0,
            'action': 'ticket',
            'reason': f'fallback:{reason or "parse"}',
            'fallback': reason or 'parse',
        }
    draft = str(data['draft']).strip()
    sources = f'{offer_text}\n{playbook_text}\n{history_text}\n{verbatim}'
    hit = engagement_hit(draft)
    if hit:
        return {
            'draft': draft,
            'confiance': float(data['confiance']),
            'action': 'ticket',
            'reason': f'engagement:{hit}',
            'fallback': '',
        }
    suspects = invented_numbers(draft, sources)
    if suspects:
        return {
            'draft': draft,
            'confiance': float(data['confiance']),
            'action': 'ticket',
            'reason': f'nombres:{",".join(suspects[:3])}',
            'fallback': '',
        }
    return {
        'draft': draft,
        'confiance': float(data['confiance']),
        'action': 'send',
        'reason': '',
        'fallback': '',
    }
