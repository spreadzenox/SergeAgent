#!/usr/bin/env python3
"""L'étape 5 de bout en bout : le vrai produit (lot 10, Q41, Q43, Q91).

Le modèle, Docker, Stripe et Cloudflare sont des faux (un serveur local qui
note chaque requête) ; le pipeline en base, l'interpréteur, les liens, les
tickets, « Appeler une API », la publication et Caddy sont réels.

Scénarios :
- « Bout en bout : le produit fini d'une calculatrice » : le plan du
  produit retient une demande des clients et en refuse une, avec son
  domaine ; validé, le produit est créé dans Stripe en mode test (avec sa
  clé de recherche), construit dans un chantier qui a la clé du mode test,
  publié en staging, relu ; essayé et validé, Serge achète le domaine chez
  Cloudflare et le fait pointer vers le serveur, met le produit en vente en
  vrai mode, le publie sur son domaine avec la clé restreinte, fait le
  paiement test de 1 € et se rembourse ; le business est prêt pour la
  prospection lourde ;
- un domaine qui n'a pas pu être acheté ouvre le ticket « Domaine » ; le
  nom donné par un humain est acheté ;
- avec un domaine commun des produits finis (réglage), rien n'est acheté :
  Serge crée l'enregistrement DNS du sous-domaine du produit, et la prod
  va sur ce sous-domaine ;
- « Construire le vrai produit » sur la fiche d'un business au test léger
  lance la conception ; sur un business candidat, rien ne part ;
- sans la clé restreinte du vrai mode, la mise en prod rate et un ticket
  le dit ;
- l'adresse du serveur vient du domaine de l'instance ; une adresse privée
  est refusée.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import socket
import sys
import tempfile
import threading
import unittest
import urllib.parse
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db, utcnow  # noqa: E402
from serge.ingress import adresse, caddy  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.mc.proj_faits import project_fait_pipe  # noqa: E402
from serge.sandbox import publier  # noqa: E402
from serge.tickets.acts import APPROVE, REJECT  # noqa: E402
from serge.tickets.lifecycle import decide  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402

IP = '93.184.216.34'


class _Services(http.server.BaseHTTPRequestHandler):
    """Stripe et Cloudflare, à une seule adresse."""

    requetes: list[dict[str, Any]] = []
    pris: set[str] = set()

    def _repondre(self) -> None:
        longueur = int(self.headers.get('Content-Length') or 0)
        brut = self.rfile.read(longueur).decode() if longueur else ''
        chemin = urllib.parse.urlsplit(self.path)
        corps: Any = (
            json.loads(brut)
            if brut.startswith('{')
            else dict(urllib.parse.parse_qsl(brut))
        )
        requete = {
            'methode': self.command,
            'chemin': chemin.path,
            'query': dict(urllib.parse.parse_qsl(chemin.query)),
            'corps': corps,
            'auth': self.headers.get('Authorization', ''),
        }
        self.requetes.append(requete)
        statut, reponse = self._reponse(requete)
        data = json.dumps(reponse).encode()
        self.send_response(statut)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _reponse(self, r: dict[str, Any]) -> tuple[int, Any]:
        chemin = r['chemin']
        compte = '/accounts/acct_test/registrar'
        if chemin == f'{compte}/domain-check':
            return 200, {
                'success': True,
                'result': {
                    'domains': [
                        {
                            'name': nom,
                            'registrable': nom not in self.pris,
                            'tier': 'standard',
                            'pricing': {
                                'currency': 'USD',
                                'registration_cost': '10.46',
                                'renewal_cost': '10.46',
                            },
                        }
                        for nom in r['corps']['domains']
                    ]
                },
            }
        if chemin == f'{compte}/registrations':
            if r['corps']['domain_name'] in self.pris:
                return 400, {
                    'success': False,
                    'errors': [{'code': 1, 'message': 'Domain unavailable'}],
                }
            return 201, {'success': True, 'result': {'state': 'succeeded'}}
        if chemin == f'{compte}/domains':
            return 200, {'success': True, 'result': []}
        if chemin == '/zones':
            return 200, {
                'success': True,
                'result': [{'id': 'zone_1', 'name': r['query']['name']}],
            }
        if chemin == '/zones/zone_1/dns_records':
            if r['methode'] == 'GET':
                return 200, {'success': True, 'result': []}
            return 200, {'success': True, 'result': {'id': 'rec_1'}}
        return 200, {
            '/v1/products': {'id': 'prod_1'},
            '/v1/prices': {'id': 'price_1'},
            '/v1/payment_links': {
                'id': 'plink_1',
                'url': 'https://buy.test/1',
            },
            '/v1/checkout/sessions': {
                'data': [
                    {
                        'payment_status': 'paid',
                        'amount_total': 100,
                        'payment_intent': 'pi_1',
                    }
                ]
            },
            '/v1/refunds': {'id': 're_1', 'status': 'succeeded'},
        }.get(chemin, {'id': chemin.rsplit('/', 1)[-1]})

    do_GET = do_POST = do_PUT = _repondre  # noqa: N815 — les noms de http.server

    def log_message(self, *_args: Any) -> None:
        pass


def appel(ident: str, nom: str, **args: Any) -> ToolCall:
    return ToolCall(ident, nom, json.dumps(args))


def _plan_produit(domaine: str, demandes: list[str]) -> dict[str, Any]:
    return {
        'hypothese': 'Des clients paient pour une calculatrice qui se souvient.',
        'cible': 'Artisans et commerçants.',
        'prix': '4 € par mois',
        'livrable': 'Une calculatrice avec un compte et un historique.',
        'plan': 'Inscription, connexion, abonnement Stripe, historique.',
        'scenarios': '1. Créer un compte, payer, retrouver ses calculs.',
        'domaine': domaine,
        'fiche_resume': 'Une calculatrice qui garde vos calculs.',
        'fiche_limites': 'Pas de fonctions scientifiques.',
        'fiche_prix': '4 € par mois.',
        'fiche_delais': 'Tout de suite.',
        'fiche_usage': 'On se connecte et on calcule.',
        'faq': [{'question': 'Puis-je arrêter ?', 'reponse': 'Oui.'}],
        'demandes': [
            {'numero': numero, 'decision': decision, 'raison': raison}
            for numero, (decision, raison) in zip(
                demandes,
                (
                    ('retenue', 'Elle fait payer.'),
                    ('refusee', 'Hors du produit.'),
                ),
                strict=False,
            )
        ],
    }


class FauxModeles:
    """Chaque invocation LLM de l'étape 5, reconnue à son prompt."""

    MARQUES = (
        ('Tu conçois le vrai produit', 'concevoir'),
        ('Tu critiques le plan du produit fini', 'critiquer'),
        ('Tu mets en vente dans Stripe', 'vendre'),
        ('Tu construis le produit fini', 'construire'),
        ('Tu essaies le produit fini', 'relire'),
        ('Tu achètes le nom de domaine', 'acheter'),
        ('Tu fais le paiement test de 1 €', 'payer'),
        ('Tu fais pointer le sous-domaine', 'pointer'),
    )

    def __init__(self, domaines: list[str]) -> None:
        self.domaines = list(domaines)
        self.par_role: dict[str, list[list[dict]]] = {}

    def __call__(self, _key, model, messages, tools=None, **_kw):
        system = messages[0]['content']
        role = next((r for m, r in self.MARQUES if m in system), None)
        assert role, f'prompt inattendu : {system[:80]}'
        self.par_role.setdefault(role, []).append(messages)
        outils = sum(1 for m in messages if m.get('role') == 'tool')
        return getattr(self, f'_{role}')(messages, outils)

    @staticmethod
    def _json(data: dict[str, Any]) -> ChatResult:
        return ChatResult(json.dumps(data), 10, 10, 'faux', 1)

    @staticmethod
    def _outils(*calls: ToolCall) -> ChatResult:
        return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)

    def _concevoir(self, messages, _outils) -> ChatResult:
        demandes = re.findall(r'cus_[0-9a-f]{12}', json.dumps(messages))
        return self._json(_plan_produit('calculatrice-pro.fr', demandes))

    def _critiquer(self, _messages, _outils) -> ChatResult:
        return self._json({'verdict': 'bon', 'avis': 'Réaliste.'})

    def _vendre(self, _messages, outils) -> ChatResult:
        if outils == 0:
            return self._outils(
                appel('p', 'stripe_creer_produit', name='Calculatrice'),
                appel(
                    'q',
                    'stripe_creer_prix_du_produit',
                    product='prod_1',
                    unit_amount=400,
                    currency='eur',
                    **{'recurring[interval]': 'month'},
                ),
            )
        return self._json(
            {'ok': 'oui', 'produit': 'prod_1', 'prix': 'price_1'}
        )

    def _construire(self, _messages, outils) -> ChatResult:
        if outils == 0:
            return self._outils(
                appel(
                    'd',
                    'chantier_ecrire',
                    path='Dockerfile',
                    content='FROM node:22\nCMD ["node", "app.js"]\n',
                ),
            )
        return self._json({'fini': 'oui', 'compte_rendu': 'Paiement essayé.'})

    def _relire(self, _messages, _outils) -> ChatResult:
        return self._json(
            {
                'verdict': 'bon',
                'remarques': '',
                'compte_rendu': 'Payé, débloqué.',
            }
        )

    def _acheter(self, messages, outils) -> ChatResult:
        domaine = self.domaines[0]
        if outils == 0:
            return self._outils(
                appel('v', 'cloudflare_disponibilite', domains=[domaine])
            )
        if outils == 1:
            resultat = json.loads(messages[-1]['content'])
            if not resultat['data']['result']['domains'][0]['registrable']:
                self.domaines.pop(0)
                return self._json(
                    {
                        'achete': 'non',
                        'domaine': domaine,
                        'raison': f'{domaine} est pris ; libre : calc-simple.fr (11,51 €).',
                    }
                )
            return self._outils(
                appel('a', 'cloudflare_acheter_domaine', domain_name=domaine),
                appel('z', 'cloudflare_zone', name=domaine),
            )
        if outils == 3:
            return self._outils(
                appel(
                    'd',
                    'cloudflare_dns_creer',
                    zone_id='zone_1',
                    name=domaine,
                    content=IP,
                )
            )
        return self._json(
            {'achete': 'oui', 'domaine': domaine, 'prix': '11,51 € par an'}
        )

    def _pointer(self, messages, outils) -> ChatResult:
        # Le nom vient de l'outil « L'adresse du produit », donné d'office.
        nom = re.findall(
            r'[a-z0-9-]+\.produits\.exemple\.fr', json.dumps(messages)
        )[0]
        if outils == 0:
            return self._outils(
                appel('z', 'cloudflare_zone', name='produits.exemple.fr')
            )
        if outils == 1:
            return self._outils(
                appel(
                    'd',
                    'cloudflare_dns_creer',
                    zone_id='zone_1',
                    name=nom,
                    content=IP,
                )
            )
        return self._json({'ok': 'oui', 'nom': nom})

    def _payer(self, _messages, outils) -> ChatResult:
        if outils == 0:
            return self._outils(
                appel(
                    'p',
                    'stripe_creer_prix',
                    product='prod_1',
                    unit_amount=100,
                    currency='eur',
                ),
                appel(
                    'l',
                    'stripe_creer_lien_paiement',
                    **{
                        'line_items[0][price]': 'price_1',
                        'line_items[0][quantity]': 1,
                    },
                ),
                appel('s', 'stripe_sessions_du_lien', payment_link='plink_1'),
                appel('r', 'stripe_rembourser', payment_intent='pi_1'),
                appel('x', 'stripe_desactiver_lien', id='plink_1'),
            )
        return self._json(
            {
                'paye': 'oui',
                'paiement': 'pi_1',
                'rembourse': 'oui',
                'compte_rendu': 'En vente sur calculatrice-pro.fr ; 1 € payé et rendu.',
            }
        )


class Etape5Tests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        secrets = self.dossier / 'config/secrets'
        secrets.mkdir(parents=True)
        for nom, valeur in (
            ('stripe-test.key', 'sk_test_faux'),
            ('stripe-live.key', 'sk_live_faux'),
            ('stripe-produits-live.key', 'rk_live_faux'),
            ('cloudflare-registrar.key', 'cf_registrar_faux'),
            ('cloudflare-infra.key', 'cf_infra_faux'),
        ):
            (secrets / nom).write_text(valeur + '\n')
        (secrets.parent / 'cloudflare-account-id').write_text('acct_test\n')
        instance = self.dossier / 'instance.toml'
        instance.write_text(
            '[identity]\npublic_hostname = "serge.exemple.fr"\n'
            f'[paths]\nconfig_root = "{self.dossier / "config"}"\n',
            encoding='utf-8',
        )
        env = {
            'SERGE_SYSTEM_ROOT': str(self.dossier),
            'SERGE_INSTANCE_FILE': str(instance),
            **faux_docker(self.dossier),
        }
        vrai = socket.getaddrinfo

        def resoudre(nom: str, *args: Any, **kwargs: Any) -> Any:
            # Le domaine de l'instance mène au serveur ; le reste est vrai.
            if nom == 'serge.exemple.fr':
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (IP, 0))]
            return vrai(nom, *args, **kwargs)

        for patcher in (
            mock.patch.dict(os.environ, env),
            mock.patch.object(publier, '_repond', return_value=True),
            mock.patch.object(caddy, 'reload', return_value=''),
            mock.patch.object(adresse.socket, 'getaddrinfo', resoudre),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        serveur = http.server.HTTPServer(('127.0.0.1', 0), _Services)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(serveur.shutdown)
        _Services.requetes = []
        _Services.pris = set()
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        self.conn.execute(
            'UPDATE api_services SET base_url=?',
            (f'http://127.0.0.1:{serveur.server_address[1]}',),
        )
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at')"
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _vider(self, modeles: FauxModeles) -> None:
        for _ in range(80):
            travaux = process_one(self.conn, 'works', caller=modeles)
            echanges = process_one(self.conn, 'conversations', caller=modeles)
            if travaux is None and echanges is None:
                return
        raise AssertionError('les files ne se vident pas')

    def _echecs(self) -> list[tuple]:
        return [
            tuple(r)
            for r in self.conn.execute(
                "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
            )
        ]

    def _repondre(self, sorte: str, acte: str, texte: str = '') -> None:
        ticket = self.conn.execute(
            'SELECT id FROM tickets WHERE type=? ORDER BY created_at DESC',
            (sorte,),
        ).fetchone()
        self.assertIsNotNone(ticket, f'pas de ticket {sorte}')
        # Comme le bouton de Mission Control : le ticket est tranché, puis
        # la réponse réveille les invocations.
        issue = (
            'APPROVED'
            if acte in APPROVE
            else 'REJECTED'
            if acte in REJECT
            else 'EDITED'
        )
        decide(self.conn, str(ticket[0]), issue, actor='owner', note=texte)
        noter_reponse(self.conn, str(ticket[0]), acte, texte, 'owner')
        self.conn.commit()

    def _un(self, sql: str, *args: Any) -> tuple:
        row = self.conn.execute(sql, args).fetchone()
        return tuple(row) if row is not None else ()

    def _env(self, conteneur: str) -> list[str]:
        etat = self.dossier / 'docker/containers' / conteneur / 'state.json'
        return json.loads(etat.read_text())['env']

    def _requetes(self, chemin: str) -> list[dict[str, Any]]:
        return [r for r in _Services.requetes if r['chemin'] == chemin]

    def _calculatrice(self, modeles: FauxModeles) -> str:
        self.assertIsNotNone(
            fire_button(self.conn, 'bouton_bout_en_bout_produit', {})
        )
        self.conn.commit()
        self._vider(modeles)
        return str(
            self._un(
                "SELECT id FROM ventures WHERE name='Calculatrice'"
                ' ORDER BY rowid DESC'
            )[0]
        )

    def test_le_produit_fini_d_une_calculatrice(self) -> None:
        modeles = FauxModeles(['calculatrice-pro.fr'])
        venture = self._calculatrice(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._un(
                'SELECT kind, status, domain, price FROM product_plans'
                " WHERE venture_id=? AND kind='product'",
                venture,
            ),
            ('product', 'challenged', 'calculatrice-pro.fr', '4 € par mois'),
        )
        etats = sorted(
            tuple(r)
            for r in self.conn.execute(
                "SELECT status, reason, plan_id <> '' FROM customer_requests"
                ' WHERE venture_id=?',
                (venture,),
            )
        )
        self.assertEqual(
            etats,
            [
                ('kept', 'Elle fait payer.', 1),
                ('new', '', 0),
                ('refused', 'Hors du produit.', 1),
            ],
        )
        # Le plan validé : Stripe en mode test, le chantier, le staging.
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        prix_test = self._requetes('/v1/prices')[0]
        self.assertEqual(prix_test['auth'], 'Bearer sk_test_faux')
        self.assertEqual(
            (
                prix_test['corps']['lookup_key'],
                prix_test['corps']['transfer_lookup_key'],
                prix_test['corps']['metadata[venture_id]'],
            ),
            (venture, 'true', venture),
        )
        self.assertIn(
            'STRIPE_SECRET_KEY=sk_test_faux',
            self._env(f'serge-chantier-{venture}-produit'),
        )
        self.assertEqual(
            self._un(
                'SELECT hostname, status FROM deployments'
                " WHERE venture_id=? AND target='staging'",
                venture,
            ),
            ('staging-calculatrice.serge.exemple.fr', 'running'),
        )
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures WHERE id=?', venture),
            ('PRODUCT_BUILDING',),
        )
        # Essayé et validé : le domaine, la vente, la prod, 1 €.
        self._repondre('TEST_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        # L'acheteur reçoit d'office l'adresse du serveur.
        self.assertIn(IP, json.dumps(modeles.par_role['acheter'][0]))
        # Acheté chez Cloudflare, un an, sans renouvellement automatique :
        # les valeurs figées partent avec leur type.
        achat = self._requetes('/accounts/acct_test/registrar/registrations')[
            0
        ]
        self.assertEqual(achat['auth'], 'Bearer cf_registrar_faux')
        self.assertEqual(
            achat['corps'],
            {
                'domain_name': 'calculatrice-pro.fr',
                'years': 1,
                'auto_renew': False,
            },
        )
        dns = self._requetes('/zones/zone_1/dns_records')[0]
        self.assertEqual(dns['auth'], 'Bearer cf_infra_faux')
        self.assertEqual(
            dns['corps'],
            {
                'name': 'calculatrice-pro.fr',
                'content': IP,
                'type': 'A',
                'ttl': 300,
                'proxied': False,
            },
        )
        prix_vrais = [
            r for r in self._requetes('/v1/prices') if 'live' in r['auth']
        ]
        self.assertEqual(prix_vrais[0]['corps']['lookup_key'], venture)
        self.assertEqual(
            self._un(
                'SELECT hostname, status FROM deployments'
                " WHERE venture_id=? AND target='prod'",
                venture,
            ),
            ('calculatrice-pro.fr', 'running'),
        )
        self.assertIn(
            'STRIPE_SECRET_KEY=rk_live_faux',
            self._env(f'serge-prod-{venture}-produit'),
        )
        rembourse = self._requetes('/v1/refunds')[0]
        self.assertEqual(
            (rembourse['auth'], rembourse['corps']['payment_intent']),
            ('Bearer sk_live_faux', 'pi_1'),
        )
        self.assertEqual(
            self._un(
                'SELECT kind, amount_eur, status FROM transactions'
                " WHERE intent_id='pi_1'"
            ),
            ('canary', 1.0, 'succeeded'),
        )
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures WHERE id=?', venture),
            ('PRODUCT_READY',),
        )
        self.assertTrue(
            self._un(
                "SELECT 1 FROM tickets WHERE title='Un produit est en vente'"
            )
        )
        fiche = project_fait_pipe(self.conn, 'venture', venture)
        assert fiche is not None
        titres = [c['titre'] for c in fiche['cadres']]
        self.assertIn('Les demandes des clients', titres)

    def test_un_domaine_pris_ouvre_le_ticket_domaine(self) -> None:
        _Services.pris = {'calculatrice-pro.fr'}
        modeles = FauxModeles(['calculatrice-pro.fr', 'calc-simple.fr'])
        self._calculatrice(modeles)
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        self._repondre('TEST_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._requetes('/accounts/acct_test/registrar/registrations'), []
        )
        self._repondre('DOMAINE_PRODUIT', 'a_corriger', 'calc-simple.fr')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertIn(
            'calc-simple.fr',
            json.dumps(modeles.par_role['acheter'][-1]),
        )
        self.assertEqual(
            self._requetes('/accounts/acct_test/registrar/registrations')[0][
                'corps'
            ]['domain_name'],
            'calc-simple.fr',
        )
        self.assertEqual(
            self._un("SELECT hostname FROM deployments WHERE target='prod'"),
            ('calc-simple.fr',),
        )

    def test_un_domaine_commun_evite_l_achat(self) -> None:
        # Le réglage « domaine commun des produits finis » (page Policy) :
        # pas d'achat, la prod sur un sous-domaine de ce domaine.
        self.conn.execute(
            "UPDATE invocation_settings SET value='produits.exemple.fr'"
            " WHERE invocation_id='choisir_domaine' AND name='domaine_commun'"
        )
        self.conn.commit()
        modeles = FauxModeles(['calculatrice-pro.fr'])
        venture = self._calculatrice(modeles)
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        self._repondre('TEST_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertNotIn('acheter', modeles.par_role)
        self.assertFalse(
            [
                r
                for r in _Services.requetes
                if r['chemin'].startswith('/accounts')
            ]
        )
        # Le sous-domaine du produit, et lui seul, pointe vers le serveur.
        dns = self._requetes('/zones/zone_1/dns_records')
        self.assertEqual(len(dns), 1)
        self.assertEqual(dns[0]['auth'], 'Bearer cf_infra_faux')
        self.assertEqual(
            (dns[0]['corps']['name'], dns[0]['corps']['content']),
            ('calculatrice.produits.exemple.fr', IP),
        )
        self.assertEqual(
            self._un(
                'SELECT hostname, status FROM deployments'
                " WHERE venture_id=? AND target='prod'",
                venture,
            ),
            ('calculatrice.produits.exemple.fr', 'running'),
        )
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures WHERE id=?', venture),
            ('PRODUCT_READY',),
        )

    def test_construire_le_vrai_produit_depuis_la_fiche(self) -> None:
        for ident, etat in (
            ('ven_pret', 'SMOKE_READY'),
            ('ven_neuf', 'CANDIDATE'),
        ):
            self.conn.execute(
                'INSERT INTO ventures(id, name, description, lifecycle,'
                ' created_at, updated_at) VALUES(?,?,?,?,?,?)',
                (
                    ident,
                    f'Devis {ident}',
                    'Des devis.',
                    etat,
                    utcnow(),
                    utcnow(),
                ),
            )
        self.conn.commit()
        fiche = project_fait_pipe(self.conn, 'venture', 'ven_pret')
        assert fiche is not None
        self.assertIn(
            'Construire le vrai produit',
            [a['libelle'] for a in fiche['actions']],
        )
        modeles = FauxModeles(['devis-pret.fr'])
        for ident in ('ven_pret', 'ven_neuf'):
            fire_button(
                self.conn, 'bouton_construire_produit', {'venture_id': ident}
            )
        self.conn.commit()
        self._vider(modeles)
        self.assertEqual(
            dict(
                self.conn.execute(
                    "SELECT id, lifecycle FROM ventures WHERE id LIKE 'ven_%'"
                ).fetchall()
            ),
            {'ven_pret': 'PRODUCT_BUILDING', 'ven_neuf': 'CANDIDATE'},
        )
        self.assertEqual(
            self._un(
                "SELECT COUNT(*) FROM product_plans WHERE kind='product'"
                " AND venture_id='ven_pret'"
            ),
            (1,),
        )
        self.assertEqual(len(modeles.par_role['concevoir']), 1)

    def test_sans_cle_restreinte_la_prod_rate(self) -> None:
        (self.dossier / 'config/secrets/stripe-produits-live.key').unlink()
        modeles = FauxModeles(['calculatrice-pro.fr'])
        venture = self._calculatrice(modeles)
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        self._repondre('TEST_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._un(
                "SELECT status FROM deployments WHERE target='prod'"
                ' AND venture_id=?',
                venture,
            ),
            ('failed',),
        )
        ticket = self._un(
            'SELECT title, payload_json FROM tickets WHERE title LIKE ?',
            '%pas pu passer en prod%',
        )
        self.assertIn('stripe-produits-live.key', ticket[1])
        self.assertNotIn('payer', modeles.par_role)
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures WHERE id=?', venture),
            ('PRODUCT_BUILDING',),
        )

    def test_l_adresse_du_serveur(self) -> None:
        self.assertEqual(
            adresse.server_address(self.conn, '', {}, 'x'),
            {'ok': True, 'hostname': 'serge.exemple.fr', 'ipv4': IP},
        )
        prive = [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.5', 0))]
        with mock.patch.object(
            adresse.socket, 'getaddrinfo', return_value=prive
        ):
            refus = adresse.server_address(self.conn, '', {}, 'x')
        self.assertEqual(refus['code'], 'adresse_privee')


if __name__ == '__main__':
    unittest.main()
