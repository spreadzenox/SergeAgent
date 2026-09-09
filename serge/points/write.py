#!/usr/bin/env python3
"""Points P2/P3 : fill_slots + write_followup (LLM-B, T1/T2) + checkers dét.

Checkers post-génération : longueur, mots interdits, chiffres sourcés,
agressivité (P3). Échec = regen 1× avec feedback, puis template brut.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from serge.points.checkers import (
    check_aggressivity,
    check_forbidden,
    check_length,
)
from serge.points.jsonio import run_json
from serge.points.reply import invented_numbers

FOLLOWUP_GENERIC = (
    'Bonjour, je reviens vers vous au sujet de mon précédent message.'
    ' Dites-moi si le sujet vous intéresse ou si je dois clore le dossier.'
)

SLOTS_SYSTEM = """Tu personnalises un template commercial (français) avec la fiche prospect.
Règles : ton courtois, phrases courtes, aucune promesse non sourcée, aucun prix inventé, pas de markdown.
Réponds UNIQUEMENT un objet JSON : {"text": "...", "slots_used": ["..."]}."""

FOLLOWUP_SYSTEM = """Tu rédiges un message de relance commerciale (français), jamais agressif.
Interdits : culpabilisation, faux ultimatum, menaces, pression ("dernière chance", "sans réponse de votre part...").
Ton : courtois, bref, une porte de sortie ("si le sujet est clos, dites-le moi").
Réponds UNIQUEMENT un objet JSON : {"text": "..."}."""


def _valid_text(data: dict[str, Any]) -> bool:
    text = data.get('text')
    return isinstance(text, str) and bool(text.strip())


def _run_text(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    point_name: str,
    messages: list[dict[str, str]],
    *,
    root: Path | None = None,
    caller: Any = None,
    max_tokens: int = 600,
) -> tuple[str | None, str]:
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': max_tokens}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, point_name, messages, _valid_text, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return None, reason or 'parse'
    return str(data['text']).strip(), ''


def _regen_or_fallback(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    point_name: str,
    messages: list[dict[str, str]],
    defect: str,
    fallback_text: str,
    check: Callable[[str], str],
    fallback_action: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> tuple[str, str, str]:
    """Regen 1× avec feedback, re-vérifiée, sinon template.

    Args:
        check: Chaîne de checkers ('' = propre).
        fallback_action: Action si regen encore fautive.

    Returns:
        Tuple (texte, action, reason).
    """
    retry = [dict(item) for item in messages]
    retry.append(
        {
            'role': 'user',
            'content': f'Défaut détecté : {defect}. Corrige et réponds le JSON seul.',
        }
    )
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 600}
    if caller is not None:
        kwargs['caller'] = caller
    data, _ = run_json(conn, policy, point_name, retry, _valid_text, **kwargs)
    if data is not None:
        fixed = str(data['text']).strip()
        if not check(fixed):
            return fixed, 'send', f'regen:{defect}'
        return fallback_text, fallback_action, f'brut:regen_{check(fixed)}'
    return fallback_text, fallback_action, f'brut:{defect}'


def fill_slots(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    template: str,
    fiche_text: str,
    *,
    forbidden: Sequence[str] = (),
    sources: str = '',
    max_chars: int = 2000,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P2 : personnalise un template (checkers + regen 1× + brut).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        template: Template avec {slots}.
        fiche_text: Fiche prospect (tronquée 600c).
        forbidden: Mots interdits venture.
        sources: Sources chiffres autorisés.
        max_chars: Longueur max.
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict text/action (send|template_brut)/reason/fallback.
    """
    messages = [
        {'role': 'system', 'content': SLOTS_SYSTEM},
        {
            'role': 'user',
            'content': f'Template : {template[:1200]}\nFiche : {fiche_text[:600]}',
        },
    ]

    def _check_slots(candidate: str) -> str:
        flaw = check_length(candidate, max_chars)
        if not flaw:
            bad = check_forbidden(candidate, forbidden)
            if bad:
                flaw = f'interdit:{bad}'
        if not flaw:
            suspects = invented_numbers(
                candidate, f'{sources}\n{fiche_text}\n{template}'
            )
            if suspects:
                flaw = f'nombres:{",".join(suspects[:3])}'
        return flaw

    text, failure = _run_text(
        conn, policy, 'fill_slots', messages, root=root, caller=caller
    )
    if text is None:
        return {
            'text': template,
            'action': 'template_brut',
            'reason': f'fallback:{failure}',
            'fallback': failure,
        }
    defect = _check_slots(text)
    if defect:
        fixed, action, reason = _regen_or_fallback(
            conn,
            policy,
            'fill_slots',
            messages,
            defect,
            template,
            _check_slots,
            'template_brut',
            root=root,
            caller=caller,
        )
        return {
            'text': fixed,
            'action': action,
            'reason': reason,
            'fallback': '' if action == 'send' else failure,
        }
    return {'text': text, 'action': 'send', 'reason': '', 'fallback': ''}


def write_followup(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    history_text: str,
    playbook_text: str = '',
    *,
    forbidden: Sequence[str] = (),
    max_chars: int = 1200,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P3 : relance LLM (checkers + agressivité + générique).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        history_text: Historique ou résumé+K (tronqué 2000c).
        playbook_text: Objections + réponses (tronqué 800c).
        forbidden: Mots interdits venture.
        max_chars: Longueur max.
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict text/action (send|template_generique)/reason/fallback.
    """
    messages = [
        {'role': 'system', 'content': FOLLOWUP_SYSTEM},
        {
            'role': 'user',
            'content': f'Historique : {history_text[:2000]}\nPlaybook : {playbook_text[:800]}',
        },
    ]

    def _check_followup(candidate: str) -> str:
        flaw = check_length(candidate, max_chars)
        if not flaw:
            bad = check_forbidden(candidate, forbidden)
            if bad:
                flaw = f'interdit:{bad}'
        if not flaw:
            aggr = check_aggressivity(candidate)
            if aggr:
                flaw = f'agressif:{aggr}'
        return flaw

    text, failure = _run_text(
        conn,
        policy,
        'write_followup',
        messages,
        root=root,
        caller=caller,
        max_tokens=500,
    )
    if text is None:
        return {
            'text': FOLLOWUP_GENERIC,
            'action': 'template_generique',
            'reason': f'fallback:{failure}',
            'fallback': failure,
        }
    defect = _check_followup(text)
    if defect:
        fixed, action, reason = _regen_or_fallback(
            conn,
            policy,
            'write_followup',
            messages,
            defect,
            FOLLOWUP_GENERIC,
            _check_followup,
            'template_generique',
            root=root,
            caller=caller,
        )
        return {
            'text': fixed,
            'action': action,
            'reason': reason,
            'fallback': '' if action == 'send' else failure,
        }
    return {'text': text, 'action': 'send', 'reason': '', 'fallback': ''}
