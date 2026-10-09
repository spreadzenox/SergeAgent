#!/usr/bin/env python3
"""Julien dans la conversation, de bout en bout (lot 8 bis, Q85 et Q86).

Le canal e-mail et le modèle sont des faux ; tout le reste est réel : le
pipeline en base, l'interpréteur, les tickets, les boutons Discord.

Scénarios :
- Serge a besoin de Julien : sa réponse attend, un ticket « Conversation »
  s'ouvre (le business, le prospect, le fil, le brouillon, pourquoi, la
  question), rien ne part ; « Envoyer le brouillon » le fait partir ;
- « Ma réponse » : le texte de Julien part tel quel, et rejoint les
  questions fréquentes avec la question du contact ;
- « Réécrire » : Serge réécrit avec les consignes, et le nouveau brouillon
  revient dans le même ticket, rouvert ;
- « Ne rien envoyer » : l'envoi est annulé ;
- personne ne répond à temps : une réponse d'attente part, le ticket reste
  ouvert et le brouillon attend toujours ;
- un business qui valide chaque brouillon : même sans doute de Serge, sa
  réponse attend un humain ;
- un garde-fou qui bloque un envoi prévient Julien et Clem.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.adapters import ADAPTERS  # noqa: E402
from serge.channels.base import Adapter  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.discord.interactions import route_interaction  # noqa: E402
from serge.interpreter.flow import notify_rows_written  # noqa: E402
from serge.interpreter.queue import expirer_tickets  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.privacy import subject_hash  # noqa: E402
from serge.tickets.admins import add_admin  # noqa: E402
from tests.test_conversations import (  # noqa: E402
    MARC,
    FauxCanal,
    FauxModele,
)
from tests.test_discord_interactions import (  # noqa: E402
    CLEM,
    _fenetre,
    _interaction,
)

PIED = '\n\nPour ne plus recevoir de message de Serge, répondez STOP.'
DOUTE = {
    'reaction': 'question',
    'reply': 'Le devis part en moins de 10 minutes.',
    'besoin_julien': 'La fiche produit ne dit rien des devis en anglais.',
    'question_produit': 'Les devis peuvent-ils être en anglais ?',
}


class Modele(FauxModele):
    """Joue aussi « Réécrire un brouillon »."""

    def __init__(self) -> None:
        super().__init__()
        self.reecrit = 'Oui, en anglais aussi.'

    def __call__(self, key, model, messages, tools=None, **kw) -> ChatResult:
        if 'Tu réécris' in messages[0]['content']:
            self.recu.append(messages[1]['content'])
            return ChatResult(
                json.dumps({'reply': self.reecrit}), 10, 10, 'faux', 1
            )
        return super().__call__(key, model, messages, tools, **kw)


class JulienDansLaConversationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.canal = FauxCanal()
        faux = Adapter(
            'email',
            'E-mail',
            'Faux canal e-mail.',
            'email',
            'tests/test_julien_conversation.py',
            self.canal.send,
            self.canal.confirm,
            self.canal.poll,
        )
        patcher = mock.patch.dict(ADAPTERS, {'email': faux})
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
            'INSERT INTO ventures(id, name, description, lifecycle,'
            " created_at, updated_at) VALUES('v1', 'Devis dictés',"
            " 'Dicter ses devis au téléphone', 'SMOKE_RUNNING', 't', 't');"
            'INSERT INTO contacts(id, venture_id, display, funnel_state,'
            " created_at, updated_at) VALUES('c1', 'v1', 'Marc', 'CONTACTING',"
            " 't', 't');"
            'INSERT INTO contact_addresses(contact_id, channel, value,'
            f" value_norm, created_at) VALUES('c1', 'email', 'Marc@Exemple.fr',"
            f" '{MARC}', 't');"
            'INSERT INTO inbound_events(id, contact_id, venture_id, channel,'
            ' address, subject, body, message_ref, status, received_at)'
            " VALUES('i1', 'c1', 'v1', 'email', 'Marc@Exemple.fr',"
            " 'Re: Vos devis', 'Et en anglais ?', '<m1@marc>', 'attached',"
            " '2026-10-09T10:00:00+00:00');"
        )
        add_admin(self.conn, CLEM, 'Clem', 'test')
        self.conn.commit()
        self.modele = Modele()

    # --- Outils du test ---------------------------------------------------

    def _un(self, sql: str, params: tuple = ()) -> tuple:
        return tuple(self.conn.execute(sql, params).fetchone())

    def _vider(self) -> None:
        from serge.interpreter.queue import process_one

        for _ in range(30):
            if (
                process_one(self.conn, 'conversations', caller=self.modele)
                is None
            ):
                break
        echecs = self.conn.execute(
            "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
        ).fetchall()
        self.assertEqual([tuple(e) for e in echecs], [])

    def _marc_ecrit(self, reponse: dict) -> None:
        """Le message de Marc arrive : « Traiter une réponse » le lit, comme
        après une relève."""
        self.modele.reponse = reponse
        notify_rows_written(self.conn, 'inbound_events', ['i1'])
        self.conn.commit()
        self._vider()

    def _ticket(self) -> dict:
        row = self.conn.execute(
            'SELECT id, state, payload_json, ref_id, question FROM tickets'
            " WHERE type='CONVERSATION'"
        ).fetchall()
        self.assertEqual(len(row), 1)
        ident, state, payload, ref, question = row[0]
        return {
            'id': ident,
            'state': state,
            'payload': json.loads(payload),
            'ref': ref,
            'question': question,
        }

    def _envoi(self) -> tuple:
        return self._un(
            "SELECT id, status, body FROM touches WHERE kind='reply'"
            ' ORDER BY created_at LIMIT 1'
        )

    def _clic(self, acte: str, n: str) -> None:
        ticket = self._ticket()['id']
        resultat = route_interaction(
            self.conn,
            _interaction(f't:{ticket}:{acte}', user_id=CLEM, interaction_id=n),
        )
        self.assertEqual(resultat['status'], 'applied', resultat)
        self.conn.commit()
        self._vider()

    def _saisie(self, acte: str, texte: str, n: str) -> None:
        ticket = self._ticket()['id']
        resultat = route_interaction(
            self.conn,
            _fenetre(
                f'm:{ticket}:{acte}', texte, user_id=CLEM, interaction_id=n
            ),
        )
        self.assertEqual(resultat['status'], 'applied', resultat)
        self.conn.commit()
        self._vider()

    def _serge_attend_julien(self) -> dict:
        self._marc_ecrit(DOUTE)
        self.assertEqual(self.canal.envoyes, [])
        touch_id, status, _body = self._envoi()
        self.assertEqual(status, 'waiting_owner')
        ticket = self._ticket()
        self.assertEqual(
            (ticket['state'], ticket['ref'], ticket['question']),
            ('OPEN', touch_id, DOUTE['question_produit']),
        )
        return ticket

    # --- Scénarios ----------------------------------------------------------

    def test_serge_demande_et_julien_envoie_le_brouillon(self) -> None:
        ticket = self._serge_attend_julien()
        payload = ticket['payload']
        self.assertEqual(
            list(payload),
            [
                'Le business',
                'Le prospect',
                'Le fil',
                'Le brouillon de Serge',
                'Pourquoi',
                'La question',
            ],
        )
        self.assertIn('Devis dictés', payload['Le business'])
        self.assertIn('Marc', payload['Le prospect'])
        self.assertIn('Et en anglais ?', payload['Le fil'])
        self.assertIn(DOUTE['reply'], payload['Le brouillon de Serge'])
        self.assertEqual(payload['Pourquoi'], DOUTE['besoin_julien'])
        self._clic('envoyer_brouillon', '7001')
        self.assertEqual(
            [m.body for m in self.canal.envoyes], [DOUTE['reply'] + PIED]
        )
        self.assertEqual(self._ticket()['state'], 'APPROVED')

    def test_ma_reponse_part_et_rejoint_les_questions_frequentes(
        self,
    ) -> None:
        self._serge_attend_julien()
        self._saisie('ma_reponse', 'Oui, en anglais et en espagnol.', '7002')
        self.assertEqual(
            [m.body for m in self.canal.envoyes],
            ['Oui, en anglais et en espagnol.' + PIED],
        )
        self.assertEqual(
            self._un('SELECT venture_id, question, answer FROM product_faq'),
            (
                'v1',
                DOUTE['question_produit'],
                'Oui, en anglais et en espagnol.',
            ),
        )

    def test_reecrire_revient_dans_le_meme_ticket(self) -> None:
        self._serge_attend_julien()
        self._saisie('reecrire', 'Dis oui, sans détail.', '7003')
        self.assertEqual(self.canal.envoyes, [])
        self.assertIn('Dis oui, sans détail.', self.modele.recu[-1])
        ticket = self._ticket()
        self.assertEqual(ticket['state'], 'OPEN')
        self.assertIn(
            'Oui, en anglais aussi.',
            ticket['payload']['Le brouillon de Serge'],
        )
        self.assertEqual(
            self._envoi()[1:], ('waiting_owner', 'Oui, en anglais aussi.')
        )
        self._clic('envoyer_brouillon', '7004')
        self.assertEqual(
            [m.body for m in self.canal.envoyes],
            ['Oui, en anglais aussi.' + PIED],
        )

    def test_ne_rien_envoyer(self) -> None:
        self._serge_attend_julien()
        self._clic('ne_rien_envoyer', '7005')
        self.assertEqual(self.canal.envoyes, [])
        self.assertEqual(self._envoi()[1], 'cancelled')
        self.assertEqual(self._ticket()['state'], 'REJECTED')

    def test_sans_reponse_une_reponse_d_attente_part(self) -> None:
        ticket = self._serge_attend_julien()
        self.conn.execute(
            "UPDATE tickets SET expiry_at='2026-01-01T00:00:00+00:00'"
            ' WHERE id=?',
            (ticket['id'],),
        )
        self.assertEqual(expirer_tickets(self.conn), [ticket['id']])
        self.conn.commit()
        self._vider()
        self.assertEqual(
            [m.body for m in self.canal.envoyes],
            [
                'Merci pour votre message. Je vérifie ce point et je reviens'
                ' vers vous très vite.' + PIED
            ],
        )
        # Le ticket reste ouvert, sans nouvelle expiration ; le brouillon
        # attend toujours, et part dès que Julien le valide.
        apres = self._ticket()
        self.assertEqual(apres['state'], 'OPEN')
        self.assertEqual(self._envoi()[1], 'waiting_owner')
        self.assertEqual(expirer_tickets(self.conn), [])
        self._clic('envoyer_brouillon', '7006')
        self.assertEqual(len(self.canal.envoyes), 2)
        self.assertEqual(self.canal.envoyes[1].body, DOUTE['reply'] + PIED)

    def test_un_business_qui_valide_chaque_brouillon(self) -> None:
        self.conn.execute(
            "UPDATE ventures SET validate_drafts=1 WHERE id='v1'"
        )
        self._marc_ecrit({'reaction': 'question', 'reply': 'Oui.'})
        self.assertEqual(self.canal.envoyes, [])
        self.assertEqual(self._envoi()[1], 'waiting_owner')
        self.assertIn(
            'valider chaque brouillon', self._ticket()['payload']['Pourquoi']
        )

    def test_un_garde_fou_qui_bloque_previent(self) -> None:
        self.conn.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, reason,'
            " added_at) VALUES('b1', 'email', ?, 'owner', 't')",
            (subject_hash(MARC),),
        )
        self._marc_ecrit({'reaction': 'question', 'reply': 'Oui.'})
        self.assertEqual(self.canal.envoyes, [])
        self.assertEqual(self._envoi()[1], 'cancelled')
        self.assertEqual(
            self._un("SELECT type, title FROM tickets WHERE type='FYI'"),
            ('FYI', 'Envoi bloqué par un garde-fou (BLOCKLISTED)'),
        )


if __name__ == '__main__':
    unittest.main()
