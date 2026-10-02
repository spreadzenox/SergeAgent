#!/usr/bin/env python3
"""MC : changer un réglage, ou remettre sa valeur précédente.

Trois sortes de réglages, sur la page Policy :

- un réglage général (``policy_settings``, ``{cible: 'policy', id}``) ;
- un réglage d'invocation marqué « policy » (``invocation_settings``,
  ``{cible: 'invocation', invocation_id, name}``) ;
- un quota de table marqué « policy » (``table_quotas``,
  ``{cible: 'quota', id}``).

Chacun garde sa valeur précédente (qui, quand) : « Remettre la valeur
précédente » la remet, et l'actuelle devient la précédente (Q68).
"""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event, utcnow
from serge.interpreter.settings import check_setting
from serge.policy_store import previous_value, set_setting, setting_lock

# Le plus grand entier que SQLite range.
_SQLITE_MAX = 2**63 - 1


class _PolicyHandler(Protocol):
    app_config: Any

    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> Any: ...


if TYPE_CHECKING:
    _Base = _PolicyHandler
else:
    _Base = object


def _quota_problem(value: str) -> str:
    ok = (
        value.isascii()
        and value.isdigit()
        and len(value) <= 19
        and int(value) <= _SQLITE_MAX
    )
    return '' if ok else f'entier entre 0 et {_SQLITE_MAX} attendu'


def _change_invocation(
    conn: sqlite3.Connection, body: dict, value: str
) -> tuple[str, dict]:
    """Change un réglage d'invocation ; rend ``(problème, clé)``."""
    ident = str(body.get('invocation_id') or '')
    name = str(body.get('name') or '')
    key = {'invocation_id': ident, 'name': name}
    row = conn.execute(
        'SELECT type, min_value, max_value FROM invocation_settings'
        ' WHERE invocation_id=? AND name=? AND policy=1',
        (ident, name),
    ).fetchone()
    if row is None:
        return 'réglage inconnu', key
    if problem := check_setting(str(row[0]), value, row[1], row[2]):
        return problem, key
    now = utcnow()
    conn.execute(
        'UPDATE invocation_settings SET previous_value=value,'
        " previous_at=?, previous_by='mc', value=?, updated_at=?,"
        " updated_by='mc' WHERE invocation_id=? AND name=?",
        (now, value, now, ident, name),
    )
    return '', key


def _change_quota(
    conn: sqlite3.Connection, body: dict, value: str
) -> tuple[str, dict]:
    """Change un quota de table ; rend ``(problème, clé)``."""
    ident = str(body.get('id') or '')
    key = {'id': ident}
    if not conn.execute(
        'SELECT 1 FROM table_quotas WHERE id=? AND policy=1', (ident,)
    ).fetchone():
        return 'quota inconnu', key
    if problem := _quota_problem(value):
        return problem, key
    now = utcnow()
    conn.execute(
        'UPDATE table_quotas SET previous_value=max_value,'
        " previous_at=?, previous_by='mc', max_value=?, updated_at=?,"
        " updated_by='mc' WHERE id=?",
        (now, int(value), now, ident),
    )
    return '', key


def _previous(conn: sqlite3.Connection, cible: str, body: dict) -> tuple:
    """``(True, valeur)`` si le réglage visé a une valeur précédente."""
    if cible == 'policy':
        return previous_value(conn, str(body.get('id') or ''))
    if cible == 'invocation':
        row = conn.execute(
            'SELECT previous_value, previous_at FROM invocation_settings'
            ' WHERE invocation_id=? AND name=?',
            (
                str(body.get('invocation_id') or ''),
                str(body.get('name') or ''),
            ),
        ).fetchone()
    elif cible == 'quota':
        row = conn.execute(
            'SELECT previous_value, previous_at FROM table_quotas WHERE id=?',
            (str(body.get('id') or ''),),
        ).fetchone()
    else:
        row = None
    if row is None or not row[1]:
        return False, None
    return True, row[0]


def change_setting(
    conn: sqlite3.Connection, cible: str, body: dict, value: Any
) -> tuple[int, str, dict]:
    """Change le réglage visé par ``body``.

    Returns:
        ``(code HTTP, problème, clé)`` : 409 si la famille du réglage est
        verrouillée (un essai tourne), 400 si la valeur est refusée, 200 si
        c'est fait.
    """
    if cible == 'policy':
        ident = str(body.get('id') or '')
        key = {'id': ident}
        if lock := setting_lock(conn, ident):
            return 409, lock, key
        problem = set_setting(conn, ident, value, 'mc')
    elif cible == 'invocation':
        problem, key = _change_invocation(conn, body, str(value).strip())
    elif cible == 'quota':
        problem, key = _change_quota(conn, body, str(value).strip())
    else:
        problem, key = 'cible : policy, invocation ou quota', {}
    return (400 if problem else 200), problem, key


class PolicyActionsMixin(_Base):
    """POST /owner/api/reglage et /owner/api/reglage/precedent."""

    def _changer(self, body: dict, value: Any, acte: str) -> None:
        cible = str(body.get('cible') or '')
        with self._db() as conn:
            code, probleme, cle = change_setting(conn, cible, body, value)
            if probleme:
                self._refus(
                    code, f'Réglage refusé : {probleme}.', 'reglage', ''
                )
                return
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={'acte': acte, 'cible': cible, **cle, 'apres': value},
                # Un réglage général a son historique : « Lire l'historique ».
                rows=[('policy_settings', cle['id'])]
                if cible == 'policy'
                else (),
            )
        self._send_json(200, {'ok': True, **cle, 'value': value})

    def _api_reglage(self) -> None:
        """Change un réglage : ``{cible, …, value}``.

        La valeur est vérifiée (sorte, bornes, relations, verrou),
        enregistrée, et l'ancienne devient la valeur précédente.
        """
        if not self._require_owner():
            return
        body = self._json_body() or {}
        self._changer(body, body.get('value', ''), 'reglage')

    def _api_reglage_precedent(self) -> None:
        """Remet la valeur précédente d'un réglage : ``{cible, …}``."""
        if not self._require_owner():
            return
        body = self._json_body() or {}
        with self._db() as conn:
            found, value = _previous(conn, str(body.get('cible') or ''), body)
        if not found:
            self._refus(
                409,
                'Ce réglage n’a pas de valeur précédente.',
                'reglage',
                'Une valeur précédente existe après un premier changement.',
            )
            return
        self._changer(body, value, 'reglage_precedent')
