#!/usr/bin/env python3
"""MC API mutations politique (M4 édition, M5 rollback, M6 testing, M12 proposition)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event
from serge.policy import PolicyError, validate_policy
from serge.policy_snapshots import (
    get_snapshot,
    policy_en_vigueur,
    snapshot_policy,
)
from serge.registry import load_ticket_types
from serge.tickets.lifecycle import create_ticket


class _PolicyHandler(Protocol):
    app_config: Any

    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> Any: ...


if TYPE_CHECKING:
    _Base = _PolicyHandler
else:
    _Base = object


class PolicyActionsMixin(_Base):
    """Endpoints de mutation politique (POST)."""

    def _api_policy_edit(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400, 'Corps JSON requis.', 'json', 'Envoie {"policy": {...}}.'
            )
            return
        policy_data = body.get('policy')
        if not isinstance(policy_data, dict):
            self._refus(
                400,
                'Section policy requise sous forme d’objet.',
                'policy',
                'Dictionnaire attendu.',
            )
            return
        decision_id = str(body.get('decision_id') or '')

        try:
            validee = validate_policy(policy_data)
        except PolicyError as exc:
            self._refus(
                400,
                f'Politique invalide : {exc}',
                'validation',
                'Vérifie les types et contraintes.',
            )
            return

        with self._db() as conn:
            snap = snapshot_policy(conn, validee, applied_by='owner')
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'policy_edit',
                    'snapshot_id': snap['id'],
                    'content_hash': snap['content_hash'],
                    'decision_id': decision_id,
                },
            )
        self._send_json(200, {'ok': True, 'snapshot': snap})

    def _api_policy_rollback(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"snapshot_id": 123}.',
            )
            return
        try:
            snapshot_id = int(body.get('snapshot_id') or 0)
        except (TypeError, ValueError):
            snapshot_id = 0
        if snapshot_id <= 0:
            self._refus(
                400,
                'snapshot_id entier requis.',
                'snapshot_id',
                'ID du snapshot à restaurer.',
            )
            return
        decision_id = str(body.get('decision_id') or '')

        with self._db() as conn:
            cible = get_snapshot(conn, snapshot_id)
            if not cible:
                self._refus(
                    404, 'Snapshot introuvable.', 'snapshot', 'ID inexistant.'
                )
                return
            nouveau_snap = snapshot_policy(
                conn, cible['content'], applied_by='owner_rollback'
            )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'policy_rollback',
                    'from_snapshot_id': snapshot_id,
                    'new_snapshot_id': nouveau_snap['id'],
                    'content_hash': nouveau_snap['content_hash'],
                    'decision_id': decision_id,
                },
            )
        self._send_json(200, {'ok': True, 'snapshot': nouveau_snap})

    def _api_policy_testing(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400, 'Corps JSON requis.', 'json', 'Envoie {"testing": {...}}.'
            )
            return
        testing_data = body.get('testing')
        if not isinstance(testing_data, dict):
            self._refus(
                400,
                'Section testing requise.',
                'testing',
                'Dictionnaire de seuils.',
            )
            return
        decision_id = str(body.get('decision_id') or '')

        from kit.instance_file import _validate_testing

        try:
            clean_testing = _validate_testing(testing_data)
        except Exception as exc:
            self._refus(
                400,
                f'Testing invalide : {exc}',
                'validation',
                'Vérifie les entiers.',
            )
            return

        with self._db() as conn:
            running = conn.execute(
                "SELECT COUNT(*) FROM campaigns WHERE state='RUNNING'"
            ).fetchone()[0]
            if int(running) > 0:
                self._refus(
                    409,
                    'Modification testing verrouillée : campagnes en cours.',
                    'lock',
                    'Le testing à froid exige 0 campagne active.',
                )
                return
            courante = dict(policy_en_vigueur(conn))
            courante['testing'] = clean_testing
            snap = snapshot_policy(conn, courante, applied_by='owner')
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'testing_edit',
                    'testing': clean_testing,
                    'snapshot_id': snap['id'],
                    'decision_id': decision_id,
                },
            )
        self._send_json(200, {'ok': True, 'testing': clean_testing})

    def _api_policy_propose(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body()
        if body is None:
            self._refus(
                400,
                'Corps JSON requis.',
                'json',
                'Envoie {"titre": "...", "diff": "..."}.',
            )
            return
        titre = str(body.get('titre') or '').strip()
        diff = str(body.get('diff') or '').strip()
        justification = str(body.get('justification') or '').strip()
        impact = str(body.get('impact') or '').strip()
        decision_id = str(body.get('decision_id') or '')

        if not titre or not diff:
            self._refus(
                400,
                'Titre et diff requis.',
                'champs',
                'Renseigne titre et diff.',
            )
            return

        with self._db() as conn:
            ticket_id = create_ticket(
                conn,
                load_ticket_types(),
                'POLICY',
                titre,
                {
                    'diff_avant_apres': diff,
                    'justification': justification,
                    'impact': impact,
                },
                creator='owner',
            )
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'propose_policy',
                    'ticket_id': ticket_id,
                    'decision_id': decision_id,
                },
            )
        self._send_json(200, {'ok': True, 'ticket_id': ticket_id})

    def _api_voice_kill(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body() or {}
        activer = bool(body.get('activer', True))
        decision = str(body.get('decision_id') or '')

        from serge.paths import system_root

        cibles = {
            self.app_config.db_path.parent / 'KILL_SWITCH',
            system_root() / 'state/KILL_SWITCH',
        }
        ok = False
        for path in cibles:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                if activer:
                    path.write_text(
                        'VOICE_KILL_SWITCH_ACTIVE\n', encoding='utf-8'
                    )
                elif path.exists():
                    path.unlink()
                ok = True
            except OSError:
                continue
        if not ok:
            self._refus(
                500,
                'Kill voix injoignable.',
                'kill',
                'Vérifie state/KILL_SWITCH.',
            )
            return

        with self._db() as conn:
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'voice_kill_toggle',
                    'actif': activer,
                    'decision_id': decision,
                },
            )

        self._send_json(200, {'ok': True, 'kill_switch': activer})
