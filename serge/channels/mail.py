#!/usr/bin/env python3
"""Le canal e-mail : Gmail par l'outil gog, ou une boîte SMTP/IMAP.

Le fichier d'instance dit lequel : ``features.mailbox`` (SMTP/IMAP, choisi
d'abord) ou ``features.gmail`` (gog). Sans l'un ni l'autre, le canal n'est
pas branché sur ce serveur (``ready``) : rien n'est relevé ni envoyé.

Deux règles valent pour les deux boîtes :

- un message reçu est rendu sans la citation du message auquel il répond
  (les lignes « > … » et la ligne « Le …, Serge a écrit : ») : le fil du
  contact contient déjà ce message ;
- une erreur ``API`` (le destinataire est refusé, par exemple) veut dire
  que le message n'est pas parti : l'envoi passe en échec. Une panne
  (réseau, accès) laisse l'envoi « en cours » : la tâche relancée
  demandera à la boîte s'il est parti.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from types import ModuleType

from serge.channels import email_gog, email_smtp
from serge.channels.base import Adapter, ChannelError, Incoming, Outgoing
from serge.channels.email_gog import MailError

_ATTRIBUTION = re.compile(r'(a écrit|wrote)\s*:\s*$', re.IGNORECASE)


def backend() -> str:
    """``smtp``, ``gog``, ou ``''`` si l'instance n'a pas de boîte."""
    raw = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    if not raw:
        return ''
    try:
        data = tomllib.loads(Path(raw).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError):
        return ''
    features = data.get('features') or {}
    if features.get('mailbox'):
        return 'smtp'
    return 'gog' if features.get('gmail') else ''


def _box() -> ModuleType:
    return email_smtp if backend() == 'smtp' else email_gog


def without_quote(text: str) -> str:
    """Le texte d'une réponse, sans le message cité en dessous."""
    lines = text.splitlines()
    for n, line in enumerate(lines):
        if line.lstrip().startswith('>') or _ATTRIBUTION.search(line):
            # Une ligne « Le mar. 7 oct. 2026 à 10:00, Serge » coupée en
            # deux part avec sa fin.
            cut = n - 1 if n and _ATTRIBUTION.search(line) else n
            if cut < n and not lines[cut].strip().startswith(('Le ', 'On ')):
                cut = n
            kept = '\n'.join(lines[:cut]).strip()
            return kept or text.strip()
    return text.strip()


def send(message: Outgoing) -> str:
    try:
        return _box().send(message)
    except MailError as exc:
        if str(exc).startswith('API:'):
            raise ChannelError(str(exc)) from exc
        raise


def confirm(message: Outgoing) -> str:
    return _box().confirm(message)


def poll(since: str) -> list[Incoming]:
    return [
        Incoming(
            external_ref=m.external_ref,
            address=m.address,
            subject=m.subject,
            body=without_quote(m.body),
            message_ref=m.message_ref,
            refs=m.refs,
            native_type=m.native_type,
        )
        for m in _box().poll(since)
    ]


ADAPTER = Adapter(
    id='email',
    title='E-mail',
    doc='Écrire et lire des e-mails, par Gmail (outil gog) ou une boîte'
    ' SMTP/IMAP, selon le fichier d’instance. Les réponses restent dans le'
    ' fil ; la boîte est relevée toutes les 2 minutes.',
    address_channel='email',
    code_path='serge/channels/mail.py',
    send=send,
    confirm=confirm,
    poll=poll,
    ready=lambda: bool(backend()),
)
