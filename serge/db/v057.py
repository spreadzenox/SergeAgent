#!/usr/bin/env python3
"""Migration v57 : un envoi qui attend que la personne accepte le contact.

Sur un réseau, on ne peut pas toujours écrire à quelqu'un tout de suite :
il faut d'abord qu'il accepte une demande de connexion (LinkedIn), ou
qu'il suive Serge en retour (X). L'invocation qui envoie demande alors le
contact comme le réseau le propose, et l'envoi attend.

``touches.contact_asked_at`` : quand Serge a demandé ce contact pour cet
envoi ; vide tant qu'il n'a rien eu à demander. L'envoi reste ``pending``
et repart plus tard ; passé le délai réglé (page Policy, « Comptes web »),
il échoue avec sa raison. Une demande de contact compte dans le plafond du
jour du canal, comme un message parti.

Exemple : le premier message pour ``https://www.linkedin.com/in/ana-roux``
ne peut pas partir, Ana n'est pas une relation. Serge lui envoie une
demande de connexion le 21 novembre à 10 h : ``contact_asked_at`` vaut
cette heure, et l'envoi repart 5 minutes plus tard voir si elle a accepté,
puis de moins en moins souvent.
"""

from __future__ import annotations

import sqlite3


def apply_v057(connection: sqlite3.Connection) -> None:
    """Ajoute à un envoi l'heure où Serge a demandé le contact."""
    have = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(touches)')
    }
    if 'contact_asked_at' not in have:
        connection.execute(
            'ALTER TABLE touches ADD COLUMN contact_asked_at TEXT NOT NULL'
            " DEFAULT ''"
        )
