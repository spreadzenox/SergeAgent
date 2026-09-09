#!/usr/bin/env python3
"""Client REST Discord v10 (stdlib) : forum, messages, embeds, callbacks.

Token en header uniquement, jamais logué. 429 = backoff borné puis erreur
typée. Toutes les erreurs sont DiscordError à code routable.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from serge.paths import config_root
from serge.secrets import read_secret_file

DISCORD_API = 'https://discord.com/api/v10'
MAX_429_RETRIES = 2


class DiscordError(ValueError):
    pass


def bot_token(root: Path | None = None) -> str:
    """Token bot depuis les secrets instance (jamais logué).

    Args:
        root: config_root (défaut : instance).

    Returns:
        Le token ou '' si absent.
    """
    base = root or config_root()
    return read_secret_file(base / 'secrets/discord-bot-token')


def _request(
    token: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    base_url: str = DISCORD_API,
    timeout: float = 20.0,
) -> Any:
    if not token:
        raise DiscordError('AUTH: token Discord manquant')
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    url = f'{base_url.rstrip("/")}{path}'
    attempt = 0
    while True:
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                'Authorization': f'Bot {token}',
                'Content-Type': 'application/json',
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode('utf-8')
                status = response.status
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_429_RETRIES:
                retry_after = 1.0
                try:
                    body = json.loads(
                        exc.read().decode('utf-8') if exc.fp else '{}'
                    )
                    retry_after = float(body.get('retry_after', 1.0))
                except (ValueError, AttributeError):
                    pass
                time.sleep(min(10.0, max(0.5, retry_after)))
                attempt += 1
                continue
            if exc.code == 401:
                raise DiscordError('AUTH: token Discord rejeté') from exc
            if exc.code == 403:
                raise DiscordError(
                    'FORBIDDEN: permissions bot insuffisantes'
                ) from exc
            if exc.code == 404:
                raise DiscordError('NOT_FOUND: canal/message inconnu') from exc
            if exc.code == 429:
                raise DiscordError('RATE_LIMITED: retry épuisés') from exc
            raise DiscordError(f'API: Discord HTTP {exc.code}') from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DiscordError(
                f'NETWORK: Discord injoignable ({exc})'
            ) from exc
        if status == 204 or not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DiscordError('API: Discord JSON illisible') from exc


def verify_token(token: str, *, base_url: str = DISCORD_API) -> dict[str, Any]:
    """Vérifie le token (GET /users/@me). Retourne l'utilisateur bot.

    Raises:
        DiscordError: AUTH/NETWORK/API.
    """
    result = _request(token, 'GET', '/users/@me', base_url=base_url)
    if not isinstance(result, dict) or not result.get('id'):
        raise DiscordError('API: réponse /users/@me invalide')
    return result


def get_channel(
    token: str, channel_id: str, *, base_url: str = DISCORD_API
) -> dict[str, Any]:
    """Lit un canal (nom, type...). Sert aux vérifications pré-envoi.

    Raises:
        DiscordError: Voir _request.
    """
    result = _request(
        token, 'GET', f'/channels/{channel_id}', base_url=base_url
    )
    if not isinstance(result, dict):
        raise DiscordError('API: réponse canal invalide')
    return result


def send_message(
    token: str,
    channel_id: str,
    payload: dict[str, Any],
    *,
    base_url: str = DISCORD_API,
) -> dict[str, Any]:
    """Envoie un message ({content?, embeds?, components?}).

    Raises:
        DiscordError: Voir _request.
    """
    result = _request(
        token,
        'POST',
        f'/channels/{channel_id}/messages',
        payload,
        base_url=base_url,
    )
    if not isinstance(result, dict):
        raise DiscordError('API: réponse message invalide')
    return result


def edit_message(
    token: str,
    channel_id: str,
    message_id: str,
    payload: dict[str, Any],
    *,
    base_url: str = DISCORD_API,
) -> dict[str, Any]:
    """Édite un message (embed/boutons à jour, idempotent).

    Raises:
        DiscordError: Voir _request.
    """
    result = _request(
        token,
        'PATCH',
        f'/channels/{channel_id}/messages/{message_id}',
        payload,
        base_url=base_url,
    )
    if not isinstance(result, dict):
        raise DiscordError('API: réponse édition invalide')
    return result


def list_messages(
    token: str,
    channel_id: str,
    limit: int = 5,
    *,
    base_url: str = DISCORD_API,
) -> list[dict[str, Any]]:
    """Liste les derniers messages (post starter, dédup...).

    Raises:
        DiscordError: Voir _request.
    """
    result = _request(
        token,
        'GET',
        f'/channels/{channel_id}/messages?limit={max(1, min(50, limit))}',
        base_url=base_url,
    )
    if not isinstance(result, list):
        raise DiscordError('API: réponse liste messages invalide')
    return [item for item in result if isinstance(item, dict)]


def delete_message(
    token: str,
    channel_id: str,
    message_id: str,
    *,
    base_url: str = DISCORD_API,
) -> None:
    """Supprime un message (cleanup tests).

    Raises:
        DiscordError: Voir _request.
    """
    _request(
        token,
        'DELETE',
        f'/channels/{channel_id}/messages/{message_id}',
        base_url=base_url,
    )


def create_forum_post(
    token: str,
    forum_id: str,
    name: str,
    message: dict[str, Any],
    *,
    base_url: str = DISCORD_API,
) -> dict[str, Any]:
    """Crée un post forum = thread + message initial (carte ticket).

    Args:
        token: Token bot.
        forum_id: Canal forum.
        name: Titre du post (≤ 100c).
        message: {content?, embeds?, components?}.

    Returns:
        Le thread créé (id du post).

    Raises:
        DiscordError: Voir _request.
    """
    result = _request(
        token,
        'POST',
        f'/channels/{forum_id}/threads',
        {
            'name': name[:100],
            'auto_archive_duration': 10080,
            'message': message,
        },
        base_url=base_url,
    )
    if not isinstance(result, dict) or not result.get('id'):
        raise DiscordError('API: création post forum invalide')
    return result


def interaction_callback(
    interaction_id: str,
    interaction_token: str,
    callback: dict[str, Any],
    *,
    base_url: str = DISCORD_API,
    timeout: float = 10.0,
) -> None:
    """Ack une interaction (pas de token bot : token d'interaction).

    Types : 1 pong, 4 message, 5 deferred, 6 deferred update, 7 update.

    Raises:
        DiscordError: NETWORK/API (jamais AUTH : pas de secret ici).
    """
    url = (
        f'{base_url.rstrip("/")}/interactions/{interaction_id}/'
        f'{interaction_token}/callback'
    )
    data = json.dumps(callback, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
    except urllib.error.HTTPError as exc:
        raise DiscordError(
            f'API: callback interaction HTTP {exc.code}'
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DiscordError(f'NETWORK: callback ({exc})') from exc
