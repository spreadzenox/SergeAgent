#!/usr/bin/env python3
"""Les sessions du navigateur des invocations : une par tâche.

Une session, ce sont des onglets et leurs cookies. Elle s'ouvre au premier
outil de navigateur d'une tâche et se ferme à la fin de la tâche
(``close_sessions``). Trois sortes :

- **dans le navigateur sans écran**, un contexte neuf, sans cookie ;
- **dans le vrai Chrome**, les onglets s'ouvrent dans son profil, qui
  garde ses cookies d'une tâche à l'autre, comme celui d'une personne ;
- **avec un compte web** (le paramètre ``account`` des outils, figé en
  base), un contexte à part, dans l'un ou l'autre navigateur : il s'ouvre
  avec les cookies gardés de ce compte (``serge/web_accounts.py``), et eux
  seuls, et ils sont gardés de nouveau, chiffrés, quand il se ferme. Le
  compte est pris par la tâche le temps de la session.

Une tâche qui a commencé dans le navigateur sans écran peut passer au vrai
Chrome (``passer_au_vrai_chrome``) : même adresse, mêmes cookies.

Exemple : la tâche ``t_12`` de « Fouiller un réseau » a le compte
``reddit``. Sa session ``t_12@reddit`` s'ouvre connectée ; à la fin, ses
cookies du jour remplacent ceux d'hier en base.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from serge import web_accounts
from serge.sandbox import chrome
from serge.sandbox.dialogues import Dialogues
from serge.sandbox.docker import journal
from serge.sandbox.gestes import ECRANS
from serge.sandbox.lecture import masquer
from serge.sandbox.telechargements import DOSSIER, Telechargements


@dataclass
class _Session:
    context: Any
    page: Any
    errors: list[str] = field(default_factory=list)
    shots: int = 0
    # Les secrets tapés dans cette session, et les champs qui les ont
    # reçus : jamais rendus au modèle, ni en texte ni sur une capture.
    masques: set[str] = field(default_factory=set)
    champs_secrets: list[Any] = field(default_factory=list)
    # Le vrai Chrome prête son profil : seuls les onglets sont à fermer.
    profil_prete: bool = False
    # Le conteneur du navigateur : un fichier téléchargé en est sorti.
    conteneur: str = ''
    # Les onglets de la session, du premier au dernier ouvert ; ``page``
    # est celui où elle agit.
    pages: list[Any] = field(default_factory=list)
    # Ce qui est arrivé aux onglets depuis le dernier résultat rendu.
    onglets: list[str] = field(default_factory=list)
    dialogues: Dialogues = field(default_factory=Dialogues)
    telechargements: Telechargements = field(default_factory=Telechargements)
    # Le compte web de la session (``web_accounts``) et la tâche qui l'a
    # pris : ses cookies sont gardés à la fermeture. ``mot_de_passe`` le
    # rend à « taper un secret », sans passer par le modèle.
    account: str = ''
    task_id: str = ''
    mot_de_passe: Callable[[], str] | None = None


@dataclass
class _Etat:
    nom: str
    browser: Any = None
    # Le profil du navigateur, noté à la connexion : c'est alors son seul
    # contexte. Ensuite, la liste des contextes n'a pas d'ordre.
    profil: Any = None
    sessions: dict[str, _Session] = field(default_factory=dict)


_ETAT = _Etat(chrome.SANS_ECRAN)
_ETAT_VRAI = _Etat(chrome.VRAI)
_PLAYWRIGHT: dict[str, Any] = {}
# Les tâches passées du navigateur sans écran au vrai Chrome.
_PASSEES: set[str] = set()


def _endpoint(conn: sqlite3.Connection, nom: str) -> str:
    return chrome.endpoint(conn, nom)


# Ce qu'il faut faire quand le paquet qui pilote le navigateur manque.
MANQUE = (
    'le paquet Python playwright manque sur ce serveur : l’installer dans le'
    ' Python des services (docs/installation/DEPLOY_VPS.md), puis'
    ' redémarrer les files'
)


class NavigateurAbsent(RuntimeError):
    """Le paquet Python qui pilote le navigateur n'est pas installé."""


def navigateur_installe() -> bool:
    """Le paquet Python qui pilote le navigateur est-il installé ? Il ne
    télécharge aucun navigateur : il se connecte au conteneur Chromium."""
    return importlib.util.find_spec('playwright') is not None


def _browser(conn: sqlite3.Connection, etat: _Etat) -> Any:
    if etat.browser is not None and etat.browser.is_connected():
        return etat.browser
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        journal(MANQUE)
        raise NavigateurAbsent(MANQUE) from exc

    if 'pw' not in _PLAYWRIGHT:
        _PLAYWRIGHT['pw'] = sync_playwright().start()
    endpoint = _endpoint(conn, etat.nom)
    try:
        # Le navigateur écrit ses téléchargements dans ce dossier de son
        # conteneur (``telechargements.py``).
        etat.browser = _PLAYWRIGHT['pw'].chromium.connect_over_cdp(
            endpoint, artifacts_dir=DOSSIER
        )
    except Exception as exc:
        journal(f'navigateur injoignable ({endpoint}) : {exc}')
        raise
    contextes = etat.browser.contexts
    etat.profil = contextes[0] if len(contextes) == 1 else None
    return etat.browser


def _contexte(
    conn: sqlite3.Connection, etat: _Etat, garde: dict[str, Any] | None
) -> Any:
    """Un contexte neuf (sans écran), le profil du vrai Chrome, ou le
    contexte d'un compte web : à part, avec ses cookies gardés (``garde``)
    et eux seuls."""
    navigateur = _browser(conn, etat)
    if garde is None and etat is _ETAT_VRAI and etat.profil is not None:
        return etat.profil
    largeur, hauteur = ECRANS['ordinateur']
    options: dict[str, Any] = {
        'locale': 'fr-FR',
        'timezone_id': 'Europe/Paris',
    }
    if etat is _ETAT_VRAI:
        # Une vraie fenêtre, à la taille de l'écran : rien n'est simulé.
        options['no_viewport'] = True
    else:
        options['viewport'] = {'width': largeur, 'height': hauteur}
    if garde:
        options['storage_state'] = garde
    return navigateur.new_context(**options)


def _cle(task_id: str, account: str) -> str:
    return f'{task_id}@{account}' if account else task_id


def _session(
    conn: sqlite3.Connection,
    task_id: str,
    etat: _Etat = _ETAT,
    account: str = '',
) -> _Session:
    """La session de la tâche ; avec un compte web, sa session à lui.

    Raises:
        web_accounts.AccountError: Le compte ne peut pas servir.
    """
    session = etat.sessions.get(_cle(task_id, account))
    if session is not None:
        if not session.page.is_closed():
            return session
        # Son dernier onglet s'est fermé (la page l'a fermé) : on repart
        # d'un onglet neuf.
        _fermer(conn, session)
    garde = web_accounts.take(conn, account, task_id) if account else None
    try:
        context = _contexte(conn, etat, garde)
        page = context.new_page()
    except Exception:  # noqa: BLE001 — une connexion perdue (navigateur relancé)
        etat.browser = None
        context = _contexte(conn, etat, garde)
        page = context.new_page()
    session = _Session(
        context,
        page,
        profil_prete=etat is _ETAT_VRAI and not account,
        conteneur=etat.nom,
        account=account,
        task_id=task_id,
    )
    if account:
        session.mot_de_passe = lambda: web_accounts.password(conn, account)
    _ecouter(session, session.page)
    etat.sessions[_cle(task_id, account)] = session
    return session


def _session_de(
    conn: sqlite3.Connection, args: dict[str, Any], etat: _Etat
) -> _Session:
    """La session que désignent les paramètres d'un outil : sa tâche, son
    compte web s'il en a un, dans le vrai Chrome si la tâche y est passée."""
    task_id = str(args.get('task_id') or '')
    account = str(args.get('account') or '').strip().lower()
    return _session(conn, task_id, _etat_de(task_id, etat), account)


def _fermer(conn: sqlite3.Connection | None, session: _Session) -> None:
    """Ferme une session. Celle d'un compte web garde d'abord ses cookies
    en base et rend le compte ; le profil du vrai Chrome ne perd que ses
    onglets."""
    try:
        if session.account and conn is not None:
            try:
                garde = session.context.storage_state()
            except Exception:  # noqa: BLE001 — un contexte déjà perdu
                garde = None
            web_accounts.release(conn, session.account, session.task_id, garde)
        if session.profil_prete:
            for page in list(session.pages):
                page.close()
        else:
            session.context.close()
    except Exception as exc:  # noqa: BLE001 — une session déjà perdue
        if session.account:
            journal(f'session du compte {session.account} mal fermée : {exc}')


def _ecouter(session: _Session, page: Any) -> None:
    """Suit un onglet de la session : ses erreurs, et ce qu'il fait hors de
    la page (une boîte de dialogue, un téléchargement, un nouvel onglet)."""
    session.pages.append(page)

    def erreur(texte: str) -> None:
        session.errors.append(masquer(texte, session.masques)[:300])
        del session.errors[:-50]

    def ouvert(nouveau: Any) -> None:
        session.page = nouveau
        _ecouter(session, nouveau)
        session.onglets.append(
            'un nouvel onglet s’est ouvert : tu y es (fermer_onglet revient'
            ' au précédent)'
        )

    def ferme(_page: Any) -> None:
        if page in session.pages:
            session.pages.remove(page)
        if session.page is page and session.pages:
            session.page = session.pages[-1]
            session.onglets.append(
                'l’onglet s’est fermé : tu es revenu au précédent'
            )

    page.on(
        'console',
        lambda m: erreur(f'console : {m.text}') if m.type == 'error' else None,
    )
    page.on('pageerror', lambda e: erreur(f'JavaScript : {e}'))
    page.on(
        'requestfailed',
        lambda r: erreur(f'requête ratée : {r.method} {r.url} ({r.failure})'),
    )
    page.on(
        'response',
        lambda r: (
            erreur(f'HTTP {r.status} : {r.url}') if r.status >= 400 else None
        ),
    )
    page.on('dialog', session.dialogues.repondre)
    page.on('download', session.telechargements.recevoir)
    page.on('popup', ouvert)
    page.on('close', ferme)


def _passer_au_vrai_chrome(
    conn: sqlite3.Connection, task_id: str, account: str = ''
) -> str:
    """Fait passer la tâche du navigateur sans écran au vrai Chrome : même
    adresse, mêmes cookies, et ce que la page gardait dans le navigateur.
    Rend ``''``, ou ce qui l'a empêché."""
    if task_id in _PASSEES:
        return 'tu es déjà dans le vrai Chrome'
    avant = _ETAT.sessions.get(_cle(task_id, account))
    adresse = avant.page.url if avant else ''
    cookies = avant.context.cookies() if avant else []
    garde: list[Any] = []
    if avant is not None:
        try:
            garde = avant.page.evaluate('() => Object.entries(localStorage)')
        except Exception:  # noqa: BLE001 — une page sans stockage
            pass
    apres = _session(conn, task_id, _ETAT_VRAI, account)
    _PASSEES.add(task_id)
    if avant is not None:
        apres.masques |= avant.masques
        apres.telechargements.fichiers.update(avant.telechargements.fichiers)
        del _ETAT.sessions[_cle(task_id, account)]
        avant.context.close()
    if cookies:
        apres.context.add_cookies(cookies)
    if adresse and adresse != 'about:blank':
        apres.page.goto(adresse, wait_until='domcontentloaded', timeout=30000)
        if garde:
            apres.page.evaluate(
                '(lignes) => { for (const [cle, valeur] of lignes)'
                ' localStorage.setItem(cle, valeur); }',
                garde,
            )
            apres.page.reload(wait_until='domcontentloaded', timeout=30000)
    return ''


def close_sessions(conn: sqlite3.Connection | None = None) -> None:
    """Ferme les sessions ouvertes : appelée à la fin de chaque tâche, avec
    la base, pour garder les cookies des comptes web."""
    for etat in (_ETAT, _ETAT_VRAI):
        for session in list(etat.sessions.values()):
            _fermer(conn, session)
        etat.sessions.clear()
    _PASSEES.clear()


def montrer(task_id: str) -> bool:
    """Met devant, sur l'écran du vrai Chrome, l'onglet de la tâche, pour
    l'humain qui va y agir. Faux si la tâche n'en a pas."""
    session = next(
        (
            s
            for cle, s in _ETAT_VRAI.sessions.items()
            if cle.partition('@')[0] == task_id
        ),
        None,
    )
    if session is None:
        return False
    try:
        session.page.bring_to_front()
    except Exception:  # noqa: BLE001 — un onglet perdu
        return False
    return True


def _etat_de(task_id: str, etat: _Etat) -> _Etat:
    """Le navigateur de la tâche : le vrai Chrome si elle y est passée."""
    return _ETAT_VRAI if task_id in _PASSEES else etat
