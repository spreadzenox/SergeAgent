#!/usr/bin/env python3
"""Gateway Discord v10 (temps réel entrant) sur WsClient partagé.

HELLO → IDENTIFY/RESUME → heartbeat + watchdog ACK → dispatch.
Recv erreur = tick (le watchdog détecte les sockets mortes : pas
d'ACK sur 2 intervalles → RECONNECT). Intents : guildes + messages +
contenu + réactions (MESSAGE_CONTENT à activer côté portail).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from serge.discord.rest import USER_AGENT
from serge.voice.ws import WsClient, WsError

GATEWAY_URL = 'wss://gateway.discord.gg/?v=10&encoding=json'
INTENT_GUILDS = 1 << 0
INTENT_GUILD_MESSAGES = 1 << 9
INTENT_GUILD_REACTIONS = 1 << 10
INTENT_MESSAGE_CONTENT = 1 << 15
DEFAULT_INTENTS = (
    INTENT_GUILDS
    | INTENT_GUILD_MESSAGES
    | INTENT_GUILD_REACTIONS
    | INTENT_MESSAGE_CONTENT
)


class GatewayError(ValueError):
    pass


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


class Gateway:
    """Connexion gateway (transport + rythme, zéro logique métier)."""

    def __init__(
        self,
        token: str,
        intents: int = DEFAULT_INTENTS,
        *,
        url: str = GATEWAY_URL,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.token = token
        self.intents = intents
        self.url = url
        self.on_event = on_event or (lambda _t, _d: None)
        self.ws: WsClient | None = None
        self.session_id = ''
        self.seq: int | None = None
        self.interval_ms = 41250
        self.last_ack_ms = 0
        self.next_beat_ms = 0
        self.connected = False

    def connect(
        self,
        factory: Callable[..., WsClient] | None = None,
        timeout: float = 20.0,
    ) -> None:
        """Connecte + HELLO + IDENTIFY (ou RESUME si session).

        Args:
            factory: (url, headers, timeout) → WsClient (tests).
            timeout: Timeout HELLO.

        Raises:
            GatewayError: HELLO/AUTH/NETWORK.
        """
        if not self.token:
            raise GatewayError('AUTH: token Discord manquant')
        maker = factory or WsClient.connect
        try:
            self.ws = maker(self.url, {'User-Agent': USER_AGENT}, timeout)
        except WsError as exc:
            raise GatewayError(f'NETWORK: gateway ({exc})') from exc
        hello = self._wait_hello(timeout)
        self.interval_ms = int(hello.get('heartbeat_interval', 41250))
        now = _now_ms()
        self.last_ack_ms = now
        self.next_beat_ms = now + self.interval_ms
        if self.session_id and self.seq is not None:
            self._send(
                {
                    'op': 6,
                    'd': {
                        'token': self.token,
                        'session_id': self.session_id,
                        'seq': self.seq,
                    },
                }
            )
        else:
            self._send(
                {
                    'op': 2,
                    'd': {
                        'token': self.token,
                        'intents': self.intents,
                        'properties': {
                            'os': 'linux',
                            'browser': 'serge',
                            'device': 'serge',
                        },
                    },
                }
            )
        self.connected = True

    def _wait_hello(self, timeout: float) -> dict[str, Any]:
        assert self.ws is not None
        deadline = _now_ms() + int(timeout * 1000)
        while _now_ms() < deadline:
            try:
                frames = self.ws.recv()
            except WsError:
                continue
            for opcode, payload in frames:
                if opcode != 0x1:
                    continue
                try:
                    event = json.loads(payload.decode('utf-8'))
                except ValueError:
                    continue
                if isinstance(event, dict) and event.get('op') == 10:
                    data = event.get('d') or {}
                    return data if isinstance(data, dict) else {}
        raise GatewayError('HELLO: timeout')

    def _send(self, payload: dict[str, Any]) -> None:
        assert self.ws is not None
        try:
            self.ws.send_text(json.dumps(payload))
        except WsError as exc:
            raise GatewayError(f'NETWORK: envoi ({exc})') from exc

    def poll(self, now_ms: int | None = None) -> list[str]:
        """Un tick : lit, heartbeat si dû, watchdog ACK, dispatch.

        Args:
            now_ms: Horloge injectable (tests).

        Returns:
            Types d'événements dispatchés (t de op 0).

        Raises:
            GatewayError: RECONNECT (watchdog/close/serveur).
        """
        if not self.connected or self.ws is None:
            raise GatewayError('RECONNECT: non connecté')
        now = now_ms if now_ms is not None else _now_ms()
        if now - self.last_ack_ms > 2 * self.interval_ms:
            raise GatewayError('RECONNECT: heartbeat sans ACK')
        if now >= self.next_beat_ms:
            self._send({'op': 1, 'd': self.seq})
            self.next_beat_ms = now + self.interval_ms
        dispatched: list[str] = []
        try:
            frames = self.ws.recv()
        except WsError:
            return dispatched
        for opcode, payload in frames:
            if opcode != 0x1:
                continue
            try:
                event = json.loads(payload.decode('utf-8'))
            except ValueError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get('s') is not None:
                self.seq = event['s']
            op = event.get('op')
            if op == 11:
                self.last_ack_ms = now
            elif op == 0:
                kind = str(event.get('t') or '')
                data = event.get('d') or {}
                if kind == 'READY' and isinstance(data, dict):
                    self.session_id = str(data.get('session_id') or '')
                if isinstance(data, dict):
                    self.on_event(kind, data)
                dispatched.append(kind)
            elif op == 7:
                raise GatewayError('RECONNECT: demandé serveur')
            elif op == 9:
                self.session_id = ''
                self.seq = None
                raise GatewayError('RECONNECT: session invalide')
        return dispatched

    def close(self) -> None:
        """Ferme (best effort, garde session pour resume)."""
        self.connected = False
        if self.ws is not None:
            try:
                self.ws.close()
            except WsError:
                pass
            self.ws = None

    def state(self) -> Mapping[str, Any]:
        """État lisible (supervision, jamais le token).

        Returns:
            Dict session/seq/connected (token exclu).
        """
        return {
            'connected': self.connected,
            'session_id': bool(self.session_id),
            'seq': self.seq,
            'interval_ms': self.interval_ms,
        }
