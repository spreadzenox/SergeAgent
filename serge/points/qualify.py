#!/usr/bin/env python3
"""Points P1 + P7 : qualify_prospect (LLM-1) + score_lead (DET + départage).

P1 : binaire + confiance ; < 0,6 = REJECT conservateur + review.
Repli : règles ICP de base. P7 : score DET (barème policy) + LLM-1
seulement en zone grise + décision coûteuse. Repli : DET seul.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.e164 import is_valid as is_valid_phone
from serge.points.jsonio import run_json
from serge.policy import PolicyError

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')

QUALIFY_SYSTEM = """Tu qualifies un prospect contre un ICP (français/anglais).
Réponds UNIQUEMENT un objet JSON : {"decision": "QUALIFIED|REJECTED", "confiance": 0.0-1.0, "motif": "...", "requested": "..."}.
QUALIFIED = correspond à l'ICP et contactable. Doute sérieux = REJECTED avec motif. requested = info manquante éventuelle ("" si rien)."""

DEPARTAGE_SYSTEM = """Tu départages un prospect en zone grise (français).
Réponds UNIQUEMENT un objet JSON : {"decision": "allouer|abandonner", "confiance": 0.0-1.0, "motif": "..."}.
allouer = vaut un appel/suivi humain ; abandonner = stopper les frais. Tiens compte de l'historique et du coût d'opportunité."""


def icp_rules(fiche: Mapping[str, Any]) -> dict[str, Any]:
    """Repli dét P1 : règles ICP de base (contactable + complet).

    Args:
        fiche: Fiche prospect (email, phone, nom, entreprise...).

    Returns:
        Dict decision/confiance/motif (confiance 0.4 → review).
    """
    email = str(fiche.get('email') or '')
    phone = str(fiche.get('phone') or '')
    contactable = bool(
        (email and EMAIL_RE.match(email)) or (phone and is_valid_phone(phone))
    )
    if not contactable:
        return {
            'decision': 'REJECTED',
            'confiance': 0.4,
            'motif': 'incontactable',
            'requested': '',
        }
    return {
        'decision': 'QUALIFIED',
        'confiance': 0.4,
        'motif': 'contactable (règles de base)',
        'requested': '',
    }


def _valid_qualify(data: dict[str, Any]) -> bool:
    if data.get('decision') not in {'QUALIFIED', 'REJECTED'}:
        return False
    try:
        confiance = float(data.get('confiance', -1))
    except (TypeError, ValueError):
        return False
    return 0.0 <= confiance <= 1.0


def qualify_prospect(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    icp_text: str,
    fiche: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P1 : qualifie un prospect vs ICP (LLM-1 + seuil conservateur).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (prospection.qualify_confidence_min).
        icp_text: ICP venture (tronqué 600c).
        fiche: Fiche prospect (dict).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict decision/confiance/motif/requested/fallback/needs_review.
    """
    try:
        threshold = float(
            (policy.get('prospection') or {}).get(
                'qualify_confidence_min', 0.6
            )
        )
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.qualify_confidence_min invalide') from exc
    fiche_text = ' ; '.join(
        f'{key}={value}' for key, value in fiche.items() if value
    )[:800]
    messages = [
        {'role': 'system', 'content': QUALIFY_SYSTEM},
        {
            'role': 'user',
            'content': f'ICP : {icp_text[:600]}\nFiche : {fiche_text}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'qualify_prospect', messages, _valid_qualify, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        fallback = icp_rules(fiche)
        return {
            **fallback,
            'fallback': reason or 'parse',
            'needs_review': True,
        }
    confiance = float(data['confiance'])
    if confiance < threshold:
        return {
            'decision': 'REJECTED',
            'confiance': confiance,
            'motif': f'sous-seuil {threshold} (conservateur)',
            'requested': str(data.get('requested') or ''),
            'fallback': '',
            'needs_review': True,
        }
    return {
        'decision': str(data['decision']),
        'confiance': confiance,
        'motif': str(data.get('motif') or ''),
        'requested': str(data.get('requested') or ''),
        'fallback': '',
        'needs_review': False,
    }


def det_score(
    conn: sqlite3.Connection, policy: Mapping[str, Any], contact_id: str
) -> dict[str, Any]:
    """P7 DET : score 0-100 depuis compteurs signaux (barème policy).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (prospection.score_w_* + lead_score_gray).
        contact_id: Contact scoré.

    Returns:
        Dict score/zone (low|gray|high)/decision DET (revoir si gray).
    """
    section = policy.get('prospection') or {}
    weights = {
        'INTENT': float(section.get('score_w_intent', 25)),
        'REPLIED': float(section.get('score_w_reply', 10)),
        'ENGAGED': float(section.get('score_w_engaged', 5)),
        'MEETING': float(section.get('score_w_meeting', 40)),
        'NEGATIVE': float(section.get('score_w_negative', -20)),
    }
    rows = conn.execute(
        'SELECT signal, class, COUNT(*) FROM inbound_events'
        ' WHERE contact_id=? GROUP BY signal, class',
        (contact_id,),
    ).fetchall()
    total = 0.0
    for signal, cls, count in rows:
        total += weights.get(str(signal), 0.0) * int(count)
        if str(cls) == 'MEETING_REQUEST':
            total += weights['MEETING'] * int(count)
    score = max(0, min(100, int(round(total))))
    gray = section.get('lead_score_gray', [40, 60])
    try:
        low, high = int(gray[0]), int(gray[1])
    except (TypeError, ValueError, IndexError):
        low, high = 40, 60
    if score < low:
        return {'score': score, 'zone': 'low', 'decision': 'abandonner'}
    if score > high:
        return {'score': score, 'zone': 'high', 'decision': 'allouer'}
    return {'score': score, 'zone': 'gray', 'decision': 'revoir'}


def _valid_departage(data: dict[str, Any]) -> bool:
    if data.get('decision') not in {'allouer', 'abandonner'}:
        return False
    try:
        confiance = float(data.get('confiance', -1))
    except (TypeError, ValueError):
        return False
    return 0.0 <= confiance <= 1.0


def score_lead(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    contact_id: str,
    history_text: str = '',
    *,
    costly: bool = False,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P7 : score DET + départage LLM-1 si zone grise + décision coûteuse.

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (barème + zone grise).
        contact_id: Contact scoré.
        history_text: Résumé historique (départage seul).
        costly: Décision coûteuse (appel humain...) ?
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict score/zone/decision (+ motif, fallback si LLM tenté).
    """
    base = det_score(conn, policy, contact_id)
    if base['zone'] != 'gray' or not costly:
        return {**base, 'motif': '', 'fallback': ''}
    messages = [
        {'role': 'system', 'content': DEPARTAGE_SYSTEM},
        {
            'role': 'user',
            'content': f'Score DET : {base["score"]} (zone grise).'
            f'\nHistorique : {history_text[:1500]}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'score_lead_departage',
        messages,
        _valid_departage,
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {**base, 'motif': '', 'fallback': reason or 'parse'}
    return {
        'score': base['score'],
        'zone': 'gray',
        'decision': str(data['decision']),
        'motif': str(data.get('motif') or ''),
        'fallback': '',
    }
