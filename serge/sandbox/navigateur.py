#!/usr/bin/env python3
"""L'interface web des invocations : lire une page et y agir comme un humain.

Un navigateur Chrome tourne dans son propre conteneur (``chrome.py``) :
le navigateur sans écran, ou le vrai Chrome, avec un écran qu'un humain
peut voir depuis Mission Control. Chaque invocation reçoit les outils de
l'un ou de l'autre (« Agir dans une page », « Agir dans le vrai Chrome »…),
réglés en base : on passe de l'un à l'autre en changeant ses outils.
Serge les pilote avec Playwright, par le protocole de débogage de Chrome.
Ils ne tournent jamais dans le programme de Serge : une page inconnue ne
peut pas l'atteindre.

Une session (ses onglets, ses cookies) par tâche, fermée à la fin de la
tâche (``sessions.py``). Une invocation à qui la base donne un compte web
(le paramètre ``account`` de ses outils) navigue connectée à ce compte, et
chacune de ses actions passe par la garde du compte : au-delà du plafond
du jour, elle est refusée (``serge/web_accounts.py``).

Après chaque action, l'outil rend la page relue, en version courte : le
modèle voit l'effet de son geste sans appel de plus. Une page se lit comme un
lecteur d'écran la lirait (``lecture.py``, ``page.js``) ; les gestes sont
ceux d'une personne (``gestes.py``). Une capture d'écran revient au modèle
comme une image ; gardée, elle est rangée avec le livrable
(``files/<business>/<livrable>/captures/``) et a sa fiche dans
``artifacts``.

Ce qui arrive hors de la page est dit dans le résultat de l'action : une
boîte de dialogue du navigateur (``dialogues.py``), un fichier téléchargé
(``telechargements.py``), un nouvel onglet (la session y passe ; fermé, elle
revient au précédent).

Une tâche qui a commencé dans le navigateur sans écran peut passer au vrai
Chrome (action ``passer_au_vrai_chrome``), quand une page refuse le
premier : elle y retrouve la même adresse et sa connexion (ses cookies, et
ce que la page gardait dans le navigateur).

L'adresse ``http://chantier:<port>`` mène au chantier du business : le
constructeur essaie ainsi le serveur qu'il vient de lancer. L'action
« taper un secret » tape la valeur d'un secret de l'instance dans un champ :
un fichier de secret, ou un champ de la carte chiffrée de Serge
(``payment-card.enc#pan``). Le modèle ne nomme que le secret, parmi ceux
figés en base, et la page relue cache la valeur. Dans la session d'un
compte web, le secret ``mot_de_passe_du_compte`` est le mot de passe de
ce compte.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge import web_accounts
from serge.policy_store import policy_en_vigueur
from serge.sandbox.gestes import agir
from serge.sandbox.lecture import lire, masquer
from serge.sandbox.lecture import vers_chantier as _vers_chantier
from serge.sandbox.sessions import (
    _ETAT,
    _ETAT_VRAI,
    _Etat,
    _passer_au_vrai_chrome,
    _session_de,
)

__all__ = ['_vers_chantier', 'masquer']


def _reglages(conn: sqlite3.Connection) -> dict[str, Any]:
    return policy_en_vigueur(conn)['tools']


# Ce qui ne touche pas le site : ces actions ne comptent pas dans les
# actions du jour d'un compte web.
SANS_LE_SITE = frozenset(
    {
        'lire_telechargement',
        'accepter_dialogue',
        'refuser_dialogue',
        'ecran',
        'attendre',
        'passer_au_vrai_chrome',
    }
)


def _refus_du_compte(exc: Exception) -> dict[str, Any]:
    return {'ok': False, 'code': 'compte', 'detail': str(exc)}


def browser_action(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
    etat: _Etat = _ETAT,
) -> dict[str, Any]:
    """Une action dans la page, puis la page relue en version courte, et
    ce qui est arrivé hors de la page. Avec un compte web, l'action passe
    d'abord par la garde du compte."""
    task_id = str(args.get('task_id') or '')
    action = str(args.get('action') or '')
    account = str(args.get('account') or '').strip().lower()
    refus = ''
    if action == 'passer_au_vrai_chrome':
        try:
            refus = _passer_au_vrai_chrome(conn, task_id, account)
        except Exception as exc:  # noqa: BLE001 — l'échec est rendu au modèle
            refus = str(exc).splitlines()[0][:300]
    try:
        session = _session_de(conn, args, etat)
    except web_accounts.AccountError as exc:
        return _refus_du_compte(exc)
    erreurs = len(session.errors)
    fichier = None
    if action == 'lire_telechargement':
        try:
            ligne = int(float(args.get('line') or 1))
        except (TypeError, ValueError):
            ligne = 1
        fichier = session.telechargements.lire(
            str(args.get('text') or ''), ligne
        )
    elif action != 'passer_au_vrai_chrome':
        if account and action not in SANS_LE_SITE:
            refus = web_accounts.count_action(conn, account)
        try:
            refus = refus or agir(session, args)
        except Exception as exc:  # noqa: BLE001 — l'échec est rendu au modèle
            refus = str(exc).splitlines()[0][:300]
        session = _session_de(conn, args, etat)
    lignes = int(_reglages(conn)['browser_lines_after_action'])
    result: dict[str, Any] = {
        'ok': not refus,
        'page': lire(session, lignes, args),
    }
    if refus:
        result['detail'] = masquer(refus, session.masques)
    nouvelles = session.errors[erreurs:]
    if nouvelles:
        result['nouvelles_erreurs'] = nouvelles[:10]
    dialogues = session.dialogues.raconter()
    if dialogues:
        result['dialogues'] = [masquer(d, session.masques) for d in dialogues]
    if session.onglets:
        result['onglets'], session.onglets = session.onglets, []
    recus = session.telechargements.ramasser(conn, args, session.conteneur)
    if recus:
        result['telechargements'] = recus
    if fichier is not None:
        result['fichier'] = fichier
    return result


def browser_read(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
    etat: _Etat = _ETAT,
) -> dict[str, Any]:
    """La page entière, et les dernières erreurs de la page."""
    try:
        session = _session_de(conn, args, etat)
    except web_accounts.AccountError as exc:
        return _refus_du_compte(exc)
    lignes = int(_reglages(conn)['browser_lines_read'])
    return {
        'ok': True,
        'page': lire(session, lignes, args),
        'erreurs': session.errors[-20:],
    }


def real_browser_action(
    conn: sqlite3.Connection, tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """« Agir dans une page », dans le vrai Chrome."""
    return browser_action(conn, tool, args, inv, _ETAT_VRAI)


def real_browser_read(
    conn: sqlite3.Connection, tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """« Lire la page », dans le vrai Chrome."""
    return browser_read(conn, tool, args, inv, _ETAT_VRAI)
