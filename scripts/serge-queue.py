#!/usr/bin/env python3
"""Le runner : vide une file de tâches, sans fin, une tâche après l'autre.

Deux copies tournent en même temps, une par file :
``serge-queue.py --queue conversations`` et ``serge-queue.py --queue works``.
Chaque tâche est enregistrée en base dès qu'elle est finie. Policy
invalide = refus de démarrer (code 2). La base est celle de l'instance
courante (``SERGE_SYSTEM_ROOT``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.interpreter.queue import run_forever  # noqa: E402
from serge.policy import PolicyError  # noqa: E402
from serge.policy_store import policy_en_vigueur  # noqa: E402

QUEUES = ('conversations', 'works')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Vider une file de Serge')
    parser.add_argument('--queue', choices=QUEUES, required=True)
    args = parser.parse_args(argv)
    conn = open_db(default_canon_path())
    try:
        try:
            policy_en_vigueur(conn)
            conn.commit()
        except PolicyError as exc:
            print(json.dumps({'status': 'refused', 'error': str(exc)}))
            return 2
        print(json.dumps({'status': 'started', 'queue': args.queue}))
        run_forever(conn, args.queue)
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
