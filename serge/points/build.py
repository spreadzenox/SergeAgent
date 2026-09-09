#!/usr/bin/env python3
"""Point B1 : build_artifact (LLM-L, T3). Création + scan dét.

Scan : secrets/credentials, trackers non déclarés, URLs hors allowlist,
prix non-spec. Sortie = artifact versionné (jamais prod directe).
Repli : ticket QNA (pas de repli dét pour créer).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json
from serge.points.reply import invented_numbers
from serge.policy import PolicyError

BUILD_SYSTEM = """Tu génères un livrable (landing, doc, script) depuis une spec (français/anglais).
Contraintes dures : jamais de secret/credential (ni réel, ni exemple plausible) ; jamais de PII réelle (données démo) ; prix/montants = spec uniquement ; réseau : uniquement les domaines allowlistés ; trackers : uniquement ceux déclarés.
Réponds UNIQUEMENT un objet JSON : {"files": [{"path": "relatif/sans/..", "content": "..."}], "notes": "..."}."""

SECRET_RE = re.compile(
    r'(?i)(?:api[_-]?key|secret|password|token)\s*[:=]\s*["\']?[A-Za-z0-9+/=_-]{12,}'
)
PRIVATE_KEY_RE = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----')
TRACKER_DOMAINS = (
    'google-analytics.com',
    'googletagmanager.com',
    'facebook.net',
    'hotjar.com',
    'mixpanel.com',
    'segment.io',
    'amplitude.com',
)
URL_RE = re.compile(r'https?://([^/\s"\')]+)')


def scan_forbidden(
    content: str,
    *,
    allowlist: Sequence[str] = (),
    declared_trackers: Sequence[str] = (),
) -> list[str]:
    """Scan dét : secrets, clés, trackers, URLs hors allowlist.

    Args:
        content: Contenu généré.
        allowlist: Domaines réseau autorisés.
        declared_trackers: Trackers déclarés par la spec.

    Returns:
        Liste des hits (vide = propre).
    """
    hits: list[str] = []
    if PRIVATE_KEY_RE.search(content):
        hits.append('private_key')
    for match in SECRET_RE.finditer(content):
        snippet = match.group(0)[:24]
        if 'example' not in snippet.lower() and 'xxx' not in snippet.lower():
            hits.append(f'secret:{snippet}')
            break
    lowered = content.lower()
    for tracker in TRACKER_DOMAINS:
        if tracker in lowered and tracker not in declared_trackers:
            hits.append(f'tracker:{tracker}')
    allowed = {item.lower() for item in allowlist} | set(declared_trackers)
    for host in set(URL_RE.findall(content)):
        clean = host.lower().split(':')[0]
        if clean and not any(
            clean == item or clean.endswith(f'.{item}') for item in allowed
        ):
            hits.append(f'url:{clean}')
    return hits


def _valid_build(data: dict[str, Any], max_files: int, max_chars: int) -> bool:
    files = data.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= max_files:
        return False
    total = 0
    for item in files:
        if not isinstance(item, dict):
            return False
        path = item.get('path')
        content = item.get('content')
        if not isinstance(path, str) or not isinstance(content, str):
            return False
        if not path or path.startswith('/') or '..' in path.split('/'):
            return False
        if not content.strip():
            return False
        total += len(content)
    if total > max_chars:
        return False
    return isinstance(data.get('notes'), str)


def build_artifact(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    spec_text: str,
    constraints_text: str,
    *,
    prev_text: str = '',
    allowlist: Sequence[str] = (),
    declared_trackers: Sequence[str] = (),
    spec_prices: str = '',
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """B1 : génère un artifact (scan dét, versionné par l'appelant).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (builder.artifact_max_files/chars).
        spec_text: Spec complète (tronquée 1500c).
        constraints_text: Stack, interdictions, perf (tronqué 800c).
        prev_text: Version précédente si itération (tronquée 1000c).
        allowlist: Domaines réseau autorisés.
        declared_trackers: Trackers déclarés.
        spec_prices: Montants spec (source chiffres).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict files/notes/action (propose|qna)/reason/fallback.
    """
    section = policy.get('builder') or {}
    try:
        max_files = int(section.get('artifact_max_files', 20))
        max_chars = int(section.get('artifact_max_chars', 200000))
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.builder.artifact bornes invalides') from exc
    messages = [
        {'role': 'system', 'content': BUILD_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'Spec : {spec_text[:1500]}'
                f'\nContraintes : {constraints_text[:800]}'
                f'\nVersion précédente : {prev_text[:1000]}'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 4000}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'build_artifact',
        messages,
        lambda obj: _valid_build(obj, max_files, max_chars),
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'files': [],
            'notes': '',
            'action': 'qna',
            'reason': reason or 'parse',
            'fallback': reason or 'parse',
        }
    files = [
        {'path': str(item['path']), 'content': str(item['content'])}
        for item in data['files']
    ]
    for item in files:
        hits = scan_forbidden(
            item['content'],
            allowlist=allowlist,
            declared_trackers=declared_trackers,
        )
        if hits:
            return {
                'files': [],
                'notes': '',
                'action': 'qna',
                'reason': f'scan:{item["path"]}:{hits[0]}',
                'fallback': f'scan:{hits[0]}',
            }
        visible = re.sub(r'<[^>]+>', ' ', item['content'])
        suspects = invented_numbers(visible, spec_prices)
        if suspects and spec_prices:
            return {
                'files': [],
                'notes': '',
                'action': 'qna',
                'reason': f'nombres:{item["path"]}:{",".join(suspects[:3])}',
                'fallback': 'nombres',
            }
    return {
        'files': files,
        'notes': str(data.get('notes') or ''),
        'action': 'propose',
        'reason': '',
        'fallback': '',
    }
