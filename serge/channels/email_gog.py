#!/usr/bin/env python3
"""L'e-mail par Gmail, avec l'outil ``gog`` (API Gmail).

Trois fonctions, celles de tout canal (``serge/channels/base.py``) :

- ``send`` envoie par ``gog gmail send`` et rend le ``Message-ID`` du
  message parti, relu dans Gmail : c'est lui qu'une réponse cite. Une
  réponse ou une relance reste dans le fil (``--reply-to-message-id``) ;
- ``confirm`` cherche l'envoi dans les messages envoyés : même
  destinataire, même texte, depuis moins de 2 jours. Gmail choisit
  lui-même le ``Message-ID`` d'un message : on ne peut pas le chercher
  avant de l'avoir envoyé ;
- ``poll`` lit la boîte de réception depuis la dernière relève.

Le binaire est ``SERGE_GOG_BIN``, sinon celui du ``PATH``. Les erreurs sont
des ``MailError`` (BIN, AUTH, API, NETWORK) ; un secret n'est jamais écrit.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from email.utils import parseaddr
from typing import Any

from serge.channels.base import Incoming, Outgoing

DEFAULT_GOG_BIN = '/usr/local/bin/gog'
ACCOUNT = 'auto'
# Ce qu'on lit au plus à chaque relève, et parmi les messages envoyés.
POLL_MAX = 50
SENT_MAX = 20
# La relève relit les 10 dernières minutes : un message arrivé pendant la
# relève précédente n'est jamais perdu (un message déjà relevé est écarté).
OVERLAP_S = 600

_REF = re.compile(r'<[^<>\s]+>')


class MailError(ValueError):
    """Une boîte e-mail a refusé l'opération."""


def _gog_bin() -> str:
    """Binaire gog : ``SERGE_GOG_BIN`` > ``PATH`` > défaut."""
    explicit = os.environ.get('SERGE_GOG_BIN', '').strip()
    if explicit:
        return explicit
    return shutil.which('gog') or DEFAULT_GOG_BIN


def _run(args: list[str], timeout: float = 60.0) -> dict[str, Any]:
    binary = _gog_bin()
    try:
        completed = subprocess.run(
            [binary, *args, '--json', '--no-input', '-a', ACCOUNT],
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


def _search(query: str, limit: int) -> list[str]:
    """Les identifiants Gmail des messages trouvés (syntaxe Gmail)."""
    payload = _run(['gmail', 'search', query, '--max', str(limit)])
    items = payload.get('messages') or payload.get('results') or []
    if not isinstance(items, list):
        return []
    return [
        str(item['id'])
        for item in items[:limit]
        if isinstance(item, dict) and item.get('id')
    ]


def _get(gmail_id: str) -> dict[str, Any]:
    payload = _run(['gmail', 'get', gmail_id])
    nested = payload.get('message')
    return nested if isinstance(nested, dict) else payload


def _headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get('payload')
    headers = payload.get('headers') if isinstance(payload, dict) else None
    found: dict[str, str] = {}
    for item in headers if isinstance(headers, list) else []:
        if isinstance(item, dict) and item.get('name'):
            found[str(item['name']).lower()] = str(item.get('value') or '')
    return found


def _walk_text(node: Any) -> str:
    """Le texte brut d'un message Gmail (parties ``text/plain``)."""
    if not isinstance(node, dict):
        return ''
    body = node.get('body') or {}
    data = body.get('data') if isinstance(body, dict) else None
    if str(node.get('mimeType') or '').startswith('text/plain') and data:
        try:
            padded = str(data) + '=' * (-len(str(data)) % 4)
            return base64.urlsafe_b64decode(padded).decode(
                'utf-8', errors='replace'
            )
        except (ValueError, OSError):
            return ''
    parts = [_walk_text(part) for part in node.get('parts') or []]
    return '\n'.join(p for p in parts if p)


def _text(message: dict[str, Any]) -> str:
    text = _walk_text(message.get('payload'))
    return text.strip() or str(message.get('snippet') or '').strip()


def _gmail_id(message_ref: str) -> str:
    """L'identifiant Gmail d'un message, par son ``Message-ID``."""
    found = _search(f'rfc822msgid:{message_ref.strip("<>")}', 1)
    return found[0] if found else ''


def _same_text(sent: str, written: str) -> bool:
    """Le message parti commence par le texte écrit (Gmail peut couper
    les lignes et ajouter la citation d'un message précédent)."""
    flat = ' '.join(written.split())[:200]
    return bool(flat) and ' '.join(sent.split()).startswith(flat)


def send(message: Outgoing) -> str:
    """Envoie un e-mail ; rend son ``Message-ID``."""
    args = [
        'gmail',
        'send',
        '--to',
        message.address,
        '--subject',
        message.subject,
        '--body',
        message.body,
    ]
    parent = _gmail_id(message.in_reply_to) if message.in_reply_to else ''
    if parent:
        args += ['--reply-to-message-id', parent]
    payload = _run(args)
    nested = payload.get('result')
    result: dict[str, Any] = nested if isinstance(nested, dict) else payload
    gmail_id = str(result.get('id') or result.get('messageId') or '')
    if not gmail_id:
        raise MailError('API: gog n’a pas rendu de message envoyé')
    return _headers(_get(gmail_id)).get('message-id') or gmail_id


def confirm(message: Outgoing) -> str:
    """Le ``Message-ID`` de l'envoi s'il est parti, sinon ``''``."""
    for gmail_id in _search(
        f'in:sent to:{message.address} newer_than:2d', SENT_MAX
    ):
        found = _get(gmail_id)
        if _same_text(_text(found), message.body):
            return _headers(found).get('message-id') or gmail_id
    return ''


def poll(since: str) -> list[Incoming]:
    """Les messages reçus depuis ``since`` (ISO), ou depuis un jour."""
    if since:
        start = int(datetime.fromisoformat(since).timestamp()) - OVERLAP_S
        query = f'in:inbox after:{start}'
    else:
        query = 'in:inbox newer_than:1d'
    received = []
    for gmail_id in _search(query, POLL_MAX):
        message = _get(gmail_id)
        headers = _headers(message)
        refs = _REF.findall(
            f'{headers.get("in-reply-to", "")} {headers.get("references", "")}'
        )
        received.append(
            Incoming(
                external_ref=gmail_id,
                address=parseaddr(headers.get('from', ''))[1],
                subject=headers.get('subject', ''),
                body=_text(message),
                message_ref=headers.get('message-id', ''),
                refs=tuple(refs),
                native_type='email',
            )
        )
    return received
