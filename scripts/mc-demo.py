#!/usr/bin/env python3
"""Démo MC : histoire d'argent + incident débogable. http://127.0.0.1:8471/owner"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.funnels.contacts import add_address  # noqa: E402
from serge.interpreter.tasks import (  # noqa: E402
    enqueue_task,
    finish_task,
    start_task,
)
from serge.mc.auth import RateLimiter  # noqa: E402
from serge.mc.server import McConfig, create_server  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402

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
        'INSERT INTO ventures(id, name, lifecycle, schedulable, created_at,'
        " updated_at) VALUES('v1','Atelier chrono freelance',"
        "'SMOKE_RUNNING',1,?,?)",
        (_iso(now), _iso(now)),
    )
    for ident, nom, email, regime, etat in (
        ('p1', 'Ada Morel', 'ada@x.io', 'INBOUND', 'INTENT'),
        ('p2', 'Bob Klein', 'bob@x.io', 'OUTBOUND', 'CONTACTING'),
        ('p3', 'Chloé Martin', 'chloe@x.io', 'INBOUND', 'CUSTOMER'),
    ):
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, regime,'
            " funnel_state, created_at, updated_at) VALUES(?,'v1',?,?,?,?,?)",
            (ident, nom, regime, etat, _iso(now), _iso(now)),
        )
        add_address(conn, ident, 'email', email)
    conn.execute(
        'INSERT INTO campaigns(id, venture_id, family, channel, state,'
        ' n_target, created_at, updated_at) VALUES'
        "('c1','v1','named','email','RUNNING',40,?,?),"
        "('c2','v1','named','voice','PAUSED',12,?,?)",
        (_iso(now),) * 4,
    )
    for tid, cid, pid, channel, statut, cle, moment in (
        ('t1', 'c1', 'p1', 'email', 'sent', 'k-t1', now - timedelta(hours=8)),
        (
            't2',
            'c1',
            'p1',
            'email',
            'delivered',
            'k-t2',
            now - timedelta(hours=6),
        ),
        ('t3', 'c1', 'p2', 'email', 'sent', 'k-t3', now - timedelta(hours=3)),
        (
            't4',
            'c1',
            'p3',
            'email',
            'delivered',
            'k-t4',
            now - timedelta(days=1),
        ),
        ('t5', 'c2', 'p2', 'sms', 'sent', 'k-t5', now - timedelta(hours=5)),
    ):
        conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, created_at, updated_at)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (tid, cid, pid, channel, statut, cle, _iso(moment), _iso(moment)),
        )
    conn.execute(
        'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
        ' intent_id, status, created_at, updated_at) VALUES'
        "('x1','v1','invoice',180.0,'in-chloe','paid',?,?),"
        "('x2','v1','invoice',90.0,'in-ada','draft',?,?)",
        (_iso(now - timedelta(hours=2)),) * 2 + (_iso(now),) * 2,
    )
    conn.execute(
        'INSERT INTO subscriptions(id, venture_id, provider, amount_eur,'
        ' period, status, created_at, updated_at) VALUES'
        "('s-chloe','v1','stripe',49.0,'monthly','active',?,?)",
        (_iso(now), _iso(now)),
    )
    conn.execute(
        'INSERT INTO accounts_standing(id, venue, handle, cooldown_until,'
        ' updated_at, role, profile_path, secret_ref, login_url,'
        ' targets_json, last_login_at, last_fetch_at, login, password) VALUES'
        "('s1','gmail','serge@atelier.io',?,?,'publication','',"
        "'gmail.session','https://mail.google.com/','[]','','',"
        "'serge@atelier.io','pw-demo-gmail'),"
        "('s2','reddit','u/serge_atelier','',?,'ecoute',"
        "'/tmp/serge-demo-profile-reddit','reddit.session',"
        "'https://www.reddit.com/login',"
        "'[\"https://www.reddit.com/r/freelance/\"]','',?,"
        "'u/serge_atelier','pw-demo-reddit')",
        (
            _iso(now + timedelta(hours=2)),
            _iso(now),
            _iso(now),
            _iso(now - timedelta(hours=10)),
        ),
    )
    conn.execute(
        'INSERT INTO listen_docs(id, source, url, title, excerpt, label,'
        ' fetched_at) VALUES'
        "('d1','rss','https://www.reddit.com/r/freelance/chrono',"
        "'Freelances cherchent un chrono simple',"
        "'Trop d’outils, besoin d’un timer facturable.','besoin_nouveau',?),"
        "('d2','rss','https://www.reddit.com/r/smallbusiness/prix',"
        "'Prix trop flous sur les ateliers',"
        "'Les gens veulent un prix affiché.','besoin_nouveau',?)",
        (_iso(now - timedelta(hours=10)), _iso(now - timedelta(hours=9))),
    )
    conn.execute(
        'INSERT INTO inbound_events(id, contact_id, campaign_id, channel,'
        ' native_type, signal, class, score, received_at, payload_json)'
        " VALUES('b1','p1','c1','email','reply','REPLIED','positive',0.86,?,"
        ' ?),'
        "('b2','p3','c1','email','reply','INTENT','intent',0.95,?,?)",
        (
            _iso(now - timedelta(hours=5)),
            json.dumps({'texte': 'Oui, envoyez le devis.'}),
            _iso(now - timedelta(hours=3)),
            json.dumps({'texte': 'Payé, merci.'}),
        ),
    )
    conn.execute(
        'INSERT INTO lessons(id, statement, confidence, scope, status,'
        ' sources_json, created_at, updated_at) VALUES'
        "('l1','Un prix affiché convertit mieux qu’une fourchette floue',"
        "0.8,'v1','active',?,?,?)",
        (
            json.dumps(['d2', 'x1']),
            _iso(now - timedelta(days=2)),
            _iso(now),
        ),
    )
    conn.execute(
        'INSERT INTO playbooks(id, name, conditions, steps_json, scope,'
        ' created_at, updated_at) VALUES'
        "('pb1','Relance J+2 e-mail','pas de réponse 48h',"
        "?, 'v1',?,?)",
        (
            json.dumps(
                ['attendre 48h', 'écrire relance courte', 'si silence → SMS']
            ),
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
            'INSERT INTO tickets(id, type, title, state, expiry_at,'
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

    # Des invocations de démonstration, sans LLM, pour remplir les files.
    demos = (
        ('demo_ecrire', 'Écrire au prospect (démo)', 'prospection_light'),
        ('demo_classer', 'Classer une réponse (démo)', 'prospection_lourde'),
        ('demo_pages', 'Ramasser des pages (démo)', 'pre_prospection'),
        ('demo_boite', 'Relever la boîte (démo)', 'prospection_lourde'),
    )
    seed_pipeline(
        conn,
        {
            'schema_version': 1,
            'invocations': [
                {
                    'id': ident,
                    'title': titre,
                    'role': 'Invocation de démonstration.',
                    'type': 'capability',
                    'capability': 'echo',
                    'step': etape,
                }
                for ident, titre, etape in demos
            ],
        },
    )
    # Serge est arrêté par défaut ; la démo le montre démarré.
    set_heartbeat(conn, True)
    running = enqueue_task(
        conn, 'demo_ecrire', {'venture_id': 'v1', 'contact_id': 'p1'}
    )
    start_task(conn, str(running))
    conn.execute(
        'UPDATE tasks SET started_at=? WHERE id=?',
        (_iso(now - timedelta(minutes=11)), running),
    )
    enqueue_task(conn, 'demo_classer', {'venture_id': 'v1'})
    enqueue_task(
        conn,
        'demo_pages',
        {'venture_id': 'v1'},
        not_before=_iso(now + timedelta(hours=1)),
    )
    failed = enqueue_task(conn, 'demo_boite', {'venture_id': 'v1'})
    start_task(conn, str(failed))
    finish_task(
        conn, str(failed), error='garde quota : 40 e-mails / boîte / jour'
    )

    event(
        conn, 'guards', 'guard', {'allowed': True}, now - timedelta(minutes=40)
    )
    event(
        conn,
        'guards',
        'guard',
        {
            'allowed': False,
            'code': 'quota_email',
            'champ': 'channels.email.max_per_day',
        },
        now - timedelta(minutes=35),
    )
    event(
        conn,
        'runner',
        'work.completed',
        {'id': 'w-vieux'},
        now - timedelta(minutes=20),
    )
    event(
        conn, 'runner', 'work.failed', {'id': failed}, now - timedelta(hours=1)
    )
    for point, tin, tout, lat, verdict, moment in (
        ('demo_classer', 1000, 400, 90, 'ok', now - timedelta(hours=4)),
        ('demo_classer', 1800, 700, 140, 'ok', now - timedelta(minutes=8)),
    ):
        conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            ' tokens_out, latency_ms, verdict, created_at)'
            " VALUES(?,'fast','nemo',?,?,?,?,?)",
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
    print(
        f'MC démo : http://127.0.0.1:{PORT}/owner  (jeton : {TOKEN})',
        flush=True,
    )
    print(f'DB : {DB} (recréée à chaque lancement)', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
