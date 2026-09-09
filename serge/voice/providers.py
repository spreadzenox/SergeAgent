#!/usr/bin/env python3
"""Turn-based voice providers: OpenAI STT/TTS + OpenRouter chat. Degrade, never crash."""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from serge.paths import config_root, system_root
from serge.secrets import read_secret_file

HTTP_TIMEOUT = 20.0
CHAT_MODEL_DEFAULT = 'openai/gpt-4o-mini'
TTS_VOICE = 'alloy'
TTS_MODEL = 'tts-1'
STT_MODEL = 'whisper-1'

SYSTEM_PROMPT = (
    'Tu es Serge, agent vocal commercial francophone. '
    'Réponds en français, une à deux phrases courtes maximum, sans markdown, '
    'sans listes, sans émoji. Reste courtois et concret. '
    "Si la conversation est terminée ou si l'interlocuteur dit au revoir, "
    'réponds exactement : Au revoir.'
)


__all__ = ['config_root', 'read_secret_file', 'system_root']


def secrets() -> dict[str, str]:
    root = config_root() / 'secrets'
    return {
        'openai': read_secret_file(root / 'openai-direct.env'),
        'openrouter': read_secret_file(root / 'openrouter-api-key'),
        'xai': read_secret_file(root / 'xai-voice.env'),
    }


def instance_llm_referer() -> str:
    raw = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    if not raw:
        return ''
    try:
        data = tomllib.loads(Path(raw).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError):
        return ''
    return str((data.get('llm') or {}).get('referer') or '')


def tts_cache_path(text: str, root: Path) -> Path:
    digest = hashlib.sha256(
        f'{TTS_MODEL}:{TTS_VOICE}:{text}'.encode()
    ).hexdigest()
    return root / 'state/voice/tts' / f'{digest}.wav'


def synthesize(text: str, api_key: str, root: Path) -> Path | None:
    """OpenAI TTS -> cached wav. None on any failure (caller degrades)."""
    dest = tts_cache_path(text, root)
    if dest.is_file() and dest.stat().st_size > 1000:
        return dest
    if not api_key:
        return None
    body = json.dumps(
        {
            'model': TTS_MODEL,
            'voice': TTS_VOICE,
            'input': text[:1000],
            'response_format': 'wav',
        }
    ).encode('utf-8')
    request = urllib.request.Request(
        'https://api.openai.com/v1/audio/speech',
        data=body,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            audio = response.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    if len(audio) < 1000:
        return None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(audio)
        dest.chmod(0o600)
    except OSError:
        return None
    return dest


def transcribe(wav_path: Path, api_key: str) -> str:
    """Whisper transcription (French). Empty string on any failure."""
    if not api_key or not wav_path.is_file() or wav_path.stat().st_size < 2000:
        return ''
    boundary = (
        '----sergevoice' + hashlib.sha256(os.urandom(16)).hexdigest()[:16]
    )
    try:
        audio = wav_path.read_bytes()
    except OSError:
        return ''
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="model"\r\n\r\n{STT_MODEL}\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="language"\r\n\r\nfr\r\n',
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="turn.wav"\r\n'
        'Content-Type: audio/wav\r\n\r\n',
    ]
    body = (
        parts[0].encode()
        + parts[1].encode()
        + parts[2].encode()
        + audio
        + f'\r\n--{boundary}--\r\n'.encode()
    )
    request = urllib.request.Request(
        'https://api.openai.com/v1/audio/transcriptions',
        data=body,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': f'multipart/form-data; boundary={boundary}',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            payload = json.loads(response.read())
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ):
        return ''
    if not isinstance(payload, dict):
        return ''
    return str(payload.get('text') or '').strip()


def chat_reply(history: list[dict[str, str]], api_key: str) -> str:
    """One OpenRouter chat turn. Empty string on any failure."""
    if not api_key:
        return ''
    model = os.environ.get('SERGE_VOICE_CHAT_MODEL', CHAT_MODEL_DEFAULT)
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}, *history[-8:]]
    body = json.dumps(
        {
            'model': model,
            'messages': messages,
            'max_tokens': 150,
            'temperature': 0.4,
        }
    ).encode('utf-8')
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
        'X-Title': 'Serge voice',
    }
    referer = instance_llm_referer()
    if referer:
        headers['HTTP-Referer'] = referer
    request = urllib.request.Request(
        'https://openrouter.ai/api/v1/chat/completions',
        data=body,
        headers=headers,
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            payload = json.loads(response.read())
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
    ):
        return ''
    try:
        choices = payload.get('choices') or []
        return str(choices[0]['message']['content']).strip()
    except (IndexError, KeyError, TypeError, AttributeError):
        return ''
