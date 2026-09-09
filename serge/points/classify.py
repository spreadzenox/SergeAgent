#!/usr/bin/env python3
"""Point O1 : classify_reply (LLM-1, T1). Taxonomie + double-check opt-out."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json
from serge.policy import PolicyError

CLASSES = (
    'MEETING_REQUEST',
    'OBJECTION',
    'QUESTION',
    'POSITIVE',
    'NEGATIVE',
    'UNSUBSCRIBE',
    'SPAM',
    'AUTO_REPLY',
    'OTHER',
)

OPT_OUT_PATTERNS = (
    'desinscri',
    'desabonn',
    'unsubscribe',
    'ne plus me contacter',
    'ne me contactez plus',
    'remove me',
    'stop',
    'arretez',
    'opt-out',
    'opt out',
    'retirez-moi',
    'supprimez-moi',
)
SPAM_PATTERNS = (
    'spam',
    'arnaque',
    'escroquerie',
    'signalement',
    'plainte cnil',
)
AUTO_PATTERNS = (
    'absent',
    'out of office',
    'automatic reply',
    'reponse automatique',
    'accuse de reception',
    'conges',
    'vacances',
)
MEETING_PATTERNS = (
    'rendez-vous',
    'rendez vous',
    'rdv',
    'creneau',
    'disponible',
    'appel',
    'call',
    'visio',
    'demo',
    'demonstration',
    'meet',
    'echange',
    'discuter',
)
OBJECTION_PATTERNS = (
    'cher',
    'budget',
    'pas le moment',
    'deja un',
    'prestataire',
    'reflechir',
    'trop tot',
)
NEGATIVE_PATTERNS = (
    'pas interesse',
    'non merci',
    'sans interet',
    'laissez-moi',
    'never',
    'pas besoin',
)
POSITIVE_PATTERNS = (
    'interesse',
    'allons-y',
    'je veux',
    'parfait',
    'super',
    'oui',
    'ok pour',
    'avec plaisir',
)


def _fold(text: str) -> str:
    folded = text.strip().lower()
    for src, dst in (
        ('é', 'e'),
        ('è', 'e'),
        ('ê', 'e'),
        ('à', 'a'),
        ('ç', 'c'),
        ('î', 'i'),
        ('ô', 'o'),
        ('û', 'u'),
    ):
        folded = folded.replace(src, dst)
    return folded


def opt_out_suspect(message: str) -> bool:
    """Double-check dét : le message ressemble-t-il à un opt-out/spam ?

    Args:
        message: Texte brut du prospect.

    Returns:
        True si un pattern opt-out/spam matche (doute = opt-out, P0).
    """
    folded = _fold(message)
    return any(
        pattern in folded for pattern in (*OPT_OUT_PATTERNS, *SPAM_PATTERNS)
    )


def keyword_fallback(message: str) -> dict[str, Any]:
    """Repli dét O1 : règles mots-clés + confiance basse forcée.

    Args:
        message: Texte brut.

    Returns:
        Dict classe/confiance/requested (confiance 0.4 → review).
    """
    folded = _fold(message)
    if any(pattern in folded for pattern in OPT_OUT_PATTERNS):
        classe = 'UNSUBSCRIBE'
    elif any(pattern in folded for pattern in SPAM_PATTERNS):
        classe = 'SPAM'
    elif any(pattern in folded for pattern in AUTO_PATTERNS):
        classe = 'AUTO_REPLY'
    elif any(pattern in folded for pattern in MEETING_PATTERNS):
        classe = 'MEETING_REQUEST'
    elif any(pattern in folded for pattern in OBJECTION_PATTERNS):
        classe = 'OBJECTION'
    elif any(pattern in folded for pattern in NEGATIVE_PATTERNS):
        classe = 'NEGATIVE'
    elif '?' in message or 'combien' in folded or 'comment' in folded:
        classe = 'QUESTION'
    elif any(pattern in folded for pattern in POSITIVE_PATTERNS):
        classe = 'POSITIVE'
    else:
        classe = 'OTHER'
    return {'classe': classe, 'confiance': 0.4, 'requested': ''}


CLASSIFY_SYSTEM = """Tu classes des réponses de prospects (français/anglais).
Réponds UNIQUEMENT un objet JSON : {"classe": "...", "confiance": 0.0-1.0, "requested": "..."}.
Classes : MEETING_REQUEST (veut un RDV/appel/démo), OBJECTION (frein : prix, timing, déjà équipé), QUESTION (demande d'info), POSITIVE (intérêt sans demande précise), NEGATIVE (refus poli), UNSUBSCRIBE (ne plus contacter), SPAM (menace/signalement), AUTO_REPLY (absence/bot), OTHER (inclassable).
requested = ce qu'il te manquerait pour mieux classer ("" si rien).
Exemples : {"classe": "MEETING_REQUEST", "confiance": 0.9, "requested": ""} / {"classe": "UNSUBSCRIBE", "confiance": 0.95, "requested": ""}."""


def _valid_classify(data: dict[str, Any]) -> bool:
    try:
        confiance = float(data.get('confiance', -1))
    except (TypeError, ValueError):
        return False
    return data.get('classe') in CLASSES and 0.0 <= confiance <= 1.0


def classify_reply(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    message: str,
    *,
    context_lines: list[str] | None = None,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """O1 : classe une réponse prospect (LLM-1 + garde-fous dét).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (seuil observation.classify_confidence_min).
        message: Texte brut (tronqué 2000c).
        context_lines: Micro-contexte (canal + 3 derniers, 1 ligne).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict classe/confiance/requested/fallback/needs_review/opt_out.
    """
    try:
        threshold = float(
            (policy.get('observation') or {}).get(
                'classify_confidence_min', 0.6
            )
        )
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.classify_confidence_min invalide') from exc
    body = message[:2000]
    context = '\n'.join(context_lines or [])[:600]
    user = f'Message : {body}\nContexte : {context}' if context else body
    messages = [
        {'role': 'system', 'content': CLASSIFY_SYSTEM},
        {'role': 'user', 'content': user},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'classify_reply', messages, _valid_classify, **kwargs
    )
    if data is None:
        fallback = keyword_fallback(message)
        reason = result.fallback if result is not None else 'error'
        return {
            **fallback,
            'fallback': reason or 'parse',
            'needs_review': True,
            'opt_out': fallback['classe'] in {'UNSUBSCRIBE', 'SPAM'}
            or opt_out_suspect(message),
        }
    suspect = opt_out_suspect(message)
    classe = str(data['classe'])
    if classe in {'UNSUBSCRIBE', 'SPAM'} and not suspect:
        pass
    elif suspect and classe not in {'UNSUBSCRIBE', 'SPAM'}:
        classe = 'UNSUBSCRIBE'
    confiance = float(data['confiance'])
    return {
        'classe': classe,
        'confiance': confiance,
        'requested': str(data.get('requested') or ''),
        'fallback': '',
        'needs_review': confiance < threshold,
        'opt_out': classe in {'UNSUBSCRIBE', 'SPAM'},
    }
