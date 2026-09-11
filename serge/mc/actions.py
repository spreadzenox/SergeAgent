#!/usr/bin/env python3
"""MC actions : handlers API (trace + mutations) — mixin McHandler.

B3 : adaptateur sans logique (tools partagés tickets/registry + audit).
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from sqlite3 import Connection
from typing import Any, Protocol

from serge.db.store import append_event
from serge.mc.proj_trace import project_trace
from serge.registry import KillError, poser_kill, retirer_kill
from serge.tickets import already_applied, decide
from serge.tickets.shared import TicketError, record_event

MAX_FORM_BYTES = 4096

ACTES_TICKET = {
    'approuver': 'APPROVED',
    'rejeter': 'REJECTED',
    'editer': 'EDITED',
}


class _Handler(Protocol):
    headers: Any
    rfile: Any

    def _require_owner(self) -> bool: ...
    def _db(self) -> AbstractContextManager[Connection]: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _query(self) -> dict[str, str]: ...


class ActionsMixin(_Handler):
    """Handlers API (self = handler HTTP, membres via _Handler)."""

    def _json_body(self) -> dict | None:
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except (TypeError, ValueError):
            return None
        if length <= 0 or length > MAX_FORM_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None:
        self._send_json(http, {'erreur': erreur, 'code': code, 'aide': aide})

    def _api_trace(self) -> None:
        if not self._require_owner():
            return
        item_id = self._query().get('item', '')
        if not item_id:
            self._send_json(
                400,
                {
                    'erreur': 'Paramètre item requis.',
                    'code': 'item',
                    'aide': 'Exemple : …/api/trace?item=w1.',
                },
            )
            return
        with self._db() as conn:
            trace = project_trace(conn, item_id)
        if trace is None:
            self._send_json(
                404,
                {
                    'erreur': 'Tâche introuvable.',
                    'code': 'trace',
                    'aide': 'Vérifie l’identifiant.',
                },
            )
            return
        self._send_json(200, trace)

    def _api_kill(self) -> None:
        self._mutation_kill(False)

    def _api_unkill(self) -> None:
        self._mutation_kill(True)

    def _mutation_kill(self, annuler: bool) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400, 'Corps JSON requis.', 'json', 'Envoie {"point": "x"}.'
            )
            return
        point = str(body.get('point') or '')
        decision = str(body.get('decision_id') or '')
        ttl_h = 24
        if not annuler:
            try:
                ttl_h = int(body.get('ttl_h', 24))
            except (TypeError, ValueError):
                ttl_h = -1
            if ttl_h <= 0:
                self._refus(400, 'TTL invalide.', 'ttl', 'ttl_h : entier > 0.')
                return
        with self._db() as conn:
            try:
                if annuler:
                    resultat = retirer_kill(conn, point, decision_id=decision)
                else:
                    resultat = poser_kill(
                        conn,
                        point,
                        str(body.get('raison') or ''),
                        decision_id=decision,
                        ttl_h=ttl_h,
                    )
            except KillError as exc:
                message = str(exc)
                if 'pas de kill' in message:
                    self._refus(
                        404,
                        'Aucun kill actif pour ce point.',
                        'kill',
                        'Rien à retirer (expiré ou jamais posé).',
                    )
                elif 'inconnu' in message:
                    self._refus(
                        404,
                        f'Point inconnu : {point}.',
                        'point',
                        'Vois la matrice P2 (noms exacts).',
                    )
                else:
                    self._refus(
                        400,
                        'Raison requise.',
                        'raison',
                        'Explique pourquoi (traçabilité).',
                    )
                return
        self._send_json(200, {'ok': True, **resultat})

    def _api_ticket_acte(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"ticket_id": "t..", "acte": "approuver"}.',
            )
            return
        ticket_id = str(body.get('ticket_id') or '')
        acte = str(body.get('acte') or '')
        note = str(body.get('note') or '')
        decision = str(body.get('decision_id') or '')
        if not ticket_id:
            self._refus(
                400,
                'ticket_id requis.',
                'ticket',
                'Identifiant du ticket visé.',
            )
            return
        outcome = ACTES_TICKET.get(acte)
        if outcome is None:
            self._refus(
                400,
                f'Acte inconnu : {acte}.',
                'acte',
                'Actes : approuver, rejeter, editer.',
            )
            return
        if outcome == 'EDITED' and not note.strip():
            self._refus(
                400,
                'Note requise pour éditer.',
                'note',
                'Décris la modification.',
            )
            return
        with self._db() as conn:
            if decision and already_applied(conn, ticket_id, decision):
                self._send_json(200, {'ok': True, 'duplicata': 'true'})
                return
            try:
                decide(conn, ticket_id, outcome, actor='owner', note=note)
            except TicketError as exc:
                if 'inconnu' in str(exc):
                    self._refus(
                        404,
                        'Ticket introuvable.',
                        'ticket',
                        'Vérifie l’identifiant.',
                    )
                else:
                    self._refus(
                        409,
                        'Ticket déjà traité.',
                        'etat',
                        'État incompatible (décidé, expiré ou clôturé).',
                    )
                return
            if decision:
                record_event(
                    conn,
                    ticket_id,
                    'owner',
                    f'mc.{acte}',
                    {'decision_id': decision},
                )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'ticket',
                    'ticket_id': ticket_id,
                    'outcome': outcome,
                    'note': note,
                    'decision_id': decision,
                },
            )
        self._send_json(200, {'ok': True, 'outcome': outcome})
