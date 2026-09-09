#!/usr/bin/env python3
"""Builder telephony: Asterisk configs, SMS route seed, voice readme."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kit.asterisk import AsteriskError, render_asterisk
from kit.builder.guards import BuilderError
from kit.instance_file import SMS_RECEIVER_UPSTREAM, SMS_VENTURE_ID

VOICE_README = """\
Serge voice grafts (instance files, safe to keep).

greeting.wav — optional owner-recorded greeting (wav, 8kHz mono ideal).
  Played on inbound/outbound legs when no OpenAI TTS key is present.
  With openai_api_key, greetings are synthesized and this file is ignored.

Consent and blocklist are managed at runtime, never here:
  python3 serge/voice/bridge.py consent-grant --to +336... --basis contract|consent
  python3 serge/voice/bridge.py consent-revoke --to +336...
  python3 serge/voice/bridge.py block-add --to +336... --reason bloctel
  python3 serge/voice/bridge.py status
"""


def write_asterisk(
    loaded: Mapping[str, Any],
    secrets: Mapping[str, str],
    config_root: Path,
    facts: Mapping[str, str],
) -> list[str]:
    try:
        rendered = render_asterisk(loaded, facts, secrets)
    except AsteriskError as exc:
        raise BuilderError(str(exc)) from exc
    dest_dir = config_root / 'asterisk'
    dest_dir.mkdir(parents=True, exist_ok=True)
    var_lib = dest_dir / 'var/lib/keys'
    var_lib.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for name, (text, mode) in sorted(rendered.items()):
        dest = dest_dir / name
        dest.write_text(text, encoding='utf-8')
        dest.chmod(mode)
        written.append(name)
    return written


def seed_sms_route(
    system_root: Path,
    installed_toml: Path,
    public_hostname: str,
) -> str:
    """Publish sms.<domain> -> sms receiver via the new tree's own broker."""
    hostname = f'sms.{public_hostname.strip().lower()}'
    script = system_root / 'orchestrator/web_ingress.py'
    if not script.is_file():
        raise BuilderError(
            'web_ingress.py missing from seed, cannot seed SMS route'
        )
    env = os.environ.copy()
    env['SERGE_SYSTEM_ROOT'] = str(system_root)
    env['SERGE_INSTANCE_FILE'] = str(installed_toml)
    # Never let the build reload a live Caddy on this host.
    env['SERGE_CADDY_BIN'] = '/nonexistent/serge-build-no-caddy'
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            'upsert',
            '--hostname',
            hostname,
            '--upstream',
            SMS_RECEIVER_UPSTREAM,
            '--venture-id',
            SMS_VENTURE_ID,
            '--health-url',
            f'http://{SMS_RECEIVER_UPSTREAM}/healthz',
            '--allow-unhealthy',
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr)[-500:]
        raise BuilderError(f'SMS route seed failed for {hostname}: {detail}')
    return hostname


def write_voice_readme(config_root: Path) -> Path:
    dest_dir = config_root / 'voice'
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / 'README.txt'
    dest.write_text(VOICE_README, encoding='utf-8')
    return dest
