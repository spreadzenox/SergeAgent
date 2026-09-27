#!/usr/bin/env python3
"""MC : modifier une invocation (prompt, niveau, file, priorité, allumée).

Le changement est écrit dans ``invocations`` et noté au journal ; la
prochaine tâche de l'invocation en tient compte, sans redémarrage. Créer
une invocation ou changer le reste de ses réglages viendra au lot 13.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from sqlite3 import Connection
from typing import TYPE_CHECKING, Protocol

from serge.db.store import append_event, utcnow

TIERS = frozenset({'fast', 'mid', 'smart'})


class _Handler(Protocol):
    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> AbstractContextManager[Connection]: ...


if TYPE_CHECKING:
    _Base = _Handler
else:
    _Base = object


def _changements(body: dict) -> tuple[dict[str, object], str]:
    """Les colonnes à modifier, ou le champ refusé."""
    updates: dict[str, object] = {}
    if 'prompt' in body:
        if not isinstance(body['prompt'], str):
            return {}, 'prompt'
        updates['prompt'] = body['prompt']
    if 'model_tier' in body:
        if body['model_tier'] not in TIERS:
            return {}, 'model_tier'
        updates['model_tier'] = body['model_tier']
    if 'priority' in body:
        priority = body['priority']
        if (
            isinstance(priority, bool)
            or not isinstance(priority, int)
            or not 0 <= priority <= 100
        ):
            return {}, 'priority'
        updates['priority'] = priority
    if 'enabled' in body:
        if not isinstance(body['enabled'], bool):
            return {}, 'enabled'
        updates['enabled'] = int(body['enabled'])
    if 'queue_id' in body:
        if not isinstance(body['queue_id'], str) or not body['queue_id']:
            return {}, 'queue_id'
        updates['queue_id'] = body['queue_id']
    return updates, ''


AIDES = {
    'prompt': 'Texte attendu.',
    'model_tier': 'Valeurs : fast, mid ou smart.',
    'priority': 'Entier de 0 à 100.',
    'enabled': 'Booléen attendu.',
    'queue_id': 'Une file en base : conversations ou works.',
}


class LlmActionsMixin(_Base):
    """POST /owner/api/invocation."""

    def _api_invocation(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"invocation_id":"...","prompt":"..."}.',
            )
            return
        ident = str(body.get('invocation_id') or '').strip()
        if not ident:
            self._refus(
                400,
                'invocation_id requis.',
                'invocation',
                'Identifiant de l’invocation.',
            )
            return
        updates, refuse = _changements(body)
        if refuse:
            self._refus(400, f'{refuse} invalide.', refuse, AIDES[refuse])
            return
        if not updates:
            self._refus(
                400,
                'Rien à modifier.',
                'fields',
                'Donne prompt, model_tier, queue_id, priority ou enabled.',
            )
            return
        with self._db() as conn:
            if (
                conn.execute(
                    "SELECT 1 FROM invocations WHERE id=? AND deleted_at=''",
                    (ident,),
                ).fetchone()
                is None
            ):
                self._refus(
                    404,
                    'Invocation introuvable.',
                    'invocation',
                    'Identifiant absent de la table invocations.',
                )
                return
            if (
                'queue_id' in updates
                and not conn.execute(
                    'SELECT 1 FROM queues WHERE id=?', (updates['queue_id'],)
                ).fetchone()
            ):
                self._refus(
                    400, 'queue_id invalide.', 'queue_id', AIDES['queue_id']
                )
                return
            columns = ', '.join(f'{key}=?' for key in updates)
            conn.execute(
                f'UPDATE invocations SET {columns}, updated_at=?,'
                " updated_by='mc' WHERE id=?",
                (*updates.values(), utcnow(), ident),
            )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'invocation_edit',
                    'invocation_id': ident,
                    'fields': sorted(updates),
                },
            )
        self._send_json(200, {'ok': True, 'invocation_id': ident})
