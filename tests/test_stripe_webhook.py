#!/usr/bin/env python3
"""Webhook Stripe : URL d’instance, HMAC, passage paid."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import redirect_stderr
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.collect import create_intent, to_issued  # noqa: E402
from serge.collect.rails import RailError  # noqa: E402
from serge.collect.receiver import Handler  # noqa: E402
from serge.collect.webhook import (  # noqa: E402
    STRIPE_WEBHOOK_PATH,
    apply_event,
    compte_pour_de_vrai,
    installer_hint,
    public_webhook_url,
    verify_event,
)
from serge.db.boot import init_schema  # noqa: E402

WHSEC = 'whsec_test_secret'


def _signed(
    body: bytes, secret: str = WHSEC, timestamp: int = 1700000000
) -> str:
    digest = hmac.new(
        secret.encode(), f'{timestamp}.'.encode() + body, hashlib.sha256
    ).hexdigest()
    return f't={timestamp},v1={digest}'


class StripeWebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_url_uses_instance_hostname(self) -> None:
        self.assertEqual(
            public_webhook_url('serge.exemple.fr'),
            'https://serge.exemple.fr/hooks/stripe',
        )
        self.assertEqual(
            public_webhook_url('https://Autre.Example.net/'),
            'https://autre.example.net/hooks/stripe',
        )
        self.assertIn(
            'https://serge.example.net/hooks/stripe',
            installer_hint('serge.example.net'),
        )

    def test_verify_live_then_test(self) -> None:
        body = json.dumps({'id': 'evt_1', 'type': 'ping'}).encode()
        mode, event = verify_event(
            body,
            _signed(body, 'whsec_live'),
            {'live': 'whsec_live', 'test': WHSEC},
            now=1700000000.0,
        )
        self.assertEqual(mode, 'live')
        self.assertEqual(event['id'], 'evt_1')
        mode, _event = verify_event(
            body,
            _signed(body),
            {'live': 'whsec_other', 'test': WHSEC},
            now=1700000000.0,
        )
        self.assertEqual(mode, 'test')
        with self.assertRaises(RailError):
            verify_event(
                body, _signed(body), {'test': 'whsec_nope'}, now=1700000000.0
            )

    def test_apply_marks_paid_and_idempotent(self) -> None:
        tx = create_intent(
            self.conn, 'v1', 'invoice', 12.0, intent_key='pi_abc123'
        )
        to_issued(self.conn, tx, 'F-1')
        event = {
            'id': 'evt_paid',
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_abc123'}},
        }
        first = apply_event(self.conn, event)
        self.assertEqual(first['status'], 'ok')
        second = apply_event(self.conn, event)
        self.assertTrue(second.get('already'))
        status = self.conn.execute(
            'SELECT status FROM transactions WHERE id=?', (tx,)
        ).fetchone()[0]
        self.assertEqual(status, 'paid')

    def test_un_paiement_du_mode_test_n_est_pas_une_vente(self) -> None:
        """Sur une instance qui encaisse en vrai mode, un paiement fait
        avec une carte factice (le staging d'un produit) est reçu, dit au
        journal, et ne passe rien en « payé ». Le même paiement en vrai
        mode est compté ; une instance sans vrai mode garde le mode test."""
        chemin = Path(self.dossier.name) / 'serge.db'
        base = sqlite3.connect(chemin)
        base.row_factory = sqlite3.Row
        init_schema(base)
        base.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        tx = create_intent(base, 'v1', 'invoice', 12.0, intent_key='pi_essai')
        to_issued(base, tx, 'F-1')
        base.commit()
        base.close()
        corps = json.dumps(
            {
                'id': 'evt_essai',
                'type': 'payment_intent.succeeded',
                'data': {'object': {'id': 'pi_essai'}},
            }
        ).encode()

        def envoyer(secret: str, secrets: dict[str, str]) -> dict:
            recepteur = type(
                'Recepteur',
                (Handler,),
                {'secrets': secrets, 'db_path': chemin},
            )
            serveur = ThreadingHTTPServer(('127.0.0.1', 0), recepteur)
            fil = threading.Thread(target=serveur.serve_forever, daemon=True)
            fil.start()
            try:
                requete = urllib.request.Request(
                    f'http://127.0.0.1:{serveur.server_address[1]}'
                    f'{STRIPE_WEBHOOK_PATH}',
                    data=corps,
                    headers={
                        'Stripe-Signature': _signed(
                            corps, secret, int(time.time())
                        )
                    },
                )
                with urllib.request.urlopen(requete, timeout=10) as reponse:
                    return json.loads(reponse.read())
            finally:
                serveur.shutdown()
                serveur.server_close()

        def statut() -> str:
            lu = sqlite3.connect(chemin)
            try:
                return lu.execute(
                    'SELECT status FROM transactions WHERE id=?', (tx,)
                ).fetchone()[0]
            finally:
                lu.close()

        les_deux = {'live': 'whsec_du_vrai_mode', 'test': WHSEC}
        journal = io.StringIO()
        with redirect_stderr(journal):
            recu = envoyer(WHSEC, les_deux)
        self.assertEqual(recu, {'status': 'ignored', 'mode': 'test'})
        self.assertIn('mode test ignoré', journal.getvalue())
        self.assertNotEqual(statut(), 'paid')
        with redirect_stderr(io.StringIO()):
            recu = envoyer('whsec_du_vrai_mode', les_deux)
        self.assertEqual((recu['status'], recu['mode']), ('ok', 'live'))
        self.assertEqual(statut(), 'paid')
        self.assertTrue(compte_pour_de_vrai('test', {'test': WHSEC}))
        self.assertFalse(compte_pour_de_vrai('test', les_deux))

    def test_unmatched_and_ignored(self) -> None:
        event = {
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_unknown'}},
        }
        self.assertEqual(apply_event(self.conn, event)['status'], 'unmatched')
        self.assertEqual(
            apply_event(self.conn, {'type': 'customer.created'})['status'],
            'ignored',
        )

    def test_checkout_session_uses_payment_intent(self) -> None:
        tx = create_intent(
            self.conn, 'v1', 'invoice', 5.0, intent_key='pi_sess'
        )
        to_issued(self.conn, tx, 'F-2')
        event = {
            'id': 'evt_sess',
            'type': 'checkout.session.completed',
            'data': {'object': {'payment_intent': 'pi_sess'}},
        }
        self.assertEqual(apply_event(self.conn, event)['status'], 'ok')

    def test_abonnement_et_facture_liee(self) -> None:
        event = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': 'sub_abc',
                    'status': 'active',
                    'current_period_end': 1800000000,
                    'items': {
                        'data': [{'price': {'unit_amount': 2900}}],
                    },
                }
            },
        }
        out = apply_event(self.conn, event)
        self.assertEqual(out['status'], 'ok')
        row = self.conn.execute(
            'SELECT amount_eur, status FROM subscriptions'
            " WHERE external_id='sub_abc'"
        ).fetchone()
        self.assertEqual(row[0], 29.0)
        self.assertEqual(row[1], 'active')
        paid = apply_event(
            self.conn,
            {
                'type': 'invoice.paid',
                'data': {
                    'object': {
                        'id': 'in_1',
                        'subscription': 'sub_abc',
                        'payment_intent': 'pi_abo1',
                        'amount_paid': 2900,
                    }
                },
            },
        )
        self.assertEqual(paid['status'], 'ok')
        tx = self.conn.execute(
            "SELECT status FROM transactions WHERE intent_id='pi_abo1'"
        ).fetchone()
        self.assertEqual(tx[0], 'paid')
        lien = self.conn.execute(
            'SELECT last_transaction_id FROM subscriptions'
            " WHERE external_id='sub_abc'"
        ).fetchone()[0]
        self.assertTrue(lien)

    def _abo(self, metadata: dict | None = None, price_md: dict | None = None):
        price: dict = {'unit_amount': 1500}
        if price_md is not None:
            price['metadata'] = price_md
        objet: dict = {
            'id': 'sub_v',
            'status': 'active',
            'items': {'data': [{'price': price}]},
        }
        if metadata is not None:
            objet['metadata'] = metadata
        return apply_event(
            self.conn,
            {
                'type': 'customer.subscription.created',
                'data': {'object': objet},
            },
        )

    def _venture_de(self, external: str) -> str:
        return self.conn.execute(
            'SELECT venture_id FROM subscriptions WHERE external_id=?',
            (external,),
        ).fetchone()[0]

    def test_abonnement_rattache_au_business_du_prix(self) -> None:
        self._abo(price_md={'venture_id': 'v1'})
        self.assertEqual(self._venture_de('sub_v'), 'v1')
        paid = apply_event(
            self.conn,
            {
                'type': 'invoice.paid',
                'data': {
                    'object': {
                        'id': 'in_v',
                        'subscription': 'sub_v',
                        'payment_intent': 'pi_v',
                        'amount_paid': 1500,
                    }
                },
            },
        )
        self.assertEqual(paid['status'], 'ok')
        tx = self.conn.execute(
            "SELECT venture_id FROM transactions WHERE intent_id='pi_v'"
        ).fetchone()
        self.assertEqual(tx[0], 'v1')

    def test_abonnement_sans_business_est_signale(self) -> None:
        self._abo(metadata={'venture_id': 'inconnu'})
        self.assertEqual(self._venture_de('sub_v'), '')
        types = [
            row[0]
            for row in self.conn.execute('SELECT type FROM events').fetchall()
        ]
        self.assertEqual(types.count('collect.subscription_unattached'), 1)
        self.conn.execute(
            "INSERT INTO ventures(id, created_at, updated_at) VALUES('v2','t','t')"
        )
        self._abo(metadata={'venture_id': 'v2'})
        self.assertEqual(self._venture_de('sub_v'), 'v2')

    def test_business_rattache_jamais_remplace(self) -> None:
        self.conn.execute(
            "INSERT INTO ventures(id, created_at, updated_at) VALUES('v2','t','t')"
        )
        self._abo(metadata={'venture_id': 'v1'})
        self._abo(metadata={'venture_id': 'v2'})
        self.assertEqual(self._venture_de('sub_v'), 'v1')


if __name__ == '__main__':
    unittest.main()
