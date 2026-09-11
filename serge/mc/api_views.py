#!/usr/bin/env python3
"""MC API vues (GET) : trace, carte, memory items, memory search — mixin McHandler."""

from __future__ import annotations

from contextlib import AbstractContextManager
from sqlite3 import Connection
from typing import TYPE_CHECKING, Any, Protocol

from serge.mc.proj_analyse import project_memory_items
from serge.mc.proj_tickets import project_carte
from serge.mc.proj_trace import project_trace


class _ViewHandler(Protocol):
    headers: Any

    def _require_owner(self) -> bool: ...
    def _db(self) -> AbstractContextManager[Connection]: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _query(self) -> dict[str, str]: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...


if TYPE_CHECKING:
    _Base = _ViewHandler
else:
    _Base = object


class ApiViewsMixin(_Base):
    """Endpoints API en lecture (GET) pour l'owner."""

    def _api_trace(self) -> None:
        if not self._require_owner():
            return
        item_id = self._query().get('item', '')
        if not item_id:
            self._refus(
                400,
                'Paramètre item requis.',
                'item',
                'Exemple : …/api/trace?item=w1.',
            )
            return
        with self._db() as conn:
            trace = project_trace(conn, item_id)
        if trace is None:
            self._refus(
                404, 'Tâche introuvable.', 'trace', 'Vérifie l’identifiant.'
            )
            return
        self._send_json(200, trace)

    def _api_ticket_carte(self) -> None:
        if not self._require_owner():
            return
        ticket_id = self._query().get('ticket', '')
        if not ticket_id:
            self._refus(
                400,
                'Paramètre ticket requis.',
                'ticket',
                'Exemple : …/api/ticket/carte?ticket=t1.',
            )
            return
        with self._db() as conn:
            carte = project_carte(conn, ticket_id)
        if carte is None:
            self._refus(
                404, 'Ticket introuvable.', 'ticket', 'Vérifie l’identifiant.'
            )
            return
        self._send_json(200, carte)

    def _api_memory_items(self) -> None:
        if not self._require_owner():
            return
        query = self._query()
        try:
            page = int(query.get('page', '1'))
            taille = int(query.get('size', '20'))
        except (TypeError, ValueError):
            page, taille = -1, -1
        if page < 1 or taille < 1:
            self._refus(
                400,
                'Pagination invalide.',
                'page',
                'page et size : entiers >= 1.',
            )
            return
        with self._db() as conn:
            resultat = project_memory_items(conn, page, taille)
        self._send_json(200, resultat)

    def _api_memory_search(self) -> None:
        if not self._require_owner():
            return
        query = self._query().get('q', '').strip()
        if not query:
            self._refus(
                400,
                'Paramètre q requis.',
                'query',
                'Exemple : …/api/memory/search?q=tarifs.',
            )
            return
        with self._db() as conn:
            from serge.memory.search import memory_search

            try:
                resultat = memory_search(conn, query, point='mc_search')
            except Exception:
                resultat = {'results': [], 'tokens_used': 0}
        self._send_json(200, resultat)
