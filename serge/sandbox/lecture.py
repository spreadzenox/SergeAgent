#!/usr/bin/env python3
"""Lire une page comme un lecteur d'écran, et y trouver ce qu'on vise.

``page.js`` lit un document : une ligne par titre, texte, champ, bouton,
lien ou élément cliquable, avec un repère (``[e7]``) pour agir. Une page
peut contenir d'autres documents, dans des cadres intégrés (un formulaire
de paiement, une vidéo) : chacun est lu à son tour, à la place de son
cadre, et ses repères commencent par celui du cadre (``e7.e2``).

Ce qu'on vise pour agir se désigne de trois façons : un repère, un texte
visible à l'écran, ou un point de l'écran (``x``, ``y``, lus sur une
capture), pour ce que la lecture ne décrit pas (un dessin, une carte).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from serge.sandbox.chantier import chantier_id, container_name
from serge.sandbox.masque import masquer

SNAPSHOT_JS = (Path(__file__).with_name('page.js')).read_text(encoding='utf-8')


def chantier(args: dict[str, Any]) -> str:
    """Le nom du conteneur du chantier de la tâche."""
    return container_name(
        chantier_id(
            str(args.get('venture_id') or ''),
            str(args.get('deliverable') or ''),
        )
    )


def vers_chantier(url: str, args: dict[str, Any]) -> str:
    """``http://chantier:3000/x`` mène au conteneur du chantier de la tâche."""
    parts = urlsplit(url)
    if parts.hostname != 'chantier':
        return url
    port = f':{parts.port}' if parts.port else ''
    return urlunsplit(parts._replace(netloc=f'{chantier(args)}{port}'))


def attendre(page: Any) -> None:
    try:
        page.wait_for_load_state('networkidle', timeout=3000)
    except Exception:  # noqa: BLE001 — une page qui ne se calme pas
        pass


def _document(frame: Any, prefixe: str, lignes: int) -> dict[str, Any]:
    return frame.evaluate(
        SNAPSHOT_JS, {'maxLines': max(lignes, 1), 'prefix': prefixe}
    )


def _cadres(page: Any, data: dict[str, Any], lignes: int) -> None:
    """Ajoute, sous la ligne de chaque cadre intégré, ce qu'il contient."""
    for frame in page.frames[1:]:
        if len(data['lines']) >= lignes:
            data['truncated'] = True
            return
        try:
            marque = frame.frame_element().get_attribute('data-serge-ref')
            if not marque:
                continue
            dedans = _document(
                frame, f'{marque}.', lignes - len(data['lines'])
            )
        except Exception:  # noqa: BLE001 — un cadre parti, ou illisible
            continue
        debut = f'[{marque}] cadre'
        rang = next(
            (
                i
                for i, ligne in enumerate(data['lines'])
                if ligne.lstrip().startswith(debut)
            ),
            None,
        )
        if rang is None:
            continue
        retrait = ' ' * (
            len(data['lines'][rang]) - len(data['lines'][rang].lstrip()) + 2
        )
        data['lines'][rang + 1 : rang + 1] = [
            retrait + ligne for ligne in dedans['lines']
        ]
        data['truncated'] = data['truncated'] or dedans['truncated']


def releve(page: Any, lignes: int) -> dict[str, Any]:
    """La page vue comme un lecteur d'écran, cadres intégrés compris. Une
    navigation en cours (un clic qui charge une autre page) coupe la
    lecture : on attend que la page se pose, puis on relit."""
    for _ in range(2):
        try:
            data = _document(page.main_frame, '', lignes)
            break
        except Exception as exc:  # noqa: BLE001 — Playwright, une navigation
            if 'context was destroyed' not in str(exc):
                raise
            attendre(page)
    else:
        data = _document(page.main_frame, '', lignes)
    _cadres(page, data, lignes)
    return data


def lire(session: Any, lignes: int, args: dict[str, Any]) -> str:
    data = releve(session.page, lignes)
    texte = '\n'.join(
        [f'Page : {data["title"]} — {data["url"]}', *data['lines']]
    )
    if data['truncated']:
        texte += f'\n(page coupée à {lignes} lignes : fais défiler)'
    texte = masquer(texte, session.masques)
    # Le conteneur du chantier garde son nom court pour le modèle.
    return texte.replace(chantier(args), 'chantier')


def element(page: Any, ref: Any) -> Any:
    """L'élément d'un repère ; ``e7.e2`` est dans le cadre intégré ``e7``."""
    repere = str(ref).strip('[] ')
    selecteur = f'[data-serge-ref="{repere}"]'
    if '.' in repere:
        for frame in page.frames[1:]:
            trouve = frame.locator(selecteur)
            if trouve.count():
                return trouve.first
    return page.locator(selecteur).first


def viser(page: Any, args: dict[str, Any], cle: str = 'text') -> Any:
    """L'élément visé : par son repère, sinon par son texte visible, ou
    par le nom qu'un lecteur d'écran lui donne (l'étiquette d'un champ, le
    texte de remplacement d'une image, une info-bulle). Le texte exact
    d'abord, dans la page puis dans ses cadres. ``None`` si l'action ne
    donne ni repère ni texte."""
    if args.get('ref'):
        return element(page, args['ref'])
    texte = str(args.get(cle) or '').strip()
    if not texte:
        return None
    for exact in (True, False):
        for frame in page.frames:
            for chercher in (
                frame.get_by_text,
                frame.get_by_label,
                frame.get_by_placeholder,
                frame.get_by_alt_text,
                frame.get_by_title,
            ):
                trouve = chercher(texte, exact=exact).filter(visible=True)
                if trouve.count():
                    return trouve.first
    return page.get_by_text(texte).first


def point(
    args: dict[str, Any], x: str = 'x', y: str = 'y'
) -> tuple[float, float] | None:
    """Le point de l'écran visé, ou ``None`` : ``x`` et ``y``, en pixels
    depuis le coin en haut à gauche, comme sur une capture de l'écran."""
    try:
        return float(args[x]), float(args[y])
    except (KeyError, TypeError, ValueError):
        return None
