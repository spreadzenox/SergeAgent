#!/usr/bin/env python3
"""Le canal e-mail de bout en bout (lot 8, PR 2), par Gmail et par SMTP/IMAP.

Seuls Gmail (un faux binaire ``gog``, ``tests/fake_gog.py``), les serveurs
SMTP/IMAP (de faux serveurs en mémoire) et le modèle sont des faux. Le
pipeline en base, l'interpréteur, les garde-fous et le code du canal sont
réels.

Scénarios :
- par Gmail : Serge écrit à Marc ; Marc répond en citant le message ; sa
  réponse est relevée, rattachée par le fil, rendue sans la citation ; la
  réponse de Serge part dans le même fil, avec la phrase « STOP » ;
- un envoi interrompu est retrouvé dans les messages envoyés, pas renvoyé ;
- un destinataire refusé par Gmail : l'envoi passe en échec ;
- sans boîte dans le fichier d'instance, le canal n'est pas branché ;
- par SMTP/IMAP : le même fil, avec le ``Message-ID`` choisi par Serge et
  la copie rangée dans les messages envoyés, qui sert à confirmer.
"""

from __future__ import annotations

import json
import os
import smtplib
import sqlite3
import sys
import tempfile
import time
import unittest
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.mailbox_config import resolve_mailbox  # noqa: E402
from serge.channels.adapters import adapter  # noqa: E402
from serge.channels.base import ChannelError  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.store import utcnow  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from tests.test_conversations import FauxModele  # noqa: E402

MARC = 'marc@exemple.fr'
STOP = 'Pour ne plus recevoir de message de Serge, répondez STOP.'
REPONSE = 'Pas encore, mais le PDF marche partout.'


class _Canal(unittest.TestCase):
    """Une base, un contact et un premier message à envoyer."""

    feature = ''

    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dir = Path(dossier.name)
        instance = self.dir / 'instance.toml'
        instance.write_text(
            f'[features]\n{self.feature} = true\n' if self.feature else '',
            encoding='utf-8',
        )
        patcher = mock.patch.dict(
            os.environ,
            {'SERGE_INSTANCE_FILE': str(instance), **self._env()},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        for nom in ('reply_delay_min_minutes', 'reply_delay_max_minutes'):
            set_setting(self.conn, f'channels.email.{nom}', 0, 'test')
        self.conn.executescript(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v1', 'Devis dictés', 'SMOKE_RUNNING', 't', 't');"
            'INSERT INTO contacts(id, venture_id, display, funnel_state,'
            " created_at, updated_at) VALUES('c1', 'v1', 'Marc', 'CONTACTING',"
            " 't', 't');"
            'INSERT INTO contact_addresses(contact_id, channel, value,'
            f" value_norm, created_at) VALUES('c1', 'email', '{MARC}',"
            f" '{MARC}', 't');"
        )
        self.modele = FauxModele()
        self.modele.reponse = {'reaction': 'question', 'reply': REPONSE}
        self.tour = 0

    def _env(self) -> dict[str, str]:
        return {}

    def _un(self, sql: str, params: tuple = ()) -> tuple:
        return tuple(self.conn.execute(sql, params).fetchone())

    def _envoi(
        self, ident: str, status: str, body: str = 'Bonjour Marc'
    ) -> None:
        moment = utcnow()
        self.conn.execute(
            'INSERT INTO touches(id, contact_id, venture_id, channel, address,'
            ' kind, status, subject, body, idempotency_key, created_at,'
            " updated_at) VALUES(?, 'c1', 'v1', 'email', ?, 'first', ?,"
            " 'Vos devis', ?, ?, ?, ?)",
            (ident, MARC, status, body, ident, moment, moment),
        )
        enqueue_task(self.conn, 'envoyer_message', {'touch_id': ident})
        self.conn.commit()
        self._vider()

    def _vider(self, now: str | None = None) -> None:
        for _ in range(20):
            if (
                process_one(
                    self.conn, 'conversations', now=now, caller=self.modele
                )
                is None
            ):
                break

    def _relever(self) -> None:
        from datetime import datetime, timedelta

        self.tour += 1
        plus_tard = datetime.fromisoformat(utcnow()) + timedelta(
            minutes=20 * self.tour
        )
        self._vider(plus_tard.isoformat())


class GmailTests(_Canal):
    feature = 'gmail'

    def _env(self) -> dict[str, str]:
        self.etat = self.dir / 'gmail.json'
        self.etat.write_text(json.dumps({'inbox': [], 'sent': []}))
        gog = self.dir / 'gog'
        gog.write_text(
            f'#!/bin/sh\nexec {sys.executable} {ROOT}/tests/fake_gog.py "$@"\n'
        )
        gog.chmod(0o755)
        return {'SERGE_GOG_BIN': str(gog), 'FAKE_GOG_STATE': str(self.etat)}

    def _gmail(self) -> dict[str, Any]:
        return json.loads(self.etat.read_text())

    def _ecrire_gmail(self, boite: dict[str, Any]) -> None:
        self.etat.write_text(json.dumps(boite))

    def test_le_fil_complet_par_gmail(self) -> None:
        self._envoi('t1', 'pending')
        boite = self._gmail()
        self.assertEqual(
            (boite['sent'][0]['to'], boite['sent'][0]['body']),
            (MARC, f'Bonjour Marc\n\n{STOP}'),
        )
        self.assertEqual(
            self._un("SELECT status, external_ref FROM touches WHERE id='t1'"),
            ('sent', '<s1@gmail.test>'),
        )
        boite['inbox'].append(
            {
                'id': 'i1',
                'from': f'Marc <{MARC}>',
                'to': 'serge@gmail.test',
                'subject': 'Re: Vos devis',
                'body': 'Ça marche avec Excel ?\n\nLe mar. 7 oct. 2026 à'
                ' 10:00, Serge <serge@gmail.test> a écrit :\n> Bonjour Marc',
                'message_id': '<i1@marc>',
                'in_reply_to': '<s1@gmail.test>',
                'date': int(time.time()),
            }
        )
        self._ecrire_gmail(boite)
        self._relever()
        self.assertEqual(
            self._un(
                'SELECT contact_id, status, body, message_ref FROM'
                ' inbound_events'
            ),
            ('c1', 'attached', 'Ça marche avec Excel ?', '<i1@marc>'),
        )
        reponse = self._gmail()['sent'][1]
        self.assertEqual(
            (reponse['to'], reponse['in_reply_to'], reponse['subject']),
            (MARC, '<i1@marc>', 'Re: Vos devis'),
        )
        self.assertTrue(reponse['body'].startswith(f'{REPONSE}\n\n{STOP}'))
        envoi = next(
            c for c in self._gmail()['calls'] if '--reply-to-message-id' in c
        )
        self.assertEqual(envoi[envoi.index('--reply-to-message-id') + 1], 'i1')
        self.assertEqual(
            self._un(
                "SELECT status, external_ref FROM touches WHERE kind='reply'"
            ),
            ('sent', '<s2@gmail.test>'),
        )

    def test_un_envoi_interrompu_est_retrouve(self) -> None:
        boite = self._gmail()
        boite['sent'].append(
            {
                'id': 's7',
                'from': 'serge@gmail.test',
                'to': MARC,
                'subject': 'Vos devis',
                'body': f'Texte unique\n\n{STOP}',
                'message_id': '<s7@gmail.test>',
                'date': int(time.time()),
            }
        )
        self._ecrire_gmail(boite)
        self._envoi('t9', 'sending', body='Texte unique')
        self.assertEqual(
            self._un("SELECT status, external_ref FROM touches WHERE id='t9'"),
            ('sent', '<s7@gmail.test>'),
        )
        self.assertEqual(len(self._gmail()['sent']), 1)

    def test_un_destinataire_refuse(self) -> None:
        with mock.patch.dict(os.environ, {'FAKE_GOG_REFUSE': MARC}):
            self._envoi('t1', 'pending')
        status, erreur = self._un(
            "SELECT status, last_error FROM touches WHERE id='t1'"
        )
        self.assertEqual(status, 'failed')
        self.assertIn('API', erreur)


class SansBoiteTests(_Canal):
    def test_le_canal_n_est_pas_branche(self) -> None:
        self.assertEqual(
            self._un(
                "SELECT etat, connected, polls FROM canaux WHERE id='email'"
            ),
            ('prevu', 0, 0),
        )
        with self.assertRaises(ChannelError):
            adapter('email')


class FauxImap:
    """Un serveur IMAP en mémoire : la boîte de réception et les envoyés."""

    boites: dict[str, list[bytes]] = {}

    def __init__(self, *_args: Any, **_kw: Any) -> None:
        self.dossier = 'INBOX'

    def __enter__(self) -> FauxImap:
        return self

    def __exit__(self, *_exc: Any) -> None:
        return None

    def login(self, *_args: str) -> None:
        return None

    def list(self) -> tuple[str, list[bytes]]:
        return 'OK', [b'(\\HasNoChildren) "/" "INBOX"', b'(\\Sent) "/" "Sent"']

    def select(self, dossier: str, readonly: bool = False) -> tuple:
        self.dossier = dossier
        return 'OK', [b'1']

    def append(
        self, dossier: str, _flags: str, _date: str, raw: bytes
    ) -> tuple:
        self.boites[dossier].append(raw)
        return 'OK', []

    def uid(self, commande: str, *args: Any) -> tuple:
        boite = self.boites[self.dossier]
        if commande == 'search':
            if 'Message-ID' in args:
                wanted = args[-1]
                found = [
                    str(n + 1).encode()
                    for n, raw in enumerate(boite)
                    if f'Message-ID: {wanted}'.encode() in raw
                ]
            else:
                found = [str(n + 1).encode() for n in range(len(boite))]
            return 'OK', [b' '.join(found)]
        raw = boite[int(args[0]) - 1]
        return 'OK', [(b'1 (RFC822)', raw)]


class SmtpTests(_Canal):
    feature = 'mailbox'

    def setUp(self) -> None:
        FauxImap.boites = {'INBOX': [], 'Sent': []}
        self.partis: list[EmailMessage] = []
        cfg = {
            **resolve_mailbox({'login': 'serge@exemple.fr'}),
            'password': 'x',
        }
        for cible, faux in (
            ('serge.channels.email_smtp.instance_config', lambda: cfg),
            ('imaplib.IMAP4_SSL', FauxImap),
        ):
            patcher = mock.patch(cible, faux)
            patcher.start()
            self.addCleanup(patcher.stop)
        smtp = mock.patch('smtplib.SMTP')
        serveur = smtp.start().return_value
        serveur.send_message.side_effect = self.partis.append
        self.addCleanup(smtp.stop)
        super().setUp()

    def test_le_fil_complet_par_smtp(self) -> None:
        self._envoi('t1', 'pending')
        self.assertEqual(
            (str(self.partis[0]['Message-ID']), self.partis[0]['To']),
            ('<serge.t1@exemple.fr>', MARC),
        )
        self.assertEqual(len(FauxImap.boites['Sent']), 1)
        recu = EmailMessage()
        recu['From'] = f'Marc <{MARC}>'
        recu['Subject'] = 'Re: Vos devis'
        recu['Message-ID'] = '<m1@marc>'
        recu['In-Reply-To'] = '<serge.t1@exemple.fr>'
        recu.set_content('Et le prix ?\n\n> Bonjour Marc')
        FauxImap.boites['INBOX'].append(recu.as_bytes())
        self._relever()
        self.assertEqual(
            self._un('SELECT contact_id, body FROM inbound_events'),
            ('c1', 'Et le prix ?'),
        )
        reponse = self.partis[1]
        self.assertEqual(reponse['In-Reply-To'], '<m1@marc>')
        self.assertEqual(reponse.get_content().strip(), f'{REPONSE}\n\n{STOP}')

    def test_un_envoi_interrompu_est_retrouve(self) -> None:
        copie = EmailMessage()
        copie['Message-ID'] = '<serge.t9@exemple.fr>'
        copie.set_content('Texte')
        FauxImap.boites['Sent'].append(copie.as_bytes())
        self._envoi('t9', 'sending')
        self.assertEqual(self.partis, [])
        self.assertEqual(
            self._un("SELECT status, external_ref FROM touches WHERE id='t9'"),
            ('sent', '<serge.t9@exemple.fr>'),
        )

    def test_un_destinataire_refuse(self) -> None:
        refus = smtplib.SMTPRecipientsRefused({MARC: (550, b'inconnu')})
        with mock.patch('smtplib.SMTP') as smtp:
            smtp.return_value.send_message.side_effect = refus
            self._envoi('t1', 'pending')
        self.assertEqual(
            self._un("SELECT status FROM touches WHERE id='t1'"), ('failed',)
        )


if __name__ == '__main__':
    unittest.main()
