#!/usr/bin/env python3
"""Conservative scan of tracked repository content without printing matches."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
GIT_ENV_KEYS = frozenset(
    {'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_PREFIX'}
)


def clean_git_env() -> dict[str, str]:
    """Drop git location overrides so `-C ROOT` governs (hooks export GIT_DIR)."""
    return {k: v for k, v in os.environ.items() if k not in GIT_ENV_KEYS}


def repo_root() -> Path:
    """Scan the repo containing this script (live, kit worktree, or clone).

    SERGE_SYSTEM_ROOT overrides when explicitly set (tests, E2E trees).
    """
    override = os.environ.get('SERGE_SYSTEM_ROOT', '').strip()
    if override:
        return Path(override)
    completed = subprocess.run(
        ['git', 'rev-parse', '--show-toplevel'],
        cwd=SCRIPT_DIR,
        capture_output=True,
        text=True,
        check=False,
        env=clean_git_env(),
    )
    if completed.returncode == 0 and completed.stdout.strip():
        return Path(completed.stdout.strip())
    return SCRIPT_DIR.parent


ROOT = repo_root()
PATTERNS = {
    'private_key': re.compile(rb'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
    'openai_style_token': re.compile(rb'\bsk-[A-Za-z0-9_-]{20,}\b'),
    'github_token': re.compile(rb'\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b'),
    'aws_access_key': re.compile(rb'\bAKIA[A-Z0-9]{16}\b'),
    'google_api_key': re.compile(rb'\bAIza[A-Za-z0-9_-]{30,}\b'),
    'assigned_secret': re.compile(
        rb'(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)\b'
        rb'\s*[:=]\s*["\']?[A-Za-z0-9+/=_-]{12,}'
    ),
}
KNOWN_FIXTURE_MARKERS = {
    b'api_key=extremely-secret-value',
    b'api_key=very-secret-value',
    # tests/test_metagrok_voice.py fixtures (self-describing dummies, not keys)
    b'sk-test-permanent-not-used',
    b'sk-permanent-must-not-leave-server',
}


def tracked_files() -> list[Path]:
    try:
        output = subprocess.check_output(
            ['git', '-C', str(ROOT), 'ls-files', '-z', '--full-name'],
            env=clean_git_env(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ScanError(f'cannot list tracked files in {ROOT}: {exc}') from exc
    return [ROOT / item.decode() for item in output.split(b'\0') if item]


class ScanError(ValueError):
    pass


def main() -> int:
    findings: list[dict[str, str]] = []
    scanned = 0
    skipped: list[str] = []
    try:
        files = tracked_files()
    except ScanError as exc:
        print(
            json.dumps(
                {
                    'status': 'error',
                    'error': str(exc),
                    'secret_values_included': False,
                },
                indent=2,
            )
        )
        return 2
    for path in files:
        try:
            data = path.read_bytes()
        except OSError:
            skipped.append(path.relative_to(ROOT).as_posix())
            continue
        scanned += 1
        for fixture in KNOWN_FIXTURE_MARKERS:
            data = data.replace(fixture, b'[KNOWN_TEST_FIXTURE]')
        for label, pattern in PATTERNS.items():
            if pattern.search(data):
                findings.append(
                    {
                        'file': path.relative_to(ROOT).as_posix(),
                        'pattern': label,
                    }
                )
    report = {
        'status': 'ok' if not findings else 'failed',
        'root': str(ROOT),
        'tracked_files_scanned': scanned,
        'skipped_unreadable': skipped,
        'finding_count': len(findings),
        'findings': findings,
        'secret_values_included': False,
    }
    print(json.dumps(report, indent=2))
    return 0 if not findings else 2


if __name__ == '__main__':
    raise SystemExit(main())
