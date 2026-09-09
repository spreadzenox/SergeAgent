#!/usr/bin/env python3
"""CLI bot Discord : serve | verify | mirror-once (config + secrets)."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from kit.instance_file import DISCORD_ID_KEYS  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.discord.bot import Bot  # noqa: E402
from serge.discord.rest import bot_token, verify_token  # noqa: E402
from serge.policy import PolicyError, load_policy  # noqa: E402


class BotError(ValueError):
    pass


def load_discord_cfg(instance_file: str = '') -> dict[str, str]:
    """Table [discord] du TOML instance (ids, jamais de secret).

    Args:
        instance_file: Chemin TOML (défaut : SERGE_INSTANCE_FILE).

    Returns:
        Dict des 5 ids + instance_file.

    Raises:
        BotError: Fichier/table/ids manquants.
    """
    raw = (instance_file or os.environ.get('SERGE_INSTANCE_FILE', '')).strip()
    if not raw:
        raise BotError('SERGE_INSTANCE_FILE requis')
    try:
        data = tomllib.loads(Path(raw).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise BotError(f'instance illisible : {exc}') from exc
    table = data.get('discord') or {}
    cfg = {key: str(table.get(key) or '').strip() for key in DISCORD_ID_KEYS}
    missing = [key for key, value in cfg.items() if not value]
    if missing:
        raise BotError(f'discord.{missing[0]} manquant (revois le wizard)')
    cfg['instance_file'] = raw
    return cfg


def main(argv: list[str] | None = None) -> int:
    """CLI : serve | verify | mirror-once."""
    import argparse

    from serge.discord.rest import DiscordError

    parser = argparse.ArgumentParser(description='Serge Discord bot')
    parser.add_argument(
        'command',
        choices=('serve', 'verify', 'mirror-once'),
        nargs='?',
        default='serve',
    )
    args = parser.parse_args(argv)
    policy: dict[str, Any] = {}
    try:
        cfg = load_discord_cfg()
        token = bot_token()
        if not token:
            print(
                json.dumps(
                    {
                        'status': 'refused',
                        'error': 'discord-bot-token manquant',
                    }
                )
            )
            return 2
        policy = load_policy()
    except (BotError, PolicyError) as exc:
        print(json.dumps({'status': 'refused', 'error': str(exc)}))
        return 2
    if args.command == 'verify':
        try:
            me = verify_token(token)
            print(
                json.dumps(
                    {
                        'status': 'ok',
                        'bot': me.get('username'),
                        'id_present': bool(me.get('id')),
                    }
                )
            )
        except DiscordError as exc:
            print(json.dumps({'status': 'error', 'error': str(exc)}))
            return 1
        return 0
    conn = open_db(default_canon_path())
    try:
        bot = Bot(conn, policy, cfg, token)
        if args.command == 'mirror-once':
            count = bot.mirror_due()
            print(json.dumps({'status': 'ok', 'mirrored': count}))
            return 0
        bot.serve()
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
