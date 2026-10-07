#!/usr/bin/env python3
"""Les conversations de bout en bout (lot 8), avec un faux canal e-mail.

Le canal (envoyer, confirmer, relever) et le modèle sont des faux qui
répondent ce qu'on leur a dit ; tout le reste est réel : le pipeline en
base, l'interpréteur, les garde-fous.

Scénarios :
- Marc répond au premier message de Serge : son message est relevé,
  rattaché à Marc par le fil, « Traiter une réponse » rend une question et
  une idée de produit, la réponse part dans le même fil ; relever de
  nouveau ne réécrit pas le message ;
- un inconnu écrit : son message n'est pas rattaché, rien n'est traité ;
- deux messages coup sur coup : une seule tâche « Traiter une réponse » ;
- Marc écrit « STOP » : rien n'est répondu, ses adresses sont bloquées
  partout, ses fiches de tous les business passent « Désinscrit », ses
  envois en attente sont annulés, Julien et Clem ont un ticket ;
- jamais deux fois : un envoi interrompu est confirmé auprès du canal, pas
  renvoyé ; une adresse bloquée n'est jamais écrite ;
- le délai de réponse est tiré entre les deux réglages du canal ;
- les relances : 4 jours sans réponse, une relance est rédigée et part
  dans le fil ; pas de relance si Marc a écrit, ni si la boîte n'a pas été
  relevée récemment ; une réponse d'absence ne les arrête pas.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.base import (  # noqa: E402
    ADAPTERS,
    Adapter,
    Incoming,
    Outgoing,
)
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.store import utcnow  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.privacy import subject_hash  # noqa: E402

MARC = 'marc@exemple.fr'
RELANCE = 'Je me permets de revenir vers vous.'


def _il_y_a(**duree: float) -> str:
    return (datetime.fromisoformat(utcnow()) - timedelta(**duree)).isoformat()


class FauxCanal:
    """Un canal e-mail qui garde ce qu'on lui envoie."""

    def __init__(self) -> None:
        self.recus: list[Incoming] = []
        self.envoyes: list[Outgoing] = []
        self.deja_partis: dict[str, str] = {}

    def send(self, message: Outgoing) -> str:
        self.envoyes.append(message)
        return f'<{message.touch_id}@serge>'

    def confirm(self, message: Outgoing) -> str:
        return self.deja_partis.get(message.touch_id, '')

    def poll(self, _since: str) -> list[Incoming]:
        return list(self.recus)


class FauxModele:
    """Joue « Traiter une réponse » et « Écrire une relance » ; garde ce
    qu'ils ont reçu."""

    def __init__(self) -> None:
        self.reponse: dict[str, Any] = {}
        self.recu: list[str] = []

    def __call__(
        self, _key, _model, messages, tools=None, **_kw
    ) -> ChatResult:
        system, user = messages[0]['content'], messages[1]['content']
        self.recu.append(user)
        data = (
            {'body': RELANCE}
            if 'Tu écris une relance' in system
            else self.reponse
        )
        return ChatResult(json.dumps(data), 10, 10, 'faux', 1)


class ConversationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.canal = FauxCanal()
        faux = Adapter(
            'email',
            'E-mail',
            'Faux canal e-mail.',
            'email',
            'tests/test_conversations.py',
            self.canal.send,
            self.canal.confirm,
            self.canal.poll,
        )
        patcher = mock.patch.dict(ADAPTERS, {'email': faux})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        # Comme le programme : les lignes se lisent aussi par leur nom.
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        for nom in ('reply_delay_min_minutes', 'reply_delay_max_minutes'):
            set_setting(self.conn, f'channels.email.{nom}', 0, 'test')
        self.conn.executescript(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v1', 'Devis dictés', 'SMOKE_RUNNING', 't', 't'),"
            " ('v2', 'Autre business', 'SMOKE_RUNNING', 't', 't');"
            'INSERT INTO product_sheets(id, venture_id, summary, limits,'
            " created_at, updated_at) VALUES('ps1', 'v1', 'Dicter ses devis',"
            " 'Pas d''export Excel', 't', 't');"
            'INSERT INTO contacts(id, venture_id, display, funnel_state,'
            " created_at, updated_at) VALUES('c1', 'v1', 'Marc', 'CONTACTING',"
            " 't', 't'), ('c2', 'v2', 'Marc', 'CONTACTING', 't', 't');"
        )
        for contact in ('c1', 'c2'):
            self.conn.execute(
                'INSERT INTO contact_addresses(contact_id, channel, value,'
                " value_norm, created_at) VALUES(?, 'email', ?, ?, 't')",
                (contact, 'Marc@Exemple.fr', MARC),
            )
        self._envoi('t1', 'first', 'sent', sent_at=_il_y_a(hours=1))
        self.conn.execute(
            "UPDATE touches SET external_ref='<t1@serge>' WHERE id='t1'"
        )
        self.conn.execute(
            "UPDATE canaux SET polled_at=? WHERE id='email'", (utcnow(),)
        )
        self.conn.commit()
        self.modele = FauxModele()
        self.tour = 0

    # --- Outils du test ---------------------------------------------------

    def _un(self, sql: str, params: tuple = ()) -> tuple:
        return tuple(self.conn.execute(sql, params).fetchone())

    def _tous(self, sql: str, params: tuple = ()) -> list[tuple]:
        return [tuple(r) for r in self.conn.execute(sql, params).fetchall()]

    def _envoi(
        self,
        ident: str,
        kind: str,
        status: str,
        *,
        contact: str = 'c1',
        sent_at: str = '',
    ) -> None:
        moment = sent_at or utcnow()
        self.conn.execute(
            'INSERT INTO touches(id, contact_id, venture_id, channel, address,'
            ' kind, status, subject, body, sent_at, idempotency_key,'
            " created_at, updated_at) VALUES(?, ?, 'v1', 'email', ?, ?, ?,"
            " 'Vos devis', 'Bonjour', ?, ?, ?, ?)",
            (
                ident,
                contact,
                MARC,
                kind,
                status,
                sent_at,
                ident,
                moment,
                moment,
            ),
        )
        self.conn.commit()

    def _recu(
        self,
        ref: str,
        texte: str,
        address: str = 'Marc@exemple.fr',
        refs: tuple[str, ...] = ('<t1@serge>',),
    ) -> None:
        self.canal.recus.append(
            Incoming(
                external_ref=ref,
                address=address,
                subject='Re: Vos devis',
                body=texte,
                message_ref=f'<{ref}@marc>',
                refs=refs,
            )
        )

    def _vider(self, now: str | None = None) -> None:
        for _ in range(20):
            fait = process_one(
                self.conn, 'conversations', now=now, caller=self.modele
            )
            if fait is None:
                break
        echecs = self._tous(
            "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
        )
        self.assertEqual(echecs, [])

    def _relever(self) -> None:
        """Un passage des déclencheurs horaires, 20 minutes plus tard."""
        self.tour += 1
        plus_tard = datetime.fromisoformat(utcnow()) + timedelta(
            minutes=20 * self.tour
        )
        self._vider(plus_tard.isoformat())

    def _envoyer(self, touch: str) -> None:
        enqueue_task(self.conn, 'envoyer_message', {'touch_id': touch})
        self.conn.commit()
        self._vider()

    def _premier_message_il_y_a_4_jours(self) -> None:
        self.conn.execute(
            "UPDATE touches SET sent_at=?, created_at=? WHERE id='t1'",
            (_il_y_a(days=4), _il_y_a(days=4)),
        )
        self.conn.commit()

    # --- Scénarios ----------------------------------------------------------

    def test_marc_repond_et_serge_lui_repond_dans_le_fil(self) -> None:
        self.modele.reponse = {
            'reaction': 'question',
            'reply': 'Pas encore, mais le PDF marche partout.',
            'requests': [{'kind': 'idée', 'text': 'Exporter vers Excel'}],
        }
        self._recu('m1', 'Ça marche avec Excel ?')
        self._relever()
        recu = self._tous(
            'SELECT id, contact_id, venture_id, status, reaction'
            ' FROM inbound_events'
        )
        self.assertEqual(len(recu), 1)
        self.assertEqual(recu[0][1:], ('c1', 'v1', 'attached', 'question'))
        # Le modèle a lu le fil (le premier message, puis la question) et la
        # fiche produit.
        lu = self.modele.recu[0]
        self.assertLess(lu.index('Bonjour'), lu.index('Ça marche avec Excel'))
        self.assertIn('export Excel', lu)
        self.assertEqual(len(self.canal.envoyes), 1)
        parti = self.canal.envoyes[0]
        self.assertEqual(
            (parti.address, parti.in_reply_to, parti.kind, parti.body),
            (
                'Marc@exemple.fr',
                '<m1@marc>',
                'reply',
                'Pas encore, mais le PDF marche partout.',
            ),
        )
        self.assertEqual(
            self._un(
                "SELECT status, reply_to FROM touches WHERE kind='reply'"
            ),
            ('sent', recu[0][0]),
        )
        self.assertEqual(
            self._un("SELECT funnel_state FROM contacts WHERE id='c1'"),
            ('ENGAGED',),
        )
        self.assertEqual(
            self._tous('SELECT kind, text, contact_id FROM customer_requests'),
            [('idée', 'Exporter vers Excel', 'c1')],
        )
        # Relever de nouveau : le message n'est pas réécrit, rien ne repart.
        self._relever()
        self.assertEqual(self._un('SELECT COUNT(*) FROM inbound_events'), (1,))
        self.assertEqual(len(self.canal.envoyes), 1)

    def test_un_inconnu_n_est_pas_traite(self) -> None:
        self._recu('m9', 'Bonjour', address='inconnu@ailleurs.fr', refs=())
        self._relever()
        self.assertEqual(
            self._tous('SELECT contact_id, status FROM inbound_events'),
            [('', 'unattached')],
        )
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM tasks'
                " WHERE invocation_id='traiter_reponse'"
            ),
            (0,),
        )

    def test_deux_messages_coup_sur_coup_une_seule_reponse(self) -> None:
        self._recu('m1', 'Bonjour')
        self._recu('m2', 'Et le prix ?', refs=())
        process_one(self.conn, 'conversations', caller=self.modele)
        self.assertEqual(
            self._un(
                "SELECT COUNT(*) FROM inbound_events WHERE contact_id='c1'"
            ),
            (2,),
        )
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM tasks'
                " WHERE invocation_id='traiter_reponse'"
            ),
            (1,),
        )

    def test_stop_desinscrit_partout(self) -> None:
        self._envoi('t2', 'first', 'pending', contact='c2')
        self.modele.reponse = {'reaction': 'désinscription', 'reply': ''}
        self._recu('m1', 'STOP')
        self._relever()
        self.assertEqual(self.canal.envoyes, [])
        self.assertEqual(
            self._tous('SELECT id, funnel_state FROM contacts ORDER BY id'),
            [('c1', 'OPTED_OUT'), ('c2', 'OPTED_OUT')],
        )
        self.assertEqual(
            self._un("SELECT status FROM touches WHERE id='t2'"),
            ('cancelled',),
        )
        self.assertEqual(
            self._tous(
                'SELECT channel FROM blocklist WHERE subject_hash=?',
                (subject_hash(MARC),),
            ),
            [('*',)],
        )
        titre, payload = self._un(
            "SELECT title, payload_json FROM tickets WHERE type='FYI'"
        )
        self.assertEqual(titre, "Un contact s'est désinscrit")
        self.assertIn('Marc (c1)', json.loads(payload)['contenu'])
        self.assertEqual(
            self._un("SELECT COUNT(*) FROM touches WHERE kind='reply'"), (0,)
        )

    def test_un_envoi_interrompu_n_est_jamais_renvoye(self) -> None:
        self._envoi('t3', 'reply', 'sending')
        self.canal.deja_partis['t3'] = '<t3@serge>'
        self._envoyer('t3')
        self.assertEqual(self.canal.envoyes, [])
        self.assertEqual(
            self._un("SELECT status, external_ref FROM touches WHERE id='t3'"),
            ('sent', '<t3@serge>'),
        )
        # Pas parti : il part, une seule fois.
        self._envoi('t4', 'reply', 'sending')
        self._envoyer('t4')
        enqueue_task(
            self.conn, 'envoyer_message', {'touch_id': 't4'}, key='encore'
        )
        self.conn.commit()
        self._vider()
        self.assertEqual([m.touch_id for m in self.canal.envoyes], ['t4'])

    def test_une_adresse_bloquee_n_est_jamais_ecrite(self) -> None:
        self.conn.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, reason,'
            " added_at) VALUES('b1', '*', ?, 'test', 't')",
            (subject_hash(MARC),),
        )
        self._envoi('t5', 'reply', 'pending')
        self._envoyer('t5')
        self.assertEqual(self.canal.envoyes, [])
        self.assertEqual(
            self._un("SELECT status, last_error FROM touches WHERE id='t5'"),
            ('cancelled', 'BLOCKLISTED'),
        )

    def test_le_delai_de_reponse_est_tire_entre_les_reglages(self) -> None:
        for nom, minutes in (('max', 20), ('min', 5)):
            set_setting(
                self.conn,
                f'channels.email.reply_delay_{nom}_minutes',
                minutes,
                't',
            )
        self.modele.reponse = {'reaction': 'question', 'reply': 'Oui.'}
        self._recu('m1', 'Ça marche ?')
        self._vider()
        self.assertEqual(self.canal.envoyes, [])
        (attente,) = self._un(
            "SELECT not_before FROM tasks WHERE invocation_id='envoyer_message'"
        )
        minutes = (
            datetime.fromisoformat(attente) - datetime.fromisoformat(utcnow())
        ) / timedelta(minutes=1)
        self.assertTrue(4.9 < minutes <= 20, minutes)

    def test_une_relance_part_dans_le_fil(self) -> None:
        self._premier_message_il_y_a_4_jours()
        self._vider()
        self.assertEqual(
            self._tous(
                'SELECT status, followup_of, body FROM touches'
                " WHERE kind='followup'"
            ),
            [('sent', 't1', RELANCE)],
        )
        self.assertEqual(self.canal.envoyes[0].in_reply_to, '<t1@serge>')
        # La suivante attend 7 jours.
        self._relever()
        self.assertEqual(len(self.canal.envoyes), 1)

    def test_pas_de_relance_si_marc_a_ecrit_ou_boite_pas_relevee(self) -> None:
        self._premier_message_il_y_a_4_jours()
        self.conn.execute(
            'INSERT INTO inbound_events(id, contact_id, channel, status,'
            " received_at) VALUES('i1', 'c1', 'email', 'attached', ?)",
            (_il_y_a(days=1),),
        )
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE id='releve_des_canaux'"
        )
        self.conn.commit()
        self._vider()
        self.assertEqual(self.canal.envoyes, [])
        # Une réponse d'absence n'arrête pas les relances, mais une boîte
        # pas relevée depuis 2 heures, si.
        self.conn.execute("UPDATE inbound_events SET status='ignored'")
        self.conn.execute(
            "UPDATE canaux SET polled_at=? WHERE id='email'",
            (_il_y_a(hours=2),),
        )
        self.conn.commit()
        self._relever()
        self.assertEqual(self.canal.envoyes, [])
        self.conn.execute(
            "UPDATE canaux SET polled_at=? WHERE id='email'", (utcnow(),)
        )
        self.conn.commit()
        self._relever()
        self.assertEqual(len(self.canal.envoyes), 1)


if __name__ == '__main__':
    unittest.main()
