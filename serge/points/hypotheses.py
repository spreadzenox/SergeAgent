#!/usr/bin/env python3
"""Points M1/M2 : draft_hypothesis_smoke/full (LLM-B, T2).

Schéma validé dét : smoke N 30-50 + fenêtre ≤ 10j + prix draft non-owné ;
full N 150-200 + seuils kill/scale + fenêtre 2-3 sem. + gate collect
(vérifié par l'appelant avant ticket). Repli : template min + QNA.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json

SMOKE_SYSTEM = """Tu rédiges une hypothèse de market test SMOKE (français).
Réponds UNIQUEMENT un objet JSON : {"hypothese": "...", "N": 30-50, "canaux": ["email"], "seuils": {"scale_min_positifs": 3}, "fenetre_jours": ≤10, "prix_draft": "fourchette, ex 29-49€ (non owné)"}.
hypothese = 2-3 phrases (cible, douleur, offre, résultat attendu)."""

FULL_SYSTEM = """Tu rédiges une hypothèse de market test FULL (français), à partir des résultats smoke.
Réponds UNIQUEMENT un objet JSON : {"hypothese": "...", "N": 150-200, "canaux": ["..."], "seuils": {"scale_min_positifs": 10, "scale_max_u4": 15.0, "kill_max_positifs": 2}, "fenetre_jours": 14-21, "prix_draft": "..."}.
Montants : uniquement ceux fournis (jamais inventés)."""

TEMPLATE_MIN_SMOKE = {
    'hypothese': 'À définir avec l\u2019owner.',
    'N': 30,
    'canaux': ['email'],
    'seuils': {'scale_min_positifs': 3},
    'fenetre_jours': 7,
    'prix_draft': 'à définir',
}
TEMPLATE_MIN_FULL = {
    'hypothese': 'À définir avec l\u2019owner.',
    'N': 150,
    'canaux': ['email'],
    'seuils': {
        'scale_min_positifs': 10,
        'scale_max_u4': 15.0,
        'kill_max_positifs': 2,
    },
    'fenetre_jours': 14,
    'prix_draft': 'à définir',
}


def validate_hypothesis(data: Mapping[str, Any], niveau: str) -> str:
    """Schéma dét M1/M2 (N, seuils, fenêtre, prix draft).

    Args:
        data: Objet à valider.
        niveau: smoke | full.

    Returns:
        Code défaut ('' si OK).
    """
    if (
        not isinstance(data.get('hypothese'), str)
        or not data['hypothese'].strip()
    ):
        return 'hypothese_vide'
    try:
        n = int(data.get('N', 0))
        fenetre = int(data.get('fenetre_jours', 0))
    except (TypeError, ValueError):
        return 'N_ou_fenetre_invalide'
    canaux = data.get('canaux')
    if not isinstance(canaux, list) or not canaux:
        return 'canaux_vides'
    seuils = data.get('seuils')
    if not isinstance(seuils, dict):
        return 'seuils_absents'
    if (
        not isinstance(data.get('prix_draft'), str)
        or not data['prix_draft'].strip()
    ):
        return 'prix_draft_vide'
    if niveau == 'smoke':
        if not 30 <= n <= 50:
            return f'N_smoke:{n}'
        if not 1 <= fenetre <= 10:
            return f'fenetre_smoke:{fenetre}'
        try:
            if int(seuils.get('scale_min_positifs', 0)) < 1:
                return 'seuil_smoke'
        except (TypeError, ValueError):
            return 'seuil_smoke'
    elif niveau == 'full':
        if not 150 <= n <= 200:
            return f'N_full:{n}'
        if not 14 <= fenetre <= 21:
            return f'fenetre_full:{fenetre}'
        try:
            if int(seuils.get('scale_min_positifs', 0)) < 1:
                return 'seuil_full'
            float(seuils.get('scale_max_u4', 0))
            int(seuils.get('kill_max_positifs', 0))
        except (TypeError, ValueError):
            return 'seuil_full'
    else:
        return 'niveau_inconnu'
    return ''


def draft_hypothesis(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    niveau: str,
    ecoute_text: str = '',
    smoke_text: str = '',
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """M1/M2 : hypothèse pré-enregistrée (schéma dét, repli template).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        niveau: smoke | full.
        ecoute_text: Signaux écoute top (M1).
        smoke_text: Résultats smoke U1-U5 (M2).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict hypothese/action (propose|template_min)/reason/fallback.
    """
    template = TEMPLATE_MIN_SMOKE if niveau == 'smoke' else TEMPLATE_MIN_FULL
    point = (
        'draft_hypothesis_smoke'
        if niveau == 'smoke'
        else ('draft_hypothesis_full')
    )
    system = SMOKE_SYSTEM if niveau == 'smoke' else FULL_SYSTEM
    context = ecoute_text[:1200] if niveau == 'smoke' else smoke_text[:2000]
    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': f'Contexte : {context}'},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 800}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        point,
        messages,
        lambda obj: not validate_hypothesis(obj, niveau),
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'hypothese': dict(template),
            'action': 'template_min',
            'reason': reason or 'parse',
            'fallback': reason or 'parse',
        }
    return {
        'hypothese': {
            'hypothese': str(data['hypothese']),
            'N': int(data['N']),
            'canaux': [str(item) for item in data['canaux']],
            'seuils': dict(data['seuils']),
            'fenetre_jours': int(data['fenetre_jours']),
            'prix_draft': str(data['prix_draft']),
        },
        'action': 'propose',
        'reason': '',
        'fallback': '',
    }
