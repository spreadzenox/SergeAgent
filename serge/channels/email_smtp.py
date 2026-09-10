#!/usr/bin/env python3
"""Transport email SMTP/IMAP (boîte de confiance) : send + search + get.

Même contrat que email_gog (entries id, messages payload/snippet) : adaptateur
IMAP vers la shape normalisée. Config injectable (tests) ou lue de l'instance
(TOML [mailbox] + secret). Erreurs MailError partagées (AUTH/NETWORK/API).
"""

from __future__ import annotations

import email
import email.policy
import imaplib
import os
import re
import smtplib
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path
from typing import Any

from kit.mailbox_config import MailboxError, resolve_mailbox
from serge.channels.email_gog import MailError
from serge.paths import config_root
from serge.secrets import read_secret_file

_UID_RE = re.compile(rb'UID (\d+)')
_IMAP_MONTHS = (
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
)


def _instance_config() -> dict[str, Any]:
    """Config mailbox de l'instance (TOML + secret).

    Raises:
        MailError: Instance absente, section invalide, secret manquant.
    """
    from kit.instance_file import InstanceError, load_toml

    raw_path = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    if not raw_path:
        raise MailError('API: SERGE_INSTANCE_FILE requise (mailbox)')
    try:
        data = load_toml(Path(raw_path))
    except InstanceError as exc:
        raise MailError(f'API: instance illisible ({exc})') from exc
    section = data.get('mailbox')
    try:
        resolved = resolve_mailbox(
            section if isinstance(section, dict) else {}
        )
    except MailboxError as exc:
        raise MailError(f'API: {exc}') from exc
    password = read_secret_file(config_root() / 'secrets/mailbox-password')
    if not password:
        raise MailError('API: secret mailbox-password manquant')
    return {**resolved, 'password': password}


def _imap_error(exc: Exception) -> str:
    lowered = str(exc).lower()
    if 'auth' in lowered or 'login' in lowered or 'credential' in lowered:
        return f'AUTH: imap refusé ({exc})'
    return f'NETWORK: imap ({exc})'


def _open_imap(cfg: Mapping[str, Any], timeout: float) -> imaplib.IMAP4:
    if cfg['imap_ssl']:
        box: imaplib.IMAP4 = imaplib.IMAP4_SSL(
            str(cfg['imap_host']), int(cfg['imap_port']), timeout=timeout
        )
    else:
        box = imaplib.IMAP4(
            str(cfg['imap_host']), int(cfg['imap_port']), timeout=timeout
        )
        box.starttls()
    try:
        box.login(str(cfg['login']), str(cfg['password']))
    except imaplib.IMAP4.error as exc:
        raise MailError(_imap_error(exc)) from exc
    return box


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    account: str = 'auto',
    thread_id: str = '',
    timeout: float = 60.0,
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Envoie un email via SMTP (idempotence gérée par l'appelant/touch).

    Args:
        to: Destinataire.
        subject: Sujet (requis).
        body: Corps texte.
        account: Ignoré (compat gog).
        thread_id: Parent (mis en In-Reply-To/References si fourni).
        timeout: Timeout secondes.
        config: Config résolue + password (défaut : instance).

    Returns:
        Dict message_id/thread_id.

    Raises:
        MailError: AUTH/NETWORK/API, sujet/destinataire vide.
    """
    _ = account
    if not to.strip() or not subject.strip() or not body.strip():
        raise MailError('API: destinataire/sujet/corps requis')
    cfg = config if config is not None else _instance_config()
    msg = EmailMessage()
    msg['From'] = str(cfg['login'])
    msg['To'] = to
    msg['Subject'] = subject
    if thread_id.strip():
        msg['In-Reply-To'] = thread_id.strip()
        msg['References'] = thread_id.strip()
    msg['Message-ID'] = make_msgid()
    msg.set_content(body)
    try:
        if cfg['smtp_ssl']:
            server = smtplib.SMTP_SSL(
                str(cfg['smtp_host']), int(cfg['smtp_port']), timeout=timeout
            )
        else:
            server = smtplib.SMTP(
                str(cfg['smtp_host']), int(cfg['smtp_port']), timeout=timeout
            )
            server.starttls()
        with server:
            server.login(str(cfg['login']), str(cfg['password']))
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(f'AUTH: smtp refusé ({exc.smtp_code})') from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f'NETWORK: smtp ({exc})') from exc
    return {'message_id': str(msg['Message-ID'] or ''), 'thread_id': thread_id}


def _imap_criteria(query: str) -> list[str]:
    """Traduit le sous-ensemble Gmail supporté (newer_than/from/-in:sent).

    Raises:
        MailError: Token de requête non supporté (ou non-ASCII).
    """
    criteria = ['UNSEEN']
    for token in query.split():
        if not token.isascii():
            raise MailError(f'API: requete_non_supportee ({token})')
        if token == '-in:sent':
            continue  # INBOX seule par construction
        if token.startswith('newer_than:'):
            span = token[len('newer_than:') :]
            if span.endswith('d') and span[:-1].isdigit():
                when = datetime.now(UTC) - timedelta(days=int(span[:-1]))
                stamp = f'{when.day:02d}-{_IMAP_MONTHS[when.month - 1]}-{when.year}'
                criteria += ['SINCE', stamp]
                continue
            raise MailError(f'API: requete_non_supportee ({token})')
        if token.startswith('from:') and len(token) > 5:
            criteria += ['FROM', f'"{token[5:]}"']
            continue
        raise MailError(f'API: requete_non_supportee ({token})')
    return criteria


def _header_mid(raw: bytes) -> str:
    try:
        parsed = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception:
        return ''
    return str(parsed.get('Message-ID') or '').strip()


def _entry_ids(fetched: list[Any]) -> list[str]:
    entries = []
    for item in fetched:
        if not isinstance(item, tuple) or len(item) != 2:
            continue
        meta, payload = item
        raw = payload if isinstance(payload, bytes) else b''
        match = _UID_RE.search(bytes(meta))
        if match:
            fallback = f'uid:{match.group(1).decode()}'
        else:
            fallback = f'uid:{bytes(meta).split(b" ")[0].decode()}'
        entries.append(_header_mid(raw) or fallback)
    return entries


def search_emails(
    query: str,
    *,
    account: str = 'auto',
    max_results: int = 20,
    timeout: float = 60.0,
    config: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Recherche IMAP (UNSEEN récents, sous-ensemble Gmail traduit).

    Args:
        query: Requête (newer_than:Nd, from:X, -in:sent supportés).
        account: Ignoré (compat gog).
        max_results: Cap (les plus récents).
        timeout: Timeout secondes.
        config: Config résolue + password (défaut : instance).

    Returns:
        Entries [{'id': Message-ID (ou uid:N)}].

    Raises:
        MailError: AUTH/NETWORK/API (requête non supportée).
    """
    _ = account
    cfg = config if config is not None else _instance_config()
    criteria = _imap_criteria(query)
    try:
        box = _open_imap(cfg, timeout)
        with box:
            status, _ = box.select('INBOX', readonly=True)
            if status != 'OK':
                raise MailError('API: imap select refusé')
            status, data = box.uid('search', 'CHARSET', 'US-ASCII', *criteria)
            if status != 'OK':
                raise MailError('API: imap search refusé')
            uids = [
                item for item in (data[0] or b'').split() if item.isdigit()
            ]
            wanted = (
                sorted(uids, key=int)[-max_results:] if max_results > 0 else []
            )
            if not wanted:
                return []
            status, fetched = box.uid(
                'fetch',
                ','.join(item.decode() for item in wanted),
                '(UID BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])',
            )
            if status != 'OK':
                raise MailError('API: imap fetch refusé')
            return [{'id': mid} for mid in _entry_ids(list(fetched or []))]
    except imaplib.IMAP4.error as exc:
        raise MailError(_imap_error(exc)) from exc
    except OSError as exc:
        raise MailError(f'NETWORK: imap ({exc})') from exc


def _message_text(parsed: EmailMessage) -> str:
    if parsed.is_multipart():
        for part in parsed.walk():
            if part.is_multipart() or part.get_content_disposition():
                continue
            if part.get_content_type() != 'text/plain':
                continue
            try:
                return str(part.get_content()).strip()
            except (ValueError, LookupError):
                return ''
        return ''
    if parsed.get_content_type() != 'text/plain':
        return ''
    try:
        return str(parsed.get_content()).strip()
    except (ValueError, LookupError):
        return ''


def get_message(
    message_id: str,
    *,
    account: str = 'auto',
    timeout: float = 60.0,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lit un message IMAP (shape normalisée payload/snippet).

    Args:
        message_id: Message-ID (ou uid:N).
        account: Ignoré (compat gog).
        timeout: Timeout secondes.
        config: Config résolue + password (défaut : instance).

    Returns:
        Dict {id, payload: {headers: [{name, value}]}, snippet}.

    Raises:
        MailError: AUTH/NETWORK/API (introuvable, illisible).
    """
    _ = account
    cfg = config if config is not None else _instance_config()
    try:
        box = _open_imap(cfg, timeout)
        with box:
            status, _ = box.select('INBOX', readonly=True)
            if status != 'OK':
                raise MailError('API: imap select refusé')
            if message_id.startswith('uid:') and message_id[4:].isdigit():
                target = message_id[4:]
            elif not message_id.isascii():
                raise MailError('API: message introuvable')
            else:
                _status, found = box.uid(
                    'search',
                    'CHARSET',
                    'US-ASCII',
                    'HEADER',
                    'Message-ID',
                    message_id,
                )
                uids = (found[0] if found else b'').split()
                if not uids:
                    raise MailError('API: message introuvable')
                target = uids[-1].decode()
            status, fetched = box.uid('fetch', target, '(RFC822)')
            if status != 'OK':
                raise MailError('API: imap fetch refusé')
            raw = b''
            for item in fetched or []:
                if isinstance(item, tuple) and isinstance(item[1], bytes):
                    raw = item[1]
                    break
            if not raw:
                raise MailError('API: message illisible')
            try:
                parsed: EmailMessage = email.message_from_bytes(
                    raw, policy=email.policy.default
                )
            except Exception as exc:
                raise MailError('API: message illisible') from exc
            text = _message_text(parsed)
            headers = [
                {'name': name, 'value': str(parsed.get(name) or '')}
                for name in ('From', 'Subject', 'Date', 'Message-ID')
            ]
            return {
                'id': message_id,
                'payload': {'headers': headers},
                'snippet': text[:500],
            }
    except imaplib.IMAP4.error as exc:
        raise MailError(_imap_error(exc)) from exc
    except OSError as exc:
        raise MailError(f'NETWORK: imap ({exc})') from exc
