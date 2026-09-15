#!/usr/bin/env python3
"""Identité de Serge : un lecteur, une source (instance), pas de table."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kit.instance_file import load_instance

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


class IdentiteError(ValueError):
    """Volet inconnu, instance illisible, ou champ interdit."""


def identite_serge(
    *,
    volet: str = 'basique',
    loaded: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Lit l’identité. Interdit d’ouvrir le TOML ailleurs.

    Args:
        volet: ``basique`` ou ``advanced`` (IBAN + facturation).
        loaded: Instance déjà validée (tests). Sinon ``load_instance``.

    Returns:
        Champs du volet, chaînes (vides si absents).

    Raises:
        IdentiteError: Volet inconnu.
    """
    if volet not in VOLETS:
        raise IdentiteError(f'volet inconnu : {volet}')
    data = dict(loaded) if loaded is not None else load_instance()
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


def _quote(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def _poser_cle(texte: str, section: str, cle: str, valeur: str) -> str:
    bloc = re.search(rf'^\[{re.escape(section)}\][^\[]*', texte, flags=re.M)
    ligne = f'{cle} = {_quote(valeur)}'
    if bloc is None:
        return texte.rstrip() + f'\n\n[{section}]\n{ligne}\n'
    corps = bloc.group(0)
    motif = re.compile(rf'^{re.escape(cle)}\s*=.*$', re.M)
    if motif.search(corps):
        nouveau = motif.sub(ligne, corps, count=1)
    else:
        nouveau = corps.rstrip() + f'\n{ligne}\n'
    return texte[: bloc.start()] + nouveau + texte[bloc.end() :]


def ecrire_identite(
    champs: Mapping[str, str],
    *,
    path: Path | None = None,
) -> dict[str, str]:
    """Réécrit l’instance (pas une copie). Token MC = confiance.

    Args:
        champs: Sous-ensemble des champs advanced (email → mailbox.login).
        path: TOML (défaut : ``SERGE_INSTANCE_FILE``).

    Returns:
        Identité advanced après écriture.

    Raises:
        IdentiteError: Chemin manquant, ou clé hors contrat.
    """
    cible = path or Path(os.environ.get('SERGE_INSTANCE_FILE', '').strip())
    if not cible or not cible.is_file():
        raise IdentiteError('fichier d’instance introuvable')
    autorise = set(CHAMPS_ADVANCED)
    texte = cible.read_text(encoding='utf-8')
    for cle, brut in champs.items():
        if cle not in autorise:
            raise IdentiteError(f'champ interdit : {cle}')
        valeur = str(brut).strip()
        if cle == 'email':
            texte = _poser_cle(texte, 'mailbox', 'login', valeur)
        elif cle == 'tel_2fa':
            texte = _poser_cle(texte, 'identity', 'phone_sms_number', valeur)
        elif cle == 'tel_did':
            texte = _poser_cle(texte, 'identity', 'phone_voice_number', valeur)
        else:
            texte = _poser_cle(texte, 'identity', cle, valeur)
    cible.write_text(texte, encoding='utf-8')
    from kit.instance_file import load_toml

    return identite_serge(volet='advanced', loaded=load_toml(cible))
