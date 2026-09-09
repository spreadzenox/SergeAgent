#!/usr/bin/env python3
"""Serge runner : exécute N cycles (scheduler + workers + expiry).

Policy invalide = refus de boot (exit 2). Canon = instance courante
(SERGE_SYSTEM_ROOT). Un résumé JSON par cycle sur stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.policy import PolicyError, load_policy  # noqa: E402
from serge.runner import run_once  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Serge runtime runner')
    parser.add_argument('--cycles', type=int, default=1)
    parser.add_argument('--max-items', type=int, default=10)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args(argv)
    try:
        policy = load_policy()
    except PolicyError as exc:
        print(json.dumps({'status': 'refused', 'error': str(exc)}))
        return 2
    cycles = 1 if args.once else max(1, args.cycles)
    conn = open_db(default_canon_path())
    try:
        for _ in range(cycles):
            summary = run_once(conn, policy, max_items=max(1, args.max_items))
            print(json.dumps({'status': 'ok', **summary}))
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
