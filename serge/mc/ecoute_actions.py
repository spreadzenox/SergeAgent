#!/usr/bin/env python3
"""MC : un bouton de Mission Control lance son invocation (déclencheur en base)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event
from serge.interpreter.flow import fire_button


class _BoutonHandler(Protocol):
    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> Any: ...


if TYPE_CHECKING:
    _Base = _BoutonHandler
else:
    _Base = object


class EcouteActionsMixin(_Base):
    """POST /owner/api/bouton : ``{trigger_id, form}``."""

    def _api_bouton(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body() or {}
        trigger_id = str(body.get('trigger_id') or '').strip()
        form = body.get('form') or {}
        if not trigger_id or not isinstance(form, dict):
            self._refus(
                400,
                'Bouton inconnu.',
                'trigger',
                'Envoie {"trigger_id": "...", "form": {...}}.',
            )
            return
        with self._db() as conn:
            task_id = fire_button(conn, trigger_id, form)
            if task_id is None:
                self._refus(
                    409,
                    'Ce bouton ne peut pas lancer de tâche.',
                    'trigger',
                    'Le déclencheur ou son invocation est éteint, ou absent.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'bouton',
                    'trigger_id': trigger_id,
                    'task': task_id,
                },
            )
        self._send_json(200, {'ok': True, 'task_id': task_id})
