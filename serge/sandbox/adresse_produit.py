#!/usr/bin/env python3
"""L'adresse d'un produit publié : son nom court, et où il est en ligne.

En staging, ``staging-<produit>.<domaine de l'instance>`` ; en prod,
``<produit>.<domaine de l'instance>`` pour un POC, et pour un produit fini
le domaine acheté ou un sous-domaine du domaine commun des produits
(``base_domain``). La nouvelle version d'un produit déjà en vente garde
l'adresse où il est en ligne (``adresse_en_prod``, décision Q119).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from serge.ingress import caddy
from serge.sandbox.docker import DockerError


def slug(text: str) -> str:
    """Un nom court pour une adresse : ``Devis Artisan`` → ``devis-artisan``."""
    brut = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return brut[:40].strip('-') or 'produit'


def avec_le_nom(
    conn: sqlite3.Connection, args: dict[str, Any]
) -> dict[str, Any]:
    """Les paramètres, avec le nom du business quand aucun nom court n'est
    figé : « Devis Vocal » donne devis-vocal.<domaine>."""
    if str(args.get('slug') or ''):
        return args
    venture_id = str(args.get('venture_id') or '')
    row = conn.execute(
        'SELECT name FROM ventures WHERE id=?', (venture_id,)
    ).fetchone()
    return {**args, 'nom': str(row[0]) if row else venture_id}


def product_hostname(args: dict[str, Any], target: str) -> str:
    """L'adresse d'un produit publié sur ``target`` (staging ou prod)."""
    domaine = str(args.get('domain') or '').strip().lower()
    if domaine and target == 'prod':
        return domaine
    # Un domaine commun des produits finis (base_domain) : la prod sur un
    # sous-domaine, calculatrice.<domaine commun>, sans domaine acheté.
    commun = str(args.get('base_domain') or '').strip().lower().strip('.')
    base = commun if commun and target == 'prod' else caddy.public_hostname()
    if not base:
        raise DockerError(
            "pas de domaine pour les produits : l'instance n'a pas de"
            ' public_hostname'
        )
    produit = slug(str(args.get('slug') or args.get('nom') or ''))
    return (
        f'staging-{produit}.{base}'
        if target == 'staging'
        else (f'{produit}.{base}')
    )


def adresse_en_prod(conn: sqlite3.Connection, deployment: str) -> str:
    """L'adresse où cette publication de prod est en ligne, ou ``''`` si
    elle ne l'est pas (jamais publiée, ou arrêtée : remplacée par un autre
    produit sur la même adresse)."""
    row = conn.execute(
        "SELECT hostname FROM deployments WHERE id=? AND status='running'",
        (deployment,),
    ).fetchone()
    return str(row[0] or '') if row else ''
