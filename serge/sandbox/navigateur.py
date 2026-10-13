#!/usr/bin/env python3
"""L'interface web des invocations : lire une page et y agir comme un humain.

Un navigateur Chrome tourne dans son propre conteneur (``serge-navigateur``,
profil « navigateur » de la page Policy) ; Serge le pilote avec Playwright,
par le protocole de débogage de Chrome. Il ne tourne jamais dans le
programme de Serge : une page inconnue ne peut pas l'atteindre.

Une session (un onglet, ses cookies) par tâche, fermée à la fin de la
tâche. Après chaque action, l'outil rend la page relue, en version courte :
le modèle voit l'effet de son clic sans appel de plus. Une page se lit
comme un lecteur d'écran la lirait (``page.js``) : une ligne par titre,
texte, champ, bouton ou lien, avec un repère (``[e7]``) pour agir. Une
capture d'écran revient au modèle comme une image ; gardée, elle est rangée
avec le livrable (``files/<business>/<livrable>/captures/``) et a sa fiche
dans ``artifacts``.

L'adresse ``http://chantier:<port>`` mène au chantier du business : le
constructeur essaie ainsi le serveur qu'il vient de lancer. L'action
« taper un secret » tape la valeur d'un secret de l'instance (un numéro de
carte) dans un champ ; le modèle ne nomme que le secret, parmi ceux figés
en base, et la page relue cache la valeur.
"""

from __future__ import annotations

import base64
import hashlib
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from serge.db.store import append_event, utcnow
from serge.paths import config_root, files_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox.chantier import (
    chantier_id,
    container_name,
    ensure_network,
)
from serge.sandbox.docker import DockerError, docker, journal
from serge.secrets import read_secret_file

CONTAINER = 'serge-navigateur'
CDP_PORT = '9222/tcp'
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


@dataclass
class _Etat:
    playwright: Any = None
    browser: Any = None
    sessions: dict[str, _Session] = field(default_factory=dict)


_ETAT = _Etat()


def _endpoint(conn: sqlite3.Connection) -> str:
    """L'adresse du navigateur (le conteneur est lancé au besoin)."""
    profile = policy_en_vigueur(conn)['sandbox']['navigateur']
    state = docker(
        [
            'ps',
            '-a',
            '--filter',
            f'name=^{CONTAINER}$',
            '--format',
            '{{.State}}',
        ],
        timeout=30,
    ).stdout.strip()
    if not state:
        ensure_network()
        docker(
            [
                'run',
                '-d',
                '--init',
                '--name',
                CONTAINER,
                '--memory',
                f'{int(profile["memory_mb"])}m',
                '--cpus',
                '1',
                '--shm-size',
                '512m',
                '-p',
                '127.0.0.1::9222',
                '--network',
                'serge-chantiers',
                str(profile['image']),
            ],
            timeout=900,
        )
    elif state != 'running':
        docker(['start', CONTAINER], timeout=120)
    port = docker(['port', CONTAINER, CDP_PORT], timeout=30).stdout
    adresse = port.strip().splitlines()[0] if port.strip() else ''
    if not adresse:
        raise DockerError('le navigateur ne publie pas son port de débogage')
    return f'http://{adresse}'


def _browser(conn: sqlite3.Connection) -> Any:
    if _ETAT.browser is not None and _ETAT.browser.is_connected():
        return _ETAT.browser
    from playwright.sync_api import sync_playwright

    if _ETAT.playwright is None:
        _ETAT.playwright = sync_playwright().start()
    endpoint = _endpoint(conn)
    try:
        _ETAT.browser = _ETAT.playwright.chromium.connect_over_cdp(endpoint)
    except Exception as exc:
        journal(f'navigateur injoignable ({endpoint}) : {exc}')
        raise
    return _ETAT.browser


def _session(conn: sqlite3.Connection, task_id: str) -> _Session:
    session = _ETAT.sessions.get(task_id)
    if session is not None:
        return session
    largeur, hauteur = ECRANS['ordinateur']
    reglage = {
        'viewport': {'width': largeur, 'height': hauteur},
        'locale': 'fr-FR',
        'timezone_id': 'Europe/Paris',
    }
    try:
        context = _browser(conn).new_context(**reglage)
    except Exception:  # noqa: BLE001 — une connexion perdue (navigateur relancé)
        _ETAT.browser = None
        context = _browser(conn).new_context(**reglage)
    page = context.new_page()
    session = _Session(context, page)

    def erreur(texte: str) -> None:
        session.errors.append(masquer(texte, session.masques)[:300])
        del session.errors[:-50]

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
    _ETAT.sessions[task_id] = session
    return session


def close_sessions() -> None:
    """Ferme les sessions ouvertes : appelée à la fin de chaque tâche."""
    for session in list(_ETAT.sessions.values()):
        try:
            session.context.close()
        except Exception:  # noqa: BLE001 — une session déjà perdue
            pass
    _ETAT.sessions.clear()


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
        valeur = read_secret_file(config_root() / 'secrets' / texte)
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
) -> dict[str, Any]:
    """Une action dans la page, puis la page relue en version courte."""
    session = _session(conn, str(args.get('task_id') or ''))
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
    return result


def browser_read(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """La page entière, et les dernières erreurs de la page."""
    session = _session(conn, str(args.get('task_id') or ''))
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
) -> dict[str, Any]:
    """Une capture de ce que voit l'écran ; gardée comme preuve sur demande.

    L'image revient au modèle (clé ``image``) ; l'interpréteur l'envoie
    comme une image, pas comme du texte.
    """
    task_id = str(args.get('task_id') or '')
    session = _session(conn, task_id)
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
