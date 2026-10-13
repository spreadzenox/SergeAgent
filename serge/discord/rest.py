#!/usr/bin/env python3
"""Client REST Discord v10 (stdlib) : fils de forum, messages, callbacks.

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
# UA distinctif exigé : Python-urllib générique = 403 Cloudflare/Discord
# (prouvé bêta WSL : 403 vs 200 selon le seul User-Agent). Sans version
# (ne se périme pas ; l'important est qu'il soit distinctif).
USER_AGENT = 'DiscordBot (https://github.com/spreadzenox/SergeAgent)'
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


def _detail(exc: urllib.error.HTTPError) -> str:
    """Le message d'erreur que Discord renvoie, ou ``''``.

    Exemple : `` (50013 Missing Permissions)``.
    """
    try:
        body = json.loads(exc.read().decode('utf-8') if exc.fp else '{}')
    except (ValueError, AttributeError, OSError):
        return ''
    if not isinstance(body, dict) or not body.get('message'):
        return ''
    return f' ({body.get("code", "")} {body.get("message")})'[:300]


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
                'User-Agent': USER_AGENT,
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
            # Ce que Discord dit de l'erreur (son code et son message, sans
            # secret), pour le journal.
            detail = _detail(exc)
            if exc.code == 401:
                raise DiscordError(
                    f'AUTH: token Discord rejeté{detail}'
                ) from exc
            if exc.code == 403:
                raise DiscordError(
                    f'FORBIDDEN: permissions bot insuffisantes{detail}'
                ) from exc
            if exc.code == 404:
                raise DiscordError(
                    f'NOT_FOUND: canal/message inconnu{detail}'
                ) from exc
            if exc.code == 429:
                raise DiscordError('RATE_LIMITED: retry épuisés') from exc
            raise DiscordError(
                f'API: Discord HTTP {exc.code}{detail}'
            ) from exc
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
) -> str:
    """Ouvre un fil dans un forum, avec son premier message ; rend l'id du
    fil, qui est aussi celui de ce premier message.

    Raises:
        DiscordError: Voir _request.
    """
    result = _request(
        token,
        'POST',
        f'/channels/{forum_id}/threads',
        {'name': name[:100] or 'Ticket', 'message': message},
        base_url=base_url,
    )
    if not isinstance(result, dict) or not result.get('id'):
        raise DiscordError('API: ouverture du fil invalide')
    return str(result['id'])


def archive_thread(
    token: str,
    thread_id: str,
    archived: bool,
    *,
    base_url: str = DISCORD_API,
) -> None:
    """Archive un fil, ou le rouvre (pour modifier sa carte).

    Raises:
        DiscordError: Voir _request.
    """
    _request(
        token,
        'PATCH',
        f'/channels/{thread_id}',
        {'archived': archived},
        base_url=base_url,
    )


def _post_interaction(
    url: str, payload: dict[str, Any], timeout: float
) -> None:
    """POST sur une URL d'interaction (pas de token bot : celui de
    l'interaction est dans l'URL)."""
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json', 'User-Agent': USER_AGENT},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
    except urllib.error.HTTPError as exc:
        raise DiscordError(
            f'API: interaction HTTP {exc.code}{_detail(exc)}'
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DiscordError(f'NETWORK: interaction ({exc})') from exc


def interaction_callback(
    interaction_id: str,
    interaction_token: str,
    callback: dict[str, Any],
    *,
    base_url: str = DISCORD_API,
    timeout: float = 10.0,
) -> None:
    """Répond à une interaction, dans les 3 secondes.

    Types : 1 pong, 4 message, 5 deferred, 6 deferred update, 7 update,
    9 fenêtre de saisie.

    Raises:
        DiscordError: NETWORK/API (jamais AUTH : pas de secret ici).
    """
    _post_interaction(
        f'{base_url.rstrip("/")}/interactions/{interaction_id}/'
        f'{interaction_token}/callback',
        callback,
        timeout,
    )


def interaction_followup(
    application_id: str,
    interaction_token: str,
    message: dict[str, Any],
    *,
    base_url: str = DISCORD_API,
    timeout: float = 10.0,
) -> None:
    """Un message de suite, après la réponse (valable 15 minutes).

    Raises:
        DiscordError: NETWORK/API.
    """
    _post_interaction(
        f'{base_url.rstrip("/")}/webhooks/{application_id}/{interaction_token}',
        message,
        timeout,
    )
