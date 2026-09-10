#!/usr/bin/env python3
"""Adaptateurs canaux : contrat can_send/send/poll par canal (B §2.2).

Routage email : SERGE_EMAIL_BACKEND=smtp -> boîte SMTP/IMAP, sinon gog.
Contrat transports : entries [{'id'}], messages avec payload.headers et
snippet (shape normalisée, quel que soit le backend).
"""

from __future__ import annotations

import os
from typing import Any

from serge.channels import email_gog, email_smtp
from serge.channels.email_gog import MailError

__all__ = ['MailError', 'get_message', 'search_emails', 'send_email']


def _backend() -> str:
    """Backend email actif (smtp si demandé, gog par défaut)."""
    if os.environ.get('SERGE_EMAIL_BACKEND', '').strip().lower() == 'smtp':
        return 'smtp'
    return 'gog'


def send_email(*args: Any, **kwargs: Any) -> dict[str, str]:
    """Envoie via le backend actif (voir email_gog/email_smtp).

    Args:
        args: Positionnels du transport (to, subject, body).
        kwargs: Nommés du transport (thread_id, timeout, ...).

    Returns:
        Dict message_id/thread_id du backend actif.
    """
    if _backend() == 'smtp':
        return email_smtp.send_email(*args, **kwargs)
    return email_gog.send_email(*args, **kwargs)


def search_emails(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Recherche via le backend actif (voir email_gog/email_smtp).

    Args:
        args: Positionnels du transport (query).
        kwargs: Nommés du transport (account, max_results, ...).

    Returns:
        Entries [{'id': str}] du backend actif.
    """
    if _backend() == 'smtp':
        return email_smtp.search_emails(*args, **kwargs)
    return email_gog.search_emails(*args, **kwargs)


def get_message(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Lit via le backend actif (voir email_gog/email_smtp).

    Args:
        args: Positionnels du transport (message_id).
        kwargs: Nommés du transport (account, timeout, ...).

    Returns:
        Message normalisé (id, payload.headers, snippet).
    """
    if _backend() == 'smtp':
        return email_smtp.get_message(*args, **kwargs)
    return email_gog.get_message(*args, **kwargs)
