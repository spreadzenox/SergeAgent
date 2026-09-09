#!/usr/bin/env python3
"""Adaptateurs canaux : contrat can_send/send/poll par canal (B §2.2)."""

from __future__ import annotations

from serge.channels.email_gog import (
    MailError,
    get_message,
    search_emails,
    send_email,
)

__all__ = ['MailError', 'get_message', 'search_emails', 'send_email']
