#!/usr/bin/env python3
"""Builder seed: git archive a SHA into a virgin, scrubbed tree + empty canon."""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from kit.builder.guards import BuilderError

WRITABLE_DIRS = (
    'state',
    'state/reporter',
    'state/snapshots',
    'queue/pending',
    'queue/running',
    'queue/review',
    'queue/rework',
    'queue/done',
    'queue/failed',
    'queue/human_block',
    'queue/archived',
    'evidence',
    'logs',
    'logs/asterisk',
    'reports',
    'projects',
    'orchestrator/runtime',
    'state/sms',
    'state/voice',
    'state/voice/records',
    'state/voice/tts',
    'state/voice/calls',
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def exclusions_payload(root: Path | None = None) -> dict[str, Any]:
    path = (root or _repo_root()) / 'schemas/serge.kit-exclusions.yaml'
    payload = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise BuilderError('kit exclusions unreadable')
    return payload


def resolve_git_sha(source_repo: Path, spec: str) -> str:
    completed = subprocess.run(
        ['git', '-C', str(source_repo), 'rev-parse', spec],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise BuilderError(f'git sha unreadable in {source_repo}: {spec}')
    return completed.stdout.strip()


def dest_is_empty(path: Path) -> bool:
    if not path.exists():
        return True
    if not path.is_dir():
        return False
    return not any(path.iterdir())


def git_archive_into(source_repo: Path, sha: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if not dest_is_empty(dest):
        raise BuilderError(f'system_root is not empty: {dest}')
    archive = subprocess.run(
        ['git', '-C', str(source_repo), 'archive', '--format=tar', sha],
        check=False,
        capture_output=True,
    )
    if archive.returncode != 0:
        detail = archive.stderr.decode('utf-8', errors='replace')[-400:]
        raise BuilderError(f'git archive failed: {detail}')
    extracted = subprocess.run(
        ['tar', '-x', '-C', str(dest)],
        input=archive.stdout,
        check=False,
        capture_output=True,
    )
    if extracted.returncode != 0:
        raise BuilderError('git archive extract failed')


def scrub_live_memory(
    system_root: Path, root: Path | None = None
) -> list[str]:
    payload = exclusions_payload(root)
    removed: list[str] = []
    for raw in payload.get('never_copy') or []:
        item = str(raw)
        if (
            item.startswith('~')
            or item.startswith('/')
            or item.startswith('*')
        ):
            if item.startswith('*.'):
                for match in system_root.rglob(item):
                    match.unlink(missing_ok=True)
                    removed.append(str(match.relative_to(system_root)))
            continue
        target = system_root / item
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(item)
        elif target.is_file():
            target.unlink()
            removed.append(item)
    return removed


def ensure_writable_tree(system_root: Path) -> None:
    for rel in WRITABLE_DIRS:
        (system_root / rel).mkdir(parents=True, exist_ok=True)


def create_empty_canon(system_root: Path) -> dict[str, Any]:
    db_path = system_root / 'state/serge.db'
    if db_path.exists():
        db_path.unlink()
    reducer = system_root / 'reducer/reducer.py'
    if reducer.is_file():
        env = os.environ.copy()
        env['SERGE_SYSTEM_ROOT'] = str(system_root)
        completed = subprocess.run(
            [sys.executable, str(reducer), '--db', str(db_path), 'init'],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        if completed.returncode != 0:
            raise BuilderError('reducer init failed for empty canon')
    else:
        sqlite3.connect(db_path).close()
    db_path.chmod(0o600)
    return {
        'path': str(db_path),
        'empty': True,
        'initialized': reducer.is_file(),
    }
