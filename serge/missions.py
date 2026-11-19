#!/usr/bin/env python3
"""Confier une mission à une autre invocation, et recevoir sa réponse.

Une invocation LLM peut avoir besoin d'un travail qui n'est pas le sien :
fouiller un réseau social, connectée à un compte, pendant qu'elle explore
le web. Elle n'en reçoit pas les outils. Elle confie la mission à une
autre invocation, qui a son propre rôle, son niveau de modèle, ses outils
et ses réglages, et qui lui rend sa réponse comme le résultat d'un outil.
Le long travail de la seconde (ses pages lues, ses captures) ne pèse pas
sur la première.

En base, c'est un outil comme un autre (capacité ``mission``). Sur l'outil
d'une invocation, la base fige l'invocation qui fait la mission
(``invocation``) et, s'il en faut un, le compte web qu'elle peut ouvrir
(``account``). Le modèle n'écrit que sa demande (``mission``).

La mission tourne dans la tâche de celle qui la confie : ses appels au
modèle comptent dans le plafond de dépense de la tâche, ses outils sont au
journal de la tâche, et si elle appelle un humain, c'est la tâche qui
attend. Elle ne fait que répondre : ses écritures et ses liens ne jouent
pas. Une mission ne confie pas de mission.

Exemple : « Explorer le web » appelle « Fouiller Reddit » avec la demande
« ce que disent les artisans de leurs devis ». « Fouiller un réseau »
navigue avec le compte ``reddit`` et rend 5 discussions, chacune avec son
adresse et un extrait.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from typing import Any

# Qui sait exécuter une invocation : l'interpréteur, qui s'inscrit ici à
# son chargement (``serge/interpreter/run.py``).
Runner = Callable[[sqlite3.Connection, str, str, Mapping[str, str]], Any]
_RUNNER: list[Runner] = []
_EN_MISSION: ContextVar[bool] = ContextVar('en_mission', default=False)


class MissionError(RuntimeError):
    """La mission n'a pas rendu de réponse utilisable ; le message dit
    pourquoi."""


def register(runner: Runner) -> None:
    """L'interpréteur dit comment exécuter une invocation."""
    _RUNNER[:] = [runner]


def run(
    conn: sqlite3.Connection,
    invocation_id: str,
    task_id: str,
    params: Mapping[str, str],
) -> Any:
    """Exécute une invocation LLM dans la tâche en cours, avec ces
    paramètres, et rend sa réponse.

    Raises:
        MissionError: Sa réponse n'a pas le bon format, même redemandée.
    """
    if not _RUNNER:
        raise MissionError('l’interpréteur n’est pas chargé')
    marque = _EN_MISSION.set(True)
    try:
        return _RUNNER[0](conn, invocation_id, task_id, params)
    finally:
        _EN_MISSION.reset(marque)


def _refus(raison: str) -> dict[str, Any]:
    return {'ok': False, 'detail': raison}


def mission(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """Capacité « Confier une mission » : ``{mission}``, avec l'invocation
    et le compte web figés en base. Rend ``{ok, reponse}``, ou le refus."""
    cible = str(args.get('invocation') or '')
    demande = str(args.get('mission') or '').strip()
    compte = str(args.get('account') or '').strip().lower()
    if _EN_MISSION.get():
        return _refus(
            'une mission ne confie pas de mission : fais ce travail'
            ' toi-même, ou rends ce que tu as'
        )
    if not demande:
        return _refus('écris ta demande (mission), en une ou deux phrases')
    row = conn.execute(
        'SELECT type, enabled, deleted_at FROM invocations WHERE id=?',
        (cible,),
    ).fetchone()
    if row is None or row[0] != 'llm' or not row[1] or row[2]:
        return _refus(f'la mission « {cible} » n’existe pas ou est éteinte')
    if compte:
        etat = conn.execute(
            'SELECT status FROM web_accounts WHERE id=?', (compte,)
        ).fetchone()
        if etat is None or etat[0] != 'active':
            return _refus(
                f'Serge n’a pas de compte « {compte} » en service : fais'
                ' sans ce réseau'
            )
    params = {'mission': demande}
    if compte:
        params['compte'] = compte
    try:
        reponse = run(conn, cible, str(args.get('task_id') or ''), params)
    except MissionError as exc:
        return _refus(f'la mission n’a pas abouti : {exc}')
    return {'ok': True, 'reponse': reponse}
