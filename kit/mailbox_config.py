#!/usr/bin/env python3
"""Mailbox SMTP/IMAP : presets + résolution (source unique, kit + runtime)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PRESETS = {
    'infomaniak': {
        'smtp_host': 'mail.infomaniak.com',
        'smtp_port': 587,
        'imap_host': 'mail.infomaniak.com',
        'imap_port': 993,
    },
    'gmail': {
        'smtp_host': 'smtp.gmail.com',
        'smtp_port': 587,
        'imap_host': 'imap.gmail.com',
        'imap_port': 993,
    },
    'fastmail': {
        'smtp_host': 'smtp.fastmail.com',
        'smtp_port': 587,
        'imap_host': 'imap.fastmail.com',
        'imap_port': 993,
    },
}
DEFAULT_PRESET = 'infomaniak'

MAILBOX_DEFAULTS = {
    'preset': 'infomaniak',
    'login': '',
    'smtp_host': '',
    'smtp_port': 587,
    'imap_host': '',
    'imap_port': 993,
}


class MailboxError(ValueError):
    pass


def _port(value: Any, field: str) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise MailboxError(f'mailbox.{field} doit être un port') from None
    if not 1 <= port <= 65535:
        raise MailboxError(f'mailbox.{field} doit être un port')
    return port


def resolve_mailbox(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Résout preset + overrides -> config complète validée.

    Args:
        raw: Dict {preset, login, smtp_host?, smtp_port?, imap_host?,
            imap_port?}. Custom exige les hosts (ports défaut 587/993).

    Returns:
        Dict {login, smtp_host, smtp_port, smtp_ssl, imap_host,
        imap_port, imap_ssl}. SSL implicite sur 465/993, STARTTLS
        explicite ailleurs.

    Raises:
        MailboxError: Preset inconnu, login vide, custom incomplet,
            port invalide.
    """
    preset = str(raw.get('preset') or DEFAULT_PRESET).strip().lower()
    if preset != 'custom' and preset not in PRESETS:
        raise MailboxError(f'mailbox.preset inconnu : {preset}')
    base = PRESETS.get(preset, {})
    login = str(raw.get('login') or '').strip()
    if not login:
        raise MailboxError('mailbox.login requis')
    smtp_host = str(raw.get('smtp_host') or base.get('smtp_host') or '')
    smtp_host = smtp_host.strip()
    imap_host = str(raw.get('imap_host') or base.get('imap_host') or '')
    imap_host = imap_host.strip()
    if not smtp_host or not imap_host:
        raise MailboxError('mailbox custom exige smtp_host + imap_host')
    smtp_port = _port(
        raw.get('smtp_port', base.get('smtp_port', 587)), 'smtp_port'
    )
    imap_port = _port(
        raw.get('imap_port', base.get('imap_port', 993)), 'imap_port'
    )
    return {
        'login': login,
        'smtp_host': smtp_host,
        'smtp_port': smtp_port,
        'smtp_ssl': smtp_port == 465,
        'imap_host': imap_host,
        'imap_port': imap_port,
        'imap_ssl': imap_port == 993,
    }


def merge_mailbox(base: Mapping[str, Any], incoming: Any) -> dict[str, Any]:
    """Fusionne la section [mailbox] (brut, validé par resolve en aval).

    Args:
        base: Défauts (MAILBOX_DEFAULTS).
        incoming: Section entrante (partielle admise).

    Returns:
        Dict fusionné (nouvel objet, base non mutée).
    """
    merged = dict(base)
    merged.update(dict(incoming or {}))
    return merged


def mailbox_toml_lines(mailbox: Mapping[str, Any], quote: Any) -> list[str]:
    """Lignes TOML [mailbox] (section déjà validée par resolve).

    Args:
        mailbox: Section normalisée (preset/login/hosts/ports).
        quote: Fonction str -> littéral TOML (ex. _toml_str du wizard).

    Returns:
        Lignes '[mailbox]' + 6 champs + vide.
    """
    box = mailbox or {}
    return [
        '[mailbox]',
        f'preset = {quote(str(box.get("preset") or "infomaniak"))}',
        f'login = {quote(str(box.get("login") or ""))}',
        f'smtp_host = {quote(str(box.get("smtp_host") or ""))}',
        f'smtp_port = {int(box.get("smtp_port") or 587)}',
        f'imap_host = {quote(str(box.get("imap_host") or ""))}',
        f'imap_port = {int(box.get("imap_port") or 993)}',
        '',
    ]
