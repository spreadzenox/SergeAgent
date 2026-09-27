#!/usr/bin/env python3
"""Fiche et page MC : identité instance (pas une table)."""

from __future__ import annotations

from typing import Any

from serge.identite import IdentiteError, identite_serge

_LIBELLES = {
    'email': 'E-mail',
    'prenom': 'Prénom',
    'nom': 'Nom',
    'pseudo': 'Pseudo',
    'tel_2fa': 'N° 2FA (SMS)',
    'tel_did': 'N° DID (voix)',
    'siret': 'SIRET',
    'iban': 'IBAN',
    'adresse_facturation': 'Adresse de facturation',
}


def project_identite(ident: str = 'serge') -> dict[str, Any] | None:
    """Miroir de ``identite_serge``. ``ident`` = ``serge`` seulement."""
    if ident != 'serge':
        return None
    try:
        basique = identite_serge(volet='basique')
        avancé = identite_serge(volet='advanced')
    except (IdentiteError, OSError, ValueError):
        return {
            'type': 'identite',
            'id': 'serge',
            'titre': 'Identité de Serge',
            'pourquoi': (
                'Pas d’instance chargée ici. En prod, la page lit'
                ' uniquement ``identite_serge()``.'
            ),
            'champs': [],
            'enfants': [],
            'preuve': '',
        }
    champs = [{'k': _LIBELLES[k], 'v': v or '—'} for k, v in avancé.items()]
    return {
        'type': 'identite',
        'id': 'serge',
        'titre': 'Identité de Serge',
        'pourquoi': (
            'Une source : le fichier d’instance. Token MC = confiance'
            ' absolue. Le volet avancé (IBAN) n’est appelé par aucune'
            ' invocation tant qu’un acte n’est pas nommé.'
        ),
        'champs': champs,
        'enfants': [],
        'preuve': '',
        'basique': basique,
    }


def project_identite_page(
    conn: object, policy: object, now: str
) -> dict[str, Any]:
    """Section page Identité (même payload que la fiche)."""
    _ = (conn, policy, now)
    fiche = project_identite('serge') or {}
    return {'fiche': fiche}
