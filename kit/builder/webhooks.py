#!/usr/bin/env python3
"""Seed Caddy : route Stripe sur le hostname public (même hôte que le MC)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from kit.builder.guards import BuilderError
from serge.collect.webhook import (
    STRIPE_RECEIVER_UPSTREAM,
    STRIPE_VENTURE_ID,
    STRIPE_WEBHOOK_PATH,
    public_webhook_url,
)


def seed_stripe_route(
    system_root: Path,
    installed_toml: Path,
    public_hostname: str,
    *,
    kit_root: Path | None = None,
) -> str:
    """Publie https://<domaine>/hooks/stripe → receiver loopback.

    Args:
        system_root: Racine d’instance (inventaire Caddy).
        installed_toml: Couple déjà posé (hostname MC).
        public_hostname: Domaine public d’instance.
        kit_root: Checkout kit (fallback si l’archive n’a pas encore caddy.py).

    Returns:
        URL HTTPS à coller dans le Dashboard Stripe.

    Raises:
        BuilderError: Renderer Caddy absent ou upsert en échec.
        ValueError: Hostname vide.
    """
    url = public_webhook_url(public_hostname)
    host = url.removeprefix('https://').split('/', 1)[0]
    candidates = []
    if kit_root is not None:
        candidates.append(kit_root / 'serge/ingress/caddy.py')
    candidates.append(system_root / 'serge/ingress/caddy.py')
    script = next((path for path in candidates if path.is_file()), None)
    if script is None:
        raise BuilderError(
            'serge/ingress/caddy.py manquant, impossible de semer Stripe'
        )
    env = os.environ.copy()
    env['SERGE_SYSTEM_ROOT'] = str(system_root)
    env['SERGE_INSTANCE_FILE'] = str(installed_toml)
    env['SERGE_CADDY_BIN'] = '/nonexistent/serge-build-no-caddy'
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            'upsert',
            '--hostname',
            host,
            '--path',
            STRIPE_WEBHOOK_PATH,
            '--upstream',
            STRIPE_RECEIVER_UPSTREAM,
            '--venture-id',
            STRIPE_VENTURE_ID,
            '--allow-unhealthy',
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + completed.stderr)[-500:]
        raise BuilderError(f'Stripe route seed failed for {url}: {detail}')
    return url
