#!/usr/bin/env python3
"""Les comptes web de Serge, de bout en bout (lot 13, décision Q104).

Un vrai Chromium tient lieu du vrai Chrome, un petit site local demande un
compte, et le modèle est un faux. Le reste est réel : les boutons de la
page Système, l'interpréteur, les capacités, la base.

Scénarios :
- « Créer un compte web » : la ligne du compte, puis l'invocation qui
  s'inscrit ; Serge tape le mot de passe, le modèle ne le voit jamais ; le
  message de vérification reçu pendant la tâche lui est rendu, pas l'e-mail
  d'un contact ; à la fin le compte est en service, son mot de passe et sa
  session sont chiffrés en base, et un ticket prévient ;
- « Vérifier un compte web », ensuite : la session gardée connecte
  d'emblée ;
- un nom de compte mal écrit est refusé avant toute navigation, et un
  ticket le dit ;
- le pseudo voulu, tapé dans le bouton, arrive à l'invocation qui crée le
  compte ;
- une ligne ouverte par erreur se retire, pas un compte en service ni un
  compte qu'une tâche utilise ;
- « Mes messages de vérification » rend un SMS reçu pendant la tâche avec
  son code et son lien ; tant qu'aucun SMS n'est jamais arrivé sur le
  serveur, il le dit, pour que l'invocation n'attende pas un code qui ne
  viendra pas (inscription sur X, le 20 novembre 2026).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge import web_accounts  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db, utcnow  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.interpreter.triggers import fire_button  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.sandbox import sessions  # noqa: E402
from serge.sms import SmsInbox  # noqa: E402
from serge.verification import received_since_task  # noqa: E402
from tests.mc_server_case import browser_ok  # noqa: E402
from tests.test_navigateur import _chrome, _site, appel  # noqa: E402

SITE = 'le site, en un mot : reddit, linkedin, instagram ou x (pas le pseudo)'
CREER = {
    SITE: 'Forum',
    'date de naissance, si le site la demande (JJ/MM/AAAA)': '',
    'pseudo voulu sur ce site (vide : celui de la page Identité)': 'serge_ia',
}


def _dernier_outil(messages: list[dict[str, Any]]) -> str:
    return next(
        str(m['content']) for m in reversed(messages) if m['role'] == 'tool'
    )


class FauxInscrit:
    """Le modèle qui crée le compte : ouvre le site, fait taper le mot de
    passe, valide, lit son message de vérification, puis rend."""

    def __init__(self, conn: Any, adresse: str) -> None:
        self.conn = conn
        self.adresse = adresse
        self.messages: list[list[dict[str, Any]]] = []
        self.outils: list[dict[str, Any]] = []

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        self.messages.append(json.loads(json.dumps(messages)))
        self.outils = tools or []
        tour = len(self.messages)
        if tour == 1:
            calls = (
                appel(
                    'a', 'vrai_chrome_agir', action='ouvrir', text=self.adresse
                ),
            )
        elif tour == 2:
            champ = re.search(
                r'\[(e\d+)\] champ password', _dernier_outil(messages)
            )
            assert champ, _dernier_outil(messages)
            calls = (
                appel(
                    'b',
                    'vrai_chrome_agir',
                    action='taper_secret',
                    ref=champ[1],
                    text=web_accounts.PASSWORD_NAME,
                ),
            )
        elif tour == 3:
            # Le site envoie son e-mail de confirmation ; un prospect écrit
            # au même moment.
            for ident, de, objet, corps, etat in (
                (
                    'in_site',
                    'noreply@forum.example',
                    'Confirmez votre adresse',
                    'Votre lien : https://forum.example/confirmer?t=42',
                    'unattached',
                ),
                (
                    'in_contact',
                    'ana@client.fr',
                    'Votre devis',
                    'Bonjour',
                    'attached',
                ),
            ):
                self.conn.execute(
                    'INSERT INTO inbound_events(id, channel, address, subject,'
                    " body, status, received_at) VALUES(?, 'email', ?, ?, ?, ?, ?)",
                    (ident, de, objet, corps, etat, utcnow()),
                )
            calls = (
                appel(
                    'c',
                    'vrai_chrome_agir',
                    action='cliquer',
                    text='Se connecter',
                ),
            )
        elif tour == 4:
            calls = (appel('d', 'messages_de_verification', wait=False),)
        else:
            reponse = {
                'cree': 'oui',
                'identifiant': 'serge@exemple.fr',
                'nom_public': 'serge-ia',
                'compte_rendu': 'Compte créé et confirmé par e-mail.',
            }
            return ChatResult(json.dumps(reponse), 10, 10, 'faux', 1)
        return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)


class FauxVerificateur:
    """Le modèle qui vérifie le compte : ouvre le site et dit ce qu'il voit."""

    def __init__(self, adresse: str) -> None:
        self.adresse = adresse
        self.pages: list[str] = []

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        if not self.pages and messages[-1]['role'] != 'tool':
            calls = (
                appel(
                    'a', 'vrai_chrome_agir', action='ouvrir', text=self.adresse
                ),
            )
            return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)
        self.pages.append(_dernier_outil(messages))
        reponse = {
            'etat': 'connecte'
            if 'Bonjour' in self.pages[-1]
            else 'deconnecte',
            'nom_public': 'serge-ia',
            'compte_rendu': 'Le site montre le compte connecté.',
        }
        return ChatResult(json.dumps(reponse), 10, 10, 'faux', 1)


@unittest.skipUnless(browser_ok(), 'pas de Chromium pour ce test')
class ComptesWebTests(unittest.TestCase):
    def setUp(self) -> None:
        from cryptography.fernet import Fernet

        dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        secrets = self.dossier / 'config/secrets'
        secrets.mkdir(parents=True)
        (secrets / 'credential-vault.key').write_bytes(Fernet.generate_key())
        instance = self.dossier / 'instance.toml'
        instance.write_text(
            f'[paths]\nconfig_root = "{self.dossier / "config"}"\n'
        )
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_SYSTEM_ROOT': str(self.dossier),
                'SERGE_INSTANCE_FILE': str(instance),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        set_heartbeat(self.conn, True)
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at')"
        )
        self.conn.commit()
        proc, endpoint = _chrome(self.dossier)
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        point = mock.patch.object(sessions, '_endpoint', return_value=endpoint)
        point.start()
        self.addCleanup(point.stop)
        self.addCleanup(sessions.close_sessions)
        serveur, self.site = _site()
        self.addCleanup(serveur.shutdown)

    def _vider(self, file: str, modele: Any = None) -> list[str]:
        """Traite la file jusqu'au bout ; rend les invocations passées."""
        faites = []
        while (
            tache := process_one(self.conn, file, caller=modele)
        ) is not None:
            invocation, statut, erreur = self.conn.execute(
                'SELECT invocation_id, status, last_error FROM tasks WHERE id=?',
                (tache,),
            ).fetchone()
            self.assertEqual((statut, erreur), ('done', ''), invocation)
            faites.append(str(invocation))
        return faites

    def _tickets(self) -> list[str]:
        return [
            str(r[0])
            for r in self.conn.execute(
                'SELECT title FROM tickets ORDER BY created_at, rowid'
            )
        ]

    def test_creer_puis_verifier_un_compte(self) -> None:
        adresse = f'{self.site}/compte'
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_creer_compte_web',
                {**CREER, 'adresse du site (https://www.reddit.com)': adresse},
            )
        )
        self.conn.commit()
        inscrit = FauxInscrit(self.conn, adresse)
        self.assertEqual(
            self._vider('works', inscrit),
            ['ouvrir_compte_web', 'creer_compte_web'],
        )
        # Le compte est en service, sous son nom en minuscules ; ses deux
        # secrets sont chiffrés, et il est rendu.
        compte = dict(
            zip(
                ('url', 'login', 'handle', 'status', 'note', 'used_by'),
                self.conn.execute(
                    'SELECT url, login, handle, status, note, used_by'
                    " FROM web_accounts WHERE id='forum'"
                ).fetchone(),
                strict=True,
            )
        )
        self.assertEqual(
            compte,
            {
                'url': adresse,
                'login': 'serge@exemple.fr',
                'handle': 'serge-ia',
                'status': 'active',
                'note': 'Compte créé et confirmé par e-mail.',
                'used_by': '',
            },
        )
        chiffres = self.conn.execute(
            'SELECT password_enc, session_enc FROM web_accounts'
        ).fetchone()
        self.assertTrue(all(chiffres))
        self.assertNotIn('jeton-de-session', chiffres[1])
        # Le pseudo tapé dans le bouton est arrivé jusqu'à lui.
        self.assertIn(
            '"pseudo": "serge_ia"',
            json.dumps(inscrit.messages[0], ensure_ascii=False).replace(
                '\\"', '"'
            ),
        )
        # Le modèle n'a jamais vu le mot de passe, et son outil ne lui
        # propose ni compte ni secrets.
        vu = json.dumps(inscrit.messages, ensure_ascii=False)
        self.assertNotIn(web_accounts.password(self.conn, 'forum'), vu)
        agir = next(
            o['function']['parameters']['properties']
            for o in inscrit.outils
            if o['function']['name'] == 'vrai_chrome_agir'
        )
        self.assertFalse({'account', 'secrets', 'task_id'} & set(agir))
        # Il a reçu le message du site, pas l'e-mail du contact.
        recu = next(
            str(m['content'])
            for m in inscrit.messages[-1]
            if m['role'] == 'tool' and m['tool_call_id'].endswith('d')
        )
        self.assertIn('https://forum.example/confirmer?t=42', recu)
        self.assertNotIn('ana@client.fr', recu)
        # Trois actions comptées : ouvrir, taper, cliquer.
        self.assertEqual(web_accounts.actions_today(self.conn, 'forum'), 3)
        self.assertEqual(self._vider('conversations'), ['prevenir_compte_web'])
        self.assertEqual(self._tickets(), ['Un compte web est créé'])

        # « Vérifier un compte web » : la session gardée connecte d'emblée.
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_verifier_compte_web',
                {'nom du compte (reddit, linkedin, x…)': 'forum'},
            )
        )
        self.conn.commit()
        verificateur = FauxVerificateur(adresse)
        self.assertEqual(
            self._vider('works', verificateur), ['verifier_compte_web']
        )
        self.assertIn('# Bonjour serge-ia', verificateur.pages[0])
        self.assertEqual(
            tuple(
                self.conn.execute(
                    'SELECT status, note FROM web_accounts'
                ).fetchone()
            ),
            ('active', 'Le site montre le compte connecté.'),
        )

    def test_un_nom_mal_ecrit_est_refuse(self) -> None:
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_creer_compte_web',
                {
                    SITE: 'Mon compte',
                    'adresse du site (https://www.reddit.com)': self.site,
                },
            )
        )
        self.conn.commit()
        self.assertEqual(self._vider('works'), ['ouvrir_compte_web'])
        self.assertEqual(self._vider('conversations'), ['prevenir_compte_web'])
        self.assertEqual(
            self._tickets(), ["Un compte web n'a pas pu être ouvert"]
        )
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM web_accounts').fetchone()[
                0
            ],
            0,
        )


class MotDePasseDuSiteTests(unittest.TestCase):
    """Le 22 novembre 2026, TikTok a refusé le mot de passe de Serge : 24
    caractères, quand le site en veut 8 à 20 (décision Q112)."""

    SIGNES = '!#%+-=?@'

    def setUp(self) -> None:
        import sqlite3

        from cryptography.fernet import Fernet

        from serge.db.boot import init_schema

        dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(dossier.cleanup)
        racine = Path(dossier.name)
        secrets = racine / 'config/secrets'
        secrets.mkdir(parents=True)
        (secrets / 'credential-vault.key').write_bytes(Fernet.generate_key())
        instance = racine / 'instance.toml'
        instance.write_text(f'[paths]\nconfig_root = "{racine / "config"}"\n')
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_SYSTEM_ROOT': str(racine),
                'SERGE_INSTANCE_FILE': str(instance),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _compte(self, etat: str) -> None:
        self.conn.execute(
            'INSERT INTO web_accounts(id, url, status, created_at, updated_at)'
            " VALUES('tiktok', 'https://www.tiktok.com', ?, ?, ?)",
            (etat, utcnow(), utcnow()),
        )

    def _changer(self, **args: Any) -> dict[str, Any]:
        return web_accounts.change_password(
            self.conn, '', {'account': 'tiktok', **args}, 'creer_compte_web'
        )

    def test_serge_choisit_vingt_caracteres(self) -> None:
        self._compte('creating')
        choisi = web_accounts.password(self.conn, 'tiktok')
        self.assertEqual(len(choisi), 20)
        for sorte in (str.islower, str.isupper, str.isdigit):
            self.assertTrue(any(sorte(c) for c in choisi))
        self.assertTrue(any(c in self.SIGNES for c in choisi))
        # Demandé une seconde fois, c'est le même.
        self.assertEqual(web_accounts.password(self.conn, 'tiktok'), choisi)

    def test_un_autre_a_la_mesure_du_site(self) -> None:
        """Le site refuse le premier : l'invocation en demande un autre,
        de la longueur qu'il accepte, sans jamais le voir."""
        self._compte('creating')
        premier = web_accounts.password(self.conn, 'tiktok')
        rendu = self._changer(longueur=12, signes='non')
        self.assertEqual(
            (rendu['ok'], rendu['longueur'], rendu['signes']),
            (True, 12, 'non'),
        )
        second = web_accounts.password(self.conn, 'tiktok')
        self.assertNotEqual(second, premier)
        self.assertEqual(len(second), 12)
        self.assertTrue(second.isalnum())
        # Ce que le modèle reçoit ne contient pas le mot de passe.
        self.assertNotIn(second, json.dumps(rendu, ensure_ascii=False))
        self.assertIn('taper_secret', rendu['detail'])
        # Sans rien préciser : 20 caractères, avec des signes.
        self.assertEqual(self._changer()['longueur'], 20)
        self.assertEqual(len(web_accounts.password(self.conn, 'tiktok')), 20)

    def test_il_refuse_ce_qui_n_a_pas_de_sens(self) -> None:
        self._compte('creating')
        garde = web_accounts.password(self.conn, 'tiktok')
        for longueur in (3, 200, 'beaucoup'):
            rendu = self._changer(longueur=longueur)
            self.assertFalse(rendu['ok'])
            self.assertIn('de 8 à 64 caractères', rendu['detail'])
        self.assertFalse(
            web_accounts.change_password(
                self.conn, '', {'account': 'inconnu'}, 'x'
            )['ok']
        )
        self.assertEqual(web_accounts.password(self.conn, 'tiktok'), garde)

    def test_un_compte_en_service_garde_le_sien(self) -> None:
        """Le site a l'ancien mot de passe : le changer ici couperait
        Serge de son compte."""
        self._compte('active')
        garde = web_accounts.password(self.conn, 'tiktok')
        rendu = self._changer(longueur=10)
        self.assertFalse(rendu['ok'])
        self.assertIn('existe déjà sur son site', rendu['detail'])
        self.assertEqual(web_accounts.password(self.conn, 'tiktok'), garde)

    def test_creer_un_compte_a_l_outil(self) -> None:
        outil = self.conn.execute(
            'SELECT t.capability_id, it.mode, it.max_calls FROM'
            ' invocation_tools it JOIN tools t ON t.id=it.tool_id'
            " WHERE it.invocation_id='creer_compte_web'"
            " AND t.id='changer_mot_de_passe_du_compte'"
        ).fetchone()
        self.assertEqual(
            tuple(outil), ('change_web_password', 'callable', '3')
        )
        consigne = self.conn.execute(
            "SELECT prompt FROM invocations WHERE id='creer_compte_web'"
        ).fetchone()[0]
        self.assertIn('« Changer le mot de passe du compte »', consigne)


class RetirerUnCompteTests(unittest.TestCase):
    def test_seul_un_compte_hors_service_se_retire(self) -> None:
        import sqlite3

        from serge.db.boot import init_schema

        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        for nom, etat, pris in (
            ('serge_chevalier_ia', 'creating', ''),
            ('reddit', 'active', ''),
            ('x', 'creating', 't_en_cours'),
        ):
            conn.execute(
                'INSERT INTO web_accounts(id, url, status, used_by,'
                ' used_since, created_at, updated_at) VALUES(?, ?, ?, ?, ?,'
                ' ?, ?)',
                (
                    nom,
                    'https://exemple.fr',
                    etat,
                    pris,
                    utcnow(),
                    utcnow(),
                    utcnow(),
                ),
            )
        web_accounts.count_action(conn, 'serge_chevalier_ia')
        web_accounts.remove(conn, ' Serge_Chevalier_IA ')
        self.assertEqual(
            [
                r[0]
                for r in conn.execute(
                    'SELECT id FROM web_accounts ORDER BY id'
                )
            ],
            ['reddit', 'x'],
        )
        self.assertEqual(
            conn.execute('SELECT COUNT(*) FROM web_account_days').fetchone()[
                0
            ],
            0,
        )
        for nom, raison in (
            ('reddit', 'est en service'),
            ('x', 'sert à une tâche en cours'),
            ('inconnu', 'pas de compte « inconnu »'),
        ):
            with self.assertRaisesRegex(web_accounts.AccountError, raison):
                web_accounts.remove(conn, nom)


class MessagesDeVerificationTests(unittest.TestCase):
    def test_un_sms_avec_son_code_et_son_lien(self) -> None:
        dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(dossier.cleanup)
        patcher = mock.patch.dict(
            os.environ, {'SERGE_SYSTEM_ROOT': dossier.name}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        conn = open_db(default_canon_path())
        self.addCleanup(conn.close)
        conn.execute(
            "UPDATE tasks SET started_at='2026-11-20T15:42:00+00:00'"
            ' WHERE id=?',
            (enqueue_task(conn, 'creer_compte_web', {'compte': 'x'}),),
        )
        tache = conn.execute('SELECT id FROM tasks').fetchone()[0]

        def lire() -> dict[str, Any]:
            return received_since_task(
                conn, '', {'task_id': tache, 'wait': False}, ''
            )

        # Rien n'est jamais arrivé : la base des SMS n'existe pas, puis
        # elle est vide.
        self.assertIn('aucun SMS', lire()['sms_jamais_recu'])
        boite = SmsInbox(Path(dossier.name) / 'state/sms/inbound.db')
        vide = lire()
        self.assertEqual(vide['sms'], [])
        self.assertIn('ne redonne pas le numéro', vide['sms_jamais_recu'])

        secret = b'0123456789abcdef0123456789abcdef'
        for ident, quand, texte in (
            (
                'sms_avant',
                '2026-11-20T15:00:00Z',
                'Un code d’hier : 111111',
            ),
            (
                'sms_code',
                '2026-11-20T15:43:00Z',
                'Votre code de confirmation X : 482931',
            ),
            (
                'sms_lien',
                '2026-11-20T15:44:00Z',
                'Confirmez votre numéro : https://x.com/i/v?t=abc',
            ),
        ):
            brut = json.dumps(
                {
                    'id': ident,
                    'from': 'X',
                    'body': texte,
                    'received_at': quand,
                },
                sort_keys=True,
            ).encode()
            boite.ingest(
                brut,
                hmac.new(secret, brut, hashlib.sha256).hexdigest(),
                secret,
                purpose='ACCOUNT_VERIFICATION',
            )
        rendu = lire()
        self.assertNotIn('sms_jamais_recu', rendu)
        # Les SMS de la tâche seulement, le plus récent d'abord.
        self.assertEqual(
            [(m['code'], m['liens']) for m in rendu['sms']],
            [('', ['https://x.com/i/v?t=abc']), ('482931', [])],
        )


def tearDownModule() -> None:
    # Le Playwright des sessions tourne dans ce fil : arrêté, les tests
    # suivants peuvent lancer le leur.
    if 'pw' in sessions._PLAYWRIGHT:
        sessions._PLAYWRIGHT.pop('pw').stop()
    sessions._ETAT.browser = sessions._ETAT_VRAI.browser = None


if __name__ == '__main__':
    unittest.main()
