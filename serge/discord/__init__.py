#!/usr/bin/env python3
"""Bot Discord (H) : miroir temps réel des tickets (DB = vérité)."""

from __future__ import annotations

from serge.discord.rest import (
    DiscordError,
    bot_token,
    create_forum_post,
    delete_message,
    edit_message,
    get_channel,
    interaction_callback,
    list_messages,
    send_message,
    verify_token,
)

__all__ = [
    'DiscordError',
    'bot_token',
    'create_forum_post',
    'delete_message',
    'edit_message',
    'get_channel',
    'interaction_callback',
    'list_messages',
    'send_message',
    'verify_token',
]
