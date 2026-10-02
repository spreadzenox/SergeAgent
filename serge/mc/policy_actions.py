#!/usr/bin/env python3
"""MC API mutations politique (édition, testing, proposition, réglages)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event, utcnow
from serge.interpreter.settings import check_setting
from serge.policy import PolicyError, validate_policy
from serge.policy_snapshots import policy_en_vigueur, snapshot_policy


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
            current = policy_en_vigueur(conn)
            running = conn.execute(
                "SELECT COUNT(*) FROM campaigns WHERE state='RUNNING'"
            ).fetchone()[0]
            if running and validee.get('testing') != current.get('testing'):
                self._refus(
                    409,
                    'Modification testing verrouillée : campagnes en cours.',
                    'lock',
                    'Attends la fin des essais.',
                )
                return
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

    def _api_reglage(self) -> None:
        """Change un réglage d'invocation ou un quota marqué « policy ».

        Corps : ``{cible: 'invocation', invocation_id, name, value}`` ou
        ``{cible: 'quota', id, value}``. La valeur est vérifiée (type,
        bornes), enregistrée, et le changement est noté au journal.
        """
        if not self._require_owner():
            return
        body = self._json_body() or {}
        cible = str(body.get('cible') or '')
        value = str(body.get('value', '')).strip()
        with self._db() as conn:
            if cible == 'invocation':
                ident = str(body.get('invocation_id') or '')
                name = str(body.get('name') or '')
                row = conn.execute(
                    'SELECT type, value, min_value, max_value'
                    ' FROM invocation_settings WHERE invocation_id=?'
                    ' AND name=? AND policy=1',
                    (ident, name),
                ).fetchone()
                probleme = (
                    'réglage inconnu'
                    if row is None
                    else check_setting(str(row[0]), value, row[2], row[3])
                )
                cle = {'invocation_id': ident, 'name': name}
                sql = (
                    'UPDATE invocation_settings SET value=?, updated_at=?,'
                    " updated_by='mc' WHERE invocation_id=? AND name=?"
                )
                args: tuple = (value, utcnow(), ident, name)
            elif cible == 'quota':
                ident = str(body.get('id') or '')
                row = conn.execute(
                    'SELECT max_value, max_value FROM table_quotas'
                    ' WHERE id=? AND policy=1',
                    (ident,),
                ).fetchone()
                probleme = (
                    'quota inconnu'
                    if row is None
                    else ''
                    if value.isascii()
                    and value.isdigit()
                    and len(value) <= 19
                    and int(value) <= 2**63 - 1
                    else 'entier entre 0 et 9223372036854775807 attendu'
                )
                cle = {'id': ident}
                sql = (
                    'UPDATE table_quotas SET max_value=?, updated_at=?,'
                    " updated_by='mc' WHERE id=?"
                )
                args = (int(value) if not probleme else 0, utcnow(), ident)
            else:
                probleme = 'cible : invocation ou quota'
                row, cle, sql, args = None, {}, '', ()
            if probleme:
                self._refus(
                    400, f'Réglage refusé : {probleme}.', 'reglage', ''
                )
                return
            conn.execute(sql, args)
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'reglage',
                    'cible': cible,
                    **cle,
                    'avant': str(row[1]) if row else '',
                    'apres': value,
                },
            )
        self._send_json(200, {'ok': True, **cle, 'value': value})
