#!/usr/bin/env python3
"""MC : Julien dans la conversation (lot 8 bis, décisions Q85 et Q86).

- POST /owner/api/discord/admin : ajouter un administrateur (identifiant
  Discord et nom) ou le retirer ;
- POST /owner/api/ticket/type : changer le délai, la décision par défaut
  annoncée ou les boutons d'un type de ticket ;
- POST /owner/api/business/validation : chaque brouillon d'un business
  attend, ou non, la validation d'un humain avant de partir.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event
from serge.tickets.admins import add_admin, remove_admin
from serge.tickets.types import set_ticket_type


class _Handler(Protocol):
    app_config: Any

    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> Any: ...


if TYPE_CHECKING:
    _Base = _Handler
else:
    _Base = object


class DiscordActionsMixin(_Base):
    """POST /owner/api/discord/admin et /owner/api/ticket/type."""

    def _api_discord_admin(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        acte = str((body or {}).get('acte') or '')
        if body is None or acte not in {'ajouter', 'retirer'}:
            self._refus(
                400,
                'Acte inconnu.',
                'acte',
                'Envoie {"acte": "ajouter", "user_id": "…", "name": "…"}'
                ' ou {"acte": "retirer", "user_id": "…"}.',
            )
            return
        user_id = str(body.get('user_id') or '').strip()
        with self._db() as conn:
            if acte == 'ajouter':
                erreur = add_admin(
                    conn, user_id, str(body.get('name') or ''), 'owner'
                )
            else:
                erreur = remove_admin(conn, user_id, 'owner')
            if erreur:
                self._refus(400, erreur, 'user_id', erreur)
                return
        self._send_json(200, {'ok': True})

    def _api_ticket_type(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        ident = str((body or {}).get('id') or '')
        if body is None or not ident:
            self._refus(
                400,
                'Type de ticket requis.',
                'id',
                'Envoie {"id": "QNA", "expiry_minutes": 4320,'
                ' "default_detail": "…", "buttons": ["approuver"]}.',
            )
            return
        delai = body.get('expiry_minutes', '')
        boutons = body.get('buttons')
        if boutons is not None and not isinstance(boutons, list):
            self._refus(
                400, 'Boutons : une liste.', 'buttons', 'Liste attendue.'
            )
            return
        detail = body.get('default_detail')
        with self._db() as conn:
            erreur = set_ticket_type(
                conn,
                ident,
                'owner',
                expiry_minutes=delai,
                default_detail=None if detail is None else str(detail),
                buttons=None if boutons is None else [str(b) for b in boutons],
            )
            if erreur:
                self._refus(400, erreur, 'ticket_type', erreur)
                return
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={'acte': 'ticket_type', 'id': ident},
            )
        self._send_json(200, {'ok': True})

    def _api_business_validation(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        venture = str((body or {}).get('venture_id') or '')
        actif = (body or {}).get('actif')
        if not venture or not isinstance(actif, bool):
            self._refus(
                400,
                'Business et choix requis.',
                'venture_id',
                'Envoie {"venture_id": "…", "actif": true}.',
            )
            return
        with self._db() as conn:
            cursor = conn.execute(
                'UPDATE ventures SET validate_drafts=? WHERE id=?',
                (int(actif), venture),
            )
            if cursor.rowcount != 1:
                self._refus(404, 'Business inconnu.', 'venture_id', venture)
                return
            append_event(
                conn,
                actor='owner',
                type='venture.validate_drafts',
                venture_id=venture,
                payload={'actif': actif},
            )
        self._send_json(200, {'ok': True, 'actif': actif})
