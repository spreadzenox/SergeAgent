#!/usr/bin/env python3
"""demande_capacite : ticket REQUESTED, refus si vide, pas de doublon.

Une demande faite pendant une tâche la gèle : elle n'écrit rien et attend
la réponse de Julien, sans limite de temps ; sa réponse (« Faire sans », ou
un texte libre) la fait repartir du début, avec la réponse (lot 11).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.demande_capacite import CapaciteError, poser_demande  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets.lifecycle import decide  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402


class DemandeCapaciteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.conn.close()

    def test_pose_un_ticket_ouvert(self) -> None:
        out = poser_demande(
            self.conn,
            'écrire sur LinkedIn',
            point='classify_reply',
            contexte='pas de canal',
            types=self.types,
        )
        self.assertTrue(out['ok'])
        self.assertFalse(out['deja'])
        self.assertEqual(out['type'], 'REQUESTED')
        row = self.conn.execute(
            'SELECT type, title, state, payload_json FROM tickets WHERE id=?',
            (out['ticket_id'],),
        ).fetchone()
        self.assertEqual(row[0], 'REQUESTED')
        self.assertEqual(row[1], 'écrire sur LinkedIn')
        self.assertEqual(row[2], 'OPEN')
        payload = json.loads(row[3])
        self.assertEqual(payload['demande'], 'écrire sur LinkedIn')
        self.assertEqual(payload['point_llm'], 'classify_reply')
        self.assertEqual(payload['contexte'], 'pas de canal')

    def test_besoin_vide_refuse(self) -> None:
        with self.assertRaises(CapaciteError):
            poser_demande(self.conn, '   ', types=self.types)

    def test_meme_besoin_deja_ouvert(self) -> None:
        first = poser_demande(
            self.conn, 'navigateur', point='p1', types=self.types
        )
        again = poser_demande(
            self.conn, 'navigateur', point='p1', types=self.types
        )
        self.assertTrue(again['deja'])
        self.assertEqual(again['ticket_id'], first['ticket_id'])
        n = self.conn.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
        self.assertEqual(n, 1)

    def _redacteur(self) -> str:
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    {'id': 'redacteur', 'type': 'llm', 'prompt': 'Écris.'}
                ],
            },
        )
        task_id = str(enqueue_task(self.conn, 'redacteur', {}))
        # Seule la tâche du rédacteur tourne : pas de déclencheur horaire.
        self.conn.execute('UPDATE triggers SET enabled=0')
        set_heartbeat(self.conn, True)
        self.conn.commit()
        return task_id

    def test_une_demande_gele_la_tache_jusqu_a_la_reponse(self) -> None:
        """Toute invocation peut demander à Julien ; sa tâche s'arrête là.

        L'outil « Demander une nouvelle capacité » est donné partout : le
        faux modèle l'appelle deux fois (une demande vide, refusée, puis
        une vraie). La tâche est gelée, le modèle n'est plus appelé. « Faire
        sans » la fait repartir : le modèle lit la réponse et rend la sienne.
        """
        task_id = self._redacteur()
        seen: list[list] = []
        lus: list[str] = []

        def model(_key, name, messages, **kwargs):
            seen.append([t['function']['name'] for t in kwargs['tools']])
            lus.append(json.dumps(messages, ensure_ascii=False))
            if 'reponses_de_julien' in lus[-1]:
                return ChatResult('Fait, sans LinkedIn.', 5, 5, name, 1)
            calls = (
                ToolCall('c1', 'demande_capacite', '{"need": " "}'),
                ToolCall(
                    'c2',
                    'demande_capacite',
                    json.dumps(
                        {
                            'summary': 'Écrire sur LinkedIn',
                            'need': 'Un compte LinkedIn et un outil pour y'
                            ' publier, avec le détail de ce qu’il faut.',
                        }
                    ),
                ),
            )
            return ChatResult('', 5, 5, name, 1, calls)

        process_one(
            self.conn, 'works', now='2026-09-28T10:00:00+00:00', caller=model
        )
        self.assertEqual(seen[0], ['demande_capacite'])
        self.assertEqual(len(seen), 1, 'gelée, la tâche ne rappelle pas')
        statut = self.conn.execute(
            'SELECT status, last_error FROM tasks WHERE id=?', (task_id,)
        ).fetchone()
        self.assertEqual(statut[0], 'blocked')
        self.assertIn('Julien', statut[1])
        row = self.conn.execute(
            'SELECT id, title, payload_json, ref_table, ref_id FROM tickets'
            " WHERE type='REQUESTED'"
        ).fetchone()
        self.assertEqual(row[1], 'Écrire sur LinkedIn')
        charge = json.loads(row[2])
        self.assertEqual(charge['en_bref'], 'Écrire sur LinkedIn')
        self.assertIn('le détail', charge['demande'])
        self.assertEqual(charge['point_llm'], 'redacteur')
        self.assertEqual((row[3], row[4]), ('tasks', task_id))
        # Sans réponse, rien ne repart.
        self.assertIsNone(
            process_one(
                self.conn,
                'works',
                now='2026-10-28T10:00:00+00:00',
                caller=model,
            )
        )
        decide(self.conn, str(row[0]), 'APPROVED', actor='owner')
        noter_reponse(self.conn, str(row[0]), 'faire_sans', '', 'owner')
        self.conn.commit()
        process_one(
            self.conn, 'works', now='2026-10-28T10:00:00+00:00', caller=model
        )
        self.assertIn('fais sans', lus[-1])
        self.assertIn('Ta demande : Écrire sur LinkedIn', lus[-1])
        self.assertEqual(
            self.conn.execute(
                'SELECT status FROM tasks WHERE id=?', (task_id,)
            ).fetchone()[0],
            'done',
        )
        evenements = [
            r[0]
            for r in self.conn.execute(
                "SELECT type FROM events WHERE type LIKE 'task.%' ORDER BY id"
            )
        ]
        self.assertEqual(
            evenements, ['task.frozen', 'task.thawed', 'task.done']
        )

    def test_une_reponse_libre_arrive_au_modele(self) -> None:
        task_id = self._redacteur()
        ticket = poser_demande(
            self.conn,
            'Une adresse de contact',
            point='redacteur',
            resume='Adresse de contact',
            task_id=task_id,
            types=self.types,
        )
        self.assertTrue(ticket['gel'])
        self.conn.execute(
            "UPDATE tasks SET status='blocked' WHERE id=?", (task_id,)
        )
        noter_reponse(
            self.conn,
            ticket['ticket_id'],
            'reponse_libre',
            'Pas d’adresse de contact pour l’instant.',
            'owner',
        )
        valeur = self.conn.execute(
            'SELECT value FROM task_params WHERE task_id=?'
            " AND name='reponses_de_julien'",
            (task_id,),
        ).fetchone()[0]
        self.assertIn('Ta demande : Adresse de contact', valeur)
        self.assertIn('Pas d’adresse de contact pour l’instant.', valeur)
        # La même demande, de la même tâche, encore ouverte : le même ticket.
        again = poser_demande(
            self.conn,
            'Une adresse de contact',
            point='redacteur',
            task_id=task_id,
            types=self.types,
        )
        self.assertEqual(again['ticket_id'], ticket['ticket_id'])


if __name__ == '__main__':
    unittest.main()
