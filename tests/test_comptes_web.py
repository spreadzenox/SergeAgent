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
  ticket le dit.
"""

from __future__ import annotations

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
from serge.interpreter.triggers import fire_button  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.sandbox import sessions  # noqa: E402
from tests.mc_server_case import browser_ok  # noqa: E402
from tests.test_navigateur import _chrome, _site, appel  # noqa: E402

CREER = {
    'nom du compte, un mot (reddit, linkedin, x…)': 'Forum',
    'date de naissance, si le site la demande (JJ/MM/AAAA)': '',
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
                    'nom du compte, un mot (reddit, linkedin, x…)': 'Mon compte',
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


def tearDownModule() -> None:
    # Le Playwright des sessions tourne dans ce fil : arrêté, les tests
    # suivants peuvent lancer le leur.
    if 'pw' in sessions._PLAYWRIGHT:
        sessions._PLAYWRIGHT.pop('pw').stop()
    sessions._ETAT.browser = sessions._ETAT_VRAI.browser = None


if __name__ == '__main__':
    unittest.main()
