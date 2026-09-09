#!/usr/bin/env python3
"""Build a virgin Serge instance from git archive + couple. Never rsync the VPS."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.builder import BuilderError, build_instance  # noqa: E402
from kit.instance_file import InstanceError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            'Instancie un Serge vierge (git archive + TOML + sidecar + mandat). '
            'N’écrit pas sur le VPS Julien sauf --confirm-live-instance-id.'
        ),
    )
    parser.add_argument('--instance-file', type=Path, required=True)
    parser.add_argument('--mandate', type=Path, required=True)
    parser.add_argument('--source-repo', type=Path, required=True)
    parser.add_argument('--git-sha', default='HEAD')
    parser.add_argument('--systemd-user-dir', type=Path)
    parser.add_argument(
        '--no-enable-units',
        action='store_true',
        help='Écrire les units sans systemctl (tests / dry-run).',
    )
    parser.add_argument(
        '--confirm-live-instance-id',
        default='',
        help='Doit être julien-vps pour autoriser les chemins live.',
    )
    args = parser.parse_args(argv)
    try:
        receipt = build_instance(
            instance_file=args.instance_file,
            mandate=args.mandate,
            source_repo=args.source_repo,
            git_sha=args.git_sha,
            systemd_user_dir=args.systemd_user_dir,
            enable=not args.no_enable_units,
            confirm_live_id=args.confirm_live_instance_id,
            kit_root=ROOT,
        )
    except (BuilderError, InstanceError, OSError, json.JSONDecodeError) as exc:
        print(f'erreur: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
