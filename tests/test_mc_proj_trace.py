#!/usr/bin/env python3
"""Trace d'exécution d'une tâche : fiche + contexte (golden).

La fiche d'une tâche dit d'abord l'essentiel (son état, son erreur, ce qui
l'a lancée, sa durée), puis montre son journal (ce qu'elle a écrit, ce
qu'on lui a refusé) et ses appels d'outils, dans l'ordre : un appel refusé
avec sa raison, et sous un appel ce que la page a signalé (un clic qui n'a
rien fait, et la réponse du site qui dit pourquoi). Le fait d'une tâche,
ouvert depuis le journal, mène à cette fiche.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.funnels.contacts import add_address  # noqa: E402
from serge.mc.proj_taches import fiche_tache  # noqa: E402
from serge.mc.proj_trace import (  # noqa: E402
    cadre_appels,
    cadres_journal,
    project_trace,
)
from tests.taches_fixtures import invocations, tache  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'


class ProjTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, created_at, updated_at) VALUES(?,?,?,?,?)',
            (
                'p1',
                'v1',
                'Ada',
                't',
                't',
            ),
        )
        add_address(self.conn, 'p1', 'email', 'ada@x.io')
        invocations(self.conn, ('appeler', 'Appeler', 'prospection_lourde'))
        self.task = tache(
            self.conn,
            'appeler',
            {'venture_id': 'v1', 'contact_id': 'p1'},
            key='k1',
            status='failed',
            error='ligne occupée',
        )
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('invocation:appeler','task.failed','',?,?)",
            (json.dumps({'task': self.task}), NOW),
        )
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('runner','cycle','v1',?,?)",
            (json.dumps({'done': 2}), NOW),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_trace_complete(self) -> None:
        trace = project_trace(self.conn, self.task)
        self.assertEqual(trace['item']['kind'], 'Appeler')
        self.assertEqual(trace['item']['statut'], 'failed')
        self.assertEqual(trace['note'], 'ligne occupée')
        self.assertIsNone(trace['ticket'])
        self.assertEqual(trace['contact']['display'], 'Ada')
        kinds = [event['type'] for event in trace['evenements']]
        self.assertIn('task.failed', kinds)
        self.assertIn('cycle', kinds)
        stamps = [event['ts'] for event in trace['evenements']]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_la_fiche_montre_les_appels_d_outils(self) -> None:
        self.assertIsNone(cadre_appels(self.conn, self.task))
        self.conn.execute(
            "INSERT INTO tools(id, titre, capability_id) VALUES('agir',"
            " 'Agir dans le vrai Chrome', 'real_browser_action')"
        )
        for seconde, appel in enumerate(
            (
                {
                    'tool': 'agir',
                    'args': '{"action": "cliquer", "ref": "e154"}',
                    'ok': True,
                    'code': '',
                    'erreurs': [
                        'HTTP 429 : https://api.site.example/inscription?…'
                    ],
                },
                {
                    'tool': 'outil_sans_fiche',
                    'args': '{"text": "Continuer"}',
                    'ok': False,
                    'code': 'echec',
                    'detail': 'plusieurs éléments portent ce texte',
                },
                {'tool': 'agir', 'args': '{}', 'ok': False, 'code': ''},
            )
        ):
            self.conn.execute(
                'INSERT INTO events(actor, type, venture_id, payload_json,'
                " ts) VALUES('invocation:appeler', 'tool.call', '', ?, ?)",
                (
                    json.dumps({'task': self.task, **appel}),
                    f'2026-11-21T15:44:2{seconde}+00:00',
                ),
            )
        # L'appel d'une autre tâche n'y est pas.
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('invocation:x', 'tool.call', '', ?, ?)",
            (json.dumps({'task': 't_autre', 'tool': 'agir'}), NOW),
        )
        cadre = cadre_appels(self.conn, self.task)
        assert cadre is not None
        # L'heure part telle qu'elle est en base : la page l'écrit à
        # l'heure de celui qui lit.
        self.assertEqual(
            cadre['journal'],
            [
                {
                    'ts': '2026-11-21T15:44:20+00:00',
                    'texte': 'Agir dans le vrai Chrome'
                    '  {"action": "cliquer", "ref": "e154"}  → fait',
                    'sous': [
                        'la page : HTTP 429 :'
                        ' https://api.site.example/inscription?…'
                    ],
                },
                {
                    'ts': '2026-11-21T15:44:21+00:00',
                    'texte': 'outil_sans_fiche  {"text": "Continuer"}'
                    '  → refusé : plusieurs éléments portent ce texte',
                    'sous': [],
                },
                {
                    'ts': '2026-11-21T15:44:22+00:00',
                    'texte': 'Agir dans le vrai Chrome  {}  → refusé',
                    'sous': [],
                },
            ],
        )
        self.conn.row_factory = sqlite3.Row
        fiche = fiche_tache(self.conn, self.task)
        assert fiche is not None
        # Le journal de la tâche (comment elle a fini), puis ses appels.
        self.assertEqual(
            [c['titre'] for c in fiche['cadres']],
            ['Son journal', 'Ses appels d’outils'],
        )
        self.assertEqual(
            [f['texte'] for f in fiche['cadres'][0]['journal']],
            ['Tâche échouée'],
        )

    def test_le_journal_dit_ce_que_la_tache_a_ecrit(self) -> None:
        """Une ligne écrite : sa table et sa ligne, sans ses valeurs ; un
        refus : sa raison."""
        for sorte, fait in (
            (
                'write.updated',
                {'table': 'canaux', 'id': 'email', 'values': {'a': 'b'}},
            ),
            (
                'write.refused',
                {'table': 'web_accounts', 'reason': 'aucune ligne où id = X'},
            ),
            ('task.frozen', {'ticket': 't_1', 'spent_eur': 0.02}),
        ):
            self.conn.execute(
                'INSERT INTO events(actor, type, venture_id, payload_json,'
                " ts) VALUES('invocation:appeler', ?, '', ?, ?)",
                (sorte, json.dumps({'task': self.task, **fait}), NOW),
            )
        journal = cadres_journal(self.conn, self.task)[0]['journal']
        self.assertEqual(
            [fait['texte'] for fait in journal],
            [
                'Tâche échouée',
                'Ligne modifiée  canaux · email',
                'Écriture refusée  web_accounts : aucune ligne où id = X',
                'Tâche gelée : elle attend Julien'
                '  ticket : t_1, dépensé en euros : 0.02',
            ],
        )

    def test_la_fiche_dit_l_essentiel_d_abord(self) -> None:
        """L'état, l'erreur, ce qui a lancé la tâche et sa durée viennent
        avant la file et la priorité."""
        self.conn.execute(
            "UPDATE tasks SET origin='button', origin_ref='bouton_x:2026',"
            " started_at='2026-09-10T12:00:00+00:00',"
            " finished_at='2026-09-10T12:03:26+00:00' WHERE id=?",
            (self.task,),
        )
        self.conn.execute(
            'INSERT INTO triggers(id, title, invocation_id, event)'
            " VALUES('bouton_x', 'Appeler quelqu’un', 'appeler', 'button')"
        )
        self.conn.row_factory = sqlite3.Row
        fiche = fiche_tache(self.conn, self.task)
        assert fiche is not None
        self.assertEqual(
            [(c['k'], c['v']) for c in fiche['champs'][:7]],
            [
                ('Invocation', 'Appeler'),
                ('État', 'Échouée'),
                ('Erreur', 'ligne occupée'),
                ('Lancée par', 'le bouton « Appeler quelqu’un »'),
                ('Commencée', '2026-09-10T12:00:00+00:00'),
                ('Finie', '2026-09-10T12:03:26+00:00'),
                ('Durée', '3 min 26 s'),
            ],
        )

    def test_le_fait_d_une_tache_mene_a_sa_fiche(self) -> None:
        from serge.mc.proj_traces import project_fait_trace

        ident = self.conn.execute(
            "SELECT id FROM events WHERE type='task.failed'"
        ).fetchone()[0]
        self.conn.row_factory = sqlite3.Row
        fiche = project_fait_trace(self.conn, 'event', str(ident))
        assert fiche is not None
        self.assertEqual(
            fiche['enfants'],
            [
                {
                    'type': 'task',
                    'id': self.task,
                    'titre': 'La tâche : Appeler',
                }
            ],
        )
        self.assertIn({'k': 'Tâche', 'v': 'Appeler'}, fiche['champs'])

    def test_trace_inconnue(self) -> None:
        self.assertIsNone(project_trace(self.conn, 'wZZ'))
        self.assertIsNone(project_trace(self.conn, ''))


if __name__ == '__main__':
    unittest.main()
