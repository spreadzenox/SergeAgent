#!/usr/bin/env python3
"""Un canal qui passe par le navigateur : LinkedIn, Instagram, X (lot 13).

Un tel canal n'a pas de code à lui. Il est décrit en base (``canaux`` : le
compte web de Serge qui lui sert, l'invocation qui envoie, celle qui
relève), et son adaptateur, ici, est le même pour tous. Envoyer un message
et relever la messagerie sont deux missions confiées à des invocations LLM
(``serge/missions.py``), qui naviguent dans le vrai Chrome connectées au
compte. Ce qu'un site a de particulier (où cliquer, la longueur d'une
note) est dans leurs consignes, en base.

Pour le reste du pipeline, rien ne change : « Envoyer un message »
applique les mêmes garde-fous, puis confie l'envoi ; « Relever les
messages » rattache les messages rendus comme ceux d'une boîte e-mail.

Un envoi attend, sans échouer, quand le compte sert à une autre tâche (10
minutes), quand il a fait ses actions du jour, ou quand le plafond de
dépense du jour est atteint (le lendemain). La messagerie n'est relevée
que s'il y a une conversation en cours : un message parti par ce canal
depuis moins de jours que le réglage (page Policy, « Comptes web »).

Exemple : un premier message pour ``https://www.linkedin.com/in/ana-roux``
part par la mission d'envoi du canal ``linkedin``, qui rend ``{envoye:
'oui', reference: 'https://www.linkedin.com/messaging/thread/42'}``.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from serge import missions, web_accounts
from serge.channels.adapters import ADAPTERS
from serge.channels.base import (
    Adapter,
    ChannelError,
    ChannelLater,
    Incoming,
    Outgoing,
)
from serge.llm.runtime import budget_reached
from serge.policy_store import policy_en_vigueur
from serge.trial import current_task

CODE = 'serge/channels/web.py'


def _demain() -> str:
    jour = datetime.now(UTC) + timedelta(days=1)
    return jour.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _attente(conn: sqlite3.Connection, compte: str) -> tuple[str, str]:
    """Pourquoi le compte ne peut pas servir maintenant, et jusqu'à quand ;
    ``('', '')`` s'il le peut."""
    pris = conn.execute(
        'SELECT used_by, used_since FROM web_accounts WHERE id=?', (compte,)
    ).fetchone()
    limite = (datetime.now(UTC) - web_accounts.LEASE).isoformat()
    if pris and pris[0] and pris[0] != current_task() and pris[1] > limite:
        plus_tard = datetime.now(UTC) + timedelta(minutes=10)
        return 'le compte sert à une autre tâche', plus_tard.isoformat()
    if web_accounts.actions_today(conn, compte) >= web_accounts.daily_cap(
        conn
    ):
        return 'le compte a fait ses actions du jour', _demain()
    if budget_reached(conn, policy_en_vigueur(conn)):
        return 'le plafond de dépense du jour est atteint', _demain()
    return '', ''


def _send(
    conn: sqlite3.Connection, canal: dict[str, str], message: Outgoing
) -> str:
    raison, quand = _attente(conn, canal['account'])
    if raison:
        raise ChannelLater(raison, quand)
    try:
        reponse = missions.run(
            conn,
            canal['send_invocation'],
            current_task(),
            {
                'compte': canal['account'],
                'canal': canal['id'],
                'adresse': message.address,
                'message': message.body,
                'sorte': message.kind,
            },
        )
    except missions.MissionError as exc:
        raise ChannelError(
            f'l’envoi par le navigateur a raté : {exc}'
        ) from exc
    if str(reponse.get('envoye') or '') not in ('oui', 'deja'):
        raise ChannelError(
            str(reponse.get('raison') or 'le message n’est pas parti')[:500]
        )
    return str(reponse.get('reference') or f'{canal["id"]}:{message.touch_id}')


def _en_cours(conn: sqlite3.Connection, canal: str) -> bool:
    """Y a-t-il une conversation à suivre : un message parti par ce canal
    depuis moins de jours que le réglage ?"""
    jours = float(policy_en_vigueur(conn)['web_accounts']['inbox_days'])
    depuis = (datetime.now(UTC) - timedelta(days=jours)).isoformat()
    return bool(
        conn.execute(
            "SELECT 1 FROM touches WHERE channel=? AND status='sent'"
            ' AND sent_at>=? LIMIT 1',
            (canal, depuis),
        ).fetchone()
    )


def _poll(
    conn: sqlite3.Connection, canal: dict[str, str], _since: str
) -> list[Incoming]:
    if not _en_cours(conn, canal['id']) or _attente(conn, canal['account'])[0]:
        return []
    try:
        reponse = missions.run(
            conn,
            canal['poll_invocation'],
            current_task(),
            {'compte': canal['account'], 'canal': canal['id']},
        )
    except missions.MissionError as exc:
        raise ChannelError(
            f'la relève par le navigateur a raté : {exc}'
        ) from exc
    recus = []
    for item in reponse.get('messages') or []:
        adresse = str(item.get('de') or '').strip()
        texte = str(item.get('texte') or '').strip()
        if not adresse or not texte:
            continue
        # raccourci : un site ne donne pas de numéro stable à un message ;
        # deux messages identiques de la même personne n'en font qu'un.
        cle = f'{canal["id"]}|{adresse.casefold().rstrip("/")}|{texte}'
        ref = hashlib.sha256(cle.encode('utf-8')).hexdigest()[:24]
        recus.append(Incoming(ref, adresse, '', texte, message_ref=ref))
    return recus


def adapter(conn: sqlite3.Connection, channel: str) -> Adapter | None:
    """L'adaptateur d'un canal du navigateur, lu en base ; ``None`` si ce
    canal n'en est pas un."""
    cursor = conn.execute(
        'SELECT id, titre, doc_md, address_channel, account, connected,'
        " send_invocation, poll_invocation FROM canaux WHERE id=? AND account<>''",
        (channel,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    canal: dict[str, Any] = dict(
        zip([d[0] for d in cursor.description], row, strict=True)
    )
    branche = bool(canal['connected'])
    return Adapter(
        id=str(canal['id']),
        title=str(canal['titre']),
        doc=str(canal['doc_md']),
        address_channel=str(canal['address_channel']),
        code_path=CODE,
        send=partial(_send, conn, canal),
        # Un envoi interrompu repart par la même mission, qui regarde
        # d'abord si le message est déjà dans la conversation.
        confirm=lambda _message: '',
        poll=partial(_poll, conn, canal),
        ready=lambda: branche,
    )


def transport(conn: sqlite3.Connection, channel: str) -> Adapter:
    """L'adaptateur d'un canal branché, quel qu'il soit : celui du code
    (l'e-mail, l'appel), sinon celui d'un canal du navigateur.

    Raises:
        ChannelError: Canal inconnu, ou pas branché ici.
    """
    found = ADAPTERS.get(channel) or adapter(conn, channel)
    if found is None or not found.ready():
        raise ChannelError(f'canal non branché : {channel}')
    return found
