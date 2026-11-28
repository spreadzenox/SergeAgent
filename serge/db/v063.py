#!/usr/bin/env python3
"""Migration v63 : les adresses de connexion validées d'un compte web.

Le mot de passe d'un compte web ne se tape que sur le site du compte.
Quelques sites font leur connexion sur un autre domaine : un compte sur
``outlook.com`` se connecte sur ``login.live.com``.

``web_accounts.login_hosts`` : les adresses de connexion du compte qu'un
humain a validées, des hôtes séparés par des virgules (vide : aucune). Le
mot de passe se tape sur le site du compte ou sur l'une d'elles. Seule la
réponse d'un humain au ticket « Adresse de connexion » y ajoute un hôte
(``serge/login_hosts.py``) : aucune invocation n'écrit cette colonne.

Exemple : ``login.live.com`` pour le compte ``outlook``.
"""

from __future__ import annotations

import sqlite3


def apply_v063(connection: sqlite3.Connection) -> None:
    """Ajoute à un compte web ses adresses de connexion validées."""
    have = {
        str(r[1])
        for r in connection.execute('PRAGMA table_info(web_accounts)')
    }
    if 'login_hosts' not in have:
        connection.execute(
            'ALTER TABLE web_accounts ADD COLUMN login_hosts TEXT NOT NULL'
            " DEFAULT ''"
        )
