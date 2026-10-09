#!/usr/bin/env python3
"""Bot Discord : les tickets en message privé à chaque administrateur.

Boucle : la gateway (boutons, fenêtres de saisie) puis l'envoi des tickets
dus et la mise à jour des cartes (``prive.deliver``). La base est la
vérité (décisions Q85 et Q86). CLI dans cli.py. Secrets : sidecar
uniquement.
"""

from __future__ import annotations

import sqlite3
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from serge.discord.gateway import Gateway, GatewayError  # noqa: E402
from serge.discord.interactions import (  # noqa: E402
    COMPOSANT,
    FENETRE,
    route_interaction,
)
from serge.discord.prive import deliver  # noqa: E402
from serge.discord.rest import (  # noqa: E402
    DiscordError,
    interaction_callback,
    verify_token,
)
from serge.tickets.admins import reprendre_admin_instance  # noqa: E402


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
        self.gateway_factory = gateway_factory
        self.gateway: Gateway | None = None
        self.bot_user_id = ''
        # L'administrateur du fichier d'instance devient, une fois, le
        # premier administrateur en base.
        reprendre_admin_instance(
            connection, str(discord_cfg.get('owner_user_id') or '')
        )
        connection.commit()

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
        """Dispatch READY / INTERACTION_CREATE.

        Les messages libres (``MESSAGE_CREATE``) ne sont pas traités : un
        texte s'écrit dans une fenêtre de saisie, rattachée à son ticket.
        """
        if kind == 'READY':
            user = data.get('user') or {}
            self.bot_user_id = str(user.get('id') or '')
        elif kind == 'INTERACTION_CREATE':
            self.on_interaction(data)
        self.conn.commit()

    def on_interaction(self, interaction: dict[str, Any]) -> None:
        """Bouton, choix ou fenêtre envoyée → acte, accusé, cartes à jour."""
        kind = int(interaction.get('type') or 0)
        if kind not in COMPOSANT and kind != FENETRE:
            return
        try:
            result = route_interaction(self.conn, interaction)
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
        elif status == 'modal':
            self._ack(interaction, 9, result['modal'])
        else:
            if kind == FENETRE:
                self._ephemeral(interaction, 'C’est noté.')
            else:
                self._ack(interaction, 6)
            # Le ticket tranché est mis à jour tout de suite chez tous.
            self.conn.commit()
            self.deliver_due()

    def deliver_due(self) -> int:
        """Envoie les tickets dus et met à jour les cartes (voir prive)."""
        try:
            return deliver(self.conn, self.token)
        except (DiscordError, ValueError):
            return 0

    def serve(self, tick_seconds: float = 1.0) -> None:
        """Boucle : gateway + messages privés, reconnect backoff (bloquant)."""
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
            self.deliver_due()
            time.sleep(tick_seconds)
