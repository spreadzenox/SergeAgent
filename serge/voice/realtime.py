#!/usr/bin/env python3
"""Voix temps réel S2S (P5) : session Realtime + routeur événements.

Providers : xAI Realtime primaire, OpenAI rollback (même forme
d'événements). Échec à tout moment = RealtimeError → l'appelant
dégrade vers tour-par-tour (turn.py), jamais de silence. Audio PCM16.

L'agent peut appeler des outils pendant l'appel (chercher un contact,
noter une adresse) : ils sont déclarés dans la session, le fournisseur
demande un appel (``response.function_call_arguments.done``) et reçoit
son résultat (``function_call_output``). Ce que dit l'interlocuteur
revient transcrit (``conversation.item.input_audio_transcription``).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from typing import Any

from serge.voice.ws import WsClient, WsError

PROVIDERS = {
    'openai': 'wss://api.openai.com/v1/realtime',
    'xai': 'wss://api.x.ai/v1/realtime',
}
# Le modèle et la voix de chaque fournisseur sont des réglages de l'agent
# vocal, en base (serge/voice/agent.py).
DEFAULT_VOICE = 'alloy'
PCM_RATE = 24000
DEFAULT_RATES = {'xai': 8000, 'openai': 24000}
# OpenAI ne transcrit l'interlocuteur que si on le demande ; xAI le fait
# d'office.
TRANSCRIBE_MODELS = {'openai': 'whisper-1'}


class RealtimeError(ValueError):
    pass


def build_session_update(
    instructions: str,
    voice: str = DEFAULT_VOICE,
    rate: int = PCM_RATE,
    tools: list[dict[str, Any]] | None = None,
    transcribe: str = '',
) -> dict[str, Any]:
    """Événement session.update (instructions + voix + PCM + outils).

    Args:
        instructions: Prompt système (lu en base, avec la fiche du contact).
        voice: Voix synthèse (eve xAI, alloy OpenAI).
        rate: Fréquence PCM (8000 xAI / 24000 OpenAI).
        tools: Les outils appelables (``{type, name, description,
            parameters}``).
        transcribe: Le modèle qui transcrit l'interlocuteur, ou ``''``.

    Returns:
        L'événement à envoyer.
    """
    pcm = {'type': 'audio/pcm', 'rate': rate}
    heard: dict[str, Any] = {'format': pcm}
    if transcribe:
        heard['transcription'] = {'model': transcribe}
    session: dict[str, Any] = {
        'instructions': instructions,
        'voice': voice,
        'turn_detection': {'type': 'server_vad'},
        'audio': {'input': heard, 'output': {'format': pcm}},
    }
    if tools:
        session['tools'] = tools
    return {'type': 'session.update', 'session': session}


def build_tool_output(call_id: str, output: str) -> dict[str, Any]:
    """Le résultat d'un outil, rendu au modèle."""
    return {
        'type': 'conversation.item.create',
        'item': {
            'type': 'function_call_output',
            'call_id': call_id,
            'output': output,
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
        Actions [(audio|transcript|transcript_delta|done|error|speech|tool|
        heard, ...)] : ``transcript`` est ce que dit Serge, ``heard`` ce que
        dit l'interlocuteur.
    """
    kind = str(event.get('type') or '')
    if kind in {'response.audio.delta', 'response.output_audio.delta'}:
        chunk = str(event.get('delta') or '')
        state.setdefault('audio', []).append(chunk)
        return [('audio', chunk)]
    if kind in {
        'response.audio_transcript.delta',
        'response.output_audio_transcript.delta',
    }:
        return [('transcript_delta', str(event.get('delta') or ''))]
    if kind in {
        'response.audio_transcript.done',
        'response.output_audio_transcript.done',
    }:
        text = str(event.get('transcript') or '')
        state['transcript'] = str(state.get('transcript') or '') + text
        return [('transcript', text)]
    if kind == 'session.updated':
        state['ready'] = True
        return [('ready', True)]
    if kind == 'response.function_call_arguments.done':
        return [
            (
                'tool',
                {
                    'call_id': str(event.get('call_id') or ''),
                    'name': str(event.get('name') or ''),
                    'arguments': str(event.get('arguments') or '{}'),
                },
            )
        ]
    if kind == 'conversation.item.input_audio_transcription.completed':
        return [('heard', str(event.get('transcript') or ''))]
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
        rate: int = PCM_RATE,
        tools: list[dict[str, Any]] | None = None,
        transcribe: str = '',
    ):
        self.ws = ws
        self.provider = ''
        self.pcm_rate = rate
        self.state: dict[str, Any] = {}
        try:
            ws.send_text(
                json.dumps(
                    build_session_update(
                        instructions, voice, rate, tools, transcribe
                    )
                )
            )
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
        tools: list[dict[str, Any]] | None = None,
    ) -> RealtimeCall:
        """Ouvre une session chez le provider.

        Args:
            provider: openai | xai.
            api_key: Clé provider (header only).
            model: Modèle realtime.
            instructions: Prompt système.
            voice: Voix synthèse.
            timeout: Timeout socket.
            tools: Les outils que l'agent peut appeler.

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
        rate = DEFAULT_RATES.get(provider, PCM_RATE)
        call = cls(
            ws,
            instructions,
            voice,
            rate,
            tools,
            TRANSCRIBE_MODELS.get(provider, ''),
        )
        call.provider = provider
        return call

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

    def send_tool_output(self, call_id: str, output: str) -> None:
        """Rend le résultat d'un outil, puis demande la suite.

        Raises:
            RealtimeError: Socket rompue.
        """
        try:
            self.ws.send_text(json.dumps(build_tool_output(call_id, output)))
            self.ws.send_text(json.dumps(build_response_create()))
        except WsError as exc:
            raise RealtimeError(f'WS: outil ({exc})') from exc

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
            if opcode == 0x2 and payload:
                actions.append(
                    ('audio', base64.b64encode(payload).decode('ascii'))
                )
                continue
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
