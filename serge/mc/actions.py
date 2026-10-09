#!/usr/bin/env python3
"""MC actions : handlers API (trace + mutations) — mixin McHandler.

B3 : adaptateur sans logique (tools partagés tickets/registry + audit).
"""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from sqlite3 import Connection
from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event
from serge.memory.lessons import delete_lesson, update_lesson
from serge.tickets import (
    already_applied,
    decide,
    discuss,
    set_item,
    tout_approuver,
)
from serge.tickets.acts import APPROVE, REJECT
from serge.tickets.shared import TicketError, fetch_ticket, record_event
from serge.tickets.types import ticket_types

MAX_FORM_BYTES = 4096
MAX_JSON_BYTES = 65536

ACTES_TICKET = {
    'approuver': 'APPROVED',
    'rejeter': 'REJECTED',
    'editer': 'EDITED',
    **{act: 'APPROVED' for act in APPROVE},
    **{act: 'REJECTED' for act in REJECT},
    'choix_qcm': 'APPROVED',
    'reponse_libre': 'APPROVED',
    'accuse_reception': 'ACK',
}

ACTES_ITEM = {'garder': 'keep', 'modifier': 'edit', 'jeter': 'drop'}


class _Handler(Protocol):
    headers: Any
    rfile: Any
    app_config: Any
    close_connection: bool

    def _require_owner(self) -> bool: ...
    def _db(self) -> AbstractContextManager[Connection]: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...


if TYPE_CHECKING:
    _Base = _Handler
else:
    _Base = object


class ActionsMixin(_Base):
    """Handlers API (self = handler HTTP, membres via McHandler)."""

    def _json_size_ok(self) -> bool:
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_JSON_BYTES:
            self.close_connection = True
            self._refus(
                413, 'Requête trop volumineuse.', 'taille', 'Maximum : 64 Kio.'
            )
            return False
        return True

    def _json_body(self) -> dict | None:
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except (TypeError, ValueError):
            return None
        if length <= 0 or length > MAX_JSON_BYTES:
            return None
        try:
            data = json.loads(self.rfile.read(length).decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _refus_ticket(self, exc: TicketError, quoi: str) -> None:
        if 'inconnu' in str(exc):
            self._refus(
                404, f'{quoi} introuvable.', 'ticket', 'Vérifie l’identifiant.'
            )
        else:
            self._refus(
                409, 'Action impossible.', 'etat', 'État incompatible.'
            )

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
                'Utilise un des actes proposés sur la carte du ticket.',
            )
            return
        if (
            acte in {'editer', 'choix_qcm', 'reponse_libre'}
            and not note.strip()
        ):
            self._refus(
                400,
                'Note ou réponse requise.',
                'note',
                'Décris la modification ou donne ta réponse.',
            )
            return
        with self._db() as conn:
            if decision and already_applied(conn, ticket_id, decision):
                self._send_json(200, {'ok': True, 'duplicata': 'true'})
                return
            try:
                ticket = fetch_ticket(conn, ticket_id)
                spec = ticket_types(conn).get(ticket['type'], {})
                if acte not in spec.get('buttons', []):
                    self._refus(
                        400,
                        'Acte absent de ce ticket.',
                        'acte',
                        'Utilise un de ses boutons.',
                    )
                    return
                if ticket['state'] not in {'OPEN', 'DISCUSSING'}:
                    raise TicketError('État incompatible.')
                if acte == 'choix_qcm':
                    options = json.loads(ticket['payload_json'] or '{}').get(
                        'options_qcm', []
                    )
                    if note not in options:
                        self._refus(
                            400,
                            'Choix inconnu.',
                            'choix',
                            'Choisis une option proposée.',
                        )
                        return
                if outcome == 'ACK':
                    record_event(
                        conn, ticket_id, 'owner', 'mc.accuse_reception'
                    )
                else:
                    if acte == 'tout_approuver':
                        tout_approuver(conn, ticket_id)
                    decide(conn, ticket_id, outcome, actor='owner', note=note)
            except TicketError as exc:
                self._refus_ticket(exc, 'Ticket')
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

    def _api_ticket_item(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"item_id": "ti..", "acte": "garder"}.',
            )
            return
        acte = str(body.get('acte') or '')
        decision = str(body.get('decision_id') or '')
        if acte == 'tout_approuver':
            self._item_tout_approuver(body, decision)
            return
        item_id = str(body.get('item_id') or '')
        if not item_id:
            self._refus(
                400, 'item_id requis.', 'item', 'Identifiant de l’item.'
            )
            return
        etat = ACTES_ITEM.get(acte)
        if etat is None:
            self._refus(
                400,
                f'Acte inconnu : {acte}.',
                'acte',
                'Actes : garder, modifier, jeter, tout_approuver.',
            )
            return
        valeur = str(body.get('valeur') or '')
        if acte == 'modifier' and not valeur.strip():
            self._refus(
                400,
                'Valeur requise pour modifier.',
                'valeur',
                'Donne le nouveau libellé.',
            )
            return
        with self._db() as conn:
            row = conn.execute(
                'SELECT ticket_id FROM ticket_items WHERE id=?', (item_id,)
            ).fetchone()
            if row is None:
                self._refus(
                    404,
                    'Item introuvable.',
                    'ticket',
                    'Vérifie l’identifiant.',
                )
                return
            ticket_id = str(row[0])
            if decision and already_applied(conn, ticket_id, decision):
                self._send_json(200, {'ok': True, 'duplicata': 'true'})
                return
            set_item(
                conn,
                item_id,
                etat,
                {'label': valeur} if acte == 'modifier' else None,
            )
            if decision:
                record_event(
                    conn,
                    ticket_id,
                    'owner',
                    'mc.item',
                    {
                        'decision_id': decision,
                        'item_id': item_id,
                        'acte': acte,
                    },
                )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'ticket_item',
                    'ticket_id': ticket_id,
                    'item_id': item_id,
                    'etat': etat,
                    'decision_id': decision,
                },
            )
        self._send_json(200, {'ok': True, 'etat': etat})

    def _item_tout_approuver(self, body: dict, decision: str) -> None:
        ticket_id = str(body.get('ticket_id') or '')
        if not ticket_id:
            self._refus(
                400,
                'ticket_id requis.',
                'ticket',
                'Pour tout-approuver, vise un ticket.',
            )
            return
        with self._db() as conn:
            if decision and already_applied(conn, ticket_id, decision):
                self._send_json(200, {'ok': True, 'duplicata': 'true'})
                return
            try:
                count = tout_approuver(conn, ticket_id)
            except TicketError as exc:
                self._refus_ticket(exc, 'Ticket')
                return
            if decision:
                record_event(
                    conn,
                    ticket_id,
                    'owner',
                    'mc.tout_approuver',
                    {'decision_id': decision, 'count': count},
                )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'ticket_item',
                    'ticket_id': ticket_id,
                    'outcome': 'tout_approuver',
                    'count': count,
                    'decision_id': decision,
                },
            )
        self._send_json(200, {'ok': True, 'bascules': count})

    def _api_ticket_discuter(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"ticket_id": "t..", "message": "..."}.',
            )
            return
        ticket_id = str(body.get('ticket_id') or '')
        message = str(body.get('message') or '')
        decision = str(body.get('decision_id') or '')
        if not ticket_id:
            self._refus(
                400,
                'ticket_id requis.',
                'ticket',
                'Identifiant du ticket visé.',
            )
            return
        if not message.strip():
            self._refus(
                400, 'Message vide.', 'message', 'Écris quelque chose.'
            )
            return
        with self._db() as conn:
            if decision and already_applied(conn, ticket_id, decision):
                self._send_json(200, {'ok': True, 'duplicata': 'true'})
                return
            try:
                discuss(conn, ticket_id)
            except TicketError as exc:
                self._refus_ticket(exc, 'Ticket')
                return
            record_event(
                conn,
                ticket_id,
                'owner',
                'mc.fil',
                {'decision_id': decision, 'message': message},
            )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'ticket_fil',
                    'ticket_id': ticket_id,
                    'message': message,
                    'decision_id': decision,
                },
            )
        self._send_json(200, {'ok': True, 'state': 'DISCUSSING'})

    def _api_memory_lesson(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"lesson_id": "...", "action": "..."}.',
            )
            return
        lesson_id = str(body.get('lesson_id') or '')
        action = str(body.get('action') or '')
        decision = str(body.get('decision_id') or '')
        if not lesson_id:
            self._refus(
                400, 'lesson_id requis.', 'lesson', 'Identifiant de la leçon.'
            )
            return
        if action not in {'modifier', 'supprimer'}:
            self._refus(
                400,
                f'Action inconnue : {action}.',
                'action',
                'Actions : modifier, supprimer.',
            )
            return
        statement = str(body.get('statement') or '')
        if action == 'modifier' and not statement.strip():
            self._refus(
                400,
                'statement requis pour modifier.',
                'statement',
                'Nouvel énoncé.',
            )
            return
        with self._db() as conn:
            try:
                if action == 'modifier':
                    update_lesson(conn, lesson_id, statement)
                else:
                    delete_lesson(conn, lesson_id)
            except ValueError as exc:
                self._refus(404, str(exc), 'lesson', 'Vérifie l’identifiant.')
                return
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'curation_lesson',
                    'lesson_id': lesson_id,
                    'action': action,
                    'statement': statement if action == 'modifier' else '',
                    'decision_id': decision,
                },
            )
        self._send_json(
            200, {'ok': True, 'action': action, 'lesson_id': lesson_id}
        )
