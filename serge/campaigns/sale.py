#!/usr/bin/env python3
"""Enregistrer une vente : relier un paiement à un contact.

Quand Stripe annonce un paiement, le webhook écrit la transaction, avec
l'e-mail du payeur. Le contact de ce business qui a cette adresse passe à
« client » : il ne reçoit plus de relance de prospection. Un acheteur
inconnu devient un contact « entrant », client lui aussi. La première
vente d'un business est signalée (un ticket d'information la suit).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow
from serge.funnels.contacts import create_contact, normalise_value

CUSTOMER = 'CUSTOMER'


def record_sale(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Enregistrer une vente » : ``{transaction_id}``.

    Rend ``contact_id``, ``nouveau`` (« oui » pour un acheteur inconnu) et
    ``premiere`` (« oui » pour la première vente du business).
    """
    # Le paiement test de 1 € de Serge (« canary ») n'est pas une vente.
    row = conn.execute(
        'SELECT venture_id, amount_eur, receipt_json FROM transactions'
        " WHERE id=? AND status='paid' AND kind<>'canary'",
        (str(args.get('transaction_id') or ''),),
    ).fetchone()
    if row is None or not str(row[0] or ''):
        return {'ok': False, 'code': 'paiement_sans_business'}
    venture = str(row[0])
    try:
        receipt = (json.loads(row[2] or '{}') or {}).get('receipt') or {}
    except ValueError:
        receipt = {}
    email = normalise_value('email', str(receipt.get('customer_email') or ''))
    paid = conn.execute(
        'SELECT COUNT(*) FROM transactions WHERE venture_id=?'
        " AND status='paid' AND kind<>'canary'",
        (venture,),
    ).fetchone()[0]
    answer: dict[str, Any] = {
        'ok': True,
        'venture_id': venture,
        'montant': f'{float(row[1]):.2f} €',
        'premiere': 'oui' if int(paid) == 1 else '',
        'contact_id': '',
        'nouveau': '',
    }
    if not email:
        return answer
    found = conn.execute(
        'SELECT c.id FROM contacts c JOIN contact_addresses a'
        " ON a.contact_id=c.id WHERE c.venture_id=? AND a.channel='email'"
        ' AND a.value_norm=? ORDER BY c.created_at LIMIT 1',
        (venture, email),
    ).fetchone()
    if found is None:
        contact = create_contact(conn, venture, email, email=email)
        conn.execute(
            "UPDATE contacts SET regime='INBOUND' WHERE id=?", (contact,)
        )
        answer['nouveau'] = 'oui'
    else:
        contact = str(found[0])
    conn.execute(
        'UPDATE contacts SET funnel_state=?, updated_at=? WHERE id=?',
        (CUSTOMER, utcnow(), contact),
    )
    append_event(
        conn,
        actor=f'invocation:{inv}',
        type='contact.customer',
        venture_id=venture,
        payload={'transaction': str(args.get('transaction_id') or '')},
        rows=[('contacts', contact)],
    )
    return {**answer, 'contact_id': contact}
