#!/usr/bin/env python3
"""MC : les actions sur le pipeline.

Le bouton d'un déclencheur, relancer une tâche, les tables qu'une
invocation voit pour comparer, le passage d'un lien à la main, et, sur la
page Pipeline, le modèle de chaque niveau et le texte « Qui est Serge ».
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Protocol

from serge.db.store import append_event, utcnow
from serge.interpreter.flow import fire_button, pass_waiting, set_link_auto
from serge.interpreter.tasks import relaunch_task
from serge.mc.proj_vues import changer_comparaison

# Un identifiant de modèle : « openai/gpt-5-mini », vide pour celui de
# l'installation.
_MODELE = re.compile(r'^[A-Za-z0-9._:/@+-]{0,200}$')


class _PipelineHandler(Protocol):
    def _require_owner(self) -> bool: ...
    def _json_body(self) -> dict | None: ...
    def _refus(self, http: int, erreur: str, code: str, aide: str) -> None: ...
    def _send_json(self, code: int, obj: dict) -> None: ...
    def _db(self) -> Any: ...


if TYPE_CHECKING:
    _Base = _PipelineHandler
else:
    _Base = object


class PipelineActionsMixin(_Base):
    """POST /owner/api/bouton, /tache/relancer, /invocation/comparer,
    /lien/* et /pipeline/*."""

    def _api_bouton(self) -> None:
        if not self._require_owner():
            return
        body = self._json_body() or {}
        trigger_id = str(body.get('trigger_id') or '').strip()
        form = body.get('form') or {}
        if not trigger_id or not isinstance(form, dict):
            self._refus(
                400,
                'Bouton inconnu.',
                'trigger',
                'Envoie {"trigger_id": "...", "form": {...}}.',
            )
            return
        with self._db() as conn:
            task_id = fire_button(conn, trigger_id, form)
            if task_id is None:
                self._refus(
                    409,
                    'Ce bouton ne peut pas lancer de tâche.',
                    'trigger',
                    'Le déclencheur ou son invocation est éteint, ou absent.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='mc_act',
                payload={
                    'acte': 'bouton',
                    'trigger_id': trigger_id,
                    'task': task_id,
                },
            )
        self._send_json(200, {'ok': True, 'task_id': task_id})

    def _api_tache_relancer(self) -> None:
        """Remet une tâche échouée dans sa file : ``{task_id}``."""
        if not self._require_owner():
            return
        body = self._json_body() or {}
        task_id = str(body.get('task_id') or '').strip()
        with self._db() as conn:
            if not task_id or not relaunch_task(conn, task_id):
                self._refus(
                    409,
                    'Cette tâche ne peut pas être relancée.',
                    'task',
                    'Seule une tâche échouée peut être relancée.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='task.relaunched',
                payload={'task': task_id},
            )
        self._send_json(200, {'ok': True, 'task_id': task_id})

    def _api_comparer(self) -> None:
        """Ajoute, retire ou remet une table à comparer.

        Corps : ``{invocation_id, table, voir}``.
        """
        if not self._require_owner():
            return
        body = self._json_body() or {}
        ident = str(body.get('invocation_id') or '').strip()
        table = str(body.get('table') or '').strip()
        voir = body.get('voir')
        if not ident or not table or not isinstance(voir, bool):
            self._refus(
                400,
                'Demande incomplète.',
                'comparer',
                'Envoie {"invocation_id": "...", "table": "...", "voir": true}.',
            )
            return
        with self._db() as conn:
            if not changer_comparaison(conn, ident, table, voir, 'owner'):
                self._refus(
                    409,
                    'Cette table ne peut pas être vue par cette invocation.',
                    'comparer',
                    'La table doit être décrite (table_views) et'
                    ' l’invocation doit exister.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='invocation.compare',
                payload={'invocation': ident, 'table': table, 'voir': voir},
            )
        self._send_json(200, {'ok': True})

    def _api_lien_passer(self) -> None:
        """« Passer à la suite » : ``{link_id, source_ref}``."""
        if not self._require_owner():
            return
        body = self._json_body() or {}
        link_id = str(body.get('link_id') or '').strip()
        ref = str(body.get('source_ref') or '').strip()
        with self._db() as conn:
            task_id = (
                pass_waiting(conn, link_id, ref) if link_id and ref else None
            )
            if task_id is None:
                self._refus(
                    409,
                    'Ce passage ne peut pas être lancé.',
                    'lien',
                    'Il est déjà passé, ou le lien ou l’invocation suivante'
                    ' est éteint.',
                )
                return
            append_event(
                conn,
                actor='owner',
                type='link.passed',
                payload={'link': link_id, 'source': ref, 'task': task_id},
            )
        self._send_json(200, {'ok': True, 'task_id': task_id})

    def _api_lien_auto(self) -> None:
        """L'interrupteur « passage automatique » : ``{link_id, auto}``."""
        if not self._require_owner():
            return
        body = self._json_body() or {}
        link_id = str(body.get('link_id') or '').strip()
        auto = body.get('auto')
        if not link_id or not isinstance(auto, bool):
            self._refus(
                400,
                'Demande incomplète.',
                'lien',
                'Envoie {"link_id": "...", "auto": true}.',
            )
            return
        with self._db() as conn:
            if not set_link_auto(conn, link_id, auto):
                self._refus(409, 'Lien inconnu.', 'lien', '')
                return
            append_event(
                conn,
                actor='owner',
                type='link.auto',
                payload={'link': link_id, 'auto': auto},
            )
        self._send_json(200, {'ok': True})

    def _api_pipeline_modele(self) -> None:
        """Le modèle derrière un niveau : ``{tier, model}`` (vide = défaut)."""
        if not self._require_owner():
            return
        body = self._json_body() or {}
        tier = str(body.get('tier') or '')
        model = str(body.get('model') or '').strip()
        if not _MODELE.match(model):
            self._refus(
                400,
                'Identifiant de modèle invalide.',
                'modele',
                'Exemple : openai/gpt-5-mini, ou vide pour celui de'
                ' l’installation.',
            )
            return
        with self._db() as conn:
            cursor = conn.execute(
                'UPDATE llm_models SET model=? WHERE tier=?', (model, tier)
            )
            if cursor.rowcount != 1:
                self._refus(
                    409, 'Niveau inconnu.', 'modele', 'fast, mid, smart.'
                )
                return
            append_event(
                conn,
                actor='owner',
                type='pipeline.model',
                payload={'tier': tier, 'model': model},
            )
        self._send_json(200, {'ok': True})

    def _api_pipeline_texte(self) -> None:
        """Le texte « Qui est Serge » : ``{body}``."""
        if not self._require_owner():
            return
        body = self._json_body() or {}
        texte = str(body.get('body') or '').strip()
        if not texte or len(texte) > 4000:
            self._refus(
                400,
                'Texte vide ou trop long.',
                'texte',
                'Entre 1 et 4000 caractères.',
            )
            return
        with self._db() as conn:
            conn.execute(
                'INSERT INTO serge_texts(id, body, updated_at)'
                " VALUES('presentation', ?, ?) ON CONFLICT(id) DO UPDATE"
                ' SET body=excluded.body, updated_at=excluded.updated_at',
                (texte, utcnow()),
            )
            append_event(
                conn,
                actor='owner',
                type='pipeline.text',
                payload={'id': 'presentation', 'longueur': len(texte)},
            )
        self._send_json(200, {'ok': True})
