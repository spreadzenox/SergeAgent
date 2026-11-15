#!/usr/bin/env python3
"""Les e-mails des produits (lot 11, Q96).

La boîte d'essai (Mailpit), Resend et Docker sont des faux : un serveur
local répond comme Mailpit et comme Resend, et un faux ``docker`` note ses
conteneurs. La base, la policy, « Appeler une API », la capacité « Ma boîte
e-mail » et la fiche du business dans Mission Control sont réels.

Scénarios :
- le relecteur a une adresse par essai, et lit ses e-mails dans la boîte
  d'essai (staging) comme chez Resend (prod), avec leurs liens ;
- sans e-mail, il le sait tout de suite s'il ne veut pas attendre ;
- la clé d'envoi d'un produit est créée une seule fois, rangée à part,
  jamais rendue au modèle ; un refus de Resend est dit clairement ;
- sans domaine d'envoi, rien ne passe en prod ;
- la boîte d'essai ne s'ouvre qu'au réseau des chantiers et à la machine ;
- la fiche du business montre les e-mails envoyés par son staging.
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

from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.mc.proj_produit import cadres_produit  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.sandbox import courriel  # noqa: E402
from serge.sandbox.docker import DockerError  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402

LIEN = 'https://staging-calcu-devis.serge.exemple.fr/valider?jeton=abc'


class _Boites(http.server.BaseHTTPRequestHandler):
    """Mailpit (``/api/v1``) et Resend, à une seule adresse."""

    mailpit: list[dict[str, Any]] = []
    recus: list[dict[str, Any]] = []
    cles: list[dict[str, Any]] = []
    refuser_cle = False

    def _envoyer(self, statut: int, corps: Any) -> None:
        data = json.dumps(corps).encode()
        self.send_response(statut)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 — le nom de http.server
        chemin = urllib.parse.urlsplit(self.path)
        query = dict(urllib.parse.parse_qsl(chemin.query))
        if chemin.path == '/api/v1/search':
            cherche = query['query']
            trouves = [
                m
                for m in self.mailpit
                if (
                    cherche.startswith('to:')
                    and cherche[3:].strip('"') == m['To'][0]['Address']
                )
                or (
                    cherche.startswith('from:')
                    and m['From']['Address'].startswith(cherche[5:])
                )
            ]
            self._envoyer(200, {'messages': trouves})
        elif chemin.path.startswith('/api/v1/message/'):
            ident = chemin.path.rsplit('/', 1)[-1]
            m = next(m for m in self.mailpit if m['ID'] == ident)
            self._envoyer(200, {'Text': m['texte'], 'HTML': m['page']})
        elif chemin.path == '/emails/receiving':
            self._envoyer(200, {'object': 'list', 'data': self.recus})
        elif chemin.path.startswith('/emails/receiving/'):
            ident = chemin.path.rsplit('/', 1)[-1]
            self._envoyer(
                200,
                {
                    'id': ident,
                    'text': None,
                    'html': f'<p>Votre reçu</p><a href="{LIEN}">ici</a>',
                },
            )
        else:
            self._envoyer(404, {'message': 'inconnu'})

    def do_POST(self) -> None:  # noqa: N802 — le nom de http.server
        longueur = int(self.headers.get('Content-Length') or 0)
        corps = json.loads(self.rfile.read(longueur) or b'{}')
        self.cles.append(corps)
        if self.refuser_cle:
            self._envoyer(403, {'message': 'API key is invalid'})
        else:
            self._envoyer(201, {'id': 'cle_1', 'token': 're_produit_secret'})

    def log_message(self, *_args: Any) -> None:
        pass


class CourrielTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        self.secrets = self.dossier / 'config/secrets'
        self.secrets.mkdir(parents=True)
        (self.secrets / 'resend.key').write_text('re_maitresse\n')
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
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        serveur = http.server.HTTPServer(('127.0.0.1', 0), _Boites)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        self.addCleanup(serveur.shutdown)
        port = serveur.server_address[1]
        _Boites.mailpit, _Boites.recus, _Boites.cles = [], [], []
        _Boites.refuser_cle = False
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        self.conn.execute(
            "UPDATE api_services SET base_url=? WHERE id='resend'",
            (f'http://127.0.0.1:{port}',),
        )
        for ident, valeur in (
            ('courriel.domaine_envoi', 'envoi.exemple.fr'),
            ('courriel.boite_relecteur', 'relecteur.exemple.fr'),
            ('sandbox.boite.port', port),
        ):
            self.assertEqual(set_setting(self.conn, ident, valeur, 'test'), '')
        self.conn.commit()

    def _dans_la_boite(self, de: str, a: str, objet: str) -> None:
        _Boites.mailpit.append(
            {
                'ID': f'm{len(_Boites.mailpit)}',
                'From': {'Address': de},
                'To': [{'Address': a}],
                'Subject': objet,
                'Created': '2026-11-15T16:00:00Z',
                'texte': f'Bonjour,\nValidez votre compte : {LIEN}\n',
                'page': '',
            }
        )

    def test_le_relecteur_lit_ses_emails_d_essai_et_de_prod(self) -> None:
        adresse = courriel.adresse_relecteur(self.conn, 't_2bb7de2909c50f7f')
        self.assertEqual(
            adresse, 'relecteur-2bb7de2909c5@relecteur.exemple.fr'
        )
        self._dans_la_boite(
            'calcu-devis@envoi.exemple.fr', adresse, 'Validez votre compte'
        )
        self._dans_la_boite(
            'calcu-devis@envoi.exemple.fr', 'autre@exemple.fr', 'Pas pour lui'
        )
        _Boites.recus = [
            {
                'id': 'r1',
                'to': [adresse],
                'from': 'receipts@stripe.com',
                'subject': 'Votre reçu',
                'created_at': '2026-11-15 16:01:00',
            },
            {'id': 'r2', 'to': ['quelquun@exemple.fr'], 'subject': 'Non'},
        ]
        resultat = courriel.boite_relecteur(
            self.conn, 'boite_mail', {'task_id': 't_2bb7de2909c50f7f'}, 'x'
        )
        self.assertTrue(resultat['ok'])
        self.assertEqual(resultat['adresse'], adresse)
        self.assertEqual(
            [(m['objet'], m['liens']) for m in resultat['messages']],
            [('Validez votre compte', [LIEN]), ('Votre reçu', [LIEN])],
        )
        self.assertIn('Votre reçu', resultat['messages'][1]['texte'])

    def test_sans_email_il_le_sait_tout_de_suite(self) -> None:
        resultat = courriel.boite_relecteur(
            self.conn, 'boite_mail', {'task_id': 't_1', 'wait': False}, 'x'
        )
        self.assertEqual(resultat['messages'], [])
        self.assertIn('aucun e-mail', resultat['detail'])

    def test_la_cle_d_un_produit_est_creee_une_seule_fois(self) -> None:
        cle = courriel.cle_produit(self.conn, 'ven_1', 'publier_prod')
        self.assertEqual(cle, 're_produit_secret')
        fichier = self.secrets / 'resend-ven_1.key'
        self.assertEqual(fichier.read_text().strip(), 're_produit_secret')
        self.assertEqual(oct(fichier.stat().st_mode & 0o777), '0o600')
        self.assertEqual(
            courriel.cle_produit(self.conn, 'ven_1', 'publier_prod'), cle
        )
        self.assertEqual(
            _Boites.cles,
            [{'name': 'produit-ven_1', 'permission': 'sending_access'}],
        )
        env, secrets = courriel.env_prod(
            self.conn, 'ven_1', 'calcu-devis', 'publier_prod'
        )
        self.assertEqual(
            env,
            {
                'SMTP_HOST': 'smtp.resend.com',
                'SMTP_PORT': '587',
                'SMTP_USER': 'resend',
                'MAIL_FROM': 'calcu-devis@envoi.exemple.fr',
            },
        )
        self.assertEqual(secrets, {'SMTP_PASS': 're_produit_secret'})

    def test_un_refus_de_resend_est_dit_clairement(self) -> None:
        _Boites.refuser_cle = True
        with redirect_stderr(io.StringIO()) as journal:
            with self.assertRaisesRegex(DockerError, 'HTTP 403'):
                courriel.cle_produit(self.conn, 'ven_2', 'publier_prod')
        self.assertIn('API key is invalid', journal.getvalue())
        self.assertFalse((self.secrets / 'resend-ven_2.key').exists())

    def test_sans_domaine_d_envoi_rien_ne_passe_en_prod(self) -> None:
        set_setting(self.conn, 'courriel.domaine_envoi', '', 'test')
        with redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(DockerError, 'domaine d’envoi'):
                courriel.env_prod(self.conn, 'ven_1', 'calcu', 'publier')
        self.assertEqual(_Boites.cles, [])

    def test_la_boite_d_essai_reste_sur_le_reseau_des_chantiers(self) -> None:
        courriel.ensure_boite(self.conn)
        etat = json.loads(
            (
                self.dossier / 'docker/containers/serge-boite/state.json'
            ).read_text()
        )
        port = self.conn.execute(
            "SELECT value_json FROM policy_settings WHERE id='sandbox.boite.port'"
        ).fetchone()[0]
        self.assertEqual(etat['networks'], ['serge-chantiers'])
        self.assertEqual(etat['flags']['-p'], f'127.0.0.1:{port}:8025')
        self.assertEqual(etat['image'], 'axllent/mailpit:v1.32.0')
        options, secrets = courriel.envoi_du_produit(
            self.conn, 'staging', 'ven_1', 'calcu-devis', 'publier'
        )
        self.assertIn('SMTP_HOST=serge-boite', options)
        self.assertIn('MAIL_FROM=calcu-devis@envoi.exemple.fr', options)
        self.assertEqual(options[-2:], ['--network', 'serge-chantiers'])
        self.assertEqual(secrets, {})

    def test_la_fiche_montre_les_emails_du_staging(self) -> None:
        self.conn.execute(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('ven_c', 'Calcu Devis', 'PRODUCT_BUILDING', '', '')"
        )
        self.conn.execute(
            'INSERT INTO deployments(id, venture_id, deliverable, target,'
            ' version, image, container, host_port, hostname, status,'
            " last_error, created_at, updated_at) VALUES('staging-x', 'ven_c',"
            " 'produit', 'staging', 1, 'i', 'c', 18001,"
            " 'staging-calcu-devis.serge.exemple.fr', 'running', '', '', '')"
        )
        self._dans_la_boite(
            'calcu-devis@envoi.exemple.fr',
            'clem@exemple.fr',
            'Validez votre compte',
        )
        cadre = next(
            c
            for c in cadres_produit(self.conn, 'ven_c')
            if c['titre'].startswith('E-mails d’essai')
        )
        self.assertIn(LIEN, cadre['champs'][0]['v'])
        self.assertIn('clem@exemple.fr', cadre['champs'][0]['k'])
        self.assertIn('Validez votre compte', cadre['pre'])


if __name__ == '__main__':
    unittest.main()
