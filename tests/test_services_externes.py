#!/usr/bin/env python3
"""Les services externes gratuits d'un produit (décision Q118).

Les modèles sont des faux, le navigateur n'est pas ouvert : le geste qui
garde la clé est joué à la main. Le reste est réel : la capacité
« Brancher un service gratuit », les invocations du service, les
déclencheurs, les tickets, la base, le coffre.

Scénarios :
- un service que le plan validé nomme : la tâche qui le demande attend ;
  Serge ouvre son compte, le crée, va chercher la clé ; la tâche repart
  avec le nom de la variable, la clé est gardée chiffrée et part au
  produit ; un ticket prévient ;
- un service hors du plan : un ticket « Service » ; « Valider » lance le
  branchement, « Rejeter » fait repartir la tâche sans lui ;
- le compte ne peut pas être créé : la tâche repart avec la raison, et le
  service n'est pas redemandé ;
- les garde-fous : un nom ou une adresse mal écrits, le nombre de services
  par produit, un service dit branché sans clé gardée ;
- le geste « garder_cle » : la clé lue dans la page n'est jamais rendue.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge import product_services, web_accounts  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import (  # noqa: E402
    enqueue_task,
    freeze_task,
    task_params,
)
from serge.llm.client import ChatResult  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.sandbox import navigateur  # noqa: E402
from serge.sandbox.chantier import sandbox_command  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402

T = '2026-11-27T10:00:00+00:00'
CLE = 'ors_5b3ce3597851110001cf6248'
PLAN = (
    'Une page de calcul de tournées.\n'
    'openrouteservice | https://openrouteservice.org | calculer un trajet'
    ' | 2 000 requêtes par jour\n'
    'Voir aussi https://exemple-concurrent.fr pour comparer.'
)
DEMANDE = {
    'venture_id': 'v1',
    'deliverable': 'poc',
    'nom': 'openrouteservice',
    'adresse': 'https://openrouteservice.org',
    'besoin': 'Une clé pour calculer des trajets.',
}


class FauxModeles:
    """Celui qui crée le compte, et celui qui va chercher la clé (son
    geste « garder_cle » est joué par ``geste``)."""

    def __init__(self, cree: str = 'oui', obtenue: str = 'oui') -> None:
        self.cree, self.obtenue = cree, obtenue
        self.geste: Any = None
        self.vus: list[str] = []

    def __call__(self, _key, model, messages, tools=None, **_kw):
        system = messages[0]['content']
        if 'Tu crées le compte de Serge' in system:
            self.vus.append('compte')
            reponse = {
                'cree': self.cree,
                'identifiant': 'serge',
                'nom_public': 'Serge',
                'compte_rendu': 'Inscription faite.'
                if self.cree == 'oui'
                else 'Le site exige une carte bancaire.',
            }
        elif 'Tu vas chercher une clé' in system:
            self.vus.append('cle')
            if self.geste:
                self.geste()
            reponse = {
                'obtenue': self.obtenue,
                'offre': '2 000 requêtes par jour',
                'compte_rendu': 'Clé créée et gardée.',
            }
        else:
            raise AssertionError(f'prompt inattendu : {system[:80]}')
        return ChatResult(json.dumps(reponse), 10, 10, model, 1)


class ServicesTests(unittest.TestCase):
    def setUp(self) -> None:
        from cryptography.fernet import Fernet

        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        racine = Path(dossier.name)
        secrets = racine / 'config/secrets'
        secrets.mkdir(parents=True)
        (secrets / 'credential-vault.key').write_bytes(
            Fernet.generate_key() + b'\n'
        )
        instance = racine / 'instance.toml'
        instance.write_text(f'[paths]\nconfig_root = "{racine / "config"}"\n')
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_INSTANCE_FILE': str(instance),
                'SERGE_SYSTEM_ROOT': str(racine),
                **faux_docker(racine),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.executescript(
            f"""
            UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at');
            INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)
            VALUES('v1', 'Tournées', 'POC_SELECTED', '{T}', '{T}');
            """
        )
        self.conn.execute(
            'INSERT INTO product_plans(id, venture_id, kind, status, plan,'
            " created_at, updated_at) VALUES('pl1', 'v1', 'poc',"
            " 'validated', ?, ?, ?)",
            (PLAN, T, T),
        )
        self._valide_par('owner')
        set_heartbeat(self.conn, True)
        self.modeles = FauxModeles()
        # La tâche de construction qui demande le service, et qui attend.
        self.tache = str(
            enqueue_task(
                self.conn,
                'prevenir_service',
                {'titre': 'La construction', 'raison': 'reprise'},
            )
        )
        self.conn.commit()

    def _valide_par(self, qui: str) -> None:
        """La réponse « Valider » au ticket du plan : d'un humain
        (``owner``), ou du défaut du ticket après 48 heures (``serge``)."""
        self.conn.execute('DELETE FROM ticket_answers')
        self.conn.execute(
            'INSERT INTO ticket_answers(id, ticket_id, ticket_type, acte,'
            ' answered_by, ref_table, ref_id, venture_id, created_at)'
            " VALUES('ta1', 't1', 'PLAN_POC', 'valider', ?,"
            " 'product_plans', 'pl1', 'v1', ?)",
            (qui, T),
        )

    def _demander(self, **champs: str) -> dict[str, Any]:
        rendu = product_services.connect_service(
            self.conn,
            'brancher_service',
            {**DEMANDE, 'task_id': self.tache, **champs},
            'construire_poc',
        )
        if rendu.get('gel'):
            # Ce que fait la file quand un outil gèle la tâche.
            freeze_task(
                self.conn,
                self.tache,
                str(rendu['ticket_id']),
                str(rendu['attente']),
            )
        self.conn.commit()
        return rendu

    def _vider(self, sauf: str = '') -> None:
        """Fait tourner les files, sans la tâche de construction."""
        for _ in range(60):
            fait = []
            for file in ('works', 'conversations'):
                # Relancée, la tâche de construction ne tourne pas ici.
                self.conn.execute(
                    "UPDATE tasks SET not_before='2999' WHERE id=?",
                    (sauf or self.tache,),
                )
                fait.append(process_one(self.conn, file, caller=self.modeles))
            if not any(fait):
                return
        raise AssertionError('les files ne se vident pas')

    def _service(self, nom: str = 'openrouteservice') -> sqlite3.Row:
        return self.conn.execute(
            'SELECT * FROM product_services WHERE name=?', (nom,)
        ).fetchone()

    def _garder(self) -> None:
        refus = product_services.keep_key(
            self.conn, str(self._service()['id']), CLE
        )
        self.assertEqual(refus, '')

    def _reponse(self) -> str:
        return task_params(self.conn, self.tache).get('reponses_de_julien', '')

    def _statut(self) -> tuple[str, str]:
        row = self.conn.execute(
            'SELECT status, last_error FROM tasks WHERE id=?', (self.tache,)
        ).fetchone()
        return str(row[0]), str(row[1])

    def test_un_service_du_plan_se_branche(self) -> None:
        self.modeles.geste = self._garder
        rendu = self._demander()
        self.assertTrue(rendu['gel'])
        self.assertEqual(rendu['ticket_id'], '')
        self.assertEqual(
            self._statut(),
            (
                'blocked',
                'en attente du service « openrouteservice » (compte et clé'
                ' en cours)',
            ),
        )
        self.assertEqual(self._service()['status'], 'connecting')
        self._vider()
        self.assertEqual(self.modeles.vus, ['compte', 'cle'])
        service = self._service()
        self.assertEqual(
            (service['status'], service['free_plan'], service['reason']),
            ('connected', '2 000 requêtes par jour', ''),
        )
        # La clé est chiffrée en base, et part au produit par sa variable.
        self.assertNotIn(CLE, service['key_enc'])
        self.assertEqual(
            product_services.service_keys(self.conn, 'v1'),
            {'SERVICE_OPENROUTESERVICE_KEY': CLE},
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM web_accounts WHERE id='openrouteservice'"
            ).fetchone()[0],
            'active',
        )
        # La tâche de construction repart avec le nom de la variable.
        self.assertEqual(self._statut()[0], 'ready')
        self.assertIn('SERVICE_OPENROUTESERVICE_KEY', self._reponse())
        self.assertNotIn(CLE, self._reponse())
        self.assertEqual(
            self.conn.execute(
                "SELECT title FROM tickets WHERE type='FYI'"
            ).fetchone()[0],
            'Un service est branché : openrouteservice',
        )
        # Redemandé : il est déjà là, sans attendre.
        encore = self._demander()
        self.assertEqual(
            (encore.get('gel'), encore['variable']),
            (None, 'SERVICE_OPENROUTESERVICE_KEY'),
        )
        # Un second produit reprend le compte de Serge sur ce site.
        self.assertEqual(
            product_services.open_service_account(
                self.conn,
                'x',
                {
                    'account': 'openrouteservice',
                    'url': 'https://openrouteservice.org',
                },
                'ouvrir_compte_service',
            )['etat'],
            'actif',
        )

    def test_le_chantier_recoit_la_cle_sans_la_montrer(self) -> None:
        self.modeles.geste = self._garder
        self._demander()
        self._vider()

        def commande(texte: str) -> dict[str, Any]:
            return sandbox_command(
                self.conn,
                'chantier_commande',
                {
                    'venture_id': 'v1',
                    'deliverable': 'poc',
                    'profile': 'chantier',
                    'command': texte,
                },
                'construire_poc',
            )

        # La variable est là (sa longueur), sa valeur ne s'affiche pas.
        longueur = commande('printf %s "${#SERVICE_OPENROUTESERVICE_KEY}"')
        self.assertEqual(longueur['output'], str(len(CLE)), longueur)
        montree = commande('echo "cle=$SERVICE_OPENROUTESERVICE_KEY"')
        self.assertEqual(montree['output'], 'cle=••••')

    def test_un_service_hors_du_plan_attend_un_humain(self) -> None:
        self.modeles.geste = self._garder
        rendu = self._demander(
            nom='mapbox', adresse='https://exemple-concurrent.fr'
        )
        ticket = str(rendu['ticket_id'])
        self.assertTrue(rendu['gel'] and ticket)
        self.assertEqual(
            tuple(
                self.conn.execute(
                    'SELECT type, state, ref_table FROM tickets WHERE id=?',
                    (ticket,),
                ).fetchone()
            ),
            ('SERVICE', 'OPEN', 'product_services'),
        )
        self.assertEqual(self._service('mapbox')['status'], 'asked')
        self._vider()
        self.assertEqual(self.modeles.vus, [])
        noter_reponse(self.conn, ticket, 'rejeter', 'Trop intrusif.', 'owner')
        self.conn.commit()
        self._vider()
        self.assertEqual(
            (
                self._service('mapbox')['status'],
                self._service('mapbox')['reason'],
            ),
            ('refused', 'Trop intrusif.'),
        )
        self.assertEqual(self._statut()[0], 'ready')
        self.assertIn('n’a pas pu être branché', self._reponse())
        self.assertFalse(self._demander(nom='mapbox')['ok'])

    def test_un_plan_applique_tout_seul_n_autorise_aucun_compte(self) -> None:
        # Personne n'a répondu au ticket du plan : il s'est appliqué au
        # bout de 48 heures. Le service du plan demande alors un humain.
        self._valide_par('serge')
        rendu = self._demander()
        self.assertTrue(rendu['ticket_id'])
        self.assertEqual(self._service()['status'], 'asked')
        self._vider()
        self.assertEqual(self.modeles.vus, [])

    def test_valider_le_ticket_lance_le_branchement(self) -> None:
        rendu = self._demander(adresse='https://api.autre-service.io')
        self.modeles.geste = self._garder
        noter_reponse(
            self.conn, str(rendu['ticket_id']), 'valider', '', 'owner'
        )
        self.conn.commit()
        self._vider()
        self.assertEqual(self.modeles.vus, ['compte', 'cle'])
        self.assertEqual(self._service()['status'], 'connected')
        self.assertIn('est branché', self._reponse())

    def test_un_compte_impossible_fait_repartir_la_tache(self) -> None:
        self.modeles.cree = 'non'
        self._demander()
        self._vider()
        self.assertEqual(self.modeles.vus, ['compte'])
        service = self._service()
        self.assertEqual(service['status'], 'failed')
        self.assertIn('carte bancaire', service['reason'])
        self.assertEqual(self._statut()[0], 'ready')
        self.assertIn('carte bancaire', self._reponse())
        refus = self._demander()
        self.assertFalse(refus['ok'])
        self.assertIn('Fais sans lui', refus['detail'])

    def test_branche_sans_cle_gardee_n_est_pas_branche(self) -> None:
        # Le modèle dit « oui » sans avoir fait garder la clé.
        self._demander()
        self._vider()
        service = self._service()
        self.assertEqual(
            (service['status'], service['reason']),
            ('failed', 'la clé n’a pas été gardée'),
        )
        self.assertEqual(product_services.service_keys(self.conn, 'v1'), {})

    def test_les_garde_fous_de_la_demande(self) -> None:
        self.assertIn(
            'un mot en minuscules', self._demander(nom='Open Route')['detail']
        )
        self.assertIn(
            'https://',
            self._demander(adresse='http://openrouteservice.org')['detail'],
        )
        set_setting(self.conn, 'web_accounts.services_per_product', 0, 'test')
        self.assertIn('le maximum est 0', self._demander()['detail'])
        self.assertIsNone(self._service())
        self.assertEqual(
            product_services.planned_hosts(PLAN), {'openrouteservice.org'}
        )
        self.assertEqual(
            product_services.env_name('open-route_2'),
            'SERVICE_OPEN_ROUTE_2_KEY',
        )

    def test_garder_cle_ne_rend_jamais_la_cle(self) -> None:
        self._demander()
        service = str(self._service()['id'])

        class Element:
            def __init__(self, valeur: str) -> None:
                self.valeur = valeur
                self.first = self

            def evaluate(self, _js: str) -> str:
                return self.valeur

        class Session:
            masques: set[str] = set()

            def __init__(self, valeur: str) -> None:
                self.page = mock.Mock()
                self.page.locator.return_value = Element(valeur)

        court = Session('Copier')
        self.assertIn(
            'ne ressemble pas à une clé',
            navigateur._garder_cle(
                self.conn, court, {'service': service, 'ref': 'e3'}
            ),
        )
        session = Session(f'  {CLE}\n')
        self.assertEqual(
            navigateur._garder_cle(
                self.conn, session, {'service': service, 'ref': 'e3'}
            ),
            '',
        )
        self.assertIn(CLE, session.masques)
        self.assertEqual(web_accounts.unseal(self._service()['key_enc']), CLE)
        self.assertIn(
            'pas de service',
            navigateur._garder_cle(self.conn, session, {'ref': 'e3'}),
        )


if __name__ == '__main__':
    unittest.main()
