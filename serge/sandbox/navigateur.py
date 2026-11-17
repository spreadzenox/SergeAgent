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
tâche. Dans le vrai Chrome, l'onglet s'ouvre dans son profil, qui garde
ses cookies d'une tâche à l'autre, comme celui d'une personne. Après
chaque action, l'outil rend la page relue, en version courte : le modèle
voit l'effet de son geste sans appel de plus. Une page se lit comme un
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
figés en base, et la page relue cache la valeur.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from serge.db.store import append_event, utcnow
from serge.paths import files_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox import chrome
from serge.sandbox.chantier import chantier_id
from serge.sandbox.dialogues import Dialogues
from serge.sandbox.docker import journal
from serge.sandbox.gestes import ECRANS, OUI, agir
from serge.sandbox.lecture import lire, masquer
from serge.sandbox.lecture import vers_chantier as _vers_chantier
from serge.sandbox.telechargements import DOSSIER, Telechargements

__all__ = ['_vers_chantier', 'masquer']


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


@dataclass
class _Etat:
    nom: str
    browser: Any = None
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
    return etat.browser


def _contexte(conn: sqlite3.Connection, etat: _Etat) -> Any:
    """Un contexte neuf (sans écran), ou le profil du vrai Chrome."""
    navigateur = _browser(conn, etat)
    if etat is _ETAT_VRAI and navigateur.contexts:
        return navigateur.contexts[0]
    largeur, hauteur = ECRANS['ordinateur']
    return navigateur.new_context(
        viewport={'width': largeur, 'height': hauteur},
        locale='fr-FR',
        timezone_id='Europe/Paris',
    )


def _session(
    conn: sqlite3.Connection, task_id: str, etat: _Etat = _ETAT
) -> _Session:
    session = etat.sessions.get(task_id)
    if session is not None:
        if not session.page.is_closed():
            return session
        # Son dernier onglet s'est fermé (la page l'a fermé) : on repart
        # d'un onglet neuf.
        if not session.profil_prete:
            session.context.close()
    try:
        context = _contexte(conn, etat)
    except Exception:  # noqa: BLE001 — une connexion perdue (navigateur relancé)
        etat.browser = None
        context = _contexte(conn, etat)
    session = _Session(
        context,
        context.new_page(),
        profil_prete=etat is _ETAT_VRAI,
        conteneur=etat.nom,
    )
    _ecouter(session, session.page)
    etat.sessions[task_id] = session
    return session


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


def _passer_au_vrai_chrome(conn: sqlite3.Connection, task_id: str) -> str:
    """Fait passer la tâche du navigateur sans écran au vrai Chrome : même
    adresse, mêmes cookies, et ce que la page gardait dans le navigateur.
    Rend ``''``, ou ce qui l'a empêché."""
    if task_id in _PASSEES:
        return 'tu es déjà dans le vrai Chrome'
    avant = _ETAT.sessions.get(task_id)
    adresse = avant.page.url if avant else ''
    cookies = avant.context.cookies() if avant else []
    garde: list[Any] = []
    if avant is not None:
        try:
            garde = avant.page.evaluate('() => Object.entries(localStorage)')
        except Exception:  # noqa: BLE001 — une page sans stockage
            pass
    apres = _session(conn, task_id, _ETAT_VRAI)
    _PASSEES.add(task_id)
    if avant is not None:
        apres.masques |= avant.masques
        apres.telechargements.fichiers.update(avant.telechargements.fichiers)
        del _ETAT.sessions[task_id]
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


def close_sessions() -> None:
    """Ferme les sessions ouvertes : appelée à la fin de chaque tâche."""
    for etat in (_ETAT, _ETAT_VRAI):
        for session in list(etat.sessions.values()):
            try:
                if session.profil_prete:
                    for page in list(session.pages):
                        page.close()
                else:
                    session.context.close()
            except Exception:  # noqa: BLE001 — une session déjà perdue
                pass
        etat.sessions.clear()
    _PASSEES.clear()


def montrer(task_id: str) -> bool:
    """Met devant, sur l'écran du vrai Chrome, l'onglet de la tâche, pour
    l'humain qui va y agir. Faux si la tâche n'en a pas."""
    session = _ETAT_VRAI.sessions.get(task_id)
    if session is None:
        return False
    try:
        session.page.bring_to_front()
    except Exception:  # noqa: BLE001 — un onglet perdu
        return False
    return True


def _cacher_secrets(session: _Session, cacher: bool) -> None:
    """Le temps d'une capture, un champ qui a reçu un secret montre des
    points, comme un mot de passe."""
    for champ in session.champs_secrets:
        try:
            champ.evaluate(
                '(e, c) => { e.style.webkitTextSecurity = c ? "disc" : ""; }',
                cacher,
                timeout=1000,
            )
        except Exception:  # noqa: BLE001 — le champ n'est plus sur la page
            pass


def _etat_de(task_id: str, etat: _Etat) -> _Etat:
    """Le navigateur de la tâche : le vrai Chrome si elle y est passée."""
    return _ETAT_VRAI if task_id in _PASSEES else etat


def _reglages(conn: sqlite3.Connection) -> dict[str, Any]:
    return policy_en_vigueur(conn)['tools']


def browser_action(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
    etat: _Etat = _ETAT,
) -> dict[str, Any]:
    """Une action dans la page, puis la page relue en version courte, et
    ce qui est arrivé hors de la page."""
    task_id = str(args.get('task_id') or '')
    action = str(args.get('action') or '')
    refus = ''
    if action == 'passer_au_vrai_chrome':
        try:
            refus = _passer_au_vrai_chrome(conn, task_id)
        except Exception as exc:  # noqa: BLE001 — l'échec est rendu au modèle
            refus = str(exc).splitlines()[0][:300]
    session = _session(conn, task_id, _etat_de(task_id, etat))
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
        try:
            refus = agir(session, args)
        except Exception as exc:  # noqa: BLE001 — l'échec est rendu au modèle
            refus = str(exc).splitlines()[0][:300]
        session = _session(conn, task_id, _etat_de(task_id, etat))
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
    task_id = str(args.get('task_id') or '')
    session = _session(conn, task_id, _etat_de(task_id, etat))
    lignes = int(_reglages(conn)['browser_lines_read'])
    return {
        'ok': True,
        'page': lire(session, lignes, args),
        'erreurs': session.errors[-20:],
    }


def browser_screenshot(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    invocation_id: str,
    etat: _Etat = _ETAT,
) -> dict[str, Any]:
    """Une capture de ce que voit l'écran ; gardée comme preuve sur demande.

    L'image revient au modèle (clé ``image``) ; l'interpréteur l'envoie
    comme une image, pas comme du texte.
    """
    task_id = str(args.get('task_id') or '')
    session = _session(conn, task_id, _etat_de(task_id, etat))
    entiere = args.get('full_page') in OUI
    _cacher_secrets(session, True)
    try:
        image = session.page.screenshot(
            type='jpeg', quality=70, full_page=entiere
        )
    finally:
        _cacher_secrets(session, False)
    session.shots += 1
    result: dict[str, Any] = {
        'ok': True,
        'image': 'data:image/jpeg;base64,' + base64.b64encode(image).decode(),
    }
    if not entiere:
        # Un point de cette image se vise tel quel (x, y) pour agir.
        largeur, hauteur = session.page.evaluate(
            '() => [innerWidth, innerHeight]'
        )
        result['ecran'] = f'{largeur} x {hauteur}'
    if args.get('keep') in OUI:
        result['gardee'] = _garder(conn, args, task_id, session, image)
        append_event(
            conn,
            actor=f'invocation:{invocation_id}',
            type='browser.capture',
            venture_id=str(args.get('venture_id') or ''),
            payload={'task': task_id, 'artifact': result['gardee']},
            rows=[('artifacts', result['gardee'])],
        )
    return result


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


def real_browser_screenshot(
    conn: sqlite3.Connection, tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """« Prendre une capture », dans le vrai Chrome."""
    return browser_screenshot(conn, tool, args, inv, _ETAT_VRAI)


def _garder(
    conn: sqlite3.Connection,
    args: dict[str, Any],
    task_id: str,
    session: _Session,
    image: bytes,
) -> str:
    venture_id = str(args.get('venture_id') or '')
    deliverable = str(args.get('deliverable') or '')
    dossier = files_root() / chantier_id(venture_id, 'x').removesuffix('-x')
    dossier = dossier / deliverable / 'captures'
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f'{task_id or "sans-tache"}-{session.shots}.jpg'
    chemin.write_bytes(image)
    ident = f'art_{hashlib.sha256(str(chemin).encode()).hexdigest()[:12]}'
    conn.execute(
        'INSERT OR REPLACE INTO artifacts(id, venture_id, kind, version,'
        ' path_or_url, hash, size_bytes, task_id, created_at)'
        " VALUES(?,?,'capture',1,?,?,?,?,?)",
        (
            ident,
            venture_id,
            str(chemin),
            hashlib.sha256(image).hexdigest(),
            len(image),
            task_id,
            utcnow(),
        ),
    )
    return ident
