#!/usr/bin/env python3
"""Bot Discord : les tickets dans le forum du serveur de Serge.

La gateway reçoit les clics (boutons, fenêtres de saisie) ; un fil à part
ouvre les fils des tickets et met leurs cartes à jour (``forum.deliver``).
La base est la vérité (décisions Q85, Q86 et Q88). CLI dans cli.py.
Secrets : sidecar uniquement.
"""

from __future__ import annotations

import sqlite3
import sys
import threading
import time
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.discord.forum import deliver  # noqa: E402
from serge.discord.gateway import Gateway, GatewayError  # noqa: E402
from serge.discord.interactions import (  # noqa: E402
    COMPOSANT,
    FENETRE,
    actor_id,
    ephemere,
    premiere_reponse,
    route_interaction,
)
from serge.discord.rest import (  # noqa: E402
    DiscordError,
    interaction_callback,
    interaction_followup,
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
        connect: Callable[[], sqlite3.Connection] | None = None,
    ):
        self.conn = connection
        self.policy = policy
        self.cfg = discord_cfg
        self.token = token
        self.gateway_factory = gateway_factory
        self.gateway: Gateway | None = None
        self.bot_user_id = ''
        # Le fil des envois ouvre sa propre connexion à la base.
        self.connect = connect or (lambda: open_db(default_canon_path()))
        self.reveil = threading.Event()
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

    def _repondre(
        self, interaction: Mapping[str, Any], body: dict[str, Any]
    ) -> None:
        """La réponse à l'interaction. Une réponse qui ne passe pas (réseau,
        délai dépassé) est notée au journal, sans arrêter le bot."""
        try:
            interaction_callback(
                str(interaction.get('id') or ''),
                str(interaction.get('token') or ''),
                body,
            )
            _journal(f'réponse envoyée (type {body.get("type")})')
        except DiscordError as exc:
            _journal(f'réponse à un clic refusée par Discord : {exc}')

    def _suite(self, interaction: Mapping[str, Any], texte: str) -> None:
        """Un message éphémère après l'accusé de réception."""
        try:
            interaction_followup(
                str(interaction.get('application_id') or ''),
                str(interaction.get('token') or ''),
                ephemere(texte),
            )
        except DiscordError as exc:
            _journal(f'message après un clic refusé par Discord : {exc}')

    def on_gateway_event(self, kind: str, data: dict[str, Any]) -> None:
        """Dispatch READY / INTERACTION_CREATE.

        Les messages libres (``MESSAGE_CREATE``) ne sont pas traités : un
        texte s'écrit dans une fenêtre de saisie, rattachée à son ticket.
        """
        if kind == 'READY':
            user = data.get('user') or {}
            self.bot_user_id = str(user.get('id') or '')
            _journal('connecté à Discord')
        elif kind == 'INTERACTION_CREATE':
            try:
                self.on_interaction(data)
            except Exception:  # noqa: BLE001 — un clic raté n'arrête pas le bot
                self.conn.rollback()
                _journal(f'clic en erreur :\n{traceback.format_exc()}')
        self.conn.commit()

    def on_interaction(self, interaction: dict[str, Any]) -> None:
        """Bouton, choix ou fenêtre envoyée → réponse immédiate, puis acte.

        Discord attend une réponse en moins de 3 secondes : le bot répond
        d'abord (une fenêtre à ouvrir, un refus, ou un accusé de réception),
        puis tranche le ticket. Un acte refusé ensuite (ticket déjà
        tranché…) est dit par un message éphémère.
        """
        kind = int(interaction.get('type') or 0)
        if kind not in COMPOSANT and kind != FENETRE:
            return
        _journal(
            f'clic reçu : {(interaction.get("data") or {}).get("custom_id")}'
            f' par {actor_id(interaction)}'
        )
        premiere = premiere_reponse(self.conn, interaction)
        if premiere is not None:
            self._repondre(interaction, premiere)
            return
        self._repondre(interaction, {'type': 6})
        try:
            result = route_interaction(self.conn, interaction)
        except (ValueError, sqlite3.Error) as exc:
            self.conn.rollback()
            result = {'status': 'error', 'error': str(exc)}
        self.conn.commit()
        status = result.get('status')
        if status == 'refused':
            self._suite(interaction, str(result.get('message') or 'Refusé.'))
        elif status == 'error':
            self._suite(interaction, f'Impossible : {result.get("error")}')
        elif status == 'applied':
            if kind == FENETRE:
                self._suite(interaction, 'C’est noté.')
            # Le ticket tranché est mis à jour tout de suite chez tous.
            self.reveil.set()

    def deliver_due(self, conn: sqlite3.Connection | None = None) -> int:
        """Envoie les tickets dus et met à jour les cartes (voir prive)."""
        try:
            return deliver(conn or self.conn, self.token)
        except (DiscordError, ValueError):
            return 0

    def _livrer_en_boucle(self, tick_seconds: float) -> None:
        """Les envois, dans un fil à part, avec leur propre connexion : un
        envoi lent (Discord qui fait patienter) ne retarde jamais la
        réponse à un clic. Un clic tranché réveille ce fil tout de suite."""
        conn = self.connect()
        while True:
            try:
                self.deliver_due(conn)
            except sqlite3.Error as exc:
                conn.rollback()
                _journal(f'envoi des tickets impossible : {exc}')
            self.reveil.wait(tick_seconds)
            self.reveil.clear()

    def serve(self, tick_seconds: float = 1.0) -> None:
        """Boucle : gateway ici, envois dans un fil à part (bloquant)."""
        me = verify_token(self.token)
        self.bot_user_id = str(me.get('id') or '')
        threading.Thread(
            target=self._livrer_en_boucle, args=(tick_seconds,), daemon=True
        ).start()
        backoff = 1.0
        while True:
            try:
                gateway = self._gateway()
                gateway.poll()
                backoff = 1.0
            except GatewayError as exc:
                _journal(f'gateway : {exc} ; reconnexion dans {backoff:.0f} s')
                self.gateway = None
                time.sleep(backoff)
                backoff = min(60.0, backoff * 2.0)


def _journal(texte: str) -> None:
    """Une ligne dans le journal du service (lisible avec journalctl)."""
    print(f'discord : {texte}', file=sys.stderr, flush=True)
