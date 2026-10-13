#!/usr/bin/env python3
"""Appeler une API décrite en base, et Stripe (lot 10, PR 5, Q56 et Q91).

Stripe est un faux serveur local qui note chaque requête ; le modèle est
un faux. Le reste est réel : la capacité, le schéma des outils, les
paramètres figés, l'interpréteur, les boutons de la fiche du business.

Scénarios :
- « Essayer Stripe (mode test) » depuis la fiche d'un business : un
  produit, un prix et un lien de paiement, avec la clé du mode test, une
  clé d'idempotence, et l'identifiant du business figé sur chaque objet,
  même si le modèle en propose un autre ;
- un paramètre que le point d'entrée ne permet pas est refusé ;
- une erreur de Stripe revient au modèle, et sa raison est au journal ;
  un secret absent aussi ;
- « Supprimer de Stripe (mode test) » archive les prix et le produit du
  business ;
- les boutons qui attendent un business sont sur sa fiche, pas sur la
  page Système.
"""

from __future__ import annotations

import http.server
import io
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db, utcnow  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tools import run_tool  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.mc.proj_ecoute import boutons_de_etape  # noqa: E402
from serge.mc.proj_faits import project_fait_pipe  # noqa: E402


class _FauxStripe(http.server.BaseHTTPRequestHandler):
    requetes: list[dict[str, Any]] = []

    def _repondre(self) -> None:
        longueur = int(self.headers.get('Content-Length') or 0)
        corps = self.rfile.read(longueur).decode() if longueur else ''
        chemin = urllib.parse.urlsplit(self.path)
        requete = {
            'methode': self.command,
            'chemin': chemin.path,
            'query': dict(urllib.parse.parse_qsl(chemin.query)),
            'corps': dict(urllib.parse.parse_qsl(corps)),
            'auth': self.headers.get('Authorization', ''),
            'idempotence': self.headers.get('Idempotency-Key', ''),
        }
        self.requetes.append(requete)
        statut, reponse = self._reponse(requete)
        data = json.dumps(reponse).encode()
        self.send_response(statut)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _reponse(self, r: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if r['chemin'] == '/v1/prices' and r['methode'] == 'POST':
            if r['corps'].get('unit_amount') == '0':
                return 400, {'error': {'message': 'Invalid integer: 0'}}
            return 200, {'id': 'price_1', 'object': 'price'}
        return 200, {
            '/v1/products': {'id': 'prod_1'},
            '/v1/payment_links': {'url': 'https://buy.stripe.com/test_1'},
            '/v1/products/search': {'data': [{'id': 'prod_1'}]},
            '/v1/prices': {'data': [{'id': 'price_1', 'active': True}]},
        }.get(r['chemin'], {'id': r['chemin'].rsplit('/', 1)[-1]})

    do_GET = do_POST = _repondre  # noqa: N815 — les noms de http.server

    def log_message(self, *_args: Any) -> None:
        pass


def appel(ident: str, nom: str, **args: Any) -> ToolCall:
    return ToolCall(ident, nom, json.dumps(args))


class FauxModele:
    """Joue une suite de tours d'outils, puis rend ``final``."""

    def __init__(self, tours: list[tuple[ToolCall, ...]], final: dict) -> None:
        self.tours = list(tours)
        self.final = final
        self.messages: list[list[dict[str, Any]]] = []

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        self.messages.append(json.loads(json.dumps(messages)))
        if self.tours:
            return ChatResult(
                '', 10, 10, 'faux', 1, tool_calls=self.tours.pop(0)
            )
        return ChatResult(json.dumps(self.final), 10, 10, 'faux', 1)


class ConnecteursTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        racine = Path(dossier.name)
        config = racine / 'config'
        (config / 'secrets').mkdir(parents=True)
        (config / 'secrets/stripe-test.key').write_text('sk_test_faux\n')
        instance = racine / 'instance.toml'
        instance.write_text(f'[paths]\nconfig_root = "{config}"\n')
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_SYSTEM_ROOT': str(racine),
                'SERGE_INSTANCE_FILE': str(instance),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        serveur = http.server.HTTPServer(('127.0.0.1', 0), _FauxStripe)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(serveur.shutdown)
        _FauxStripe.requetes = []
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        self.conn.execute(
            'UPDATE api_services SET base_url=?',
            (f'http://127.0.0.1:{serveur.server_address[1]}',),
        )
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at')"
        )
        self.conn.execute(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('ven_7', 'Devis Artisan', 'POC_SELECTED', ?, ?)",
            (utcnow(), utcnow()),
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _bouton(self, trigger: str, modele: FauxModele) -> str:
        tache = fire_button(self.conn, trigger, {'venture_id': 'ven_7'})
        self.assertIsNotNone(tache)
        self.conn.commit()
        process_one(self.conn, 'works', caller=modele)
        statut, erreur = self.conn.execute(
            'SELECT status, last_error FROM tasks WHERE id=?', (tache,)
        ).fetchone()
        self.assertEqual((statut, erreur), ('done', ''))
        return str(tache)

    def _resultats(self, modele: FauxModele, tour: int) -> list[dict]:
        return [
            json.loads(m['content'])
            for m in modele.messages[tour]
            if m.get('role') == 'tool'
        ]

    def test_essayer_stripe_depuis_la_fiche_du_business(self) -> None:
        modele = FauxModele(
            [
                (appel('a', 'stripe_creer_produit', name='Essai Serge'),),
                (
                    appel(
                        'b',
                        'stripe_creer_prix',
                        product='prod_1',
                        unit_amount=100,
                        currency='eur',
                        **{
                            'recurring[interval]': 'month',
                            'metadata[venture_id]': 'ven_AUTRE',
                        },
                    ),
                ),
                (
                    appel(
                        'c',
                        'stripe_creer_lien_paiement',
                        **{
                            'line_items[0][price]': 'price_1',
                            'line_items[0][quantity]': 1,
                        },
                    ),
                ),
            ],
            {'lien': 'https://buy.stripe.com/test_1', 'compte_rendu': 'Fait.'},
        )
        self._bouton('bouton_essayer_stripe', modele)
        produit, prix, lien = _FauxStripe.requetes
        self.assertEqual(
            (produit['methode'], produit['chemin']), ('POST', '/v1/products')
        )
        self.assertEqual(produit['auth'], 'Bearer sk_test_faux')
        self.assertTrue(produit['idempotence'].startswith('serge-'))
        for requete in (produit, prix, lien):
            self.assertEqual(requete['corps']['metadata[venture_id]'], 'ven_7')
        self.assertEqual(prix['corps']['unit_amount'], '100')
        self.assertEqual(prix['corps']['recurring[interval]'], 'month')
        self.assertEqual(lien['corps']['line_items[0][quantity]'], '1')
        self.assertEqual(
            self._resultats(modele, 3)[-1]['data']['url'],
            'https://buy.stripe.com/test_1',
        )
        # Le schéma ne montre pas au modèle ce qui est figé en base.
        schema = json.dumps(modele.messages[0])
        self.assertNotIn('metadata[venture_id]', schema)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM events WHERE type='api.call'"
            ).fetchone()[0],
            3,
        )

    def test_parametre_interdit_erreur_et_secret_absent(self) -> None:
        tache = {'venture_id': 'ven_7', 'task_id': 't1'}
        lien = self.conn.execute(
            "SELECT id FROM invocation_tools WHERE invocation_id='essayer_stripe'"
            " AND tool_id='stripe_creer_prix'"
        ).fetchone()[0]

        def prix(**args: Any) -> dict[str, Any]:
            return run_tool(
                self.conn,
                'essayer_stripe',
                lien,
                'stripe_creer_prix',
                args,
                tache,
            )

        refus = prix(
            product='prod_1', unit_amount=1, currency='eur', email='x'
        )
        self.assertEqual(refus['code'], 'parametre_inconnu')
        with redirect_stderr(io.StringIO()) as journal:
            erreur = prix(product='prod_1', unit_amount=0, currency='eur')
        self.assertEqual((erreur['ok'], erreur['status']), (False, 400))
        self.assertIn(
            'connecteur : stripe_test POST /v1/prices : HTTP 400 Invalid'
            ' integer: 0',
            journal.getvalue(),
        )
        self.conn.execute(
            "UPDATE api_services SET secret_file='absent.key'"
            " WHERE id='stripe_test'"
        )
        with redirect_stderr(io.StringIO()) as journal:
            absent = prix(product='prod_1', unit_amount=1, currency='eur')
        self.assertEqual(absent['code'], 'secret_absent')
        self.assertIn('absent.key', journal.getvalue())

    def test_supprimer_de_stripe(self) -> None:
        modele = FauxModele(
            [
                (
                    appel(
                        'a',
                        'stripe_chercher_produits',
                        query="metadata['venture_id']:'ven_7'",
                    ),
                ),
                (appel('b', 'stripe_lister_prix', product='prod_1'),),
                (
                    appel('c', 'stripe_archiver_prix', id='price_1'),
                    appel('d', 'stripe_archiver_produit', id='prod_1'),
                ),
            ],
            {'produits': 1, 'compte_rendu': 'Un produit archivé.'},
        )
        self._bouton('bouton_supprimer_stripe_test', modele)
        chercher, lister, prix, produit = _FauxStripe.requetes
        self.assertEqual(
            chercher['query']['query'], "metadata['venture_id']:'ven_7'"
        )
        self.assertEqual(lister['query']['product'], 'prod_1')
        self.assertEqual(
            (prix['chemin'], prix['corps']),
            ('/v1/prices/price_1', {'active': 'false'}),
        )
        self.assertEqual(
            (produit['chemin'], produit['corps']),
            ('/v1/products/prod_1', {'active': 'false'}),
        )

    def test_les_boutons_d_un_business_sont_sur_sa_fiche(self) -> None:
        fiche = project_fait_pipe(self.conn, 'venture', 'ven_7')
        assert fiche is not None
        boutons = {
            a['libelle']: a['charge']
            for a in fiche['actions']
            if 'charge' in a
        }
        self.assertEqual(
            boutons['Supprimer de Stripe (mode test)'],
            {
                'trigger_id': 'bouton_supprimer_stripe_test',
                'form': {'venture_id': 'ven_7'},
            },
        )
        self.assertIn('Essayer Stripe (mode test)', boutons)
        sans_etape = {b['titre'] for b in boutons_de_etape(self.conn, '')}
        self.assertNotIn('Supprimer de Stripe (mode test)', sans_etape)
        self.assertIn('Lancer un essai', sans_etape)


if __name__ == '__main__':
    unittest.main()
