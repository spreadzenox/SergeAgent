#!/usr/bin/env python3
"""Migration v60 : faire vivre un produit fini en vente (décision Q119).

Trois ajouts :

- ``product_reviews`` : un point sur un produit en vente. Il est fait
  chaque semaine (``cause = semaine``) ou quand un client signale un bug
  (``bug``, avec ``request_id``, la demande du client). Il garde ce qui a
  été décidé pour le produit (``product_action`` : ``rien``, ``corriger``
  ou ``faire_evoluer``, avec ses consignes) et pour la prospection
  (``prospecting_action`` : ``rien`` ou ``relancer``), et le compte rendu.
  Un point qui lance une nouvelle version du produit en porte l'état
  (``version_status``) : ``open`` tant qu'elle se construit, ``online``
  quand elle est en ligne (avec son numéro, ``version``), ``dropped`` si
  elle est abandonnée ; ``none`` : ce point n'a rien lancé. Un business
  n'a qu'une version ``open`` à la fois (règle de doublon en base) ;
- ``product_offers`` : les offres payantes d'un produit, écrites avec son
  plan. Exemple : ``standard``, 19 € par mois, et ``pro``, 49 € par mois.
  Chacune a son prix dans Stripe ;
- ``deployments.contact_email`` : l'adresse de contact que montre un
  produit en ligne. Un e-mail écrit à cette adresse est rattaché à son
  business (``serge/conversations/receive.py``).
"""

from __future__ import annotations

import sqlite3


def apply_v060(connection: sqlite3.Connection) -> None:
    """Crée les points et les offres des produits, et l'adresse de contact
    d'une publication."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS product_reviews (
            id TEXT PRIMARY KEY,
            venture_id TEXT NOT NULL,
            cause TEXT NOT NULL DEFAULT 'semaine',
            request_id TEXT NOT NULL DEFAULT '',
            product_action TEXT NOT NULL DEFAULT 'rien',
            product_notes TEXT NOT NULL DEFAULT '',
            prospecting_action TEXT NOT NULL DEFAULT 'rien',
            prospecting_notes TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            version_status TEXT NOT NULL DEFAULT 'none',
            version TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS product_reviews_venture
            ON product_reviews(venture_id, version_status);
        CREATE TABLE IF NOT EXISTS product_offers (
            id TEXT PRIMARY KEY,
            venture_id TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            main TEXT NOT NULL DEFAULT 'non',
            amount_cents INTEGER NOT NULL DEFAULT 0,
            interval TEXT NOT NULL DEFAULT 'month',
            includes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS product_offers_venture
            ON product_offers(venture_id);
        """
    )
    have = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(deployments)')
    }
    if 'contact_email' not in have:
        connection.execute(
            'ALTER TABLE deployments ADD COLUMN contact_email TEXT NOT NULL'
            " DEFAULT ''"
        )
