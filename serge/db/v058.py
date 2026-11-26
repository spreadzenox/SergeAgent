#!/usr/bin/env python3
"""Migration v58 : un compte web connecté avec Google, dans le profil du
vrai Chrome.

Certains comptes n'ont pas de mot de passe : un humain les a créés avec
« Continuer avec Google ». Serge ne peut pas s'y connecter par un
identifiant et un mot de passe, et leur connexion ne tient pas dans des
cookies rangés en base : elle dépend de celle du compte Google.

``web_accounts.sign_in_with`` : comment on se connecte à ce compte. Vide :
par son identifiant et son mot de passe, et sa session est gardée en base,
chiffrée, comme avant. ``google`` : avec Google ; ses tâches ouvrent leurs
onglets dans le profil du vrai Chrome, où un humain a connecté Google à la
main, et qui garde ses connexions comme le navigateur d'une personne. Rien
de sa session n'est écrit en base.

Exemple : le compte ``linkedin`` créé par Clem avec le compte Google de
Serge a ``sign_in_with = 'google'``. « Envoyer un message par le
navigateur » ouvre LinkedIn dans le profil : il est déjà connecté.
"""

from __future__ import annotations

import sqlite3


def apply_v058(connection: sqlite3.Connection) -> None:
    """Ajoute à un compte web la façon de s'y connecter."""
    have = {
        str(r[1])
        for r in connection.execute('PRAGMA table_info(web_accounts)')
    }
    if 'sign_in_with' not in have:
        connection.execute(
            'ALTER TABLE web_accounts ADD COLUMN sign_in_with TEXT NOT NULL'
            " DEFAULT ''"
        )
