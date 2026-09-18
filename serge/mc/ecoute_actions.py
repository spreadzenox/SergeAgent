#!/usr/bin/env python3
"""Actions Mission Control de l'onglet Écoute."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event
from serge.listen.memory import create_cycle
from serge.policy_snapshots import policy_en_vigueur
from serge.scheduler import enqueue


class _ListenHandler(Protocol):
    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> Any: ...


if TYPE_CHECKING:
    _Base = _ListenHandler
else:
    _Base = object


class EcouteActionsMixin(_Base):
    """Mutations owner du cycle de pré-prospection."""

    def _api_listen_settings(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(400, 'Corps JSON requis.', 'json', 'n et p requis.')
            return
        self._refus(
            410,
            'Les paramètres Écoute se modifient dans Policy.',
            'policy_only',
            'Ouvre Policy > Écoute du web.',
        )

    def _api_listen_start(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body() or {}
        guide = str(body.get('guide') or '').strip()
        with self._db() as conn:
            policy = policy_en_vigueur(conn)
            listen = policy.get('listen') or {}
            needs_target = int(listen['discovery_needs_target'])
            business_target = int(listen['poc_business_target'])
            cycle_id = create_cycle(
                conn, guide, needs_target, business_target
            )
            item_id = enqueue(
                conn,
                kind='listen.business_cycle',
                idempotency_key=f'listen:business_cycle:{cycle_id}',
                priority=50,
                payload={'cycle_id': cycle_id},
            )
            append_event(
                conn,
                actor='owner',
                type='listen.cycle_start',
                payload={'cycle_id': cycle_id, 'work_item_id': item_id},
            )
        self._send_json(200, {'ok': True, 'cycle_id': cycle_id, 'work_item_id': item_id})
