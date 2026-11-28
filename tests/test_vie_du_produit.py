#!/usr/bin/env python3
"""Faire vivre un produit fini en vente (lot 16, décision Q119).

Tout part d'une calculatrice en vente, construite comme à l'étape 5
(``tests/test_etape5.py``) : mêmes faux Docker, Stripe, Cloudflare et
Resend, et des modèles qui répondent d'avance.

Scénarios :
- le point de la semaine décide de corriger : la construction reprend
  avec ses consignes, et la correction part en prod dès que le relecteur
  la juge bonne, à la même adresse, sans essai humain, sans domaine, sans
  Stripe ni paiement test ; le point passe à « en ligne », les demandes
  retenues à « livrée », et deux tickets d'information préviennent ;
- une seule nouvelle version à la fois : un second point qui veut
  corriger pendant qu'une version est en cours ne lance rien ;
- le point du lundi ne visite pas le business d'un essai ; le bouton
  de la fiche d'un business le lance à la demande, et ne fait rien sans
  produit en vente ;
- le point décide de faire évoluer le produit (une offre de plus) et de
  relancer la prospection : le plan repasse par la conception, le critique
  et le ticket « Plan », Stripe reçoit le prix de la nouvelle offre en
  mode test puis en vrai mode (avec une clé de recherche au numéro du
  business), un humain essaie la nouvelle version, et elle part en prod
  sans racheter de domaine ; de nouvelles campagnes sont écrites ;
- un client signale un bug : le tri décide de le corriger, et seulement
  lui ; sa demande est retenue, puis livrée ; le bug d'un business qui
  n'a pas de produit en vente ne lance rien ;
- le verrou de préfixe : un modèle ne peut pas donner au prix d'une offre
  la clé d'un autre business ;
- une nouvelle version abandonnée (bouton de Mission Control) laisse la
  place à une autre ;
- un humain renvoie une correction en conception : elle devient une
  évolution, qu'un humain essaiera avant la prod ;
- une nouvelle version garde l'adresse du produit ; sans produit en prod,
  elle est refusée ;
- dans Mission Control, le bouton « Faire le point sur ce produit
  maintenant » de la fiche d'un business demande sa consigne, et elle
  part avec lui ;
- l'adresse de contact d'un produit : il la reçoit à sa publication, et
  un e-mail écrit à cette adresse par un inconnu devient le message d'un
  contact « entrant » de son business ; une réponse automatique non.
"""

from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.canaux import ensure_canaux  # noqa: E402
from serge.channels.auto_reply import AUTO_REPLY  # noqa: E402
from serge.channels.base import Incoming  # noqa: E402
from serge.conversations.receive import attach  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.store import utcnow  # noqa: E402
from serge.funnels.contacts import create_contact  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.interpreter.tools import run_tool  # noqa: E402
from serge.interpreter.triggers import (  # noqa: E402
    fire_button,
    fire_due_triggers,
    notify_rows_written,
)
from serge.llm.client import ChatResult  # noqa: E402
from serge.mc.proj_faits import project_fait_pipe  # noqa: E402
from serge.sandbox import courriel, publier  # noqa: E402
from tests import test_etape5  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402
from tests.test_etape5 import (  # noqa: E402
    FauxModeles,
    _plan_produit,
    appel,
)

CORRECTION = 'Le bouton « égal » ne répond pas sur mobile : corrige-le.'
EVOLUTION = 'Ajoute une offre Pro à 9 € par mois, avec l’export des calculs.'
RELANCE = 'Vise les comptables indépendants, par e-mail.'
ACHATS = '/accounts/acct_test/registrar/registrations'


class Modeles(FauxModeles):
    """Les modèles de l'étape 5, plus ceux qui font vivre le produit."""

    MARQUES = (
        *FauxModeles.MARQUES,
        ('Tu fais le point sur le produit fini', 'point'),
        ('a décidé de relancer sa prospection', 'relancer'),
        ('Tu prépares sa\nprospection lourde', 'lourde'),
        ('Un client signale un bug sur le produit fini', 'trier'),
    )

    def __init__(self) -> None:
        super().__init__(['calculatrice-pro.fr'])
        self.points: list[dict[str, Any]] = []
        self.offre_pro = False

    def _point(self, _messages, _outils) -> ChatResult:
        return self._json(self.points.pop(0))

    def _campagnes(self, raison: str) -> ChatResult:
        cible = {
            'canal': 'email',
            'cible': 'Des comptables.',
            'angle': 'Le prix.',
        }
        return self._json({'campagnes': [cible], 'compte_rendu': raison})

    def _lourde(self, _messages, _outils) -> ChatResult:
        return self._campagnes('Une campagne par e-mail.')

    def _relancer(self, _messages, _outils) -> ChatResult:
        return self._campagnes('Une nouvelle cible par e-mail.')

    def _trier(self, _messages, _outils) -> ChatResult:
        return self._json(
            {
                'decision': 'corriger',
                'consignes': 'Le total est faux après une division : corrige'
                ' seulement ça.',
                'raison': 'Un client voit un total faux ; on corrige.',
            }
        )

    def _concevoir(self, messages, outils) -> ChatResult:
        if not self.offre_pro:
            return super()._concevoir(messages, outils)
        plan = _plan_produit('calculatrice-pro.fr', [])
        plan['prix'] = '4 € par mois, ou 9 € par mois pour Pro'
        plan['offres'].append(
            {
                'code': 'pro',
                'nom': 'Pro',
                'principale': 'non',
                'prix_centimes': 900,
                'periode': 'month',
                'comprend': 'Tout Standard, plus l’export des calculs.',
            }
        )
        return self._json(plan)

    def _vendre(self, messages, outils) -> ChatResult:
        if not self.offre_pro:
            return super()._vendre(messages, outils)
        if outils == 0:
            venture = re.findall(r'ven_[0-9a-f]{12}', json.dumps(messages))[0]
            return self._outils(
                appel('l', 'stripe_lister_prix', product='prod_1'),
                appel(
                    'o',
                    'stripe_creer_prix_d_offre',
                    product='prod_1',
                    unit_amount=900,
                    currency='eur',
                    nickname='Pro',
                    lookup_key=f'{venture}_pro',
                    **{'recurring[interval]': 'month'},
                ),
            )
        return self._json(
            {'ok': 'oui', 'produit': 'prod_1', 'prix': 'price_1'}
        )


def _decision(produit: str, prospection: str = 'rien') -> dict[str, Any]:
    return {
        'produit': produit,
        'consignes_produit': {
            'corriger': CORRECTION,
            'faire_evoluer': EVOLUTION,
        }.get(produit, ''),
        'prospection': prospection,
        'consignes_prospection': RELANCE if prospection == 'relancer' else '',
        'compte_rendu': f'Aucune vente cette semaine : {produit}.',
    }


class VieDuProduitTests(test_etape5.Etape5Tests):
    # Les scénarios de l'étape 5 ont leur fichier : ils ne sont pas rejoués.
    test_le_produit_fini_d_une_calculatrice = None  # type: ignore[assignment]
    test_revoir_le_plan_du_produit_renvoie_a_la_conception = None  # type: ignore[assignment]
    test_un_domaine_pris_ouvre_le_ticket_domaine = None  # type: ignore[assignment]
    test_le_verrou_de_prix_tient_meme_si_le_modele_desobeit = None  # type: ignore[assignment]
    test_un_domaine_commun_evite_l_achat = None  # type: ignore[assignment]
    test_l_essai_total_a_partir_de_l_etape_5 = None  # type: ignore[assignment]
    test_un_essai_n_achete_jamais_de_domaine = None  # type: ignore[assignment]
    test_sans_cle_restreinte_la_prod_rate = None  # type: ignore[assignment]
    test_sans_domaine_d_envoi_la_prod_rate = None  # type: ignore[assignment]
    test_l_adresse_du_serveur = None  # type: ignore[assignment]

    def _en_vente(self, modeles: Modeles) -> str:
        """La calculatrice, de son plan à sa mise en vente (étape 5)."""
        venture = self._calculatrice(modeles)
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        self._repondre('TEST_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures WHERE id=?', venture),
            ('PRODUCT_READY',),
        )
        # La prospection tourne : la prospection lourde se prépare.
        self.conn.execute(
            'UPDATE pipeline_steps SET enabled=1 WHERE id IN'
            " ('prospection_light', 'prospection_lourde')"
        )
        self.conn.commit()
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        return venture

    def _point(self, modeles: Modeles, decision: dict[str, Any]) -> None:
        """Le déclencheur du lundi matin fait le point sur chaque produit
        en vente."""
        modeles.points.append(decision)
        self.conn.execute(
            "UPDATE triggers SET enabled=1, last_fired_at='' WHERE id IN"
            " ('point_de_la_semaine', 'point_de_la_semaine_sans_campagne')"
        )
        # Un lundi à 9 heures, heure de Paris ; le suivant à chaque appel.
        self.semaine = getattr(self, 'semaine', 0) + 1
        lundi = datetime(
            2026, 11, 23, 9, 0, tzinfo=ZoneInfo('Europe/Paris')
        ) + timedelta(days=7 * (self.semaine - 1))
        fire_due_triggers(self.conn, lundi.isoformat())
        self.conn.commit()
        self._vider(modeles)

    def _points(self, venture: str) -> list[tuple]:
        return [
            tuple(r)
            for r in self.conn.execute(
                'SELECT cause, product_action, prospecting_action,'
                ' version_status, version FROM product_reviews'
                ' WHERE venture_id=? ORDER BY rowid',
                (venture,),
            )
        ]

    def _tickets(self, sorte: str) -> int:
        return int(
            self._un('SELECT COUNT(*) FROM tickets WHERE type=?', sorte)[0]
        )

    def _prod(self, venture: str) -> tuple:
        return self._un(
            'SELECT hostname, version, status FROM deployments'
            " WHERE venture_id=? AND target='prod' AND deliverable='produit'",
            venture,
        )

    def test_le_point_de_la_semaine_corrige_le_produit(self) -> None:
        modeles = Modeles()
        venture = self._en_vente(modeles)
        self.assertEqual(
            self._prod(venture), ('calculatrice-pro.fr', 1, 'running')
        )
        ventes_stripe = len(modeles.par_role['vendre'])
        self._point(modeles, _decision('corriger'))
        self.assertEqual(self._echecs(), [])
        # Le point a tout reçu, et le constructeur a ses consignes.
        recu = json.dumps(modeles.par_role['point'][0], ensure_ascii=False)
        for titre in ('Les ventes', 'Les offres', 'Les demandes des clients'):
            self.assertIn(titre, recu)
        self.assertIn(
            CORRECTION,
            json.dumps(modeles.par_role['construire'][-1], ensure_ascii=False),
        )
        # La correction est en prod à la même adresse : ni essai humain, ni
        # domaine, ni Stripe, ni second paiement test.
        self.assertEqual(
            self._prod(venture), ('calculatrice-pro.fr', 2, 'running')
        )
        self.assertEqual(self._tickets('TEST_PRODUIT'), 1)
        self.assertEqual(len(self._requetes(ACHATS)), 1)
        self.assertEqual(len(self._requetes('/v1/refunds')), 1)
        self.assertEqual(len(modeles.par_role['vendre']), ventes_stripe)
        self.assertEqual(
            self._points(venture),
            [('semaine', 'corriger', 'rien', 'online', '2')],
        )
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures WHERE id=?', venture),
            ('PRODUCT_READY',),
        )
        # La demande que le plan avait retenue est livrée, avec la version.
        self.assertEqual(
            self._un(
                'SELECT status, delivered_version FROM customer_requests'
                " WHERE venture_id=? AND reason='Elle fait payer.'",
                venture,
            ),
            ('delivered', 2),
        )
        for titre, texte in (
            ('Le point de la semaine sur un produit en vente', 'corriger'),
            ("Une nouvelle version d'un produit est en ligne", CORRECTION),
        ):
            ticket = self._un(
                'SELECT payload_json FROM tickets WHERE title=?', titre
            )
            self.assertTrue(ticket, titre)
            self.assertIn(texte, json.loads(ticket[0])['contenu'])
        # Le point suivant ne décide rien : il est gardé, sans version.
        self._point(modeles, _decision('rien'))
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._points(venture)[1], ('semaine', 'rien', 'rien', 'none', '')
        )
        self.assertIn(
            'Aucune vente cette semaine : corriger',
            json.dumps(modeles.par_role['point'][1], ensure_ascii=False),
        )
        self.assertEqual(self._prod(venture)[1], 2)

    def test_une_seule_nouvelle_version_a_la_fois(self) -> None:
        modeles = Modeles()
        venture = self._en_vente(modeles)
        constructions = len(modeles.par_role['construire'])
        maintenant = utcnow()
        self.conn.execute(
            'INSERT INTO product_reviews(id, venture_id, product_action,'
            " version_status, created_at, updated_at) VALUES('pro_en_cours',"
            " ?, 'faire_evoluer', 'open', ?, ?)",
            (venture, maintenant, maintenant),
        )
        self._point(modeles, _decision('corriger', 'relancer'))
        self.assertEqual(self._echecs(), [])
        # Rien n'est lancé pour le produit ; la relance, elle, part.
        self.assertEqual(len(modeles.par_role['construire']), constructions)
        self.assertEqual(
            self._points(venture),
            [('semaine', 'faire_evoluer', 'rien', 'open', '')],
        )
        self.assertEqual(len(modeles.par_role['relancer']), 1)
        # Abandonnée depuis Mission Control, elle laisse la place.
        self.assertIsNotNone(
            fire_button(
                self.conn, 'bouton_abandonner_version', {'venture_id': venture}
            )
        )
        self.conn.commit()
        self._vider(modeles)
        self.assertEqual(self._points(venture)[0][3], 'dropped')
        self._point(modeles, _decision('corriger'))
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._points(venture)[1],
            ('semaine', 'corriger', 'rien', 'online', '2'),
        )

    def test_le_point_du_lundi_laisse_les_essais_au_bouton(self) -> None:
        modeles = Modeles()
        venture = self._en_vente(modeles)
        # Le lundi ne visite pas le business d'un essai…
        self.conn.execute('UPDATE ventures SET trial=1 WHERE id=?', (venture,))
        self._point(modeles, _decision('rien'))
        self.assertEqual(self._points(venture), [])
        self.assertNotIn('point', modeles.par_role)

        consigne = 'C’est un essai : ne change rien.'
        # Le champ du formulaire porte son libellé, comme dans Mission
        # Control.
        champ = self._un(
            "SELECT value FROM trigger_params WHERE param_name='consigne'"
            " AND trigger_id='bouton_faire_le_point'"
        )[0]

        def bouton() -> None:
            self.assertIsNotNone(
                fire_button(
                    self.conn,
                    'bouton_faire_le_point',
                    {'venture_id': venture, champ: consigne},
                )
            )
            self.conn.commit()
            self._vider(modeles)
            self.assertEqual(self._echecs(), [])

        # … le bouton de sa fiche le lance à la demande.
        bouton()
        self.assertEqual(
            self._points(venture), [('semaine', 'rien', 'rien', 'none', '')]
        )
        # La consigne de l'humain arrive au modèle.
        self.assertIn(
            consigne,
            json.dumps(modeles.par_role['point'][0], ensure_ascii=False),
        )
        # Sans produit en vente, le bouton ne fait rien.
        self.conn.execute(
            "UPDATE ventures SET lifecycle='SMOKE_RUNNING' WHERE id=?",
            (venture,),
        )
        bouton()
        self.assertEqual(len(self._points(venture)), 1)
        self.assertEqual(len(modeles.par_role['point']), 1)

    def test_le_point_fait_evoluer_le_produit_avec_une_offre_de_plus(
        self,
    ) -> None:
        modeles = Modeles()
        venture = self._en_vente(modeles)
        campagnes = int(
            self._un(
                'SELECT COUNT(*) FROM campaigns WHERE venture_id=?', venture
            )[0]
        )
        modeles.offre_pro = True
        self._point(modeles, _decision('faire_evoluer', 'relancer'))
        self.assertEqual(self._echecs(), [])
        # Le plan repart en conception avec les consignes et le plan déjà
        # construit, puis attend un humain : rien n'est encore construit.
        conception = json.dumps(
            modeles.par_role['concevoir'][-1], ensure_ascii=False
        )
        self.assertIn(EVOLUTION, conception)
        self.assertIn('déjà construit', conception)
        self.assertEqual(self._tickets('PLAN_PRODUIT'), 2)
        self.assertEqual(self._prod(venture)[1], 1)
        self.assertEqual(
            sorted(
                tuple(r)
                for r in self.conn.execute(
                    'SELECT code, main, amount_cents, interval FROM'
                    ' product_offers WHERE venture_id=?',
                    (venture,),
                )
            ),
            [('pro', 'non', 900, 'month'), ('standard', 'oui', 400, 'month')],
        )
        # La relance : une nouvelle campagne lourde, prête.
        self.assertIn(
            RELANCE,
            json.dumps(modeles.par_role['relancer'][0], ensure_ascii=False),
        )
        self.assertEqual(
            int(
                self._un(
                    'SELECT COUNT(*) FROM campaigns WHERE venture_id=?',
                    venture,
                )[0]
            ),
            campagnes + 1,
        )
        # Le plan validé : Stripe en mode test, la construction, le
        # staging, puis l'essai d'un humain (c'est une évolution).
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        offre_test = self._requetes('/v1/prices')[-1]
        self.assertEqual(offre_test['auth'], 'Bearer sk_test_faux')
        self.assertEqual(
            (
                offre_test['corps']['lookup_key'],
                offre_test['corps']['transfer_lookup_key'],
                offre_test['corps']['metadata[venture_id]'],
                offre_test['corps']['unit_amount'],
            ),
            (f'{venture}_pro', 'true', venture, '900'),
        )
        self.assertEqual(self._tickets('TEST_PRODUIT'), 2)
        self.assertEqual(self._prod(venture)[1], 1)
        # Essayée et validée : Stripe en vrai mode, puis la prod, à la
        # même adresse. Ni domaine, ni paiement test, ni nouvelle
        # prospection lourde.
        self._repondre('TEST_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        offre_vraie = self._requetes('/v1/prices')[-1]
        self.assertEqual(offre_vraie['auth'], 'Bearer sk_live_faux')
        self.assertEqual(offre_vraie['corps']['lookup_key'], f'{venture}_pro')
        self.assertEqual(
            self._prod(venture), ('calculatrice-pro.fr', 2, 'running')
        )
        self.assertEqual(len(self._requetes(ACHATS)), 1)
        self.assertEqual(len(self._requetes('/v1/refunds')), 1)
        self.assertEqual(len(modeles.par_role['lourde']), 1)
        self.assertEqual(
            self._points(venture),
            [('semaine', 'faire_evoluer', 'relancer', 'online', '2')],
        )
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures WHERE id=?', venture),
            ('PRODUCT_READY',),
        )

    def _bug(self, venture: str, numero: str) -> None:
        """Un client signale un bug, comme le note « Traiter une réponse »."""
        client = create_contact(
            self.conn, venture, 'Un client', email=f'{numero}@atelier.fr'
        )
        self.conn.execute(
            'INSERT INTO customer_requests(id, venture_id, contact_id, kind,'
            " text, created_at, status) VALUES(?, ?, ?, 'bug', ?, ?, 'new')",
            (
                numero,
                venture,
                client,
                'Le total est faux après une division.',
                utcnow(),
            ),
        )
        notify_rows_written(self.conn, 'customer_requests', [numero])
        self.conn.commit()

    def test_un_bug_signale_est_corrige_et_rien_d_autre(self) -> None:
        modeles = Modeles()
        venture = self._en_vente(modeles)
        self._bug(venture, 'cus_bug000000001')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertIn(
            'Le total est faux après une division.',
            json.dumps(modeles.par_role['trier'][0], ensure_ascii=False),
        )
        self.assertIn(
            'corrige seulement ça',
            json.dumps(modeles.par_role['construire'][-1], ensure_ascii=False),
        )
        self.assertEqual(
            self._points(venture), [('bug', 'corriger', 'rien', 'online', '2')]
        )
        self.assertEqual(self._prod(venture)[1], 2)
        self.assertEqual(self._tickets('TEST_PRODUIT'), 1)
        self.assertEqual(
            self._un(
                'SELECT status, delivered_version FROM customer_requests'
                " WHERE id='cus_bug000000001'"
            ),
            ('delivered', 2),
        )
        self.assertTrue(
            self._un(
                'SELECT 1 FROM tickets WHERE title=?',
                'Un client a signalé un bug sur un produit en vente',
            )
        )
        # Le bug d'un business sans produit en vente ne lance rien.
        self.conn.execute(
            "UPDATE ventures SET lifecycle='SMOKE_RUNNING' WHERE id=?",
            (venture,),
        )
        self._bug(venture, 'cus_bug000000002')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(len(modeles.par_role['trier']), 1)
        self.assertEqual(
            self._un(
                "SELECT status FROM customer_requests WHERE id='cus_bug000000002'"
            ),
            ('new',),
        )

    def test_une_correction_renvoyee_en_conception_devient_une_evolution(
        self,
    ) -> None:
        modeles = Modeles()
        venture = self._en_vente(modeles)
        maintenant = utcnow()
        self.conn.execute(
            'INSERT INTO product_reviews(id, venture_id, product_action,'
            " version_status, created_at, updated_at) VALUES('pro_correction',"
            " ?, 'corriger', 'open', ?, ?)",
            (venture, maintenant, maintenant),
        )
        build = self._un(
            'SELECT id FROM builds WHERE venture_id=? ORDER BY rowid DESC',
            venture,
        )[0]
        # Un humain, au ticket de test de cette correction, demande de
        # revoir le plan.
        enqueue_task(
            self.conn,
            'suite_test_produit',
            {
                'acte': 'revoir_plan',
                'texte': 'Il faut aussi un export.',
                'build_id': build,
                'venture_id': venture,
            },
            origin='trigger',
            origin_ref='essai:revoir',
        )
        self.conn.commit()
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._points(venture),
            [('semaine', 'faire_evoluer', 'rien', 'open', '')],
        )
        self.assertEqual(self._tickets('PLAN_PRODUIT'), 2)
        # Validée, construite et relue : un humain l'essaie avant la prod.
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(self._tickets('TEST_PRODUIT'), 2)
        self.assertEqual(self._prod(venture)[1], 1)

    def test_une_nouvelle_version_garde_l_adresse_et_recoit_son_contact(
        self,
    ) -> None:
        modeles = Modeles()
        venture = self._calculatrice(modeles)
        self._repondre('PLAN_PRODUIT', 'valider')
        self._vider(modeles)
        republier = {
            'venture_id': venture,
            'deliverable': 'produit',
            'target': 'prod',
            'same_address': 'oui',
        }
        # Pas encore en prod : aucune adresse à garder.
        refus = publier.publish_version(self.conn, '', dict(republier), 'test')
        self.assertEqual((refus['ok'], refus['code']), (False, 'pas_en_prod'))
        # Un POC publié ne reçoit pas d'adresse de contact : seule la
        # publication d'un produit fini la demande.
        self.assertEqual(
            sorted(
                tuple(r)
                for r in self.conn.execute(
                    'SELECT i.id, p.value FROM invocations i JOIN'
                    ' invocation_tool_params p ON p.invocation_id=i.id'
                    " AND p.invocation_tool_id=0 AND p.param_name='contact'"
                    " WHERE i.capability_id='publish_version'"
                )
            ),
            [
                ('publier_prod_produit', 'oui'),
                ('publier_prod_version', 'oui'),
                ('publier_staging_produit', 'oui'),
            ],
        )
        identite = {'email': 'serge@exemple.fr'}
        with mock.patch.object(
            courriel, 'identite_serge', return_value=identite
        ):
            self._repondre('TEST_PRODUIT', 'valider')
            self._vider(modeles)
            self.assertEqual(self._echecs(), [])
            # En prod, le produit connaît son adresse de contact, et la
            # base la garde pour rattacher les e-mails qui lui sont écrits.
            contact = 'serge+calculatrice@exemple.fr'
            self.assertIn(
                f'CONTACT_EMAIL={contact}',
                self._env(f'serge-prod-{venture}-produit'),
            )
            self.assertEqual(
                self._un(
                    'SELECT contact_email FROM deployments WHERE id=?',
                    f'prod-{venture}-produit',
                ),
                (contact,),
            )
            republier['env_secrets'] = (
                'STRIPE_SECRET_KEY=stripe-produits-live.key'
            )
            encore = publier.publish_version(
                self.conn, '', dict(republier), 'test'
            )
        self.assertTrue(encore['ok'], encore)
        self.assertEqual(encore['url'], 'https://calculatrice-pro.fr')

    def test_la_cle_du_prix_d_une_offre_porte_le_numero_du_business(
        self,
    ) -> None:
        lien = self._un(
            "SELECT id FROM invocation_tools WHERE invocation_id='mettre_en_vente'"
            " AND tool_id='stripe_creer_prix_d_offre'"
        )[0]

        def creer(cle: str) -> dict[str, Any]:
            return run_tool(
                self.conn,
                'mettre_en_vente',
                lien,
                'stripe_creer_prix_d_offre',
                {
                    'product': 'prod_1',
                    'unit_amount': 900,
                    'currency': 'eur',
                    'recurring[interval]': 'month',
                    'lookup_key': cle,
                },
                {'task_id': 't1', 'venture_id': 'ven_12'},
            )

        for cle in ('ven_13_pro', 'ven_12', 'ven_12_', 'pro'):
            with redirect_stderr(io.StringIO()) as journal:
                refus = creer(cle)
            self.assertEqual(refus['code'], 'verrou', cle)
            self.assertIn('verrou de préfixe', journal.getvalue())
        self.assertEqual(self._requetes('/v1/prices'), [])
        self.assertTrue(creer('ven_12_pro')['ok'])
        corps = self._requetes('/v1/prices')[0]['corps']
        self.assertEqual(
            (corps['lookup_key'], corps['metadata[venture_id]']),
            ('ven_12_pro', 'ven_12'),
        )


class AdresseDeContactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        ensure_canaux(self.conn)
        maintenant = utcnow()
        self.conn.execute(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('ven_calcu', 'CalcuDevis', 'FULL_RUNNING', ?, ?)",
            (maintenant, maintenant),
        )
        self.conn.execute(
            'INSERT INTO deployments(id, venture_id, deliverable, target,'
            ' version, image, container, host_port, hostname, status,'
            ' created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                'prod-ven_calcu-produit',
                'ven_calcu',
                'produit',
                'prod',
                1,
                'image',
                'conteneur',
                18001,
                'calcudevis.exemple.fr',
                'running',
                maintenant,
                maintenant,
            ),
        )

    def _message(
        self, de: str, a: str, sorte: str = 'email'
    ) -> dict[str, Any]:
        return attach(
            self.conn,
            'email',
            Incoming(
                external_ref=f'ref-{de}-{a}-{sorte}',
                address=de,
                subject='Une question',
                body='Bonjour, comment exporter mes devis ?',
                native_type=sorte,
                to=(a,),
            ),
        )

    def test_un_e_mail_a_l_adresse_du_produit_est_rattache(self) -> None:
        identite = {'email': 'Serge.IA@exemple.fr'}
        with mock.patch.object(
            courriel, 'identite_serge', return_value=identite
        ):
            self.assertEqual(
                courriel.contact_du_produit('calcudevis'),
                'serge.ia+calcudevis@exemple.fr',
            )
        contact = 'serge.ia+calcudevis@exemple.fr'
        courriel.noter_contact(self.conn, 'prod-ven_calcu-produit', contact)
        # Un inconnu écrit à l'adresse du produit : un contact entrant.
        recu = self._message('Client@Atelier.fr', contact)
        self.assertEqual(
            (recu['status'], recu['venture_id']), ('attached', 'ven_calcu')
        )
        self.assertEqual(
            tuple(
                self.conn.execute(
                    'SELECT c.venture_id, c.regime, a.value_norm FROM contacts c'
                    ' JOIN contact_addresses a ON a.contact_id=c.id'
                    ' WHERE c.id=?',
                    (recu['contact_id'],),
                ).fetchone()
            ),
            ('ven_calcu', 'INBOUND', 'client@atelier.fr'),
        )
        # Son message suivant retrouve sa fiche, par son adresse.
        encore = self._message('client@atelier.fr', contact)
        self.assertEqual(encore['contact_id'], recu['contact_id'])
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0], 1
        )
        # Une réponse automatique, ou un e-mail écrit ailleurs, ne crée
        # pas de contact : il reste non rattaché.
        for de, a, sorte in (
            ('robot@atelier.fr', contact, AUTO_REPLY),
            ('autre@atelier.fr', 'serge.ia@exemple.fr', 'email'),
            ('autre@atelier.fr', 'serge.ia+inconnu@exemple.fr', 'email'),
        ):
            self.assertEqual(
                self._message(de, a, sorte)['status'], 'unattached'
            )
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0], 1
        )
        # Sans boîte e-mail, un produit n'a pas d'adresse de contact.
        with mock.patch.object(
            courriel, 'identite_serge', return_value={'email': ''}
        ):
            self.assertEqual(courriel.contact_du_produit('calcudevis'), '')


class BoutonDuPointTests(McBrowserCase):
    """Sur la fiche d'un business, dans Mission Control, le bouton « Faire
    le point sur ce produit maintenant » demande sa consigne."""

    def _base(self, sql: str, *args: Any) -> list[tuple]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(sql, args).fetchall()
            conn.commit()
            return rows
        finally:
            conn.close()

    def test_la_consigne_part_avec_le_bouton(self) -> None:
        from playwright.sync_api import expect

        maintenant = utcnow()
        self._base(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('ven_calcu', 'CalcuDevis', 'FULL_RUNNING', ?, ?)",
            maintenant,
            maintenant,
        )
        bouton = 'Faire le point sur ce produit maintenant'
        consigne = 'Ajoute une offre Pro à 9 € par mois.'
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/objet/venture/ven_calcu')
        page.get_by_role('button', name=bouton).click()
        modale = page.locator('.modale')
        expect(modale).to_contain_text('Avec une consigne', timeout=10000)
        modale.locator('textarea').fill(consigne)
        modale.get_by_role('button', name=bouton).click()
        expect(page.locator('body')).to_contain_text('fait.', timeout=10000)
        self.assertEqual(
            self._base(
                'SELECT p.name, p.value FROM tasks t JOIN task_params p'
                " ON p.task_id=t.id WHERE t.invocation_id='point_a_la_demande'"
                ' ORDER BY p.name'
            ),
            [('consigne', consigne), ('venture_id', 'ven_calcu')],
        )
        # Un bouton sans autre champ garde sa simple confirmation.
        fiche = project_fait_pipe(
            sqlite3.connect(self.db_path), 'venture', 'ven_calcu'
        )
        assert fiche is not None
        champs = {a['libelle']: a.get('champs') for a in fiche['actions']}
        self.assertEqual(len(champs[bouton]), 1)
        self.assertEqual(champs['Supprimer de Stripe (mode test)'], [])


if __name__ == '__main__':
    unittest.main()
