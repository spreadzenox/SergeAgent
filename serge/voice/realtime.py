#!/usr/bin/env python3
"""Voix temps réel S2S (P5) : session Realtime + routeur événements.

Providers : OpenAI Realtime primaire, xAI rollback (même forme
d'événements). Échec à tout moment = RealtimeError → l'appelant
dégrade vers tour-par-tour (turn.py), jamais de silence. Audio PCM16.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from serge.voice.ws import WsClient, WsError

PROVIDERS = {
    'openai': 'wss://api.openai.com/v1/realtime',
    'xai': 'wss://api.x.ai/v1/realtime',
}
DEFAULT_VOICE = 'alloy'


class RealtimeError(ValueError):
    pass


def build_session_update(
    instructions: str,
    voice: str = DEFAULT_VOICE,
    modalities: list[str] | None = None,
) -> dict[str, Any]:
    """Événement session.update (instructions + voix + audio).

    Args:
        instructions: Prompt système (script P4 + règles dures).
        voice: Voix synthèse.
        modalities: Modalités (défaut : texte + audio).

    Returns:
        L'événement à envoyer.
    """
    return {
        'type': 'session.update',
        'session': {
            'modalities': modalities or ['text', 'audio'],
            'instructions': instructions,
            'voice': voice,
            'input_audio_format': 'pcm16',
            'output_audio_format': 'pcm16',
            'turn_detection': {'type': 'server_vad'},
        },
    }


def build_audio_append(audio_b64: str) -> dict[str, Any]:
    """Chunk micro → buffer d'entrée.

    Args:
        audio_b64: PCM16 base64.

    Returns:
        L'événement input_audio_buffer.append.
    """
    return {'type': 'input_audio_buffer.append', 'audio': audio_b64}


def build_audio_commit() -> dict[str, Any]:
    """Valide le buffer micro (tour de parole terminé)."""
    return {'type': 'input_audio_buffer.commit'}


def build_text_item(text: str) -> dict[str, Any]:
    """Injecte un message texte (redirect, consigne...).

    Args:
        text: Contenu.

    Returns:
        L'événement conversation.item.create.
    """
    return {
        'type': 'conversation.item.create',
        'item': {
            'type': 'message',
            'role': 'user',
            'content': [{'type': 'input_text', 'text': text}],
        },
    }


def build_response_create() -> dict[str, Any]:
    """Demande une réponse (après commit/inject)."""
    return {'type': 'response.create'}


def route_event(
    event: Mapping[str, Any], state: dict[str, Any]
) -> list[tuple[str, Any]]:
    """Route un événement serveur (pur, testable sans réseau).

    Args:
        event: Événement JSON parsé.
        state: État mutable (transcript, audio, done, error).

    Returns:
        Actions [(audio|transcript|transcript_delta|done|error|speech, ...)].
    """
    kind = str(event.get('type') or '')
    if kind == 'response.audio.delta':
        chunk = str(event.get('delta') or '')
        state.setdefault('audio', []).append(chunk)
        return [('audio', chunk)]
    if kind == 'response.audio_transcript.delta':
        return [('transcript_delta', str(event.get('delta') or ''))]
    if kind == 'response.audio_transcript.done':
        text = str(event.get('transcript') or '')
        state['transcript'] = str(state.get('transcript') or '') + text
        return [('transcript', text)]
    if kind == 'response.done':
        state['done'] = True
        return [('done', dict(event.get('response') or {}))]
    if kind == 'error':
        detail = event.get('error') or {}
        state['error'] = detail
        return [('error', detail)]
    if kind in {
        'input_audio_buffer.speech_started',
        'input_audio_buffer.speech_stopped',
    }:
        return [('speech', kind)]
    return []


class RealtimeCall:
    """Session S2S sur WsClient (erreurs → RealtimeError → degrade)."""

    def __init__(
        self,
        ws: WsClient,
        instructions: str,
        voice: str = DEFAULT_VOICE,
    ):
        self.ws = ws
        self.state: dict[str, Any] = {}
        try:
            ws.send_text(json.dumps(build_session_update(instructions, voice)))
        except WsError as exc:
            raise RealtimeError(f'WS: session ({exc})') from exc

    @classmethod
    def dial(
        cls,
        provider: str,
        api_key: str,
        model: str,
        instructions: str,
        voice: str = DEFAULT_VOICE,
        timeout: float = 20.0,
    ) -> RealtimeCall:
        """Ouvre une session chez le provider.

        Args:
            provider: openai | xai.
            api_key: Clé provider (header only).
            model: Modèle realtime.
            instructions: Prompt système.
            voice: Voix synthèse.
            timeout: Timeout socket.

        Returns:
            Session prête.

        Raises:
            RealtimeError: Provider inconnu, clé, réseau, handshake.
        """
        base = PROVIDERS.get(provider)
        if not base:
            raise RealtimeError(f'PROVIDER: inconnu ({provider})')
        if not api_key:
            raise RealtimeError('PROVIDER: clé manquante')
        from urllib.parse import quote

        url = f'{base}?model={quote(model)}'
        headers = {'Authorization': f'Bearer {api_key}'}
        if provider == 'openai':
            headers['OpenAI-Beta'] = 'realtime=v1'
        try:
            ws = WsClient.connect(url, headers, timeout)
        except WsError as exc:
            raise RealtimeError(f'WS: {exc}') from exc
        return cls(ws, instructions, voice)

    def send_audio(self, audio_b64: str) -> None:
        """Envoie un chunk micro.

        Raises:
            RealtimeError: Socket rompue.
        """
        try:
            self.ws.send_text(json.dumps(build_audio_append(audio_b64)))
        except WsError as exc:
            raise RealtimeError(f'WS: audio ({exc})') from exc

    def commit_turn(self) -> None:
        """Valide le tour + demande réponse.

        Raises:
            RealtimeError: Socket rompue.
        """
        try:
            self.ws.send_text(json.dumps(build_audio_commit()))
            self.ws.send_text(json.dumps(build_response_create()))
        except WsError as exc:
            raise RealtimeError(f'WS: commit ({exc})') from exc

    def inject_text(self, text: str) -> None:
        """Injecte un texte (redirect "revenons à...") + réponse.

        Raises:
            RealtimeError: Socket rompue.
        """
        try:
            self.ws.send_text(json.dumps(build_text_item(text)))
            self.ws.send_text(json.dumps(build_response_create()))
        except WsError as exc:
            raise RealtimeError(f'WS: inject ({exc})') from exc

    def poll(self) -> list[tuple[str, Any]]:
        """Lit + route les événements (erreurs provider → RealtimeError).

        Returns:
            Actions plates (audio, transcript, done...).

        Raises:
            RealtimeError: WS ou erreur provider.
        """
        try:
            frames = self.ws.recv()
        except WsError as exc:
            raise RealtimeError(f'WS: poll ({exc})') from exc
        actions: list[tuple[str, Any]] = []
        for opcode, payload in frames:
            if opcode != 0x1:
                continue
            try:
                event = json.loads(payload.decode('utf-8'))
            except (ValueError, UnicodeDecodeError) as exc:
                raise RealtimeError(f'PROTO: JSON ({exc})') from exc
            if not isinstance(event, dict):
                raise RealtimeError('PROTO: événement non-objet')
            for action in route_event(event, self.state):
                if action[0] == 'error':
                    raise RealtimeError(f'PROVIDER: {action[1]}')
                actions.append(action)
        return actions

    def close(self) -> None:
        """Ferme la session (best effort)."""
        self.ws.close()
