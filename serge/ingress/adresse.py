#!/usr/bin/env python3
"""L'adresse publique du serveur de Serge (lot 10, Q91).

Pour faire pointer le domaine d'un produit fini vers le serveur, il faut
son adresse IPv4 (un enregistrement DNS de type A). Serge la tire du
domaine de l'instance (``identity.public_hostname``), qui pointe déjà vers
lui : exemple, ``serge.exemple.fr`` → ``203.0.113.7``. Une adresse locale
ou privée est refusée : elle ne servirait à rien sur Internet.
"""

from __future__ import annotations

import ipaddress
import socket
import sqlite3
import sys
from typing import Any

from serge.ingress.caddy import public_hostname


def server_address(
    _conn: sqlite3.Connection,
    _tool: str,
    _args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """Le domaine de l'instance et l'adresse IPv4 publique du serveur."""
    nom = public_hostname()
    if not nom:
        return {
            'ok': False,
            'code': 'pas_de_domaine',
            'detail': "l'instance n'a pas de public_hostname",
        }
    try:
        ipv4 = str(socket.getaddrinfo(nom, None, socket.AF_INET)[0][4][0])
    except (OSError, IndexError) as exc:
        print(f'adresse : {nom} introuvable : {exc}', file=sys.stderr)
        return {'ok': False, 'code': 'introuvable', 'detail': f'{nom} : {exc}'}
    if not ipaddress.ip_address(ipv4).is_global:
        return {
            'ok': False,
            'code': 'adresse_privee',
            'detail': f'{nom} mène à {ipv4}, une adresse qui n’est pas publique',
        }
    return {'ok': True, 'hostname': nom, 'ipv4': ipv4}
