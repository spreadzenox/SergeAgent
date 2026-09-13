#!/usr/bin/env python3
"""Déploie sur la machine courante (VPS). Secrets via l’environnement local."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kit.builder.guards import BuilderError  # noqa: E402
from kit.deploy import deploy_instance  # noqa: E402
from kit.instance_file import InstanceError  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Deploy Serge sur cet hôte')
    parser.add_argument(
        '--instance-file',
        type=Path,
        default=os.environ.get('SERGE_DEPLOY_INSTANCE_FILE', '') or None,
    )
    parser.add_argument(
        '--mandate',
        type=Path,
        default=os.environ.get('SERGE_DEPLOY_MANDATE', '') or None,
    )
    parser.add_argument('--source-repo', type=Path, default=ROOT)
    parser.add_argument(
        '--git-sha',
        default=os.environ.get('GITHUB_SHA', 'HEAD'),
    )
    parser.add_argument(
        '--confirm-live-instance-id',
        default=os.environ.get('SERGE_DEPLOY_CONFIRM_LIVE_ID', 'julien-vps'),
    )
    args = parser.parse_args(argv)
    if args.instance_file is None or args.mandate is None:
        print(
            'erreur: SERGE_DEPLOY_INSTANCE_FILE et SERGE_DEPLOY_MANDATE requis',
            file=sys.stderr,
        )
        return 2
    try:
        receipt = deploy_instance(
            instance_file=args.instance_file,
            mandate=args.mandate,
            source_repo=args.source_repo,
            git_sha=args.git_sha,
            confirm_live_id=args.confirm_live_instance_id,
            kit_root=ROOT,
        )
    except (BuilderError, InstanceError, OSError) as exc:
        print(f'erreur: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
