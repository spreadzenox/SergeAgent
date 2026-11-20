#!/usr/bin/env python3
"""Identité de Serge : un lecteur, une source (instance), pas de table."""

from __future__ import annotations

import os
import re
import shutil
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kit.instance_file import InstanceError, load_toml, validate_toml

VOLETS = frozenset({'basique', 'advanced'})

CHAMPS_BASIQUE = (
    'email',
    'prenom',
    'nom',
    'pseudo',
    'tel_2fa',
    'tel_did',
    'siret',
)

CHAMPS_ADVANCED = CHAMPS_BASIQUE + ('iban', 'adresse_facturation')

# Ce que Serge donne à un site pour s'y inscrire, et que la page Identité
# de Mission Control sait écrire.
CHAMPS_INSCRIPTION = {
    'email': 'adresse e-mail',
    'prenom': 'prénom',
    'nom': 'nom',
    'pseudo': 'pseudo',
}
_LONGUEUR_MAX = 200


class IdentiteError(ValueError):
    """Volet inconnu, instance illisible, ou champ interdit."""


def _fichier() -> Path:
    brut = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    if not brut or not Path(brut).is_file():
        raise IdentiteError('fichier d’instance introuvable')
    return Path(brut)


def _instance() -> dict[str, Any]:
    """Le fichier d'instance, sans ses secrets : l'identité n'en est pas
    un, et un service ne sait pas les déchiffrer (le 20 novembre 2026,
    l'outil « L'identité de Serge » échouait pour cette raison)."""
    try:
        return load_toml(_fichier())
    except InstanceError as exc:
        raise IdentiteError(f'fichier d’instance illisible : {exc}') from exc


def identite_serge(
    *,
    volet: str = 'basique',
    loaded: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Lit l’identité. Interdit d’ouvrir le TOML ailleurs.

    Args:
        volet: ``basique`` ou ``advanced`` (IBAN + facturation).
        loaded: Instance déjà lue (tests). Sinon le fichier d'instance.

    Returns:
        Champs du volet, chaînes (vides si absents).

    Raises:
        IdentiteError: Volet inconnu, ou fichier d'instance illisible.
    """
    if volet not in VOLETS:
        raise IdentiteError(f'volet inconnu : {volet}')
    data = dict(loaded) if loaded is not None else _instance()
    ident = data.get('identity') or {}
    box = data.get('mailbox') or {}
    tous = {
        'email': str(box.get('login') or ''),
        'prenom': str(ident.get('prenom') or ''),
        'nom': str(ident.get('nom') or ''),
        'pseudo': str(ident.get('pseudo') or ''),
        'tel_2fa': str(ident.get('phone_sms_number') or ''),
        'tel_did': str(ident.get('phone_voice_number') or ''),
        'siret': str(ident.get('siret') or ''),
        'iban': str(ident.get('iban') or ''),
        'adresse_facturation': str(ident.get('adresse_facturation') or ''),
    }
    cles = CHAMPS_ADVANCED if volet == 'advanced' else CHAMPS_BASIQUE
    return {cle: tous[cle] for cle in cles}


def identity_read(
    _conn: Any, _tool: str, _args: dict[str, Any], _invocation_id: str
) -> dict[str, Any]:
    """Capacité « L'identité de Serge » : ce qu'il donne à un site pour
    s'y inscrire. Ni son SIRET, ni son IBAN, ni son adresse."""
    try:
        qui = identite_serge()
    except (IdentiteError, OSError, ValueError) as exc:
        return {'ok': False, 'detail': f'identité illisible : {exc}'}
    rendu: dict[str, Any] = {
        'ok': True,
        'prenom': qui['prenom'],
        'nom': qui['nom'],
        'pseudo': qui['pseudo'],
        'email': qui['email'],
        'telephone_pour_les_sms': qui['tel_2fa'],
    }
    vides = [nom for cle, nom in CHAMPS_INSCRIPTION.items() if not qui[cle]]
    if vides:
        rendu['manque'] = (
            ', '.join(vides)
            + ' : à remplir par un humain dans Mission Control, page Identité'
        )
    return rendu


def _quote(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _poser_cle(texte: str, section: str, cle: str, valeur: str) -> str:
    # La section va de son titre à la prochaine ligne qui ouvre une section.
    bloc = re.search(
        rf'^\[{re.escape(section)}\][^\n]*\n?(?:(?!\[)[^\n]*\n?)*',
        texte,
        flags=re.M,
    )
    ligne = f'{cle} = {_quote(valeur)}'
    if bloc is None:
        return texte.rstrip() + f'\n\n[{section}]\n{ligne}\n'
    corps = bloc.group(0)
    motif = re.compile(rf'^{re.escape(cle)}\s*=.*$', re.M)
    if motif.search(corps):
        # Une fonction : la valeur n'est pas lue comme un motif (ses barres
        # obliques restent telles quelles).
        nouveau = motif.sub(lambda _: ligne, corps, count=1)
    else:
        nouveau = corps.rstrip() + f'\n{ligne}\n'
    return texte[: bloc.start()] + nouveau + texte[bloc.end() :]


def _invalide(texte: str) -> str:
    """Pourquoi ce texte n'est pas une instance valide, ou ``''``."""
    try:
        validate_toml(tomllib.loads(texte))
    except (tomllib.TOMLDecodeError, InstanceError) as exc:
        return str(exc)
    return ''


def ecrire_identite(
    champs: Mapping[str, str],
    *,
    path: Path | None = None,
) -> dict[str, str]:
    """Réécrit l’instance (pas une copie). Token MC = confiance.

    Le fichier n'est remplacé que si le nouveau texte est encore une
    instance valide : une valeur mal écrite ne peut pas empêcher Serge de
    redémarrer.

    Args:
        champs: Sous-ensemble des champs advanced (email → mailbox.login).
        path: TOML (défaut : ``SERGE_INSTANCE_FILE``).

    Returns:
        Identité advanced après écriture.

    Raises:
        IdentiteError: Chemin manquant, clé hors contrat, ou valeur
            refusée (retour à la ligne, trop longue).
    """
    cible = path or Path(os.environ.get('SERGE_INSTANCE_FILE', '').strip())
    if not cible or not cible.is_file():
        raise IdentiteError('fichier d’instance introuvable')
    autorise = set(CHAMPS_ADVANCED)
    avant = texte = cible.read_text(encoding='utf-8')
    for cle, brut in champs.items():
        if cle not in autorise:
            raise IdentiteError(f'champ interdit : {cle}')
        valeur = str(brut).strip()
        if len(valeur) > _LONGUEUR_MAX or not valeur.isprintable():
            raise IdentiteError(
                f'{cle} : une seule ligne, {_LONGUEUR_MAX} caractères au plus'
            )
        if cle == 'email':
            texte = _poser_cle(texte, 'mailbox', 'login', valeur)
        elif cle == 'tel_2fa':
            texte = _poser_cle(texte, 'identity', 'phone_sms_number', valeur)
        elif cle == 'tel_did':
            texte = _poser_cle(texte, 'identity', 'phone_voice_number', valeur)
        else:
            texte = _poser_cle(texte, 'identity', cle, valeur)
    # Une instance valide doit le rester ; un modèle d'instance incomplet
    # (sans ses numéros Discord, par exemple) doit au moins rester lisible.
    raison = _invalide(texte)
    if raison and not _invalide(avant):
        raise IdentiteError(
            f'le fichier d’instance ne serait plus valide : {raison}'
        )
    try:
        relu = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as exc:
        raise IdentiteError(
            f'le fichier d’instance ne serait plus lisible : {exc}'
        ) from exc
    # Écrit à côté puis mis à sa place d'un coup : jamais un fichier à moitié.
    neuf = cible.with_name(cible.name + '.neuf')
    neuf.write_text(texte, encoding='utf-8')
    shutil.copymode(cible, neuf)
    os.replace(neuf, cible)
    return identite_serge(volet='advanced', loaded=relu)


def modifier_inscription(champs: Mapping[str, Any]) -> dict[str, str]:
    """Page Identité de Mission Control : écrit ce que Serge donne à un
    site pour s'y inscrire (e-mail, prénom, nom, pseudo), et rien d'autre.

    L'adresse e-mail d'une instance à boîte SMTP/IMAP est l'identifiant de
    cette boîte : la changer ici couperait le courrier, donc elle ne se
    change que dans le fichier d'instance.

    Returns:
        Les champs écrits, tels qu'ils sont maintenant dans l'instance.

    Raises:
        IdentiteError: Rien à écrire, valeur refusée, fichier illisible.
    """
    voulus = {
        cle: str(champs[cle] or '').strip()
        for cle in CHAMPS_INSCRIPTION
        if cle in champs
    }
    avant = identite_serge()
    voulus = {c: v for c, v in voulus.items() if v != avant[c]}
    if not voulus:
        raise IdentiteError('rien à changer')
    email = voulus.get('email')
    if email is not None:
        if (_instance().get('features') or {}).get('mailbox'):
            raise IdentiteError(
                'l’adresse e-mail est l’identifiant de la boîte SMTP/IMAP :'
                ' elle se change dans le fichier d’instance'
            )
        if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
            raise IdentiteError(f'adresse e-mail mal écrite : « {email} »')
    apres = ecrire_identite(voulus, path=_fichier())
    return {cle: apres[cle] for cle in voulus}
