#!/usr/bin/env python3
"""MC : POST /owner/api/coupe (Serge, étape, kind)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.coupe_circuit import CIBLES, CoupeError, appliquer_coupe
from serge.db.store import append_event


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


class CoupeActionsMixin(_Base):
    """POST /owner/api/coupe."""

    def _api_coupe(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"cible": "serge", "marche": false}.',
            )
            return
        cible = str(body.get('cible') or '').strip()
        if cible not in CIBLES:
            self._refus(
                400,
                'Cible inconnue.',
                'cible',
                'cible : serge, etape ou kind.',
            )
            return
        ident = str(body.get('id') or '').strip()
        if cible != 'serge' and ident == '':
            self._refus(
                400,
                'Identifiant requis.',
                'id',
                'id : étape (pre_prospection) ou kind (email.send).',
            )
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
                etat = appliquer_coupe(
                    conn, cible, ident, bool(body['marche'])
                )
                append_event(
                    conn,
                    actor='owner',
                    type='mc_act',
                    payload={
                        'acte': 'coupe',
                        'cible': cible,
                        'id': ident,
                        'marche': etat['marche'],
                        'decision_id': decision_id,
                    },
                )
        except CoupeError:
            self._refus(
                404,
                'Cible inconnue.',
                cible if cible in {'etape', 'kind'} else 'cible',
                'Ids : 8 sacs, ou kinds du seed.',
            )
            return
        self._send_json(200, {'ok': True, **etat})
