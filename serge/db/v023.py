#!/usr/bin/env python3
"""Migration v23 : abonnements sans faux business.

Avant, chaque abonnement et chaque facture d'abonnement étaient rattachés
à un faux business, ``serge-collect-stripe``. Ils passent « sans
business » (``venture_id`` vide) : le vrai sera lu dans Stripe au prochain
événement. La colonne ``last_transaction_id``, ajoutée jusqu'ici à la
volée par le code, est posée ici.
"""

from __future__ import annotations

import sqlite3

FAUX_BUSINESS = 'serge-collect-stripe'


def apply_v023(connection: sqlite3.Connection) -> None:
    """Retire le faux business des abonnements et des paiements."""
    colonnes = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(subscriptions)')
    }
    if 'last_transaction_id' not in colonnes:
        connection.execute(
            'ALTER TABLE subscriptions ADD COLUMN last_transaction_id'
            " TEXT NOT NULL DEFAULT ''"
        )
    for table in ('subscriptions', 'transactions'):
        connection.execute(
            f"UPDATE {table} SET venture_id='' WHERE venture_id=?",
            (FAUX_BUSINESS,),
        )
