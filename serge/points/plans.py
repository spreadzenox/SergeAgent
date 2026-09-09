#!/usr/bin/env python3
"""Points M3/M4/M5 : plan_scale + options_pivot (LLM-L, T3) + resume (R, T1).

M3 : sections + justification obligatoires (bornes = appelant → VETO).
M4 : 2-3 options + diff déclarée non vide vérifiée dét (jamais d'auto).
M5 : résumé chiffré (nombres = DB ou rien). Replis : replay/extend/brut.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json
from serge.points.reply import invented_numbers

SCALE_SYSTEM = """Tu planifies l'industrialisation d'un test gagnant (français).
Réponds UNIQUEMENT un objet JSON : {"volumes": "...", "canaux": ["..."], "budget_eur": 0.0, "builder": ["..."], "jalons": ["..."], "risques": ["..."], "justification": "..."}.
Chaque section non vide. justification = pourquoi ce plan (3-5 phrases). Propositions, jamais d'engagements."""

PIVOT_SYSTEM = """Tu proposes 2-3 options de pivot à partir d'objections (français).
Réponds UNIQUEMENT un objet JSON : {"options": [{"changement": "...", "rationnel": "...", "risque": "...", "dimensions_changees": ["canal|cible|prix|message|offre"], "pre_enregistrement": "..."}]}.
Chaque option change ≥ 1 dimension (jamais "refaire pareil")."""

RESUME_SYSTEM = """Tu résumes un market test terminé (français).
Réponds UNIQUEMENT un objet JSON : {"resume": "...", "apprentissages": ["..."], "suites": "..."}.
Chiffres : UNIQUEMENT ceux fournis (aucun inventé). Anonymise la PII."""

DIMS = frozenset({'canal', 'cible', 'prix', 'message', 'offre'})


def _valid_scale(data: dict[str, Any]) -> bool:
    for key in ('volumes', 'justification'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            return False
    for key in ('canaux', 'builder', 'jalons', 'risques'):
        if not isinstance(data.get(key), list) or not data[key]:
            return False
    try:
        budget = float(data.get('budget_eur', -1))
    except (TypeError, ValueError):
        return False
    return budget >= 0


def plan_scale(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    full_text: str,
    budget_text: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """M3 : plan d'industrialisation (bornes vérifiées par l'appelant).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        full_text: Résultats full + budget restant (tronqué 2000c).
        budget_text: Contraintes + standing (tronqué 800c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict plan/action (propose|replay)/reason/fallback.
    """
    messages = [
        {'role': 'system', 'content': SCALE_SYSTEM},
        {
            'role': 'user',
            'content': f'Full : {full_text[:2000]}\nBudget : {budget_text[:800]}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 1500}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'plan_scale', messages, _valid_scale, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'plan': None,
            'action': 'replay',
            'reason': reason or 'parse',
            'fallback': reason or 'parse',
        }
    return {
        'plan': {
            'volumes': str(data['volumes']),
            'canaux': [str(item) for item in data['canaux']],
            'budget_eur': float(data['budget_eur']),
            'builder': [str(item) for item in data['builder']],
            'jalons': [str(item) for item in data['jalons']],
            'risques': [str(item) for item in data['risques']],
            'justification': str(data['justification']),
        },
        'action': 'propose',
        'reason': '',
        'fallback': '',
    }


def _valid_pivot(data: dict[str, Any]) -> bool:
    options = data.get('options')
    if not isinstance(options, list) or not 2 <= len(options) <= 3:
        return False
    for option in options:
        if not isinstance(option, dict):
            return False
        for key in ('changement', 'rationnel', 'risque', 'pre_enregistrement'):
            if not isinstance(option.get(key), str) or not option[key].strip():
                return False
        dims = option.get('dimensions_changees')
        if (
            not isinstance(dims, list)
            or not dims
            or any(item not in DIMS for item in dims)
        ):
            return False
    return True


def options_pivot(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    objections_text: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """M4 : options de pivot (diff non vide vérifiée dét).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        objections_text: Verbatims top-10 (tronqué 1500c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict options/action (propose|extend)/reason/fallback.
    """
    messages = [
        {'role': 'system', 'content': PIVOT_SYSTEM},
        {'role': 'user', 'content': f'Objections : {objections_text[:1500]}'},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 1200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'options_pivot', messages, _valid_pivot, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'options': [],
            'action': 'extend',
            'reason': reason or 'parse',
            'fallback': reason or 'parse',
        }
    return {
        'options': [
            {
                'changement': str(option['changement']),
                'rationnel': str(option['rationnel']),
                'risque': str(option['risque']),
                'dimensions_changees': [
                    str(item) for item in option['dimensions_changees']
                ],
                'pre_enregistrement': str(option['pre_enregistrement']),
            }
            for option in data['options']
        ],
        'action': 'propose',
        'reason': '',
        'fallback': '',
    }


def _valid_resume(data: dict[str, Any]) -> bool:
    if not isinstance(data.get('resume'), str) or not data['resume'].strip():
        return False
    if not isinstance(data.get('apprentissages'), list):
        return False
    return isinstance(data.get('suites'), str)


def resume_test(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    metrics_text: str,
    verdict_text: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """M5 : résumé de test (chiffres DB ou rien, lecture seule).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        metrics_text: Compteurs + verdict + preuves (tronqué 800c).
        verdict_text: Objections + leçons candidates (tronqué 800c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict resume/apprentissages/suites/fallback (repli = brut).
    """
    metrics = metrics_text[:800]
    messages = [
        {'role': 'system', 'content': RESUME_SYSTEM},
        {
            'role': 'user',
            'content': f'Mesures : {metrics}\nVerdict : {verdict_text[:800]}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 800}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'resume_test', messages, _valid_resume, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'resume': metrics,
            'apprentissages': [],
            'suites': '',
            'fallback': reason or 'parse',
        }
    text = f'{data["resume"]}\n{" ".join(str(item) for item in data["apprentissages"])}'
    suspects = invented_numbers(text, metrics)
    if suspects:
        return {
            'resume': metrics,
            'apprentissages': [],
            'suites': '',
            'fallback': f'nombres:{",".join(suspects[:3])}',
        }
    return {
        'resume': str(data['resume']),
        'apprentissages': [str(item) for item in data['apprentissages']],
        'suites': str(data.get('suites') or ''),
        'fallback': '',
    }
