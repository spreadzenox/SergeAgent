#!/usr/bin/env python3
"""Points B2/B3 : review_build (LLM-1 multimodal, T2) + dette (R, T1).

B2 : verdict enum strict (passes 1-2 : PASS/FIX/REBUILD ; passe 3 : binaire
SHIP/REBUILD + dette), FIX ≤ 5 localisés, contradiction inter-passes
flaguée (candidat-leçon). FAIL-CLOSED : échec = attente + ALERT, jamais
de PASS silencieux. B3 : dette structurée + dédupliquée.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json
from serge.policy import PolicyError

REVIEW_SYSTEM = """Tu reviewes un livrable contre sa spec (français). Tu as le code, des captures desktop+mobile et un log d'interaction sandboxée.
Réponds UNIQUEMENT un objet JSON : {"verdict": "...", "fix_items": [{"fichier": "...", "ligne": "...", "probleme": "...", "suggestion": "..."}], "reserves": ["..."], "dette": ["..."], "justification": "..."}.
Verdicts : passes 1-2 = PASS (conforme) | FIX (≤ 5 items localisés) | REBUILD (reprendre) ; passe 3 = SHIP | REBUILD uniquement + dette explicite. Sois concret et localisé."""

DEBT_SYSTEM = """Tu structures une dette technique de build (français).
Réponds UNIQUEMENT un objet JSON : {"dettes": [{"titre": "...", "localisation": "...", "gravite": "basse|moyenne|haute", "suggestion": "..."}]}.
Une entrée par réserve/dette fournie, sans doublon, sans invention."""

EARLY_VERDICTS = frozenset({'PASS', 'FIX', 'REBUILD'})
GATE3_VERDICTS = frozenset({'SHIP', 'REBUILD'})


def _valid_review(data: dict[str, Any], passe: int, fix_max: int) -> bool:
    allowed = GATE3_VERDICTS if passe >= 3 else EARLY_VERDICTS
    if data.get('verdict') not in allowed:
        return False
    items = data.get('fix_items')
    if not isinstance(items, list) or len(items) > fix_max:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if not item.get('fichier') or not item.get('probleme'):
            return False
    if not isinstance(data.get('reserves'), list):
        return False
    if not isinstance(data.get('dette'), list):
        return False
    if passe >= 3 and data['verdict'] == 'SHIP' and data['dette']:
        pass
    return isinstance(data.get('justification'), str)


def review_build(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    spec_text: str,
    artifact_text: str,
    *,
    passe: int = 1,
    images: Sequence[str] = (),
    interaction_log: str = '',
    prev_verdicts: Sequence[str] = (),
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """B2 : review multimodale (fail-closed, juge distinct du builder).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (builder.fix_max_items).
        spec_text: Spec + critères (tronqué 1500c).
        artifact_text: Code/HTML (tronqué 4000c).
        passe: N° de passe (1/2/3, 3 = binaire).
        images: Captures (URLs ou data-URLs, multimodal).
        interaction_log: Session sandboxée (tronqué 1500c).
        prev_verdicts: Verdicts passes précédentes (contradictions).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict verdict/fix_items/reserves/dette/contradiction/action/alert.
    """
    try:
        fix_max = int((policy.get('builder') or {}).get('fix_max_items', 5))
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.builder.fix_max_items invalide') from exc
    passe = max(1, min(3, int(passe)))

    def _attente(reason: str) -> dict[str, Any]:
        return {
            'verdict': None,
            'fix_items': [],
            'reserves': [],
            'dette': [],
            'contradiction': False,
            'action': 'attente',
            'alert': True,
            'reason': reason,
            'fallback': reason,
        }

    user_blocks: list[dict[str, Any]] = [
        {
            'type': 'text',
            'text': (
                f'Spec : {spec_text[:1500]}'
                f'\nPasse : {passe}/3'
                + (
                    ' (BINAIRE : SHIP ou REBUILD + dette)'
                    if passe >= 3
                    else ''
                )
                + f'\nLivrable : {artifact_text[:4000]}'
                f'\nInteraction sandbox : {interaction_log[:1500]}'
            ),
        }
    ]
    for image in images:
        user_blocks.append({'type': 'image_url', 'image_url': {'url': image}})
    messages = [
        {'role': 'system', 'content': REVIEW_SYSTEM},
        {'role': 'user', 'content': user_blocks},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 1500}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'review_build',
        messages,
        lambda obj: _valid_review(obj, passe, fix_max),
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return _attente(reason or 'parse')
    verdict = str(data['verdict'])
    contradiction = (
        bool(prev_verdicts)
        and (
            (prev_verdicts[-1] in {'PASS', 'SHIP'} and verdict == 'REBUILD')
            or (prev_verdicts[-1] == 'REBUILD' and verdict in {'PASS', 'SHIP'})
        )
        and not str(data.get('justification') or '').strip()
    )
    return {
        'verdict': verdict,
        'fix_items': [
            {
                'fichier': str(item.get('fichier') or ''),
                'ligne': str(item.get('ligne') or ''),
                'probleme': str(item.get('probleme') or ''),
                'suggestion': str(item.get('suggestion') or ''),
            }
            for item in data['fix_items']
        ],
        'reserves': [str(item) for item in data['reserves']],
        'dette': [str(item) for item in data['dette']],
        'contradiction': contradiction,
        'action': verdict.lower(),
        'alert': False,
        'reason': '',
        'fallback': '',
    }


def _valid_debt(data: dict[str, Any]) -> bool:
    items = data.get('dettes')
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if not item.get('titre'):
            return False
        if item.get('gravite') not in {'basse', 'moyenne', 'haute'}:
            return False
    return True


def summarize_build_debt(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    verdict_text: str,
    existing_titles: Sequence[str] = (),
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """B3 : dette build structurée (dédupliquée dét, lecture seule).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        verdict_text: Verdict passe 3 + réserves (tronqué 800c).
        existing_titles: Titres déjà connus (anti-doublon).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict dettes/fallback (repli = réserves brutes copiées).
    """
    messages = [
        {'role': 'system', 'content': DEBT_SYSTEM},
        {'role': 'user', 'content': f'Verdict : {verdict_text[:800]}'},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 600}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'summarize_build_debt', messages, _valid_debt, **kwargs
    )
    known = {str(item).strip().lower() for item in existing_titles}
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'dettes': [
                {
                    'titre': verdict_text[:200],
                    'localisation': '',
                    'gravite': 'moyenne',
                    'suggestion': '',
                }
            ],
            'fallback': reason or 'parse',
        }
    dettes = []
    for item in data['dettes']:
        title = str(item.get('titre') or '').strip()
        if not title or title.lower() in known:
            continue
        known.add(title.lower())
        dettes.append(
            {
                'titre': title,
                'localisation': str(item.get('localisation') or ''),
                'gravite': str(item['gravite']),
                'suggestion': str(item.get('suggestion') or ''),
            }
        )
    return {'dettes': dettes, 'fallback': ''}
