#!/usr/bin/env python3
"""Inventaire de routes + Caddyfile (remplace orchestrator/web_ingress)."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from pathlib import Path
from typing import Any

MC_UPSTREAM = '127.0.0.1:8790'
MC_VENTURE = 'serge-owner-mission-control'


def _root() -> Path:
    raw = os.environ.get('SERGE_SYSTEM_ROOT', '').strip()
    if not raw:
        raise SystemExit('SERGE_SYSTEM_ROOT manquant')
    return Path(raw)


def _paths(root: Path) -> tuple[Path, Path]:
    folder = root / 'state/web-ingress'
    return folder / 'inventory.json', folder / 'Caddyfile'


def _load_inventory(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except ValueError:
        return []
    raw = data.get('routes') if isinstance(data, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if isinstance(item, dict) and item.get('hostname'):
            out.append(
                {
                    'hostname': str(item['hostname']),
                    'upstream': str(item.get('upstream') or ''),
                    'venture_id': str(item.get('venture_id') or ''),
                }
            )
    return out


def _save(inventory: Path, caddy: Path, routes: list[dict[str, str]]) -> None:
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text(
        json.dumps({'routes': routes}, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    lines = [
        f'{route["hostname"]} {{\n\treverse_proxy {route["upstream"]}\n}}\n'
        for route in routes
        if route.get('hostname') and route.get('upstream')
    ]
    caddy.write_text(''.join(lines) or '# vide\n', encoding='utf-8')


def _mc_route() -> dict[str, str] | None:
    raw = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    if not raw:
        return None
    try:
        data = tomllib.loads(Path(raw).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    host = str((data.get('identity') or {}).get('public_hostname') or '')
    if not host:
        return None
    return {
        'hostname': host,
        'upstream': MC_UPSTREAM,
        'venture_id': MC_VENTURE,
    }


def upsert(hostname: str, upstream: str, venture_id: str) -> dict[str, Any]:
    """Ajoute ou remplace une route, puis réécrit le Caddyfile."""
    inventory, caddy = _paths(_root())
    routes = _load_inventory(inventory)
    seen = {route['hostname'] for route in routes}
    mc = _mc_route()
    if mc and mc['hostname'] not in seen:
        routes.insert(0, mc)
        seen.add(mc['hostname'])
    if hostname:
        entry = {
            'hostname': hostname,
            'upstream': upstream,
            'venture_id': venture_id,
        }
        routes = [r for r in routes if r['hostname'] != hostname]
        routes.append(entry)
    _save(inventory, caddy, routes)
    return {'status': 'ok', 'routes': len(routes)}


def render() -> dict[str, Any]:
    """Réécrit le Caddyfile depuis l'inventaire."""
    inventory, caddy = _paths(_root())
    routes = _load_inventory(inventory)
    _save(inventory, caddy, routes)
    return {'status': 'ok', 'routes': len(routes)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Caddy ingress Serge')
    parser.add_argument('command', choices=('upsert', 'render'))
    parser.add_argument('--hostname', default='')
    parser.add_argument('--upstream', default='')
    parser.add_argument('--venture-id', default='')
    parser.add_argument('--health-url', default='')
    parser.add_argument('--allow-unhealthy', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'render':
        print(json.dumps(render(), ensure_ascii=False))
        return 0
    print(
        json.dumps(
            upsert(args.hostname, args.upstream, args.venture_id),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
