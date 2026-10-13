#!/usr/bin/env python3
"""Les réponses automatiques ne font jamais répondre Serge sans fin
(lot 10 bis, Q93).

Le canal e-mail et le modèle sont des faux ; tout le reste est réel : la
relève, le pipeline en base, l'interpréteur, les garde-fous.

Scénarios :
- une réponse automatique reconnue à ses en-têtes est rangée dans le fil
  sans être traitée : le modèle n'est pas appelé, rien n'est répondu, et
  la relance part quand même ;
- « Traiter une réponse » décide d'arrêter avec un contact (un robot) :
  la fiche passe « Arrêté », ses envois en attente sont annulés, ce qu'il
  écrit ensuite n'est plus traité et aucune relance ne lui est écrite ;
- une conversation qui tourne en rond (le modèle répond à chaque fois) :
  au-delà des messages permis en 24 heures, l'envoi est annulé, Serge
  arrête avec ce contact, et Julien et Clem ont un ticket ;
- les en-têtes d'une réponse automatique (Auto-Submitted, X-Autoreply,
  Precedence) sont reconnus, ceux d'un humain non.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.adapters import ADAPTERS  # noqa: E402
from serge.channels.auto_reply import AUTO_REPLY, is_auto_reply  # noqa: E402
from serge.channels.base import Adapter, Incoming  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.store import utcnow  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from tests.test_conversations import MARC, FauxCanal, FauxModele  # noqa: E402

ROBOT = {'reaction': 'hors sujet', 'reply': '', 'arreter': 'oui'}
QUESTION = {'reaction': 'question', 'reply': 'Avec plaisir.', 'arreter': 'non'}


def _il_y_a(**duree: float) -> str:
    return (datetime.fromisoformat(utcnow()) - timedelta(**duree)).isoformat()


class ReponsesAutomatiquesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.canal = FauxCanal()
        faux = Adapter(
            'email',
            'E-mail',
            'Faux canal e-mail.',
            'email',
            'tests/test_reponses_automatiques.py',
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
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v1', 'Devis dictés', 'SMOKE_RUNNING', 't', 't');"
            'INSERT INTO contacts(id, venture_id, display, funnel_state,'
            " created_at, updated_at) VALUES('c1', 'v1', 'Marc', 'CONTACTING',"
            " 't', 't');"
            'INSERT INTO contact_addresses(contact_id, channel, value,'
            f" value_norm, created_at) VALUES('c1', 'email', 'Marc@Exemple.fr',"
            f" '{MARC}', 't');"
        )
        self._envoi('t1', 'first', 'sent', sent_at=_il_y_a(hours=1))
        self.conn.execute(
            "UPDATE canaux SET polled_at=? WHERE id='email'", (utcnow(),)
        )
        self.conn.commit()
        self.modele = FauxModele()
        self.tour = 0
        self.n = 0

    # --- Outils du test ---------------------------------------------------

    def _un(self, sql: str, params: tuple = ()) -> tuple:
        return tuple(self.conn.execute(sql, params).fetchone())

    def _tous(self, sql: str, params: tuple = ()) -> list[tuple]:
        return [tuple(r) for r in self.conn.execute(sql, params).fetchall()]

    def _envoi(
        self, ident: str, kind: str, status: str, sent_at: str = ''
    ) -> None:
        moment = sent_at or utcnow()
        self.conn.execute(
            'INSERT INTO touches(id, contact_id, venture_id, channel, address,'
            ' kind, status, subject, body, sent_at, external_ref,'
            " idempotency_key, created_at, updated_at) VALUES(?, 'c1', 'v1',"
            " 'email', ?, ?, ?, 'Vos devis', 'Bonjour', ?, ?, ?, ?, ?)",
            (
                ident,
                MARC,
                kind,
                status,
                sent_at,
                f'<{ident}@serge>' if status == 'sent' else '',
                ident,
                moment,
                moment,
            ),
        )
        self.conn.commit()

    def _recu(self, native_type: str = 'email') -> None:
        """Marc (ou son robot) répond au dernier message de Serge."""
        self.n += 1
        dernier = self._un(
            "SELECT external_ref FROM touches WHERE status='sent'"
            ' ORDER BY sent_at DESC LIMIT 1'
        )[0]
        self.canal.recus.append(
            Incoming(
                external_ref=f'r{self.n}',
                address='Marc@exemple.fr',
                subject='Re: Vos devis',
                body='Votre message a bien été reçu.',
                message_ref=f'<r{self.n}@marc>',
                refs=(str(dernier),),
                native_type=native_type,
            )
        )

    def _relever(self) -> None:
        """Un passage des déclencheurs horaires, 20 minutes plus tard."""
        self.tour += 1
        plus_tard = datetime.fromisoformat(utcnow()) + timedelta(
            minutes=20 * self.tour
        )
        for _ in range(30):
            if (
                process_one(
                    self.conn,
                    'conversations',
                    now=plus_tard.isoformat(),
                    caller=self.modele,
                )
                is None
            ):
                break
        echecs = self._tous(
            "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
        )
        self.assertEqual(echecs, [])

    def _etape(self) -> str:
        return str(
            self._un("SELECT funnel_state FROM contacts WHERE id='c1'")[0]
        )

    # --- Scénarios --------------------------------------------------------

    def test_une_reponse_automatique_n_est_pas_traitee(self) -> None:
        self._recu(AUTO_REPLY)
        self._relever()
        self.assertEqual(
            self._tous('SELECT native_type, status FROM inbound_events'),
            [(AUTO_REPLY, 'ignored')],
        )
        self.assertEqual(self.modele.recu, [])
        self.assertEqual(
            self._tous("SELECT id FROM touches WHERE kind='reply'"), []
        )
        # Quatre jours plus tard, la relance part quand même.
        self.conn.execute(
            "UPDATE touches SET sent_at=?, created_at=? WHERE id='t1'",
            (_il_y_a(days=4), _il_y_a(days=4)),
        )
        self.conn.commit()
        self._relever()
        self.assertEqual(
            self._tous("SELECT status FROM touches WHERE kind='followup'"),
            [('sent',)],
        )

    def test_traiter_une_reponse_peut_arreter_avec_un_contact(self) -> None:
        self._envoi('t2', 'followup', 'to_write')
        self.modele.reponse = ROBOT
        self._recu()
        self._relever()
        self.assertEqual(self._etape(), 'STOPPED')
        self.assertEqual(
            self._un("SELECT status, last_error FROM touches WHERE id='t2'"),
            (
                'cancelled',
                'contact arrêté : conversation sans issue (Traiter une'
                ' réponse)',
            ),
        )
        appels = len(self.modele.recu)
        # Il écrit encore : rangé dans le fil, sans être traité.
        self._recu()
        self._relever()
        self.assertEqual(len(self.modele.recu), appels)
        self.assertEqual(
            self._tous('SELECT status FROM inbound_events ORDER BY rowid'),
            [('attached',), ('ignored',)],
        )
        # Et aucune relance ne lui est écrite.
        self.conn.execute(
            "UPDATE touches SET sent_at=?, created_at=? WHERE id='t1'",
            (_il_y_a(days=4), _il_y_a(days=4)),
        )
        self.conn.commit()
        self._relever()
        self.assertEqual(
            self._tous(
                "SELECT id FROM touches WHERE kind='followup' AND id<>'t2'"
            ),
            [],
        )

    def test_une_conversation_qui_tourne_en_rond_s_arrete(self) -> None:
        set_setting(self.conn, 'contacts.max_messages_24h', 3, 'test')
        self.conn.commit()
        self.modele.reponse = QUESTION
        for _ in range(4):
            self._recu()
            self._relever()
        # Le premier message et deux réponses sont partis ; la troisième
        # réponse aurait dépassé 3 messages en 24 heures.
        self.assertEqual(
            self._tous(
                "SELECT status FROM touches WHERE kind='reply' ORDER BY rowid"
            )[:3],
            [('sent',), ('sent',), ('cancelled',)],
        )
        self.assertEqual(self._etape(), 'STOPPED')
        self.assertEqual(
            self._un(
                "SELECT COUNT(*) FROM tickets WHERE type='FYI'"
                " AND title LIKE '%QUOTA_CONTACT_24H%'"
            ),
            (1,),
        )
        self.assertEqual(
            self._un(
                'SELECT status FROM inbound_events ORDER BY rowid DESC LIMIT 1'
            ),
            ('ignored',),
        )

    def test_les_en_tetes_d_une_reponse_automatique(self) -> None:
        for headers in (
            {'auto-submitted': 'auto-replied'},
            {'x-autoreply': 'yes'},
            {'precedence': 'bulk'},
        ):
            self.assertTrue(is_auto_reply(headers), headers)
        for headers in ({'auto-submitted': 'no'}, {'from': MARC}):
            self.assertFalse(is_auto_reply(headers), headers)


if __name__ == '__main__':
    unittest.main()
