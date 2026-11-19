#!/usr/bin/env python3
"""Migration v55 : les comptes web de Serge (lot 13).

``web_accounts`` : un compte de Serge sur un site (Reddit, LinkedIn…), nommé
d'un mot (``reddit``). Il garde l'adresse du site, l'identifiant de
connexion, le nom public, et deux secrets chiffrés par la clé du coffre de
l'instance : le mot de passe (``password_enc``) et la session du navigateur
(``session_enc`` : les cookies, et ce que le site garde dans le
navigateur). ``used_by`` dit quelle tâche s'en sert : un compte n'est
ouvert que par une tâche à la fois.

``web_account_days`` compte les actions faites avec un compte, jour par
jour (UTC) : la garde des comptes refuse au-delà du plafond du jour.

``accounts_standing`` est retirée : elle gardait le mot de passe en clair,
et rien n'y a jamais écrit (0 ligne sur le serveur le 19 novembre 2026).
"""

from __future__ import annotations

import sqlite3

SQL = """
CREATE TABLE IF NOT EXISTS web_accounts (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL DEFAULT '',
    login TEXT NOT NULL DEFAULT '',
    handle TEXT NOT NULL DEFAULT '',
    password_enc TEXT NOT NULL DEFAULT '',
    session_enc TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'creating'
        CHECK (status IN ('creating', 'active', 'blocked')),
    note TEXT NOT NULL DEFAULT '',
    used_by TEXT NOT NULL DEFAULT '',
    used_since TEXT NOT NULL DEFAULT '',
    session_saved_at TEXT NOT NULL DEFAULT '',
    last_used_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS web_account_days (
    account_id TEXT NOT NULL,
    day TEXT NOT NULL,
    actions INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, day));
DROP TABLE IF EXISTS accounts_standing;
"""


def apply_v055(connection: sqlite3.Connection) -> None:
    """Crée les comptes web et leur compteur ; retire l'ancienne table."""
    connection.executescript(SQL)
