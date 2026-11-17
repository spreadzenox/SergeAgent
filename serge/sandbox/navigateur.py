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

Une session (un onglet, ses cookies) par tâche, fermée à la fin de la
tâche. Dans le vrai Chrome, l'onglet s'ouvre dans son profil, qui garde
ses cookies d'une tâche à l'autre, comme celui d'une personne. Après chaque action, l'outil rend la page relue, en version courte :
le modèle voit l'effet de son clic sans appel de plus. Une page se lit
comme un lecteur d'écran la lirait (``page.js``) : une ligne par titre,
texte, champ, bouton ou lien, avec un repère (``[e7]``) pour agir. Une
capture d'écran revient au modèle comme une image ; gardée, elle est rangée
avec le livrable (``files/<business>/<livrable>/captures/``) et a sa fiche
dans ``artifacts``.

L'adresse ``http://chantier:<port>`` mène au chantier du business : le
constructeur essaie ainsi le serveur qu'il vient de lancer. L'action
« taper un secret » tape la valeur d'un secret de l'instance dans un champ :
un fichier de secret, ou un champ de la carte chiffrée de Serge
(``payment-card.enc#pan``). Le modèle ne nomme que le secret, parmi ceux
figés en base, et la page relue cache la valeur.

Une boîte de dialogue du navigateur (message, question, saisie) n'est pas
dans la page : Serge y répond lui-même et le dit dans le résultat de
l'action (``dialogues.py``).
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from serge.db.store import append_event, utcnow
from serge.paths import config_root, files_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox import chrome
from serge.sandbox.chantier import chantier_id, container_name
from serge.sandbox.dialogues import Dialogues
from serge.sandbox.docker import journal
from serge.secrets import read_secret_value

SNAPSHOT_JS = (Path(__file__).with_name('page.js')).read_text(encoding='utf-8')
ECRANS = {'ordinateur': (1280, 800), 'mobile': (390, 844)}


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
    # Le vrai Chrome prête son profil : seul l'onglet est à fermer.
    profil_prete: bool = False
    dialogues: Dialogues = field(default_factory=Dialogues)


@dataclass
class _Etat:
    nom: str
    browser: Any = None
    sessions: dict[str, _Session] = field(default_factory=dict)


_ETAT = _Etat(chrome.SANS_ECRAN)
_ETAT_VRAI = _Etat(chrome.VRAI)
_PLAYWRIGHT: dict[str, Any] = {}


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
        etat.browser = _PLAYWRIGHT['pw'].chromium.connect_over_cdp(endpoint)
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
        return session
    try:
        context = _contexte(conn, etat)
    except Exception:  # noqa: BLE001 — une connexion perdue (navigateur relancé)
        etat.browser = None
        context = _contexte(conn, etat)
    page = context.new_page()
    session = _Session(context, page, profil_prete=etat is _ETAT_VRAI)

    def erreur(texte: str) -> None:
        session.errors.append(masquer(texte, session.masques)[:300])
        del session.errors[:-50]

    page.on(
        'console',
        lambda m: erreur(f'console : {m.text}') if m.type == 'error' else None,
    )
    page.on('pageerror', lambda e: erreur(f'JavaScript : {e}'))
    page.on('dialog', session.dialogues.repondre)
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
    etat.sessions[task_id] = session
    return session


def close_sessions() -> None:
    """Ferme les sessions ouvertes : appelée à la fin de chaque tâche."""
    for etat in (_ETAT, _ETAT_VRAI):
        for session in list(etat.sessions.values()):
            try:
                if session.profil_prete:
                    session.page.close()
                else:
                    session.context.close()
            except Exception:  # noqa: BLE001 — une session déjà perdue
                pass
        etat.sessions.clear()


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


def _chantier(args: dict[str, Any]) -> str:
    return container_name(
        chantier_id(
            str(args.get('venture_id') or ''),
            str(args.get('deliverable') or ''),
        )
    )


def _vers_chantier(url: str, args: dict[str, Any]) -> str:
    """``http://chantier:3000/x`` mène au conteneur du chantier de la tâche."""
    parts = urlsplit(url)
    if parts.hostname != 'chantier':
        return url
    port = f':{parts.port}' if parts.port else ''
    return urlunsplit(parts._replace(netloc=f'{_chantier(args)}{port}'))


def _releve(page: Any, lignes: int) -> dict[str, Any]:
    """La page vue comme un lecteur d'écran. Une navigation en cours (un
    clic qui charge une autre page) coupe la lecture : on attend que la
    page se pose, puis on relit."""
    for _ in range(2):
        try:
            return page.evaluate(SNAPSHOT_JS, {'maxLines': lignes})
        except Exception as exc:  # noqa: BLE001 — Playwright, une navigation
            if 'context was destroyed' not in str(exc):
                raise
            _attendre(page)
    return page.evaluate(SNAPSHOT_JS, {'maxLines': lignes})


def _lire(session: _Session, lignes: int, args: dict[str, Any]) -> str:
    data = _releve(session.page, lignes)
    texte = '\n'.join(
        [f'Page : {data["title"]} — {data["url"]}', *data['lines']]
    )
    if data['truncated']:
        texte += f'\n(page coupée à {lignes} lignes : fais défiler)'
    texte = masquer(texte, session.masques)
    # Le conteneur du chantier garde son nom court pour le modèle.
    return texte.replace(_chantier(args), 'chantier')


def masquer(texte: str, secrets: set[str]) -> str:
    """Remplace chaque secret par ``••••``, même remis en forme par la
    page : ``4242 4242 4242 4242`` ou ``12 / 34``."""
    for secret in secrets:
        motif = r'[\s/.\-]*'.join(
            re.escape(c) for c in secret if not c.isspace()
        )
        if motif:
            texte = re.sub(motif, '••••', texte)
    return texte


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


def _attendre(page: Any) -> None:
    try:
        page.wait_for_load_state('networkidle', timeout=3000)
    except Exception:  # noqa: BLE001 — une page qui ne se calme pas
        pass


def _element(page: Any, ref: Any) -> Any:
    return page.locator(f'[data-serge-ref="{str(ref).strip("[]")}"]').first


def _agir(session: _Session, args: dict[str, Any]) -> str:
    """Fait l'action ; rend ``''``, ou ce qui l'a empêchée."""
    page = session.page
    action = str(args.get('action') or '')
    texte = str(args.get('text') or '')
    if action == 'ouvrir':
        page.goto(
            _vers_chantier(texte, args),
            wait_until='domcontentloaded',
            timeout=30000,
        )
    elif action == 'cliquer':
        _element(page, args.get('ref')).click(timeout=10000)
    elif action == 'taper':
        element = _element(page, args.get('ref'))
        element.fill(texte, timeout=10000)
        if args.get('submit') in (True, 'true', '1', 'oui'):
            element.press('Enter')
    elif action == 'taper_secret':
        # Le modèle nomme le secret ; Serge tape sa valeur, que le modèle ne
        # voit jamais. Seuls les secrets figés en base sont permis.
        permis = {
            n.strip() for n in str(args.get('secrets') or '').split(',')
        } - {''}
        if texte not in permis:
            return f'secret non permis : {texte}'
        valeur = read_secret_value(config_root() / 'secrets', texte)
        if not valeur:
            return f'secret absent sur ce serveur : {texte}'
        session.masques.add(valeur)
        element = _element(page, args.get('ref'))
        element.fill(valeur, timeout=10000)
        session.champs_secrets.append(element)
    elif action == 'choisir':
        element = _element(page, args.get('ref'))
        try:
            element.select_option(label=texte, timeout=5000)
        except Exception:  # noqa: BLE001 — sinon par sa valeur
            element.select_option(value=texte, timeout=5000)
    elif action == 'touche':
        page.keyboard.press(texte or 'Enter')
    elif action == 'defiler':
        page.mouse.wheel(0, -700 if texte == 'haut' else 700)
    elif action == 'revenir':
        page.go_back(wait_until='domcontentloaded', timeout=15000)
    elif action == 'attendre':
        if texte:
            page.get_by_text(texte).first.wait_for(timeout=15000)
        else:
            page.wait_for_timeout(3000)
    elif action == 'ecran':
        largeur, hauteur = ECRANS.get(texte, ECRANS['ordinateur'])
        page.set_viewport_size({'width': largeur, 'height': hauteur})
    elif action in ('accepter_dialogue', 'refuser_dialogue'):
        session.dialogues.preparer(action == 'accepter_dialogue', texte)
    else:
        return f'action inconnue : {action}'
    _attendre(page)
    return ''


def _reglages(conn: sqlite3.Connection) -> dict[str, Any]:
    return policy_en_vigueur(conn)['tools']


def browser_action(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
    etat: _Etat = _ETAT,
) -> dict[str, Any]:
    """Une action dans la page, puis la page relue en version courte."""
    session = _session(conn, str(args.get('task_id') or ''), etat)
    erreurs = len(session.errors)
    try:
        refus = _agir(session, args)
    except Exception as exc:  # noqa: BLE001 — l'échec est rendu au modèle
        refus = str(exc).splitlines()[0][:300]
    lignes = int(_reglages(conn)['browser_lines_after_action'])
    result: dict[str, Any] = {
        'ok': not refus,
        'page': _lire(session, lignes, args),
    }
    if refus:
        result['detail'] = masquer(refus, session.masques)
    nouvelles = session.errors[erreurs:]
    if nouvelles:
        result['nouvelles_erreurs'] = nouvelles[:10]
    dialogues = session.dialogues.raconter()
    if dialogues:
        result['dialogues'] = [masquer(d, session.masques) for d in dialogues]
    return result


def browser_read(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
    etat: _Etat = _ETAT,
) -> dict[str, Any]:
    """La page entière, et les dernières erreurs de la page."""
    session = _session(conn, str(args.get('task_id') or ''), etat)
    lignes = int(_reglages(conn)['browser_lines_read'])
    return {
        'ok': True,
        'page': _lire(session, lignes, args),
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
    session = _session(conn, task_id, etat)
    entiere = args.get('full_page') in (True, 'true', '1', 'oui')
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
    if args.get('keep') in (True, 'true', '1', 'oui'):
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
