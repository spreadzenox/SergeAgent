#!/usr/bin/env python3
"""Appeler les outils qu'un modèle demande, pendant un tour d'outils.

Chaque appel respecte la limite réglée sur l'outil (« au plus 10
recherches »), est noté au journal (l'outil, ses paramètres en court,
s'il a marché, la raison d'un refus, et ce que la page a signalé pendant
l'appel), et rend un résultat borné : il repart au modèle à chaque tour
suivant. Les vieilles captures d'écran sortent de l'historique.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.db.store import append_event
from serge.interpreter.settings import load_settings, resolve_count
from serge.interpreter.tools import run_tool

# Ce que le journal garde des paramètres d'un appel d'outil, et de la
# raison d'un refus.
JOURNAL_MAX = 300
# Ce qu'il garde des erreurs qu'une page a signalées pendant l'appel.
ERREURS_MAX = 6
ERREUR_MAX = 240
# Les erreurs de page qui disent ce que le site a répondu (les premières
# gardées), telles que les écrit ``serge/sandbox/sessions.py``.
RESEAU = ('HTTP ', 'requête ratée')
_APRES_LE_POINT_D_INTERROGATION = re.compile(r'\?[^\s)]*')


def drop_old_images(
    history: list[dict[str, Any]], kept: int, note: str
) -> None:
    """Retire de l'historique les vieilles images, par paquets.

    Tout l'historique repart au modèle à chaque tour ; une image gardée y
    coûte peu, car elle est relue dans le cache du fournisseur. Mais
    retirer une vieille image change le début de l'historique : le cache ne
    sert plus, et tout est réécrit au prix fort (0,35 $ pour 138 000 jetons
    avec Sonnet, le 15 novembre 2026, à chaque capture). On les retire donc
    d'un coup, seulement quand il y en a plus du double de ``kept`` : il en
    reste alors ``kept``, et une image retirée devient un texte court
    (``note``). Exemple : avec 10, la 21e capture fait retirer les 11 plus
    anciennes ; les suivantes restent jusqu'à la 31e.
    """
    images = [
        (content, index)
        for message in history
        if isinstance(content := message.get('content'), list)
        for index, part in enumerate(content)
        if isinstance(part, dict) and part.get('type') == 'image_url'
    ]
    if len(images) <= 2 * kept:
        return
    for content, index in images[: len(images) - kept]:
        # Un texte vidé sur la page Pipeline n'est pas envoyé.
        content[index] = {'type': 'text', 'text': note or '…'}


def bounded(texte: str, limite: int, note: str) -> str:
    """Un résultat d'outil coupé à ``limite`` caractères, avec une note
    dont le repère ``{reste}`` dit combien de caractères ont été coupés."""
    if limite <= 0 or len(texte) <= limite:
        return texte
    reste = str(len(texte) - limite)
    return f'{texte[:limite]}… {note.replace("{reste}", reste)}'.rstrip()


def call_limits(
    conn: sqlite3.Connection,
    invocation_id: str,
    links: Mapping[str, int | None],
) -> dict[str, int]:
    """Le nombre maximum d'appels de chaque outil qui en a un."""
    settings = load_settings(conn, invocation_id)
    limits: dict[str, int] = {}
    for name, link_id in links.items():
        if link_id is None:
            continue
        row = conn.execute(
            'SELECT max_calls FROM invocation_tools WHERE id=?', (link_id,)
        ).fetchone()
        limit = resolve_count(str(row[0]), settings) if row else None
        if limit is not None:
            limits[name] = limit
    return limits


def limited_call(
    conn: sqlite3.Connection,
    invocation_id: str,
    links: Mapping[str, int | None],
    limits: Mapping[str, int],
    calls: dict[str, int],
    call: Any,
    task: Mapping[str, str],
) -> dict[str, Any]:
    """Un appel d'outil demandé par le modèle, noté au journal.

    Seul un appel qui part vraiment compte dans la limite de l'outil : des
    paramètres illisibles (un JSON coupé) ou un outil non permis ne font
    rien, et le modèle peut renvoyer l'appel. Exemple : « Mettre en vente »
    n'a droit qu'à une création de prix ; son premier essai, illisible, ne
    lui enlève pas ce droit (16 novembre 2026).

    Exemple d'événement ``tool.call`` : l'outil ``navigateur_agir``, ses
    paramètres ``{"action": "cliquer", "ref": "e7"}``, et ``ok`` vrai. Un
    appel refusé garde sa raison (``detail``) ; un appel pendant lequel la
    page a signalé des erreurs les garde (``erreurs``).
    """
    args = _arguments(call.arguments)
    done = calls.get(call.name, 0)
    if call.name not in links:
        outcome: dict[str, Any] = {'ok': False, 'code': 'outil_non_autorise'}
    elif args is None:
        outcome = {
            'ok': False,
            'code': 'arguments_illisibles',
            'detail': 'les paramètres ne sont pas un objet JSON complet ;'
            ' rien n’est parti, renvoie l’appel en entier',
        }
    elif call.name in limits and done >= limits[call.name]:
        outcome = {
            'ok': False,
            'code': 'limite_atteinte',
            'detail': f'au plus {limits[call.name]} appels de cet outil',
        }
    else:
        calls[call.name] = done + 1
        outcome = _call_tool(
            conn, invocation_id, links[call.name], call.name, args, task
        )
    payload: dict[str, Any] = {
        'task': task.get('task_id', ''),
        'tool': call.name,
        'args': str(call.arguments or '')[:JOURNAL_MAX],
        'ok': outcome.get('ok', True) is not False,
        'code': str(outcome.get('code') or ''),
    }
    if not payload['ok'] and outcome.get('detail'):
        payload['detail'] = str(outcome['detail'])[:JOURNAL_MAX]
    erreurs = _erreurs_de_page(outcome)
    if erreurs:
        payload['erreurs'] = erreurs
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='tool.call',
        payload=payload,
    )
    return outcome


def _erreurs_de_page(outcome: Mapping[str, Any]) -> list[str]:
    """Ce qu'une page a signalé pendant l'appel (outils du navigateur, clé
    ``nouvelles_erreurs``) : c'est la réponse du site à l'action.

    Les réponses refusées et les requêtes ratées passent avant les erreurs
    de console, et une adresse perd ce qui suit son « ? » : un jeton de
    session n'a rien à faire au journal. Exemple : un clic sur
    « Continuer » qui n'a rien fait, et ``HTTP 429 :
    https://api.site.example/inscription`` dit pourquoi (inscription sur
    X, le 21 novembre 2026 : la réponse du site n'était gardée nulle part).
    """
    brutes = outcome.get('nouvelles_erreurs')
    if not isinstance(brutes, list):
        return []
    lignes = [
        _APRES_LE_POINT_D_INTERROGATION.sub('?…', str(brute))[:ERREUR_MAX]
        for brute in brutes
    ]
    lignes.sort(key=lambda ligne: not ligne.startswith(RESEAU))
    return lignes[:ERREURS_MAX]


def _arguments(raw: str) -> dict[str, Any] | None:
    """Les paramètres d'un appel, ou ``None`` s'ils sont illisibles."""
    try:
        args = json.loads(raw or '{}')
    except json.JSONDecodeError:
        return None
    return args if isinstance(args, dict) else None


def _call_tool(
    conn: sqlite3.Connection,
    invocation_id: str,
    link: int | None,
    name: str,
    args: dict[str, Any],
    task: Mapping[str, str],
) -> dict[str, Any]:
    try:
        return run_tool(conn, invocation_id, link, name, args, task)
    except Exception as exc:  # noqa: BLE001 — un outil en échec ne tue pas l'invocation
        return {'ok': False, 'code': 'echec', 'detail': str(exc)[:200]}
