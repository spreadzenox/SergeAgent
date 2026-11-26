#!/usr/bin/env python3
"""Les gestes d'une invocation dans une page : ceux d'une personne.

Avec une souris : cliquer, double-cliquer, clic droit, survoler, glisser et
déposer, faire défiler. Avec un clavier : taper, appuyer sur une touche ou
un raccourci. Et le reste de ce qu'on fait dans un navigateur : ouvrir une
adresse, revenir, recharger, choisir dans une liste, déposer un fichier,
fermer un onglet, changer la taille de l'écran, attendre.

Ce qu'un geste vise se désigne par son repère dans la page lue (``ref``),
par un texte visible à l'écran (``text``), ou par un point de l'écran
(``x``, ``y``), lu sur une capture. Un point marche sur tout ce qui se
voit, même ce que la lecture ne décrit pas (un dessin, une carte).

Exemples : ``{action: 'cliquer', text: 'Exporter en CSV'}`` ;
``{action: 'glisser', ref: 'e4', to: 'e9'}`` ;
``{action: 'cliquer', x: 640, y: 300}``.
"""

from __future__ import annotations

import mimetypes
import re
from collections.abc import Callable
from typing import Any

from serge.paths import config_root
from serge.sandbox.lecture import (
    attendre,
    element,
    point,
    vers_chantier,
    viser,
)
from serge.secrets import read_secret_value
from serge.web_accounts import PASSWORD_NAME, AccountError

ECRANS = {'ordinateur': (1280, 800), 'mobile': (390, 844)}
OUI = (True, 'true', '1', 'oui')
SANS_CIBLE = (
    'il manque ce qui est visé : un repère (ref), un texte visible (text)'
    ' ou un point de l’écran (x, y)'
)


def _cliquer(session: Any, args: dict[str, Any], **souris: Any) -> str:
    """Un clic sur ce qui est visé ; ``souris`` : double clic, clic droit."""
    page = session.page
    cible = viser(page, args)
    if cible is not None:
        cible.click(timeout=10000, **souris)
        return ''
    ou = point(args)
    if ou is None:
        return SANS_CIBLE
    page.mouse.click(*ou, **souris)
    return ''


def _survoler(session: Any, args: dict[str, Any]) -> str:
    cible = viser(session.page, args)
    if cible is not None:
        cible.hover(timeout=10000)
        return ''
    ou = point(args)
    if ou is None:
        return SANS_CIBLE
    session.page.mouse.move(*ou)
    return ''


def _destination(page: Any, vers: str) -> Any:
    """Où déposer : un point (``640,300``), un repère (``e9``), ou un texte
    visible."""
    x, virgule, y = vers.partition(',')
    if virgule:
        try:
            return float(x), float(y)
        except ValueError:
            pass
    if re.fullmatch(r'\[?e\d+(\.e\d+)*\]?', vers):
        return element(page, vers)
    return viser(page, {'text': vers})


def _glisser(session: Any, args: dict[str, Any]) -> str:
    page = session.page
    vers = str(args.get('to') or '').strip()
    if not vers:
        return 'glisser : dis où déposer (to : un repère, ou « x,y »)'
    depart = element(page, args['ref']) if args.get('ref') else point(args)
    if depart is None:
        return 'glisser : dis quoi prendre (ref, ou x et y)'
    arrivee = _destination(page, vers)
    if not isinstance(depart, tuple) and not isinstance(arrivee, tuple):
        depart.drag_to(arrivee, timeout=10000)
        return ''
    # À la souris, pas à pas, comme une main : d'un point à un point.
    for bout in (depart, arrivee):
        if not isinstance(bout, tuple):
            bout.scroll_into_view_if_needed(timeout=5000)
    debut, fin = (
        b if isinstance(b, tuple) else _centre(b) for b in (depart, arrivee)
    )
    page.mouse.move(*debut)
    page.mouse.down()
    page.mouse.move(*fin, steps=12)
    page.mouse.up()
    return ''


def _centre(cible: Any) -> tuple[float, float]:
    boite = cible.bounding_box(timeout=5000)
    return boite['x'] + boite['width'] / 2, boite['y'] + boite['height'] / 2


def _taper(session: Any, args: dict[str, Any]) -> str:
    """Dans un champ (``ref``) ; sans repère, au clavier, là où est le
    curseur (après un clic dans un éditeur ou un dessin, par exemple)."""
    page = session.page
    texte = str(args.get('text') or '')
    if args.get('ref'):
        champ = element(page, args['ref'])
        champ.fill(texte, timeout=10000)
        if args.get('submit') in OUI:
            champ.press('Enter')
        return ''
    page.keyboard.type(texte)
    if args.get('submit') in OUI:
        page.keyboard.press('Enter')
    return ''


def _taper_secret(session: Any, args: dict[str, Any]) -> str:
    # Le modèle nomme le secret ; Serge tape sa valeur, que le modèle ne
    # voit jamais. Seuls les secrets figés en base sont permis, et, dans
    # la session d'un compte web, le mot de passe de ce compte.
    nom = str(args.get('text') or '')
    permis = {n.strip() for n in str(args.get('secrets') or '').split(',')} - {
        ''
    }
    if nom == PASSWORD_NAME and session.mot_de_passe is not None:
        try:
            valeur = session.mot_de_passe()
        except AccountError as exc:
            # Un compte connecté avec Google n'a pas de mot de passe : le
            # refus dit au modèle comment se connecter.
            return str(exc)
    elif nom not in permis:
        return f'secret non permis : {nom}'
    else:
        valeur = read_secret_value(config_root() / 'secrets', nom)
    if not valeur:
        return f'secret absent sur ce serveur : {nom}'
    session.masques.add(valeur)
    champ = element(session.page, args.get('ref'))
    champ.fill(valeur, timeout=10000)
    session.champs_secrets.append(champ)
    return ''


def _choisir(session: Any, args: dict[str, Any]) -> str:
    liste = element(session.page, args.get('ref'))
    texte = str(args.get('text') or '')
    try:
        liste.select_option(label=texte, timeout=5000)
    except Exception:  # noqa: BLE001 — sinon par sa valeur
        liste.select_option(value=texte, timeout=5000)
    return ''


def _defiler(session: Any, args: dict[str, Any]) -> str:
    """Jusqu'à un élément (``ref``) ; sinon d'un écran, vers le haut ou le
    bas, là où est la souris (``x``, ``y`` : dans un bloc qui défile)."""
    page = session.page
    if args.get('ref'):
        element(page, args['ref']).scroll_into_view_if_needed(timeout=10000)
        return ''
    ou = point(args)
    if ou is not None:
        page.mouse.move(*ou)
    page.mouse.wheel(0, -700 if str(args.get('text') or '') == 'haut' else 700)
    return ''


def _attendre(session: Any, args: dict[str, Any]) -> str:
    texte = str(args.get('text') or '')
    if texte:
        session.page.get_by_text(texte).first.wait_for(timeout=15000)
    else:
        session.page.wait_for_timeout(3000)
    return ''


def _ecran(session: Any, args: dict[str, Any]) -> str:
    largeur, hauteur = ECRANS.get(
        str(args.get('text') or ''), ECRANS['ordinateur']
    )
    session.page.set_viewport_size({'width': largeur, 'height': hauteur})
    return ''


def _deposer_fichier(session: Any, args: dict[str, Any]) -> str:
    """Donne un fichier à la page : dans un champ fichier, ou par le bouton
    qui ouvre le choix d'un fichier. Le fichier est écrit par le modèle
    (``content``), ou c'est un fichier téléchargé dans la session."""
    nom = str(args.get('text') or '').strip()
    if not nom:
        return 'deposer_fichier : donne le nom du fichier (text)'
    if args.get('content') is not None:
        contenu = str(args['content']).encode('utf-8')
    elif nom in session.telechargements.fichiers:
        contenu = session.telechargements.fichiers[nom].read_bytes()
    else:
        return (
            f'deposer_fichier : écris le contenu de « {nom} » (content), ou'
            ' nomme un fichier téléchargé dans cette session'
        )
    fichier = {
        'name': nom,
        'mimeType': mimetypes.guess_type(nom)[0] or 'application/octet-stream',
        'buffer': contenu,
    }
    cible = viser(session.page, {'ref': args.get('ref')})
    if cible is None:
        return (
            'deposer_fichier : dis où (ref : le champ fichier, ou le bouton)'
        )
    if cible.evaluate('e => e.tagName === "INPUT" && e.type === "file"'):
        cible.set_input_files(fichier, timeout=10000)
        return ''
    with session.page.expect_file_chooser(timeout=10000) as choix:
        cible.click(timeout=10000)
    choix.value.set_files(fichier)
    return ''


def _fermer_onglet(session: Any, _args: dict[str, Any]) -> str:
    if len(session.pages) < 2:
        return 'un seul onglet est ouvert'
    ancien = session.page
    ancien.close()
    if session.page is ancien:
        # La session revient au précédent sans attendre que le navigateur
        # ait dit que l'onglet est fermé.
        session.pages.remove(ancien)
        session.page = session.pages[-1]
        session.onglets.append(
            'l’onglet s’est fermé : tu es revenu au précédent'
        )
    return ''


GESTES: dict[str, Callable[[Any, dict[str, Any]], str]] = {
    'cliquer': _cliquer,
    'double_cliquer': lambda s, a: _cliquer(s, a, click_count=2),
    'clic_droit': lambda s, a: _cliquer(s, a, button='right'),
    'survoler': _survoler,
    'glisser': _glisser,
    'taper': _taper,
    'taper_secret': _taper_secret,
    'choisir': _choisir,
    'defiler': _defiler,
    'attendre': _attendre,
    'ecran': _ecran,
    'deposer_fichier': _deposer_fichier,
    'fermer_onglet': _fermer_onglet,
}


def agir(session: Any, args: dict[str, Any]) -> str:
    """Fait le geste ; rend ``''``, ou ce qui l'a empêché."""
    page = session.page
    action = str(args.get('action') or '')
    texte = str(args.get('text') or '')
    if action == 'ouvrir':
        page.goto(
            vers_chantier(texte, args),
            wait_until='domcontentloaded',
            timeout=30000,
        )
    elif action == 'touche':
        page.keyboard.press(texte or 'Enter')
    elif action == 'revenir':
        page.go_back(wait_until='domcontentloaded', timeout=15000)
    elif action == 'recharger':
        page.reload(wait_until='domcontentloaded', timeout=30000)
    elif action in ('accepter_dialogue', 'refuser_dialogue'):
        session.dialogues.preparer(action == 'accepter_dialogue', texte)
    elif action in GESTES:
        refus = GESTES[action](session, args)
        if refus:
            return refus
    else:
        return f'action inconnue : {action}'
    # Un geste peut ouvrir un autre onglet, un instant après : on lui laisse
    # le temps d'arriver, et c'est lui qu'on attend.
    session.page.wait_for_timeout(300)
    attendre(session.page)
    return ''
