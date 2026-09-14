#!/usr/bin/env python3
"""Inventaire de routes + Caddyfile (chemins optionnels sur le même hôte)."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from collections import defaultdict
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
                    'path': str(item.get('path') or ''),
                }
            )
    return out


def _caddyfile(routes: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for route in routes:
        if route.get('hostname') and route.get('upstream'):
            grouped[route['hostname']].append(route)
    blocks: list[str] = []
    for host, items in grouped.items():
        paths = [item for item in items if item.get('path')]
        roots = [item for item in items if not item.get('path')]
        if not paths and len(roots) == 1:
            blocks.append(
                f'{host} {{\n\treverse_proxy {roots[0]["upstream"]}\n}}\n'
            )
            continue
        lines = [f'{host} {{']
        for item in paths:
            lines.append(f'\thandle {item["path"]}* {{')
            lines.append(f'\t\treverse_proxy {item["upstream"]}')
            lines.append('\t}')
        if roots:
            lines.append('\thandle {')
            lines.append(f'\t\treverse_proxy {roots[0]["upstream"]}')
            lines.append('\t}')
        lines.append('}\n')
        blocks.append('\n'.join(lines))
    return ''.join(blocks) or '# vide\n'


def _save(inventory: Path, caddy: Path, routes: list[dict[str, str]]) -> None:
    inventory.parent.mkdir(parents=True, exist_ok=True)
    inventory.write_text(
        json.dumps({'routes': routes}, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )
    caddy.write_text(_caddyfile(routes), encoding='utf-8')


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
        'path': '',
    }


def _key(route: dict[str, str]) -> tuple[str, str]:
    return (route['hostname'], route.get('path') or '')


def upsert(
    hostname: str,
    upstream: str,
    venture_id: str,
    path: str = '',
) -> dict[str, Any]:
    """Ajoute ou remplace une route (hôte + chemin), puis réécrit Caddyfile."""
    inventory, caddy = _paths(_root())
    routes = _load_inventory(inventory)
    seen = {_key(route) for route in routes}
    mc = _mc_route()
    if mc and _key(mc) not in seen:
        routes.insert(0, mc)
        seen.add(_key(mc))
    if hostname:
        entry = {
            'hostname': hostname,
            'upstream': upstream,
            'venture_id': venture_id,
            'path': path,
        }
        routes = [r for r in routes if _key(r) != _key(entry)]
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
    parser.add_argument('--path', default='')
    parser.add_argument('--health-url', default='')
    parser.add_argument('--allow-unhealthy', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'render':
        print(json.dumps(render(), ensure_ascii=False))
        return 0
    print(
        json.dumps(
            upsert(args.hostname, args.upstream, args.venture_id, args.path),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
