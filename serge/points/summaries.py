#!/usr/bin/env python3
"""Points lecture seule (LLM-R, T1) : summarize_thread + score_call.

Aucun état modifié (metering seul). Replis : brut tronqué (thread),
pas de score (appel → file chronologique).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json

THREAD_SYSTEM = """Tu résumes une conversation commerciale (français).
Réponds UNIQUEMENT un objet JSON : {"resume": "...", "statut": "ouvert|en_attente|clos", "next_step": "..."}.
resume = 3-6 phrases (faits, objections, accords). PII : anonymise (prénom + initiale)."""

SCORE_SYSTEM = """Tu notes un appel commercial transcrit (français), 1 à 5 :
5 = excellent (écoute, objections traitées, next step clair) ; 4 = bon ; 3 = moyen ; 2 = faible (dérive, agressivité, promesse douteuse) ; 1 = raté.
Réponds UNIQUEMENT un objet JSON : {"note": 1-5, "flags": ["..."], "ecouter": true|false}.
flags parmi : derive, agressivite, promesse_douteuse, prix_non_catalogue, objection_non_traitee, conclusion_floue. ecouter = true si note ≤ 2 ou promesse_douteuse."""

FLAGS = frozenset(
    {
        'derive',
        'agressivite',
        'promesse_douteuse',
        'prix_non_catalogue',
        'objection_non_traitee',
        'conclusion_floue',
    }
)
MAX_THREAD_CHARS = 5000
MAX_TRANSCRIPT_CHARS = 3000


def _valid_thread(data: dict[str, Any]) -> bool:
    if not isinstance(data.get('resume'), str) or not data['resume'].strip():
        return False
    if data.get('statut') not in {'ouvert', 'en_attente', 'clos'}:
        return False
    return isinstance(data.get('next_step'), str)


def summarize_thread(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    history_text: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P6/O5 : résume un thread (régénérable, lecture seule).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        history_text: Historique (borné 5000c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict resume/statut/next_step/fallback (repli = brut tronqué).
    """
    bounded = history_text[-MAX_THREAD_CHARS:]
    messages = [
        {'role': 'system', 'content': THREAD_SYSTEM},
        {'role': 'user', 'content': bounded},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 800}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'summarize_thread', messages, _valid_thread, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'resume': bounded[-1500:],
            'statut': 'ouvert',
            'next_step': '',
            'fallback': reason or 'parse',
        }
    return {
        'resume': str(data['resume']),
        'statut': str(data['statut']),
        'next_step': str(data.get('next_step') or ''),
        'fallback': '',
    }


def _valid_score(data: dict[str, Any]) -> bool:
    note = data.get('note')
    if isinstance(note, bool) or not isinstance(note, int):
        return False
    if note not in {1, 2, 3, 4, 5}:
        return False
    flags = data.get('flags')
    if not isinstance(flags, list) or any(item not in FLAGS for item in flags):
        return False
    return isinstance(data.get('ecouter'), bool)


def score_call(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    transcript: str,
    metadata_text: str = '',
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Scoring post-appel F4b (note 1-5 + flags → file écoute).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        transcript: Transcription (bornée 3000c).
        metadata_text: Durée, direction, DTMF... (court).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict note/flags/ecouter/fallback (repli = pas de score).
    """
    bounded = transcript[:MAX_TRANSCRIPT_CHARS]
    user = f'Métadonnées : {metadata_text[:400]}\nTranscription : {bounded}'
    messages = [
        {'role': 'system', 'content': SCORE_SYSTEM},
        {'role': 'user', 'content': user},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 300}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'score_call', messages, _valid_score, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'note': None,
            'flags': [],
            'ecouter': False,
            'fallback': reason or 'parse',
        }
    return {
        'note': int(data['note']),
        'flags': [str(item) for item in data['flags']],
        'ecouter': bool(data['ecouter']),
        'fallback': '',
    }
