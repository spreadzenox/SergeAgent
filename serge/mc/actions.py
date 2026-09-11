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
from serge.memory.summaries import rollback_summary
from serge.registry import KillError, poser_kill, retirer_kill
from serge.tickets import (
    already_applied,
    decide,
    discuss,
    set_item,
    tout_approuver,
)
from serge.tickets.shared import TicketError, record_event

MAX_FORM_BYTES = 4096

ACTES_TICKET = {
    'approuver': 'APPROVED',
    'rejeter': 'REJECTED',
    'editer': 'EDITED',
}

ACTES_ITEM = {'garder': 'keep', 'modifier': 'edit', 'jeter': 'drop'}


class _Handler(Protocol):
    headers: Any
    rfile: Any

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

    def _refus_ticket(self, exc: TicketError, quoi: str) -> None:
        if 'inconnu' in str(exc):
            self._refus(
                404,
                f'{quoi} introuvable.',
                'ticket',
                'Vérifie l’identifiant.',
            )
        else:
            self._refus(
                409,
                'Action impossible.',
                'etat',
                'État incompatible (décidé, expiré, clôturé ou pas ouvert).',
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
            if decision:
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

    def _api_memory_rollback(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body() or {}
        decision = str(body.get('decision_id') or '')
        with self._db() as conn:
            reussi = rollback_summary(conn, 'serge_md')
            if not reussi:
                self._refus(
                    404,
                    'Aucune version précédente pour SERGE.md.',
                    'rollback',
                    'Pas de révision antérieure.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={'acte': 'rollback_serge_md', 'decision_id': decision},
            )
        self._send_json(200, {'ok': True, 'restaure': True})
