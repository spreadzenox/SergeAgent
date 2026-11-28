#!/usr/bin/env python3
"""Lecture secrets instance (P4 : un seul lecteur, voix + LLM + rails)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from serge.paths import config_root


def read_secret_file(path: Path) -> str:
    """Lit un secret (token brut ou dotenv KEY=value, 1re ligne).

    Args:
        path: Fichier secret (absent/illisible = chaîne vide).

    Returns:
        Le secret déshabillé (jamais logué par les appelants).
    """
    try:
        text = path.read_text(encoding='utf-8').strip()
    except OSError:
        return ''
    if not text:
        return ''
    first = text.splitlines()[0].strip()
    match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', first)
    if match:
        key, rest = match.group(1), match.group(2)
        if rest.strip():
            return rest.strip().strip('"').strip("'")
        if re.fullmatch(r'[A-Z_][A-Z0-9_]*', key):
            return ''
    return first


# La clé du coffre de l'instance : elle déchiffre les fichiers chiffrés des
# secrets, comme la carte de Serge (payment-card.enc).
CLE_DU_COFFRE = 'credential-vault.key'


def read_vault_field(secrets_dir: Path, nom: str) -> str:
    """Un champ d'un fichier chiffré du coffre : ``payment-card.enc#pan``.

    Le fichier est un objet JSON chiffré (Fernet) par la clé du coffre. Le
    champ ``expiration`` est tiré de ``exp_month`` et ``exp_year`` : « 08/29 ».
    Rien n'est jamais écrit en clair ; ``''`` si le fichier, la clé ou le
    champ manquent.
    """
    fichier, _, champ = nom.partition('#')
    try:
        from cryptography.fernet import Fernet, InvalidToken

        cle = (secrets_dir / CLE_DU_COFFRE).read_bytes().strip()
        brut = Fernet(cle).decrypt(
            (secrets_dir / fichier).read_bytes().strip()
        )
        donnees = json.loads(brut.decode('utf-8'))
    except (ImportError, OSError, ValueError, InvalidToken):
        return ''
    if not isinstance(donnees, dict):
        return ''
    if champ == 'expiration' and 'expiration' not in donnees:
        mois, annee = donnees.get('exp_month'), donnees.get('exp_year')
        if not mois or not annee:
            return ''
        return f'{int(mois):02d}/{str(annee).strip()[-2:]}'
    valeur = donnees.get(champ)
    return '' if valeur is None else str(valeur).strip()


def read_secret_value(secrets_dir: Path, nom: str) -> str:
    """Un secret par son nom : un fichier (``stripe-test.key``), ou un champ
    d'un fichier chiffré du coffre (``payment-card.enc#pan``)."""
    if '#' in nom:
        return read_vault_field(secrets_dir, nom)
    return read_secret_file(secrets_dir / nom)


def owner_dashboard_token(system: Path | None = None) -> str:
    """Token MC : sidecar config_root, puis system_root, puis env.

    Args:
        system: system_root (défaut : SERGE_SYSTEM_ROOT).

    Returns:
        Le jeton, ou ``''`` si rien n’est lisible : Mission Control
        refuse alors de démarrer.
    """
    from serge.paths import system_root

    root = system or system_root()
    cfg = config_root()
    for path in (
        cfg / 'secrets/owner-dashboard.token',
        cfg / 'secrets/owner_dashboard_token',
        root / 'secrets/owner-dashboard.token',
        root / 'secrets/owner_dashboard_token',
    ):
        found = read_secret_file(path)
        if found:
            return found
    return os.environ.get('SERGE_MC_TOKEN', '')
