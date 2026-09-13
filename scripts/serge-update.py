#!/usr/bin/env python3
"""Met à jour le code d’une instance déjà construite (overlay git archive)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.builder.guards import BuilderError  # noqa: E402
from kit.instance_file import InstanceError  # noqa: E402
from kit.update import update_instance  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Update overlay Serge')
    parser.add_argument('--instance-file', type=Path, required=True)
    parser.add_argument('--source-repo', type=Path, default=ROOT)
    parser.add_argument('--git-sha', default='HEAD')
    parser.add_argument('--confirm-live-instance-id', default='')
    parser.add_argument('--systemd-user-dir', type=Path)
    args = parser.parse_args(argv)
    try:
        receipt = update_instance(
            instance_file=args.instance_file,
            source_repo=args.source_repo,
            git_sha=args.git_sha,
            confirm_live_id=args.confirm_live_instance_id,
            kit_root=ROOT,
            systemd_user_dir=args.systemd_user_dir,
        )
    except (BuilderError, InstanceError, OSError) as exc:
        print(f'erreur: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
