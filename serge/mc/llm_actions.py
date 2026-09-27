#!/usr/bin/env python3
"""Mutation MC minimale des métadonnées runtime d'un point LLM."""

from __future__ import annotations

from contextlib import AbstractContextManager
from sqlite3 import Connection
from typing import TYPE_CHECKING, Protocol

from serge.db.store import append_event, utcnow


class _Handler(Protocol):
    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> AbstractContextManager[Connection]: ...


if TYPE_CHECKING:
    _Base = _Handler
else:
    _Base = object


class LlmActionsMixin(_Base):
    """Endpoint owner pour éditer prompt, mode et information externe."""

    def _api_llm_point(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"point_id":"...","prompt":"..."}.',
            )
            return
        point_id = str(body.get('point_id') or '').strip()
        if not point_id:
            self._refus(
                400, 'point_id requis.', 'point', 'Identifiant du point.'
            )
            return
        updates: dict[str, object] = {}
        if 'prompt' in body:
            if not isinstance(body['prompt'], str):
                self._refus(
                    400, 'Prompt invalide.', 'prompt', 'Texte attendu.'
                )
                return
            updates['prompt'] = body['prompt']
        if 'output_mode' in body:
            output_mode = body['output_mode']
            if output_mode not in {'structured', 'text'}:
                self._refus(
                    400,
                    'Mode de sortie invalide.',
                    'output_mode',
                    'Valeurs : structured ou text.',
                )
                return
            updates['output_mode'] = output_mode
        if 'external_info' in body:
            external_info = body['external_info']
            if not isinstance(external_info, bool):
                self._refus(
                    400,
                    'Information externe invalide.',
                    'external_info',
                    'Booléen attendu.',
                )
                return
            updates['external_info'] = int(external_info)
        if not updates:
            self._refus(
                400,
                'Aucune métadonnée à modifier.',
                'fields',
                'Donne prompt, output_mode ou external_info.',
            )
            return
        with self._db() as conn:
            if (
                conn.execute(
                    'SELECT 1 FROM llm_points WHERE id=?', (point_id,)
                ).fetchone()
                is None
            ):
                self._refus(
                    404,
                    'Point LLM introuvable.',
                    'point',
                    'Identifiant absent de llm_points.',
                )
                return
            columns = ', '.join(f'{key}=?' for key in updates)
            conn.execute(
                f'UPDATE llm_points SET {columns}, updated_at=? WHERE id=?',
                (*updates.values(), utcnow(), point_id),
            )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'llm_point_edit',
                    'point_id': point_id,
                    'fields': sorted(updates),
                },
            )
        self._send_json(200, {'ok': True, 'point_id': point_id})
