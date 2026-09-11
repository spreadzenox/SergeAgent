#!/usr/bin/env python3
"""MC API vues (GET) : trace, carte, memory items, memory search — mixin McHandler."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
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
    def _is_owner(self) -> bool: ...
    def _send(self, code: int, body: bytes, content_type: str) -> None: ...

    path: str


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

    def _api_voice_audio(self) -> None:
        from serge.mc.signedlinks import verifier_url

        # Vérification du lien signé HMAC E7 ou auth owner
        path_query = f'{self.path}'
        secret = 'serge_mc_voice_signed_audio'
        if not verifier_url(path_query, secret) and not self._is_owner():
            self._refus(
                401,
                'Lien audio expiré ou signature invalide.',
                'audio_auth',
                'Redemande le lien.',
            )
            return

        query = self._query()
        cdr_id = query.get('cdr', '').strip()
        if not cdr_id:
            self._refus(
                400, 'Paramètre cdr requis.', 'cdr', 'Identifiant appel.'
            )
            return

        import sqlite3

        from serge.voice.policy import default_ledger_path

        ledger_p = default_ledger_path()
        rec_path = None
        if ledger_p.is_file():
            try:
                conn = sqlite3.connect(ledger_p, timeout=5)
                row = conn.execute(
                    'SELECT recording_path FROM calls WHERE cdr_id=?',
                    (cdr_id,),
                ).fetchone()
                if row and row[0]:
                    rec_path = Path(str(row[0]))
                conn.close()
            except sqlite3.OperationalError:
                pass

        if not rec_path or not rec_path.is_file():
            self._refus(
                404,
                'Enregistrement audio introuvable ou purgé.',
                'audio_404',
                'Fichier inexistant.',
            )
            return

        try:
            audio_bytes = rec_path.read_bytes()
        except OSError:
            self._refus(
                500, 'Lecture audio impossible.', 'audio_io', 'Erreur disque.'
            )
            return

        self._send(200, audio_bytes, 'audio/wav')
