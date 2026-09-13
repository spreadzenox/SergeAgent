#!/usr/bin/env python3
"""MC : couper / remettre une étape du pipe (table pipeline_steps)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event
from serge.etapes import EtapeError, set_etape_marche


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


class EtapeActionsMixin(_Base):
    """POST /owner/api/etape."""

    def _api_etape(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"id": "ecoute", "marche": false}.',
            )
            return
        ident = str(body.get('id') or '').strip()
        if ident == '':
            self._refus(400, 'Étape requise.', 'etape', 'id : ecoute, test, …')
            return
        if 'marche' not in body or not isinstance(body.get('marche'), bool):
            self._refus(
                400,
                'Marche : oui ou non.',
                'marche',
                'Booléen attendu (marche).',
            )
            return
        decision_id = str(body.get('decision_id') or '')
        try:
            with self._db() as conn:
                etat = set_etape_marche(conn, ident, bool(body['marche']))
                append_event(
                    conn,
                    actor='owner',
                    type='mc_act',
                    payload={
                        'acte': 'etape_marche',
                        'id': ident,
                        'marche': etat['marche'],
                        'decision_id': decision_id,
                    },
                )
        except EtapeError:
            self._refus(
                404,
                f'Étape inconnue : {ident}.',
                'etape',
                'Ids : ecoute, hypothese, test, qualif, conversation, intent, caisse.',
            )
            return
        self._send_json(200, {'ok': True, **etat})
