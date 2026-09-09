#!/usr/bin/env python3
"""Harnais live-prudent : DB isolée, cap session, prérequis live.

Tests live = vraies clés, allowlist proprio, volumes minimums, DB
jetable, cap session dur. Jamais de prod (SERGE_ENV=test exigé).
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from serge.db.store import open_db
from serge.policy import is_test_env, load_policy
from serge.testenv import load_test_allowlist


class SessionCapExceeded(ValueError):
    pass


class SessionCap:
    """Compteur dur d'actions externes par session de test live."""

    def __init__(self, max_actions: int):
        if max_actions < 1:
            raise ValueError('SessionCap max_actions >= 1')
        self.max_actions = max_actions
        self.spent = 0

    def spend(self, kind: str) -> int:
        """Consomme 1 action. Lève si le cap est atteint.

        Args:
            kind: Nature de l'action (log/claim).

        Returns:
            Le compteur après consommation.

        Raises:
            SessionCapExceeded: Cap atteint (le test doit s'arrêter).
        """
        if self.spent >= self.max_actions:
            raise SessionCapExceeded(f'cap session atteint ({kind} refusé)')
        self.spent += 1
        return self.spent


@contextmanager
def temp_canon() -> Iterator[tuple[sqlite3.Connection, Path]]:
    """Canon jetable (tmpdir + open_db). Jamais la prod.

    Yields:
        Tuple (connexion, chemin DB).
    """
    with tempfile.TemporaryDirectory(prefix='serge-test-') as raw:
        db_path = Path(raw) / 'canon.db'
        connection = open_db(db_path)
        try:
            yield connection, db_path
        finally:
            connection.close()


def require_live() -> Mapping[str, Any]:
    """Prérequis live-prudent ou SkipTest (à appeler en setUp).

    Returns:
        L'allowlist de test (emails, sms, discord).

    Raises:
        unittest.SkipTest: Hors SERGE_ENV=test ou allowlist absente.
    """
    if not is_test_env():
        raise unittest.SkipTest('live only (SERGE_ENV=test requis)')
    try:
        load_policy()
        return load_test_allowlist()
    except ValueError as exc:
        raise unittest.SkipTest(f'live indisponible : {exc}') from exc
