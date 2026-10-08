#!/usr/bin/env python3
"""Le canal appel : passer un appel par le pont téléphonique (``serge/voice``).

Le « message » d'un appel est son but : il est remis à l'agent vocal au
décrochage, avec la fiche du contact et son fil. L'appel est demandé au
pont téléphonique (``serge/voice/bridge.py``, à l'adresse locale
``127.0.0.1:8791``), qui tient le journal des appels, décide (accord,
liste de blocage, heures et plafonds) puis compose. Cet adaptateur ne
parle qu'au pont : il ne lit ni la base ni le journal.

- ``send`` demande l'appel et rend son numéro dans le journal. Une demande
  refusée pour un temps (hors des heures d'appel, plafond du jour, un appel
  déjà en cours) attend : ``ChannelLater`` (décision Q83). Un autre refus,
  ou une ligne en panne, fait échouer l'envoi ;
- ``confirm`` demande au pont les appels de cet envoi : un appel déjà
  composé n'est jamais refait ;
- pas de relève : l'agent vocal écrit lui-même chaque appel dans le fil.

Le canal est branché quand le fichier d'instance a ``features.phone_voice``.
"""

from __future__ import annotations

import json
import os
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from serge.channels.base import Adapter, ChannelError, ChannelLater, Outgoing

DEFAULT_BRIDGE = '127.0.0.1:8791'


def ready() -> bool:
    """Le fichier d'instance a le téléphone (``features.phone_voice``)."""
    raw = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    if not raw:
        return False
    try:
        data = tomllib.loads(Path(raw).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    return bool((data.get('features') or {}).get('phone_voice'))


def _bridge(
    path: str, payload: dict[str, str] | None = None
) -> dict[str, Any]:
    """Une requête au pont : ``POST`` avec ``payload``, sinon ``GET``.

    Le pont injoignable lève ``OSError`` : l'envoi reste « en cours », et
    la tâche relancée demandera au pont s'il est parti.
    """
    listen = os.environ.get('SERGE_VOICE_BRIDGE_LISTEN', DEFAULT_BRIDGE)
    request = urllib.request.Request(
        f'http://{listen}{path}',
        data=json.dumps(payload).encode('utf-8') if payload else None,
        headers={'Content-Type': 'application/json'},
        method='POST' if payload else 'GET',
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # 403 refusé, 502 non composé, 400 demande invalide : la décision
        # est dans la réponse.
        answer = json.loads(exc.read() or b'{}')
    return answer if isinstance(answer, dict) else {}


def send(message: Outgoing) -> str:
    """Demande l'appel ; rend son numéro dans le journal des appels."""
    result = _bridge(
        '/originate',
        {
            'to': message.address,
            'purpose': 'callback'
            if message.kind == 'reply'
            else 'prospection',
            'task_id': message.touch_id,
            'message': message.body,
        },
    )
    if 'decision' not in result:
        raise ChannelError(f'appel refusé : {result.get("error", "")}')
    reason = str(result.get('reason') or '')
    if result.get('decision') != 'allowed':
        if result.get('retry_at'):
            raise ChannelLater(
                f'appel reporté : {reason}', str(result['retry_at'])
            )
        raise ChannelError(f'appel refusé : {reason}')
    if not result.get('originated') and not result.get('duplicate'):
        raise ChannelError(f'appel non composé : {result.get("error", "")}')
    return str(result['cdr_id'])


def confirm(message: Outgoing) -> str:
    """Le numéro de l'appel s'il a été composé pour cet envoi, sinon ``''``."""
    query = urllib.parse.urlencode({'task_id': message.touch_id})
    calls = _bridge(f'/calls?{query}').get('calls') or []
    for call in reversed(calls):
        if (
            call['decision'] == 'allowed'
            and call['outcome'] != 'originate_failed'
        ):
            return str(call['cdr_id'])
    return ''


ADAPTER = Adapter(
    id='voice',
    title='Voix',
    doc='Appeler et recevoir des appels : le pont compose après ses'
    ' garde-fous (accord, heures d’appel, plafonds), et un agent vocal'
    ' parle en direct, réglé en base comme une invocation.',
    address_channel='phone',
    code_path='serge/channels/voice.py',
    send=send,
    confirm=confirm,
    ready=ready,
)
