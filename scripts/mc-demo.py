#!/usr/bin/env python3
"""Démo MC : histoire d'argent + incident débogable. http://127.0.0.1:8471/owner"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path('/home/jpesquet/SergeAgent')
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.mc.auth import RateLimiter  # noqa: E402
from serge.mc.server import McConfig, create_server  # noqa: E402
from serge.scheduler import claim, enqueue  # noqa: E402

DB = Path('/tmp/mc-demo.db')
TOKEN = 'demo-locale'
PORT = 8471


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def event(conn, actor, type_, payload, moment):
    append_event(conn, actor=actor, type=type_, payload=payload)
    rowid = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.execute('UPDATE events SET ts=? WHERE id=?', (_iso(moment), rowid))


def main() -> None:
    now = datetime.now(UTC)
    if DB.exists():
        DB.unlink()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    init_schema(conn)

    conn.execute(
        "INSERT INTO ventures(id, name, lifecycle, schedulable, created_at,"
        " updated_at) VALUES('v1','Atelier chrono freelance',"
        "'SMOKE_RUNNING',1,?,?)",
        (_iso(now), _iso(now)),
    )
    conn.execute(
        "INSERT INTO contacts(id, venture_id, display, email, regime,"
        " funnel_state, created_at, updated_at) VALUES"
        "('p1','v1','Ada Morel','ada@x.io','INBOUND','INTENT',?,?),"
        "('p2','v1','Bob Klein','bob@x.io','OUTBOUND','CONTACTING',?,?),"
        "('p3','v1','Chloé Martin','chloe@x.io','INBOUND','CUSTOMER',?,?)",
        (_iso(now),) * 6,
    )
    conn.execute(
        "INSERT INTO campaigns(id, venture_id, family, channel, state,"
        " n_target, created_at, updated_at) VALUES"
        "('c1','v1','named','email','RUNNING',40,?,?),"
        "('c2','v1','named','voice','PAUSED',12,?,?)",
        (_iso(now),) * 4,
    )
    for tid, cid, pid, channel, statut, cle, moment in (
        ('t1', 'c1', 'p1', 'email', 'sent', 'k-t1', now - timedelta(hours=8)),
        ('t2', 'c1', 'p1', 'email', 'delivered', 'k-t2', now - timedelta(hours=6)),
        ('t3', 'c1', 'p2', 'email', 'sent', 'k-t3', now - timedelta(hours=3)),
        ('t4', 'c1', 'p3', 'email', 'delivered', 'k-t4', now - timedelta(days=1)),
        ('t5', 'c2', 'p2', 'sms', 'sent', 'k-t5', now - timedelta(hours=5)),
    ):
        conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, created_at, updated_at)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (tid, cid, pid, channel, statut, cle, _iso(moment), _iso(moment)),
        )
    conn.execute(
        "INSERT INTO transactions(id, venture_id, kind, amount_eur,"
        " intent_id, status, created_at, updated_at) VALUES"
        "('x1','v1','invoice',180.0,'in-chloe','paid',?,?),"
        "('x2','v1','invoice',90.0,'in-ada','draft',?,?)",
        (_iso(now - timedelta(hours=2)),) * 2
        + (_iso(now),) * 2,
    )
    conn.execute(
        "INSERT INTO subscriptions(id, venture_id, provider, amount_eur,"
        " period, status, created_at, updated_at) VALUES"
        "('s-chloe','v1','stripe',49.0,'monthly','active',?,?)",
        (_iso(now), _iso(now)),
    )
    conn.execute(
        "INSERT INTO accounts_standing(id, venue, handle, cooldown_until,"
        " updated_at) VALUES('s1','gmail','serge@atelier.io',?,?),"
        "('s2','rss','écoute-marché','',?)",
        (_iso(now + timedelta(hours=2)), _iso(now), _iso(now)),
    )
    conn.execute(
        "INSERT INTO listen_docs(id, source, url, title, excerpt, cluster_id,"
        " fetched_at) VALUES"
        "('d1','rss','https://www.reddit.com/r/freelance/chrono',"
        "'Freelances cherchent un chrono simple',"
        "'Trop d’outils, besoin d’un timer facturable.','cA',?),"
        "('d2','rss','https://www.reddit.com/r/smallbusiness/prix',"
        "'Prix trop flous sur les ateliers',"
        "'Les gens veulent un prix affiché.','cA',?)",
        (_iso(now - timedelta(hours=10)), _iso(now - timedelta(hours=9))),
    )
    conn.execute(
        "INSERT INTO inbound_events(id, contact_id, campaign_id, channel,"
        " native_type, signal, class, score, received_at, payload_json)"
        " VALUES('b1','p1','c1','email','reply','REPLIED','positive',0.86,?,"
        " ?),"
        "('b2','p3','c1','email','reply','INTENT','intent',0.95,?,?)",
        (
            _iso(now - timedelta(hours=5)),
            json.dumps({'texte': 'Oui, envoyez le devis.'}),
            _iso(now - timedelta(hours=3)),
            json.dumps({'texte': 'Payé, merci.'}),
        ),
    )
    conn.execute(
        "INSERT INTO lessons(id, statement, confidence, scope, status,"
        " sources_json, created_at, updated_at) VALUES"
        "('l1','Un prix affiché convertit mieux qu’une fourchette floue',"
        "0.8,'v1','active',?,?,?)",
        (
            json.dumps(['d2', 'x1']),
            _iso(now - timedelta(days=2)),
            _iso(now),
        ),
    )
    conn.execute(
        "INSERT INTO playbooks(id, name, conditions, steps_json, scope,"
        " created_at, updated_at) VALUES"
        "('pb1','Relance J+2 e-mail','pas de réponse 48h',"
        "?, 'v1',?,?)",
        (
            json.dumps(['attendre 48h', 'écrire relance courte', 'si silence → SMS']),
            _iso(now),
            _iso(now),
        ),
    )
    for tid, typ, title, expiry in (
        (
            't-guichet',
            'GUICHET',
            'Captcha Gmail à résoudre',
            now + timedelta(minutes=10),
        ),
        (
            't-veto',
            'VETO_AMONT',
            'Valider le prix 180 €',
            now + timedelta(minutes=30),
        ),
        ('t-alert', 'ALERT', 'Quota e-mail à 80 %', None),
        ('t-hypo', 'HYPOTHESIS', 'Piste atelier chrono', None),
    ):
        conn.execute(
            "INSERT INTO tickets(id, type, title, state, expiry_at,"
            " created_at, updated_at) VALUES(?,?,?,'OPEN',?,?,?)",
            (
                tid,
                typ,
                title,
                _iso(expiry) if expiry else '',
                _iso(now),
                _iso(now),
            ),
        )

    running = enqueue(conn, kind='email.send', idempotency_key='k-run', venture_id='v1')
    claim(conn, running)
    conn.execute(
        'UPDATE work_items SET contact_id=?, campaign_id=?, updated_at=?'
        ' WHERE id=?',
        ('p1', 'c1', _iso(now - timedelta(minutes=11)), running),
    )
    enqueue(conn, kind='inbound.classify', idempotency_key='k-r1', venture_id='v1')
    enqueue(
        conn,
        kind='listen.collect',
        idempotency_key='k-r2',
        venture_id='v1',
        blocked_until=_iso(now + timedelta(hours=1)),
    )
    failed = enqueue(conn, kind='email.poll', idempotency_key='k-f1', venture_id='v1')
    conn.execute(
        "UPDATE work_items SET status='FAILED', payload_json=?, updated_at=?"
        ' WHERE id=?',
        (
            json.dumps({'motif': 'garde quota : 40 e-mails / boîte / jour'}),
            _iso(now - timedelta(hours=1)),
            failed,
        ),
    )

    event(conn, 'guards', 'guard', {'allowed': True}, now - timedelta(minutes=40))
    event(
        conn,
        'guards',
        'guard',
        {'allowed': False, 'code': 'quota_email', 'champ': 'quotas.email_per_mailbox_per_day'},
        now - timedelta(minutes=35),
    )
    event(conn, 'runner', 'work.completed', {'id': 'w-vieux'}, now - timedelta(minutes=20))
    event(conn, 'runner', 'work.failed', {'id': failed}, now - timedelta(hours=1))
    prompt = (
        'Contexte : Ada a répondu « Oui, envoyez le devis. »\n'
        'Tâche : classer le signal (positive / objection / autre).\n'
        'Leçon active : un prix affiché convertit mieux.'
    )
    sortie = (
        'Classe : positive.\n'
        'Confiance : 0,86.\n'
        'Suite : préparer un devis à 180 €, prix affiché, sans fourchette.\n'
        'Justification : le message ouvre la porte ; la leçon l1 interdit de flouer le montant.\n'
        'Dernier caractère utile : ne pas relancer tant que le devis n’est pas parti.'
    )
    event(
        conn,
        'classify_reply',
        'llm.io',
        {'point': 'classify_reply', 'prompt': prompt, 'sortie': sortie},
        now - timedelta(minutes=8),
    )
    for point, tin, tout, lat, verdict, moment in (
        ('qualify_prospect', 1000, 400, 90, 'ok', now - timedelta(hours=4)),
        ('classify_reply', 1800, 700, 140, 'ok', now - timedelta(minutes=8)),
        ('draft_price', 900, 300, 80, 'ok', now - timedelta(hours=3)),
        ('cluster_demand', 2200, 600, 200, 'ok', now - timedelta(hours=9)),
    ):
        conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            ' tokens_out, latency_ms, verdict, created_at)'
            " VALUES(?,'T1','nemo',?,?,?,?,?)",
            (point, tin, tout, lat, verdict, _iso(moment)),
        )

    conn.commit()
    conn.close()

    config = McConfig(
        db_path=DB,
        owner_token=TOKEN,
        static_dir=ROOT / 'serge/mc/static',
        templates_dir=ROOT / 'serge/mc/templates',
        limiter=RateLimiter(),
    )
    server = create_server(config, port=PORT)
    print(f'MC démo : http://127.0.0.1:{PORT}/owner  (jeton : {TOKEN})', flush=True)
    print(f'DB : {DB} (recréée à chaque lancement)', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
