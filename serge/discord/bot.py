#!/usr/bin/env python3
"""Bot Discord : gateway + miroir + actes (DB = vérité, H §1).

Boucle : poll gateway (interactions/boutons, mentions, réactions) +
miroir tickets dus (H1 à la création, réutilisé aux edits).
CLI dans cli.py. Secrets : sidecar uniquement.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from serge.db.store import utcnow  # noqa: E402
from serge.discord.gateway import Gateway, GatewayError  # noqa: E402
from serge.discord.interactions import route_interaction  # noqa: E402
from serge.discord.mirror import (  # noqa: E402
    mirror_ticket,
    read_ref,
)
from serge.discord.rest import (  # noqa: E402
    DiscordError,
    interaction_callback,
    verify_token,
)
from serge.points.interact import render_context_fr  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets import create_ticket, publish  # noqa: E402

H1_KEYS = ('titre', 'ou', 'enjeu', 'attente')


class Bot:
    """Orchestre gateway + REST + tickets (reconnect backoff)."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        policy: Mapping[str, Any],
        discord_cfg: Mapping[str, str],
        token: str,
        *,
        gateway_factory: Callable[..., Gateway] | None = None,
    ):
        self.conn = connection
        self.policy = policy
        self.cfg = discord_cfg
        self.token = token
        self.types = load_ticket_types()
        self.gateway_factory = gateway_factory
        self.gateway: Gateway | None = None
        self.bot_user_id = ''

    def _gateway(self) -> Gateway:
        if self.gateway is None:
            maker = self.gateway_factory or (
                lambda **kwargs: Gateway(**kwargs)
            )
            self.gateway = maker(
                token=self.token, on_event=self.on_gateway_event
            )
            self.gateway.connect()
        return self.gateway

    def _ack(
        self,
        interaction: Mapping[str, Any],
        kind: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        body: dict[str, Any] = {'type': kind}
        if payload is not None:
            body['data'] = payload
        interaction_callback(
            str(interaction.get('id') or ''),
            str(interaction.get('token') or ''),
            body,
        )

    def _ephemeral(self, interaction: Mapping[str, Any], text: str) -> None:
        self._ack(interaction, 4, {'content': text[:2000], 'flags': 64})

    def on_gateway_event(self, kind: str, data: dict[str, Any]) -> None:
        """Dispatch READY/MESSAGE_CREATE/INTERACTION_CREATE/REACTION_ADD."""
        if kind == 'READY':
            user = data.get('user') or {}
            self.bot_user_id = str(user.get('id') or '')
        elif kind == 'INTERACTION_CREATE':
            self.on_interaction(data)
        elif kind == 'MESSAGE_CREATE':
            self.on_message(data)
        elif kind == 'MESSAGE_REACTION_ADD':
            self.on_reaction(data)
        self.conn.commit()

    def on_interaction(self, interaction: dict[str, Any]) -> None:
        """Bouton/select → acte + ack + refresh carte."""
        if int(interaction.get('type') or 0) not in {2, 3}:
            return
        try:
            result = route_interaction(
                self.conn, interaction, str(self.cfg.get('owner_user_id'))
            )
        except ValueError as exc:
            self._ephemeral(interaction, f'Erreur : {exc}')
            return
        status = result.get('status')
        if status == 'duplicate':
            self._ack(interaction, 6)
        elif status == 'refused':
            self._ephemeral(
                interaction, str(result.get('message') or 'Refusé.')
            )
        elif status == 'error':
            self._ephemeral(interaction, f'Impossible : {result.get("error")}')
        else:
            if result.get('hint'):
                self._ephemeral(interaction, str(result['hint']))
                return
            self._ack(interaction, 6)
            ticket_id = str(result.get('ticket_id') or '')
            if ticket_id:
                self._refresh(ticket_id)

    def _refresh(self, ticket_id: str) -> None:
        from serge.tickets import get_ticket

        try:
            ticket = get_ticket(self.conn, ticket_id)
        except ValueError:
            return
        spec = self.types.get(str(ticket.get('type')) or '')
        if not isinstance(spec, dict):
            return
        ref = read_ref(str(ticket.get('thread_ref') or ''))
        try:
            mirror_ticket(
                self.conn,
                self.token,
                self.cfg,
                ticket,
                spec,
                self.policy,
                h1=ref.get('h1') if isinstance(ref.get('h1'), dict) else None,
                now_iso=utcnow(),
            )
        except (DiscordError, ValueError):
            pass

    def on_message(self, message: dict[str, Any]) -> None:
        """Mention @Serge → flux owner (+ refresh carte)."""
        from serge.discord.owner_flow import handle_owner_message

        result = handle_owner_message(
            self.conn,
            self.policy,
            self.types,
            self.token,
            str(self.cfg.get('owner_user_id')),
            self.bot_user_id,
            message,
        )
        if result.get('ticket_id'):
            self._refresh(str(result['ticket_id']))

    def on_reaction(self, event: dict[str, Any]) -> None:
        """🧵 sur digest → ticket de discussion (H §2)."""
        emoji = event.get('emoji') or {}
        if str(emoji.get('name') or '') != '🧵':
            return
        if str(event.get('channel_id') or '') != str(
            self.cfg.get('digest_channel_id')
        ):
            return
        if str(event.get('user_id') or '') != str(
            self.cfg.get('owner_user_id')
        ):
            return
        ticket_id = create_ticket(
            self.conn,
            self.types,
            'QNA',
            'Discussion digest (🧵)',
            {
                'question': 'Sujet du digest à discuter.',
                'options_qcm': [],
                'contexte': f'message {event.get("message_id")}',
            },
            creator='owner',
        )
        publish(self.conn, ticket_id)
        self._refresh(ticket_id)

    def mirror_due(self) -> int:
        """Miroirise les tickets dus (H1 à la création, réutilisé sinon)."""
        from serge.discord.mirror import due_tickets as _due
        from serge.tickets import get_ticket

        count = 0
        for ticket_id in _due(self.conn):
            try:
                ticket = get_ticket(self.conn, ticket_id)
            except ValueError:
                continue
            spec = self.types.get(str(ticket.get('type')) or '')
            if not isinstance(spec, dict):
                continue
            ref = read_ref(str(ticket.get('thread_ref') or ''))
            stored = ref.get('h1')
            h1 = (
                {key: stored.get(key, '') for key in H1_KEYS}
                if isinstance(stored, dict)
                else None
            )
            if not ref.get('post_id') and h1 is None:
                rendered = render_context_fr(
                    self.conn,
                    self.policy,
                    json.dumps(
                        {
                            'titre': ticket.get('title'),
                            'type': ticket.get('type'),
                            'payload': ticket.get('payload_json'),
                        },
                        ensure_ascii=False,
                    ),
                )
                if not rendered.get('fallback'):
                    h1 = {key: rendered.get(key, '') for key in H1_KEYS}
            try:
                mirror_ticket(
                    self.conn,
                    self.token,
                    self.cfg,
                    ticket,
                    spec,
                    self.policy,
                    h1=h1,
                    now_iso=utcnow(),
                )
            except (DiscordError, ValueError):
                continue
            if h1 is not None:
                fresh = read_ref(
                    self.conn.execute(
                        'SELECT thread_ref FROM tickets WHERE id=?',
                        (ticket_id,),
                    ).fetchone()[0]
                )
                fresh['h1'] = h1
                self.conn.execute(
                    'UPDATE tickets SET thread_ref=? WHERE id=?',
                    (json.dumps(fresh, ensure_ascii=False), ticket_id),
                )
            count += 1
        self.conn.commit()
        return count

    def serve(self, tick_seconds: float = 1.0) -> None:
        """Boucle : gateway + miroir, reconnect backoff (bloquant)."""
        me = verify_token(self.token)
        self.bot_user_id = str(me.get('id') or '')
        backoff = 1.0
        while True:
            try:
                gateway = self._gateway()
                gateway.poll()
                backoff = 1.0
            except GatewayError:
                self.gateway = None
                time.sleep(backoff)
                backoff = min(60.0, backoff * 2.0)
            try:
                self.mirror_due()
            except (DiscordError, ValueError):
                pass
            time.sleep(tick_seconds)
