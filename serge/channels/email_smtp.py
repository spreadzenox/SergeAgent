#!/usr/bin/env python3
"""L'e-mail par une boîte SMTP/IMAP (Infomaniak, Fastmail…), sans OAuth.

Trois fonctions, celles de tout canal (``serge/channels/base.py``) :

- ``send`` envoie par SMTP, avec un ``Message-ID`` tiré du numéro de
  l'envoi (``<serge.tou_3f2a@exemple.fr>``), puis en range une copie dans
  le dossier des messages envoyés : le serveur SMTP ne le fait pas ;
- ``confirm`` cherche ce ``Message-ID`` dans les messages envoyés ;
- ``poll`` lit la boîte de réception depuis la dernière relève.

La boîte est celle du fichier d'instance (``[mailbox]``) et son mot de
passe le secret ``mailbox-password``. TLS est toujours vérifié. Les
erreurs sont des ``MailError`` (AUTH, NETWORK, API).
"""

from __future__ import annotations

import email.policy
import imaplib
import os
import re
import smtplib
import time
from collections.abc import Mapping
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate, parseaddr
from pathlib import Path
from typing import Any

from kit.mailbox_config import MailboxError, resolve_mailbox
from serge.channels.base import Incoming, Outgoing
from serge.channels.email_gog import POLL_MAX, MailError
from serge.paths import config_root
from serge.secrets import read_secret_file

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
_REF = re.compile(r'<[^<>\s]+>')
# Le dossier des envois quand le serveur ne le signale pas (\Sent).
SENT_FALLBACK = 'Sent'


def instance_config() -> dict[str, Any]:
    """La boîte de l'instance (fichier d'instance + secret).

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
    password_value = read_secret_file(
        config_root() / 'secrets/mailbox-password'
    )
    if not password_value:
        raise MailError('API: secret mailbox-password manquant')
    return {**resolved, 'password': password_value}


def _imap_error(exc: Exception) -> str:
    lowered = str(exc).lower()
    if 'auth' in lowered or 'login' in lowered or 'credential' in lowered:
        return f'AUTH: imap refusé ({exc})'
    return f'NETWORK: imap ({exc})'


def _open_imap(cfg: Mapping[str, Any], timeout: float = 60.0) -> imaplib.IMAP4:
    try:
        if cfg['imap_ssl']:
            box: imaplib.IMAP4 = imaplib.IMAP4_SSL(
                str(cfg['imap_host']), int(cfg['imap_port']), timeout=timeout
            )
        else:
            box = imaplib.IMAP4(
                str(cfg['imap_host']), int(cfg['imap_port']), timeout=timeout
            )
            box.starttls()
        box.login(str(cfg['login']), str(cfg['password']))
    except imaplib.IMAP4.error as exc:
        raise MailError(_imap_error(exc)) from exc
    except OSError as exc:
        raise MailError(f'NETWORK: imap ({exc})') from exc
    return box


def _sent_folder(box: imaplib.IMAP4) -> str:
    """Le dossier des messages envoyés, tel que le serveur le signale."""
    _status, folders = box.list()
    for line in folders or []:
        text = line.decode(errors='replace') if isinstance(line, bytes) else ''
        if '\\Sent' in text:
            return text.rsplit(' ', 1)[-1].strip('"')
    return SENT_FALLBACK


def message_id(cfg: Mapping[str, Any], touch_id: str) -> str:
    """Le ``Message-ID`` d'un envoi, tiré de son numéro."""
    domain = str(cfg['login']).rpartition('@')[2] or 'serge.local'
    return f'<serge.{touch_id}@{domain}>'


def _smtp_send(cfg: Mapping[str, Any], msg: EmailMessage) -> None:
    try:
        if cfg['smtp_ssl']:
            server = smtplib.SMTP_SSL(
                str(cfg['smtp_host']), int(cfg['smtp_port']), timeout=60
            )
        else:
            server = smtplib.SMTP(
                str(cfg['smtp_host']), int(cfg['smtp_port']), timeout=60
            )
            server.starttls()
        with server:
            server.login(str(cfg['login']), str(cfg['password']))
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(f'AUTH: smtp refusé ({exc.smtp_code})') from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError(f'API: destinataire refusé ({exc})') from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f'NETWORK: smtp ({exc})') from exc


def send(message: Outgoing, config: dict[str, Any] | None = None) -> str:
    """Envoie un e-mail ; rend son ``Message-ID``."""
    cfg = config if config is not None else instance_config()
    msg = EmailMessage()
    msg['From'] = str(cfg['login'])
    msg['To'] = message.address
    msg['Subject'] = message.subject
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = message_id(cfg, message.touch_id)
    if message.in_reply_to:
        msg['In-Reply-To'] = message.in_reply_to
        msg['References'] = message.in_reply_to
    msg.set_content(message.body)
    _smtp_send(cfg, msg)
    # Le message est parti : ranger sa copie ne doit jamais faire croire le
    # contraire. Sans copie, un envoi interrompu juste ici serait refait.
    try:
        box = _open_imap(cfg)
        with box:
            box.append(
                _sent_folder(box),
                '\\Seen',
                imaplib.Time2Internaldate(time.time()),
                msg.as_bytes(),
            )
    except (MailError, imaplib.IMAP4.error, OSError):
        pass
    return str(msg['Message-ID'])


def confirm(message: Outgoing, config: dict[str, Any] | None = None) -> str:
    """Le ``Message-ID`` de l'envoi s'il est parti, sinon ``''``."""
    cfg = config if config is not None else instance_config()
    wanted = message_id(cfg, message.touch_id)
    box = _open_imap(cfg)
    try:
        with box:
            status, _ = box.select(_sent_folder(box), readonly=True)
            if status != 'OK':
                return ''
            _status, found = box.uid(
                'search', 'CHARSET', 'US-ASCII', 'HEADER', 'Message-ID', wanted
            )
    except imaplib.IMAP4.error as exc:
        raise MailError(_imap_error(exc)) from exc
    return wanted if found and (found[0] or b'').split() else ''


def _text(parsed: EmailMessage) -> str:
    part = parsed.get_body(preferencelist=('plain',))
    if part is None:
        return ''
    try:
        return str(part.get_content()).strip()
    except (ValueError, LookupError):
        return ''


def _since(since: str) -> str:
    """La date IMAP (jour) de la relève : la veille de ``since``, pour ne
    rien perdre d'un fuseau à l'autre."""
    start = (
        datetime.fromisoformat(since) if since else datetime.now()
    ) - timedelta(days=1)
    return f'{start.day:02d}-{_IMAP_MONTHS[start.month - 1]}-{start.year}'


def poll(since: str, config: dict[str, Any] | None = None) -> list[Incoming]:
    """Les messages reçus depuis ``since`` (ISO), ou depuis un jour.

    IMAP ne cherche qu'au jour près : les messages déjà relevés sont
    écartés par la relève (même ``Message-ID``).
    """
    cfg = config if config is not None else instance_config()
    box = _open_imap(cfg)
    received = []
    try:
        with box:
            status, _ = box.select('INBOX', readonly=True)
            if status != 'OK':
                raise MailError('API: imap select refusé')
            _status, data = box.uid('search', 'SINCE', _since(since))
            uids = sorted(
                (u.decode() for u in (data[0] or b'').split() if u.isdigit()),
                key=int,
            )[-POLL_MAX:]
            for uid in uids:
                _status, fetched = box.uid('fetch', uid, '(RFC822)')
                raw = next(
                    (
                        item[1]
                        for item in fetched or []
                        if isinstance(item, tuple)
                        and isinstance(item[1], bytes)
                    ),
                    b'',
                )
                if not raw:
                    continue
                parsed = BytesParser(policy=email.policy.default).parsebytes(
                    raw
                )
                own = str(parsed.get('Message-ID') or '').strip()
                refs = _REF.findall(
                    f'{parsed.get("In-Reply-To") or ""}'
                    f' {parsed.get("References") or ""}'
                )
                received.append(
                    Incoming(
                        external_ref=own or f'uid:{uid}',
                        address=parseaddr(str(parsed.get('From') or ''))[1],
                        subject=str(parsed.get('Subject') or ''),
                        body=_text(parsed),
                        message_ref=own,
                        refs=tuple(refs),
                        native_type='email',
                    )
                )
    except imaplib.IMAP4.error as exc:
        raise MailError(_imap_error(exc)) from exc
    except OSError as exc:
        raise MailError(f'NETWORK: imap ({exc})') from exc
    return received
