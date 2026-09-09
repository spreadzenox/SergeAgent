#!/usr/bin/env python3
"""Transport email via gog CLI (Gmail API) : send + search + get.

Binaire + compte injectables (tests mockés). Sorties JSON parsées.
Erreurs typées MailError (BIN/AUTH/API/NETWORK). Secrets jamais logués.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any

DEFAULT_GOG_BIN = '/usr/local/bin/gog'


class MailError(ValueError):
    pass


def _gog_bin(override: str = '') -> str:
    if override:
        return override
    return os.environ.get('SERGE_GOG_BIN', DEFAULT_GOG_BIN)


def _run(
    args: list[str], gog_bin: str = '', timeout: float = 60.0
) -> dict[str, Any]:
    binary = _gog_bin(gog_bin)
    try:
        completed = subprocess.run(
            [binary, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise MailError(f'BIN: gog introuvable ({binary})') from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MailError(f'NETWORK: gog ({exc})') from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout)[-300:]
        lowered = detail.lower()
        if 'auth' in lowered or 'permission' in lowered or '401' in lowered:
            raise MailError(f'AUTH: gog refusé ({detail.strip()})')
        raise MailError(f'API: gog a échoué ({detail.strip()})')
    try:
        payload = json.loads(completed.stdout or '{}')
    except json.JSONDecodeError as exc:
        raise MailError('API: gog JSON illisible') from exc
    if not isinstance(payload, dict):
        raise MailError('API: gog réponse non-objet')
    return payload


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    account: str = 'auto',
    thread_id: str = '',
    gog_bin: str = '',
    timeout: float = 60.0,
) -> dict[str, str]:
    """Envoie un email (idempotence gérée par l'appelant/touch).

    Args:
        to: Destinataire.
        subject: Sujet (requis).
        body: Corps texte.
        account: Compte gog (défaut auto).
        thread_id: Thread de réponse ('' = nouveau).
        gog_bin: Binaire (défaut : standard).
        timeout: Timeout secondes.

    Returns:
        Dict message_id/thread_id ('' si absent).

    Raises:
        MailError: BIN/AUTH/API/NETWORK, sujet/destinataire vide.
    """
    if not to.strip() or not subject.strip() or not body.strip():
        raise MailError('API: destinataire/sujet/corps requis')
    args = [
        'gmail',
        'send',
        '--json',
        '--no-input',
        '-a',
        account,
        '--to',
        to,
        '--subject',
        subject,
        '--body',
        body,
    ]
    if thread_id:
        args += ['--thread-id', thread_id]
    payload = _run(args, gog_bin, timeout)
    nested = payload.get('result')
    result: dict[str, Any] = nested if isinstance(nested, dict) else payload
    return {
        'message_id': str(result.get('id') or result.get('messageId') or ''),
        'thread_id': str(result.get('threadId') or thread_id),
    }


def search_emails(
    query: str,
    *,
    account: str = 'auto',
    max_results: int = 20,
    gog_bin: str = '',
    timeout: float = 60.0,
) -> list[dict[str, Any]]:
    """Recherche Gmail (syntaxe Gmail, ex. newer_than:1d -in:sent).

    Args:
        query: Requête Gmail.
        account: Compte gog.
        max_results: Cap résultats.
        gog_bin: Binaire.
        timeout: Timeout.

    Returns:
        Messages [{id, threadId, ...}] (vide si aucun).

    Raises:
        MailError: BIN/AUTH/API/NETWORK.
    """
    payload = _run(
        ['gmail', 'search', query, '--json', '--no-input', '-a', account],
        gog_bin,
        timeout,
    )
    items = payload.get('messages') or payload.get('results') or []
    if not isinstance(items, list):
        return []
    return [
        item for item in items[: max(1, max_results)] if isinstance(item, dict)
    ]


def get_message(
    message_id: str,
    *,
    account: str = 'auto',
    gog_bin: str = '',
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Lit un message complet (corps + headers).

    Args:
        message_id: Id Gmail.
        account: Compte gog.
        gog_bin: Binaire.
        timeout: Timeout.

    Returns:
        Objet message brut (snippet, payload...).

    Raises:
        MailError: BIN/AUTH/API/NETWORK.
    """
    return _run(
        ['gmail', 'get', message_id, '--json', '--no-input', '-a', account],
        gog_bin,
        timeout,
    )
