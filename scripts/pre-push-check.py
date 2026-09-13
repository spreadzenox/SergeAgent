#!/usr/bin/env python3
"""Pre-push : gates + suite complète (E2E + LLM live). Clé obligatoire.

Pas de clé OpenRouter = push refusé. La clé (env ou fichier instance)
n’est jamais affichée. CI PR n’appelle pas ce script.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.paths import config_root  # noqa: E402
from serge.secrets import read_secret_file  # noqa: E402

GATES = (
    [
        'uv',
        'run',
        'ruff',
        'check',
        'kit',
        'serge',
        'scripts/serge-builder.py',
        'scripts/serge-instance-wizard.py',
        'scripts/serge-mandate-wizard.py',
        'scripts/serge-install.py',
        'scripts/pre-push-check.py',
        'tests',
    ],
    [
        'uv',
        'run',
        'ty',
        'check',
        'kit',
        'serge',
        'scripts/serge-builder.py',
        'scripts/serge-instance-wizard.py',
        'scripts/serge-mandate-wizard.py',
        'scripts/pre-push-check.py',
    ],
    ['uv', 'run', 'python', 'scripts/scan-repo-secrets.py'],
)
INSTANCE_VARS = (
    'SERGE_INSTANCE_FILE',
    'SERGE_SYSTEM_ROOT',
    'SERGE_CONFIG_DIR',
    'SERGE_AGE_IDENTITY',
    'SERGE_SECRETS_DOTENV',
    'SERGE_MANDATE_PATH',
    'SERGE_POLICY_PATH',
)


def resolve_openrouter_key() -> str:
    """Clé OpenRouter : env d'abord, sinon fichier instance. Jamais loguée."""
    env = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if env:
        return env
    return read_secret_file(config_root() / 'secrets/openrouter-api-key')


def run_gates() -> int:
    """Ruff + ty + scan secrets (même périmètre que scripts/ci.sh)."""
    for cmd in GATES:
        if subprocess.run(cmd, cwd=ROOT, check=False).returncode != 0:
            return 1
    return 0


def live_llm_skipped(result: unittest.TestResult) -> bool:
    """True si le test OpenRouter réel a été skippé."""
    for test, _reason in result.skipped:
        ident = test.id()
        if 'test_live_llm' in ident or 'LiveLlmTests' in ident:
            return True
    return False


def run_suite(key: str) -> int:
    """Suite entière : E2E requis, LLM live allumé, instance locale hors jeu."""
    os.environ['SERGE_CI'] = '1'
    os.environ['SERGE_ENV'] = 'test'
    os.environ['OPENROUTER_API_KEY'] = key
    for name in INSTANCE_VARS:
        os.environ.pop(name, None)
    suite = unittest.TestLoader().discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(verbosity=1, stream=sys.stderr).run(suite)
    if live_llm_skipped(result):
        print('live LLM skippé malgré une clé — push refusé.', file=sys.stderr)
        return 1
    if not result.wasSuccessful():
        return 1
    return 0


def run_pre_push() -> int:
    """0 = ok, 1 = pas de clé, gates rouges, suite rouge ou LLM skippé."""
    key = resolve_openrouter_key()
    if not key:
        print(
            'pas de clé OpenRouter (env ou fichier instance) — push refusé.',
            file=sys.stderr,
        )
        return 1
    if run_gates() != 0:
        return 1
    return run_suite(key)


if __name__ == '__main__':
    raise SystemExit(run_pre_push())
