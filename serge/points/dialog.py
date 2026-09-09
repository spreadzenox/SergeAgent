#!/usr/bin/env python3
"""Point P5 : voice_dialog (LLM-B, T2). Un tour temps réel + garde-fous.

Tours/durée max (coupure gracieuse), recentrage 1× puis raccrochage propre,
anti-engagement/prix, C5 interdite (contexte pré-chargé). Repli : message
secours + hangup (appelant : répondeur + ticket + rappel).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json
from serge.points.reply import engagement_hit, invented_numbers
from serge.policy import PolicyError

DIALOG_SYSTEM = """Tu es Serge, agent vocal commercial francophone temps réel.
Règles dures : français, 1-2 phrases courtes, sans markdown ; jamais d'engagement/prix inventé ; hors-sujet → action redirect ("revenons à...") ; fin de conversation → action hangup avec "Au revoir".
Réponds UNIQUEMENT un objet JSON : {"text": "...", "action": "continue|redirect|hangup|dtmf_callback"}.
dtmf_callback = proposer le rappel humain (touche 1) quand pertinent."""

GOODBYE = 'Merci pour votre temps, au revoir.'
RESCUE = (
    'Je rencontre un souci technique, je vous recontacte très vite. Au revoir.'
)
ACTIONS = frozenset({'continue', 'redirect', 'hangup', 'dtmf_callback'})
MAX_TEXT_CHARS = 500


def _valid_turn(data: dict[str, Any]) -> bool:
    text = data.get('text')
    if not isinstance(text, str) or not text.strip():
        return False
    if len(text) > MAX_TEXT_CHARS:
        return False
    return data.get('action') in ACTIONS


def voice_turn(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    history: Sequence[Mapping[str, str]],
    script_text: str,
    *,
    turn_index: int = 0,
    redirected: bool = False,
    allowed_text: str = '',
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P5 : un tour de dialogue (filets dét, C5 interdite).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (voice.max_turns).
        history: Tours [{role: user|serge, text}] (borné 8).
        script_text: Script P4 (règles dures incluses).
        turn_index: N° du tour (0-based).
        redirected: Recentrage déjà consommé ?
        allowed_text: Sources chiffres autorisés.
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict text/action/fallback (hangup gracieux aux bornes).
    """
    try:
        max_turns = int((policy.get('voice') or {}).get('max_turns', 12))
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.voice.max_turns invalide') from exc
    if turn_index >= max(1, max_turns):
        return {
            'text': GOODBYE,
            'action': 'hangup',
            'fallback': 'max_turns',
        }
    lines = [
        f'{"Prospect" if item.get("role") == "user" else "Serge"} :'
        f' {str(item.get("text") or "")[:300]}'
        for item in history[-8:]
    ]
    messages = [
        {
            'role': 'system',
            'content': f'{DIALOG_SYSTEM}\nScript : {script_text[:1500]}',
        },
        {'role': 'user', 'content': '\n'.join(lines)[-2000:]},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'voice_dialog', messages, _valid_turn, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'text': RESCUE,
            'action': 'hangup',
            'fallback': reason or 'parse',
        }
    text = str(data['text']).strip()
    action = str(data['action'])
    if engagement_hit(text) or (
        allowed_text and invented_numbers(text, allowed_text)
    ):
        return {'text': RESCUE, 'action': 'hangup', 'fallback': 'filet'}
    if redirected and action == 'redirect':
        return {'text': GOODBYE, 'action': 'hangup', 'fallback': ''}
    return {'text': text, 'action': action, 'fallback': ''}
