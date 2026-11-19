#!/usr/bin/env python3
"""Les captures d'écran du navigateur des invocations.

Une capture revient au modèle comme une image. Gardée, elle est rangée
avec le livrable (``files/<business>/<livrable>/captures/``) et a sa fiche
dans ``artifacts``. Le temps d'une capture, un champ qui a reçu un secret
montre des points, comme un mot de passe.
"""

from __future__ import annotations

import base64
import hashlib
import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow
from serge.paths import files_root
from serge.sandbox.chantier import chantier_id
from serge.sandbox.gestes import OUI
from serge.sandbox.sessions import _ETAT, _ETAT_VRAI, _Etat, _session_de
from serge.web_accounts import AccountError


def _cacher_secrets(session: Any, cacher: bool) -> None:
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
    try:
        session = _session_de(conn, args, etat)
    except AccountError as exc:
        return {'ok': False, 'code': 'compte', 'detail': str(exc)}
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


def real_browser_screenshot(
    conn: sqlite3.Connection, tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """« Prendre une capture », dans le vrai Chrome."""
    return browser_screenshot(conn, tool, args, inv, _ETAT_VRAI)


def _garder(
    conn: sqlite3.Connection,
    args: dict[str, Any],
    task_id: str,
    session: Any,
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
