#!/usr/bin/env python3
"""Projecteurs P6 Économie : entonnoir, transactions, coûts LLM, traçabilité."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.funnels.metrics import campaign_metrics
from serge.points.interact import strip_ids


def project_entonnoir(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Entonnoir kit unifié : Ventures x U1-U5 x Intents Collect (evidence-strict).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Horodatage ISO (ignoré).

    Returns:
        Dict {ventures: [...], totaux: {u1, u2, u3, paid_eur}}.
    """
    _ = (policy, now)
    v_rows = conn.execute(
        'SELECT id, name, lifecycle FROM ventures ORDER BY created_at'
    ).fetchall()

    ventures = []
    tot_u1 = tot_u2 = tot_u3 = 0
    tot_paid_eur = 0.0

    for v in v_rows:
        vid, vname, vlife = str(v[0]), str(v[1]), str(v[2])
        # Récupère campagnes
        c_rows = conn.execute(
            'SELECT id FROM campaigns WHERE venture_id=?', (vid,)
        ).fetchall()
        u1 = u2 = u3 = 0
        for c in c_rows:
            m = campaign_metrics(conn, str(c[0]))
            u1 += int(m.get('u1', 0))
            u2 += int(m.get('u2', 0))
            u3 += int(m.get('u3', 0))

        # Transactions paid pour cette venture
        t_row = conn.execute(
            "SELECT COALESCE(SUM(amount_eur), 0) FROM transactions WHERE venture_id=? AND status='paid'",
            (vid,),
        ).fetchone()
        paid_eur = float(t_row[0]) if t_row else 0.0

        tot_u1 += u1
        tot_u2 += u2
        tot_u3 += u3
        tot_paid_eur += paid_eur

        ventures.append(
            {
                'id': vid,
                'name': strip_ids(vname),
                'lifecycle': vlife,
                'u1': u1,
                'u2': u2,
                'u3': u3,
                'paid_eur': paid_eur,
            }
        )

    return {
        'ventures': ventures,
        'totaux': {
            'u1': tot_u1,
            'u2': tot_u2,
            'u3': tot_u3,
            'paid_eur': round(tot_paid_eur, 2),
        },
    }


def project_transactions_subscriptions(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Intents de facturation et abonnements récurrents.

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Horodatage ISO (ignoré).

    Returns:
        Dict {transactions: [...], subscriptions: [...], mrr_eur}.
    """
    _ = (policy, now)
    tx_rows = conn.execute(
        'SELECT id, venture_id, kind, amount_eur, currency, status, doc_ref, created_at'
        ' FROM transactions ORDER BY created_at DESC LIMIT 30'
    ).fetchall()
    transactions = [
        {
            'id': str(r[0]),
            'venture_id': str(r[1]),
            'kind': str(r[2]),
            'amount_eur': float(r[3]),
            'currency': str(r[4]),
            'status': str(r[5]),
            'doc_ref': str(r[6]),
            'created_at': str(r[7]),
        }
        for r in tx_rows
    ]

    sub_rows = conn.execute(
        'SELECT id, venture_id, provider, amount_eur, period, status, renews_at'
        ' FROM subscriptions ORDER BY created_at DESC LIMIT 20'
    ).fetchall()
    subscriptions = [
        {
            'id': str(r[0]),
            'venture_id': str(r[1]),
            'provider': str(r[2]),
            'amount_eur': float(r[3]),
            'period': str(r[4]),
            'status': str(r[5]),
            'renews_at': str(r[6]),
        }
        for r in sub_rows
    ]

    mrr = sum(
        (
            float(s['amount_eur'])
            for s in subscriptions
            if s['status'] == 'active' and s['period'] == 'monthly'
        ),
        0.0,
    )

    return {
        'transactions': transactions,
        'subscriptions': subscriptions,
        'mrr_eur': round(mrr, 2),
    }


def project_couts_cognitifs(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Coûts LLM : tokens, estimation EUR, ratio tokens/€ de revenu (E6).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (budget.llm_eur_per_1k_tokens).
        now: Horodatage ISO (ignoré).

    Returns:
        Dict {total_tokens, total_cost_eur, total_revenue_eur, tokens_par_euro}.
    """
    _ = now
    budget_cfg = policy.get('budget') or {}
    rate = float(budget_cfg.get('llm_eur_per_1k_tokens', 0.004) or 0.004)

    row_tok = conn.execute(
        'SELECT COALESCE(SUM(tokens_in + tokens_out), 0) FROM llm_usage'
    ).fetchone()
    total_tokens = int(row_tok[0]) if row_tok else 0
    total_cost_eur = round((total_tokens / 1000.0) * rate, 2)

    row_rev = conn.execute(
        "SELECT COALESCE(SUM(amount_eur), 0) FROM transactions WHERE status='paid'"
    ).fetchone()
    total_revenue_eur = round(float(row_rev[0]), 2) if row_rev else 0.0

    tokens_par_euro = (
        round(total_tokens / total_revenue_eur, 1)
        if total_revenue_eur > 0
        else None
    )

    return {
        'total_tokens': total_tokens,
        'total_cost_eur': total_cost_eur,
        'total_revenue_eur': total_revenue_eur,
        'tokens_par_euro': tokens_par_euro,
    }


def project_audit_reponses(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Traçabilité des réponses full-auto (E10) et dette builder (E9).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Horodatage ISO (ignoré).

    Returns:
        Dict {reponses: [...], dette_builder: [...]}.
    """
    _ = (policy, now)
    # Réponses semi-auto / full-auto : touches envoyées récentes
    touch_rows = conn.execute(
        'SELECT t.id, t.campaign_id, t.channel, t.status, t.cost_eur, t.created_at, c.display'
        ' FROM touches t LEFT JOIN contacts c ON c.id=t.contact_id'
        ' ORDER BY t.created_at DESC LIMIT 20'
    ).fetchall()
    reponses = [
        {
            'id': str(r[0]),
            'campaign_id': str(r[1]),
            'channel': str(r[2]),
            'status': str(r[3]),
            'cost_eur': float(r[4] or 0),
            'created_at': str(r[5]),
            'contact': strip_ids(str(r[6] or '—')),
        }
        for r in touch_rows
    ]

    # Dette builder (E9) : artifacts en attente / synthèses
    art_rows = conn.execute(
        'SELECT id, venture_id, kind, version, created_at FROM artifacts'
        ' ORDER BY created_at DESC LIMIT 10'
    ).fetchall()
    dette_builder = [
        {
            'id': str(r[0]),
            'venture_id': str(r[1]),
            'kind': str(r[2]),
            'version': int(r[3]),
            'created_at': str(r[4]),
        }
        for r in art_rows
    ]

    return {
        'reponses': reponses,
        'dette_builder': dette_builder,
    }
