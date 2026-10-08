#!/usr/bin/env python3
"""Le canal appel de bout en bout (lot 8, PR 3).

Seuls le pont téléphonique (sa réponse à « composer »), le fournisseur de
la voix en direct et le modèle sont des faux. Le pipeline en base,
l'interpréteur, les garde-fous, le journal des appels, l'agent vocal et
la pompe AudioSocket sont réels.

Scénarios :
- un appel part depuis le pipeline, avec son but ; un appel interrompu est
  retrouvé dans le journal, jamais recomposé ;
- hors des heures d'appel, l'appel attend le prochain créneau (Q83) ;
  le pont qui refuse pour un temps fait attendre aussi ; un refus net fait
  échouer l'envoi ;
- l'agent sait à qui il parle : sa fiche, son fil, le but de l'appel ; il
  note l'e-mail qu'on lui dicte ; un appelant inconnu reconnu par son nom
  est rattaché à sa fiche ;
- la transcription entre dans le fil et lance « Traiter une réponse » ; la
  suite part par e-mail si Serge a l'adresse, sinon Serge rappelle (Q83) ;
- un appel complet par la pompe AudioSocket : l'UUID dit le numéro, les
  outils demandés sont exécutés, la transcription des deux voix est rangée.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.adapters import ADAPTERS  # noqa: E402
from serge.channels.base import Adapter, Outgoing  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db, utcnow  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.voice.agent import (  # noqa: E402
    close_interrupted_calls,
    finish_call,
    hear,
    instructions,
    peer_from_uuid,
    run_tool_call,
    start_call,
    tools,
)
from serge.voice.audiosocket import encode  # noqa: E402
from serge.voice.ledger import VoiceLedger  # noqa: E402
from serge.voice.policy import default_ledger_path  # noqa: E402
from serge.voice.s2s import pump  # noqa: E402
from tests.test_conversations import FauxModele  # noqa: E402

MARC = '+33612345678'
MARDI_MIDI = '2026-09-08T10:30:00+00:00'
DIMANCHE = '2026-09-06T10:30:00+00:00'
SUITE = 'Voici la documentation promise.'


def _uuid(direction: str, phone: str) -> bytes:
    """L'UUID qu'écrit le plan d'appel d'Asterisk (kit/asterisk.py)."""
    peer = ('0' * 15 + phone.lstrip('+'))[-15:]
    sens = '1' if direction == 'inbound' else '2'
    return uuid.UUID(f'5e7e0000-0000-4000-{sens}{peer[:3]}-{peer[3:]}').bytes


class _Appel(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        root = Path(dossier.name)
        instance = root / 'instance.toml'
        instance.write_text('[features]\nphone_voice = true\n')
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_SYSTEM_ROOT': str(root),
                'SERGE_INSTANCE_FILE': str(instance),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        set_heartbeat(self.conn, True)
        for canal in ('email', 'voice'):
            for borne in ('min', 'max'):
                set_setting(
                    self.conn,
                    f'channels.{canal}.reply_delay_{borne}_minutes',
                    0,
                    't',
                )
        self.conn.executescript(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v1', 'Devis dictés', 'SMOKE_RUNNING', 't', 't');"
            'INSERT INTO product_sheets(id, venture_id, summary, created_at,'
            " updated_at) VALUES('ps1', 'v1', 'Dicter ses devis', 't', 't');"
            'INSERT INTO contacts(id, venture_id, display, funnel_state,'
            " created_at, updated_at) VALUES('c1', 'v1', 'Marc Durand',"
            " 'CONTACTING', 't', 't');"
            'INSERT INTO contact_addresses(contact_id, channel, value,'
            f" value_norm, created_at) VALUES('c1', 'phone', '{MARC}',"
            f" '{MARC}', 't');"
        )
        self.conn.commit()
        self.ledger = VoiceLedger(default_ledger_path())
        # La voix exige l'accord de la personne (garde-fous et pont).
        self.ledger.grant_consent(MARC, 'consent')
        self.composes: list[dict[str, str]] = []
        self.decision: dict[str, Any] = {
            'decision': 'allowed',
            'originated': True,
        }
        # Le pont est réel (numéro de la demande, délai de reprise, journal
        # des appels) ; seul « composer » est un faux.
        for cible, faux in (
            ('serge.channels.voice._bridge', self._pont),
            ('serge.voice.bridge.originate', self._composer),
        ):
            patcher = mock.patch(cible, side_effect=faux)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.mails: list[Outgoing] = []
        faux_mail = Adapter(
            'email',
            'E-mail',
            '',
            'email',
            'x.py',
            lambda m: self.mails.append(m) or f'<{m.touch_id}@serge>',
            lambda _m: '',
        )
        patcher = mock.patch.dict(ADAPTERS, {'email': faux_mail})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.modele = FauxModele()
        self.modele.reponse = {'reaction': 'intéressé', 'reply': SUITE}

    def _pont(
        self, path: str, payload: dict[str, str] | None = None
    ) -> dict[str, Any]:
        from urllib.parse import parse_qs, urlparse

        from serge.voice.bridge import originate_for_task

        if path.startswith('/calls'):
            task = parse_qs(urlparse(path).query)['task_id'][0]
            return {'calls': self.ledger.calls_for_task(task)}
        return originate_for_task(dict(payload or {}))

    def _composer(self, **demande: Any) -> dict[str, Any]:
        self.composes.append(demande)
        return {**self.decision, 'cdr_id': f'cdr_{len(self.composes)}'}

    def _un(self, sql: str, params: tuple = ()) -> tuple:
        return tuple(self.conn.execute(sql, params).fetchone())

    def _envoi(self, ident: str, status: str = 'pending') -> None:
        moment = utcnow()
        self.conn.execute(
            'INSERT INTO touches(id, contact_id, venture_id, channel, address,'
            ' kind, status, subject, body, idempotency_key, created_at,'
            " updated_at) VALUES(?, 'c1', 'v1', 'voice', ?, 'first', ?,"
            " 'Vos devis', 'Présenter les devis dictés', ?, ?, ?)",
            (ident, MARC, status, ident, moment, moment),
        )
        self.conn.commit()

    def _vider(self, heure: str = MARDI_MIDI) -> None:
        with mock.patch('serge.guards.check.utcnow', return_value=heure):
            for _ in range(20):
                if (
                    process_one(self.conn, 'conversations', caller=self.modele)
                    is None
                ):
                    break
        echecs = self.conn.execute(
            "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
        ).fetchall()
        self.assertEqual([tuple(e) for e in echecs], [])

    def _envoyer(self, ident: str, heure: str = MARDI_MIDI) -> None:
        enqueue_task(self.conn, 'envoyer_message', {'touch_id': ident})
        self.conn.commit()
        self._vider(heure)


class AppelSortantTests(_Appel):
    def test_un_appel_part_avec_son_but_et_n_est_jamais_recompose(
        self,
    ) -> None:
        self._envoi('t1')
        self._envoyer('t1')
        self.assertEqual(
            [
                (c['request_id'], c['to_e164'], c['purpose'], c['message'])
                for c in self.composes
            ],
            [('t1.1', MARC, 'prospection', 'Présenter les devis dictés')],
        )
        self.assertEqual(
            self._un("SELECT status, external_ref FROM touches WHERE id='t1'"),
            ('sent', 'cdr_1'),
        )
        # Interrompu après avoir composé : le journal le sait.
        self._envoi('t2', status='sending')
        with self.ledger._connect() as journal:
            journal.execute(
                'INSERT INTO calls(request_id, cdr_id, direction, to_e164,'
                ' to_hash, cli, purpose, task_id, decision, reason, created_at)'
                " VALUES('t2.1', 'cdr_t2', 'outbound', ?, 'h', '', 'prospection',"
                " 't2', 'allowed', 'allowed', ?)",
                (MARC, utcnow()),
            )
        self._envoyer('t2')
        self.assertEqual(len(self.composes), 1)
        self.assertEqual(
            self._un("SELECT status, external_ref FROM touches WHERE id='t2'"),
            ('sent', 'cdr_t2'),
        )

    def test_hors_des_heures_l_appel_attend(self) -> None:
        self._envoi('t1')
        self._envoyer('t1', heure=DIMANCHE)
        self.assertEqual(self.composes, [])
        self.assertEqual(
            self._un("SELECT status FROM touches WHERE id='t1'"), ('pending',)
        )
        # Il reprendra le lundi suivant à 10 h, heure de Paris.
        self.assertEqual(
            self._un(
                'SELECT COUNT(*) FROM tasks'
                " WHERE invocation_id='envoyer_message' AND not_before=?",
                ('2026-09-07T08:00:00+00:00',),
            ),
            (1,),
        )

    def test_le_pont_qui_refuse_pour_un_temps_fait_attendre(self) -> None:
        self.decision = {'decision': 'denied', 'reason': 'already_in_progress'}
        self._envoi('t1')
        self._envoyer('t1')
        status, erreur = self._un(
            "SELECT status, last_error FROM touches WHERE id='t1'"
        )
        self.assertEqual(status, 'pending')
        self.assertIn('already_in_progress', erreur)
        (attente,) = self._un(
            "SELECT not_before FROM tasks WHERE status='ready'"
            " AND invocation_id='envoyer_message'"
        )
        self.assertGreater(attente, utcnow())
        # Un refus net (adresse bloquée par le pont) fait échouer l'envoi.
        self.decision = {'decision': 'denied', 'reason': 'blocklisted'}
        self._envoi('t2')
        self._envoyer('t2')
        self.assertEqual(
            self._un("SELECT status FROM touches WHERE id='t2'"), ('failed',)
        )


class AgentTests(_Appel):
    def test_l_agent_sait_a_qui_il_parle_et_note_l_e_mail(self) -> None:
        self._envoi('t1', status='sent')
        appel = start_call(self.conn, 'outbound', MARC, 'cdr_1', 't1')
        assert appel is not None
        consigne = instructions(self.conn, appel)
        for attendu in (
            'Tu es Serge, au téléphone',
            'Marc Durand',
            'Présenter les devis dictés',
            'Dicter ses devis',
        ):
            self.assertIn(attendu, consigne)
        noms = {t['name'] for t in tools(self.conn, appel)}
        self.assertLessEqual({'chercher_contact', 'noter_adresse'}, noms)
        resultat = json.loads(
            run_tool_call(
                self.conn,
                appel,
                'noter_adresse',
                json.dumps(
                    {
                        'contact_id': 'c1',
                        'channel': 'email',
                        'value': 'marc@exemple.fr',
                    }
                ),
            )
        )
        self.assertTrue(resultat['ok'])
        hear(appel, 'Serge', 'Bonjour Marc, ici Serge.')
        hear(appel, 'Contact', 'Envoyez-moi la doc à marc@exemple.fr.')
        finish_call(self.conn, appel)
        self.assertEqual(
            self._un(
                'SELECT contact_id, status, channel, native_type, body FROM inbound_events'
            ),
            (
                'c1',
                'attached',
                'voice',
                'call',
                'Serge : Bonjour Marc, ici Serge.\nContact : Envoyez-moi la doc à marc@exemple.fr.',
            ),
        )
        # La suite part par e-mail : Serge a maintenant l'adresse (Q83).
        self._vider()
        self.assertEqual(
            [(m.address, m.body.startswith(SUITE)) for m in self.mails],
            [('marc@exemple.fr', True)],
        )
        self.assertEqual(len(self.composes), 0)

    def test_sans_e_mail_serge_rappelle(self) -> None:
        appel = start_call(self.conn, 'inbound', MARC, 'cdr_9')
        assert appel is not None
        hear(appel, 'Contact', 'Rappelez-moi pour le devis.')
        finish_call(self.conn, appel)
        self._vider()
        self.assertEqual(self.mails, [])
        self.assertEqual(
            [(c['to_e164'], c['purpose']) for c in self.composes],
            [(MARC, 'callback')],
        )

    def test_un_appelant_inconnu_reconnu_par_son_nom(self) -> None:
        appel = start_call(self.conn, 'inbound', '+33700000000', 'cdr_5')
        assert appel is not None
        self.assertNotIn('Marc Durand', instructions(self.conn, appel))
        trouve = json.loads(
            run_tool_call(
                self.conn, appel, 'chercher_contact', '{"query": "Durand"}'
            )
        )
        self.assertEqual(
            trouve['rows'],
            [
                {
                    'id': 'c1',
                    'name': 'Marc Durand',
                    'business': 'Devis dictés',
                    'stage': 'CONTACTING',
                }
            ],
        )
        hear(appel, 'Contact', 'Bonjour, c’est Marc Durand.')
        finish_call(self.conn, appel)
        self.assertEqual(
            self._un('SELECT contact_id, status FROM inbound_events'),
            ('c1', 'attached'),
        )

    def test_la_file_appels_coupee_fait_taire_l_agent(self) -> None:
        self.conn.execute("UPDATE queues SET enabled=0 WHERE id='voice'")
        self.assertIsNone(start_call(self.conn, 'inbound', MARC, 'cdr_8'))

    def test_un_appel_coupe_par_un_redemarrage_est_clos(self) -> None:
        appel = start_call(self.conn, 'inbound', MARC, 'cdr_7')
        assert appel is not None
        self.assertEqual(close_interrupted_calls(self.conn), 1)
        self.assertEqual(
            self._un('SELECT status FROM tasks WHERE id=?', (appel.task_id,)),
            ('failed',),
        )

    def test_l_uuid_dit_le_sens_et_le_numero(self) -> None:
        self.assertEqual(
            peer_from_uuid(_uuid('outbound', MARC)), ('outbound', MARC)
        )
        self.assertEqual(
            peer_from_uuid(_uuid('inbound', '+18005551234')),
            ('inbound', '+18005551234'),
        )
        self.assertEqual(peer_from_uuid(b'x' * 16), ('', ''))


class PompeTests(_Appel):
    def test_un_appel_complet_par_la_pompe(self) -> None:
        with self.ledger._connect() as journal:
            journal.execute(
                'INSERT INTO calls(request_id, cdr_id, direction, to_e164,'
                ' to_hash, cli, purpose, task_id, decision, reason, created_at)'
                " VALUES('t1.1', 'cdr_t1', 'outbound', ?, ?, '', 'prospection',"
                " 't1', 'allowed', 'allowed', ?)",
                (
                    MARC,
                    __import__('hashlib').sha256(MARC.encode()).hexdigest(),
                    datetime.now(UTC).isoformat(),
                ),
            )
        self._envoi('t1', status='sent')
        session = mock.Mock()
        session.ws.sock = mock.Mock()
        session.poll.side_effect = [
            [('transcript', 'Bonjour Marc, ici Serge.')],
            [('heard', 'Oui, envoyez la doc à marc@exemple.fr.')],
            [
                (
                    'tool',
                    {
                        'call_id': 'o1',
                        'name': 'noter_adresse',
                        'arguments': json.dumps(
                            {
                                'contact_id': 'c1',
                                'channel': 'email',
                                'value': 'marc@exemple.fr',
                            }
                        ),
                    },
                )
            ],
        ] + [[]] * 1000
        gauche, droite = socket.socketpair()

        def raccrocher() -> None:
            droite.sendall(encode('uuid', _uuid('outbound', MARC)))
            # On raccroche une fois le résultat de l'outil rendu à l'agent.
            fin = time.monotonic() + 5
            while (
                not session.send_tool_output.called and time.monotonic() < fin
            ):
                time.sleep(0.02)
            droite.sendall(encode('hangup'))

        threading.Thread(target=raccrocher, daemon=True).start()
        with mock.patch(
            'serge.voice.s2s.open_session', return_value=session
        ) as ouvre:
            pump(gauche, max_s=8)
        droite.close()
        consigne = ouvre.call_args[0][1]
        self.assertIn('Présenter les devis dictés', consigne)
        sortie = session.send_tool_output.call_args[0]
        self.assertEqual(
            (sortie[0], json.loads(sortie[1])['ok']), ('o1', True)
        )
        conn = sqlite3.connect(default_canon_path())
        try:
            body = conn.execute(
                "SELECT body FROM inbound_events WHERE external_ref='cdr_t1'"
            ).fetchone()[0]
            adresse = conn.execute(
                "SELECT value FROM contact_addresses WHERE channel='email'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(
            body,
            'Serge : Bonjour Marc, ici Serge.\nContact : Oui, envoyez la doc à marc@exemple.fr.',
        )
        self.assertEqual(adresse, 'marc@exemple.fr')
        with self.ledger._connect() as journal:
            issue = journal.execute(
                "SELECT outcome, claimed_at<>'' FROM calls WHERE cdr_id='cdr_t1'"
            ).fetchone()
        self.assertEqual(tuple(issue), ('completed', 1))


if __name__ == '__main__':
    unittest.main()
