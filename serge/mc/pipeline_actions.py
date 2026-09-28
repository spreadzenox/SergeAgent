#!/usr/bin/env python3
"""MC : les actions sur le pipeline.

Le bouton d'un déclencheur, relancer une tâche, et les tables qu'une
invocation voit pour comparer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event
from serge.interpreter.flow import fire_button
from serge.interpreter.tasks import relaunch_task
from serge.mc.proj_vues import changer_comparaison


class _PipelineHandler(Protocol):
    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> Any: ...


if TYPE_CHECKING:
    _Base = _PipelineHandler
else:
    _Base = object


class PipelineActionsMixin(_Base):
    """POST /owner/api/bouton, /tache/relancer et /invocation/comparer."""

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

    def _api_tache_relancer(self) -> None:
        """Remet une tâche échouée dans sa file : ``{task_id}``."""
        if not self._require_owner():
            return
        body = self._json_body() or {}
        task_id = str(body.get('task_id') or '').strip()
        with self._db() as conn:
            if not task_id or not relaunch_task(conn, task_id):
                self._refus(
                    409,
                    'Cette tâche ne peut pas être relancée.',
                    'task',
                    'Seule une tâche échouée peut être relancée.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='task.relaunched',
                payload={'task': task_id},
            )
        self._send_json(200, {'ok': True, 'task_id': task_id})

    def _api_comparer(self) -> None:
        """Ajoute, retire ou remet une table à comparer.

        Corps : ``{invocation_id, table, voir}``.
        """
        if not self._require_owner():
            return
        body = self._json_body() or {}
        ident = str(body.get('invocation_id') or '').strip()
        table = str(body.get('table') or '').strip()
        voir = body.get('voir')
        if not ident or not table or not isinstance(voir, bool):
            self._refus(
                400,
                'Demande incomplète.',
                'comparer',
                'Envoie {"invocation_id": "...", "table": "...", "voir": true}.',
            )
            return
        with self._db() as conn:
            if not changer_comparaison(conn, ident, table, voir, 'owner'):
                self._refus(
                    409,
                    'Cette table ne peut pas être vue par cette invocation.',
                    'comparer',
                    'La table doit être décrite (table_views) et'
                    ' l’invocation doit exister.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='invocation.compare',
                payload={'invocation': ident, 'table': table, 'voir': voir},
            )
        self._send_json(200, {'ok': True})
