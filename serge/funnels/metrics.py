#!/usr/bin/env python3
"""U1-U5 : LLM classe, code compte. 0 jugement, que des compteurs.

U1 reach = touches envoyées (statut sent, INVALID exclus pour N).
U2 engagement = signaux ENGAGED + REPLIED.
U3 intent = signaux INTENT (strict : le seul "positif" des seuils).
U4 économie = coût total EUR / U3 (si U3=0 : dépense sans intent).
U5 apprentissage = classes distinctes non vides (+ verbatims bruts).
"""

from __future__ import annotations

import sqlite3
from typing import Any

SENT_STATUSES = ('sent', 'delivered')
ENGAGE_SIGNALS = ('ENGAGED', 'REPLIED')
CONTENT_SIGNALS = ('REPLIED', 'INTENT')


def campaign_metrics(
    connection: sqlite3.Connection, campaign_id: str
) -> dict[str, Any]:
    """U1-U5 + taux + coûts d'une campagne (fenêtre entière).

    Args:
        connection: Connexion canon (lecture).
        campaign_id: Campagne mesurée.

    Returns:
        u1, n_valid, u2, u3, u4_eur, u5_classes, verbatims, cost_eur,
        positifs (= u3), engage_rate, intent_rate, bounce_rate.
    """
    touches = connection.execute(
        'SELECT t.status, t.cost_eur, COALESCE(c.funnel_state, "")'
        ' FROM touches t LEFT JOIN contacts c ON c.id=t.contact_id'
        ' WHERE t.campaign_id=?',
        (campaign_id,),
    ).fetchall()
    sent = [row for row in touches if row[0] in SENT_STATUSES]
    u1 = len(sent)
    n_valid = sum(1 for row in sent if row[2] != 'INVALID')
    bounced = sum(1 for row in touches if row[0] == 'bounced')
    touch_cost = sum(float(row[1] or 0) for row in touches)
    inbound = connection.execute(
        'SELECT signal, class, cost_eur FROM inbound_events'
        ' WHERE campaign_id=?',
        (campaign_id,),
    ).fetchall()
    u2 = sum(1 for row in inbound if row[0] in ENGAGE_SIGNALS)
    u3 = sum(1 for row in inbound if row[0] == 'INTENT')
    classes = {str(row[1]) for row in inbound if str(row[1])}
    verbatims = sum(1 for row in inbound if row[0] in CONTENT_SIGNALS)
    inbound_cost = sum(float(row[2] or 0) for row in inbound)
    cost = touch_cost + inbound_cost
    return {
        'u1': u1,
        'n_valid': n_valid,
        'u2': u2,
        'u3': u3,
        'u4_eur': round(cost / u3, 2) if u3 else round(cost, 2),
        'u5_classes': len(classes),
        'verbatims': verbatims,
        'cost_eur': round(cost, 2),
        'positifs': u3,
        'engage_rate': round(u2 / u1, 4) if u1 else 0.0,
        'intent_rate': round(u3 / u1, 4) if u1 else 0.0,
        'bounce_rate': round(bounced / u1, 4) if u1 else 0.0,
    }


def venture_metrics(
    connection: sqlite3.Connection, venture_id: str
) -> dict[str, Any]:
    """Agrégat venture : sommes + U4/U5 recalculés (pas moyennés).

    Args:
        connection: Connexion canon (lecture).
        venture_id: Venture mesurée.

    Returns:
        Même forme que campaign_metrics, toutes campagnes confondues.
    """
    campaigns = connection.execute(
        'SELECT id FROM campaigns WHERE venture_id=?', (venture_id,)
    ).fetchall()
    total = {
        'u1': 0,
        'n_valid': 0,
        'u2': 0,
        'u3': 0,
        'u5_classes': 0,
        'verbatims': 0,
        'cost_eur': 0.0,
    }
    classes: set[str] = set()
    for (campaign_id,) in campaigns:
        metrics = campaign_metrics(connection, campaign_id)
        total['u1'] += metrics['u1']
        total['n_valid'] += metrics['n_valid']
        total['u2'] += metrics['u2']
        total['u3'] += metrics['u3']
        total['verbatims'] += metrics['verbatims']
        total['cost_eur'] += metrics['cost_eur']
        rows = connection.execute(
            'SELECT DISTINCT class FROM inbound_events'
            " WHERE campaign_id=? AND class<>''",
            (campaign_id,),
        ).fetchall()
        classes.update(str(row[0]) for row in rows)
    u1 = total['u1']
    u3 = total['u3']
    cost = round(total['cost_eur'], 2)
    return {
        **total,
        'cost_eur': cost,
        'u4_eur': round(cost / u3, 2) if u3 else cost,
        'u5_classes': len(classes),
        'positifs': u3,
        'engage_rate': round(total['u2'] / u1, 4) if u1 else 0.0,
        'intent_rate': round(u3 / u1, 4) if u1 else 0.0,
    }
