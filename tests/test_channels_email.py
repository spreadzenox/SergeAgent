#!/usr/bin/env python3
"""Le canal e-mail : les parties piégeuses, sans réseau.

- quelle boîte : SMTP/IMAP d'abord, sinon Gmail, sinon pas de canal ;
- la citation retirée d'une réponse, même quand la ligne « Le …, Serge a
  écrit : » est coupée en deux ;
- le binaire gog trouvé, et ses erreurs classées (BIN, AUTH, API).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels import email_gog, mail  # noqa: E402
from serge.channels.base import ChannelError, Outgoing  # noqa: E402

ENVOI = Outgoing('t1', 'email', 'a@x.io', 'Sujet', 'Corps')


def _sortie(payload: dict, code: int = 0, err: str = ''):
    return subprocess.CompletedProcess(['gog'], code, json.dumps(payload), err)


class BoiteTests(unittest.TestCase):
    def test_la_boite_vient_du_fichier_d_instance(self) -> None:
        with tempfile.TemporaryDirectory() as dossier:
            instance = Path(dossier) / 'instance.toml'
            for texte, attendu in (
                ('[features]\nmailbox = true\ngmail = true\n', 'smtp'),
                ('[features]\ngmail = true\n', 'gog'),
                ('[features]\n', ''),
            ):
                instance.write_text(texte, encoding='utf-8')
                with mock.patch.dict(
                    os.environ, {'SERGE_INSTANCE_FILE': str(instance)}
                ):
                    self.assertEqual(mail.backend(), attendu)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(mail.backend(), '')


class CitationTests(unittest.TestCase):
    def test_la_citation_est_retiree(self) -> None:
        for texte in (
            'Et le prix ?\n\n> Bonjour Marc',
            'Et le prix ?\n\nLe mar. 7 oct. 2026 à 10:00, Serge'
            ' <s@x.fr> a écrit :\n> Bonjour Marc',
            'Et le prix ?\n\nLe mar. 7 oct. 2026 à 10:00, Serge <s@x.fr>\n'
            'a écrit :\n\n> Bonjour Marc',
            'Et le prix ?\n\nOn Tue, Oct 7, 2026, Serge wrote:\n> Hello',
        ):
            self.assertEqual(mail.without_quote(texte), 'Et le prix ?')
        # Un message qui n'est qu'une citation est gardé tel quel.
        self.assertEqual(mail.without_quote('> tout'), '> tout')


class GogTests(unittest.TestCase):
    def test_le_binaire_gog(self) -> None:
        for env, trouve, attendu in (
            ({'SERGE_GOG_BIN': '/x/gog'}, '/p/gog', '/x/gog'),
            ({}, '/p/gog', '/p/gog'),
            ({}, None, '/usr/local/bin/gog'),
        ):
            with (
                mock.patch.dict(os.environ, env, clear=True),
                mock.patch('shutil.which', return_value=trouve),
                mock.patch(
                    'subprocess.run', return_value=_sortie({'messages': []})
                ) as lance,
            ):
                email_gog.poll('')
            self.assertEqual(lance.call_args[0][0][0], attendu)

    def test_les_erreurs_de_gog(self) -> None:
        with mock.patch('subprocess.run', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(email_gog.MailError, '^BIN'):
                email_gog.poll('')
        with mock.patch(
            'subprocess.run', return_value=_sortie({}, 1, 'auth denied')
        ):
            with self.assertRaisesRegex(email_gog.MailError, '^AUTH'):
                email_gog.poll('')

    def test_un_refus_de_gmail_fait_echouer_l_envoi(self) -> None:
        """Une erreur API : le message n'est pas parti (l'envoi passe en
        échec). Une panne d'accès : l'envoi reste « en cours »."""
        with (
            mock.patch.object(mail, 'backend', return_value='gog'),
            mock.patch(
                'subprocess.run',
                return_value=_sortie({}, 1, 'invalid recipient'),
            ),
        ):
            with self.assertRaises(ChannelError):
                mail.send(ENVOI)
        with (
            mock.patch.object(mail, 'backend', return_value='gog'),
            mock.patch(
                'subprocess.run', return_value=_sortie({}, 1, '401 auth')
            ),
        ):
            with self.assertRaisesRegex(email_gog.MailError, '^AUTH'):
                mail.send(ENVOI)


if __name__ == '__main__':
    unittest.main()
