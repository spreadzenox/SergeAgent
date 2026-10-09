#!/usr/bin/env python3
"""Bot Discord : les tickets en message privé à chaque administrateur."""

from __future__ import annotations

from serge.discord.rest import (
    DiscordError,
    bot_token,
    create_dm,
    delete_message,
    edit_message,
    get_channel,
    interaction_callback,
    send_message,
    verify_token,
)

__all__ = [
    'DiscordError',
    'bot_token',
    'create_dm',
    'delete_message',
    'edit_message',
    'get_channel',
    'interaction_callback',
    'send_message',
    'verify_token',
]
