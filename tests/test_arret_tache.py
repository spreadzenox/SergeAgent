#!/usr/bin/env python3
"""Arrêter une tâche en plein travail (lot 10, correctifs du 15 novembre 2026).

Le modèle est un faux ; la file, l'interpréteur et la base sont réels.

Scénarios :
- le coupe-circuit pendant une tâche : elle s'arrête avant l'outil suivant,
  n'écrit rien, revient dans la file, et repart du début au redémarrage ;
- le plafond de dépense d'une tâche : elle échoue avec la raison, et un
  ticket prévient Julien et Clem ;
- plus de crédit chez OpenRouter : la tâche attend une demi-heure au lieu
  d'échouer, et un seul ticket prévient, même pour plusieurs tâches ;
- le chien de garde arrête la file quand une tâche ne s'arrête pas
  d'elle-même après le coupe-circuit ;
- chaque appel d'outil est noté au journal.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.halt import watchdog  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult, LlmError, ToolCall  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402

MAINTENANT = '2026-11-15T15:00:00+00:00'


class ArretTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    {'id': 'redacteur', 'type': 'llm', 'prompt': 'Écris.'}
                ],
            },
        )
        self.conn.execute('UPDATE triggers SET enabled=0')
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _tache(self, cle: str = 'a') -> str:
        task_id = str(enqueue_task(self.conn, 'redacteur', {'cle': cle}))
        self.conn.commit()
        return task_id

    def _etat(self, task_id: str) -> tuple:
        return tuple(
            self.conn.execute(
                'SELECT status, last_error, not_before FROM tasks WHERE id=?',
                (task_id,),
            ).fetchone()
        )

    def _fyi(self) -> list[str]:
        return [
            str(r[0])
            for r in self.conn.execute(
                "SELECT title FROM tickets WHERE type='FYI' ORDER BY rowid"
            )
        ]

    @staticmethod
    def _outil(name: str, cout: float = 0.01) -> ChatResult:
        appel = ToolCall('h', 'lire_historique', json.dumps({'table': 'x'}))
        return ChatResult('', 10, 10, name, 1, (appel,), cost_usd=cout)

    def test_le_coupe_circuit_arrete_la_tache_et_elle_reprend(self) -> None:
        task_id = self._tache()
        appels: list[int] = []

        def model(_key, name, _messages, **_kw):
            appels.append(1)
            if len(appels) == 1:
                # Julien appuie sur le bouton rouge pendant l'appel.
                set_heartbeat(self.conn, False)
                self.conn.commit()
                return self._outil(name)
            return ChatResult('{"text": "fini"}', 1, 1, name, 1)

        process_one(self.conn, 'works', now=MAINTENANT, caller=model)
        self.assertEqual(self._etat(task_id)[0], 'ready')
        self.assertEqual(len(appels), 1)
        types = [
            r[0]
            for r in self.conn.execute(
                "SELECT type FROM events WHERE type LIKE 'task.%'"
            )
        ]
        self.assertEqual(types, ['task.cut'])
        # Arrêté, Serge ne la relance pas ; redémarré, elle repart du début.
        self.assertIsNone(
            process_one(self.conn, 'works', now=MAINTENANT, caller=model)
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()
        process_one(self.conn, 'works', now=MAINTENANT, caller=model)
        self.assertEqual(self._etat(task_id)[0], 'done')

    def test_le_plafond_d_une_tache_l_arrete_et_previent(self) -> None:
        self.assertEqual(
            set_setting(self.conn, 'budget.task_max_eur', 0.5, 'test'), ''
        )
        self.conn.commit()
        task_id = self._tache()

        def model(_key, name, _messages, **_kw):
            return self._outil(name, cout=1.0)

        process_one(self.conn, 'works', now=MAINTENANT, caller=model)
        statut, raison, _ = self._etat(task_id)
        self.assertEqual(statut, 'failed')
        self.assertIn('plafond de dépense de la tâche atteint', raison)
        self.assertEqual(
            self._fyi(), ['Une tâche a atteint son plafond de dépense']
        )
        outils = [
            json.loads(r[0])
            for r in self.conn.execute(
                "SELECT payload_json FROM events WHERE type='tool.call'"
            )
        ]
        self.assertEqual(len(outils), 0, 'arrêtée avant l’outil')

    def test_le_plafond_compte_seulement_la_tentative_en_cours(self) -> None:
        """Une tâche qui repart du début (après une panne) a de nouveau tout
        son plafond : la dépense de sa tentative perdue ne compte pas."""
        self.assertEqual(
            set_setting(self.conn, 'budget.task_max_eur', 0.5, 'test'), ''
        )
        task_id = self._tache()
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in, tokens_out,'
            ' latency_ms, verdict, cost_usd, task_id, created_at) VALUES'
            "('redacteur', 'smart', 'faux', 1, 1, 1, 'outil', 10.0, ?,"
            " '2026-11-14T10:00:00+00:00')",
            (task_id,),
        )
        self.conn.commit()
        appels: list[int] = []

        def model(_key, name, _messages, **_kw):
            appels.append(1)
            if len(appels) == 1:
                return self._outil(name, cout=0.01)
            return ChatResult('{"text": "fini"}', 1, 1, name, 1)

        process_one(self.conn, 'works', now=MAINTENANT, caller=model)
        self.assertEqual(self._etat(task_id)[0], 'done')

    def test_sans_credit_la_tache_attend_et_un_seul_ticket(self) -> None:
        taches = [self._tache('a'), self._tache('b')]

        def model(*_args, **_kw):
            raise LlmError(
                'CREDIT: OpenRouter HTTP 402, plus de crédit : Insufficient'
            )

        for _ in taches:
            process_one(self.conn, 'works', now=MAINTENANT, caller=model)
        for task_id in taches:
            statut, _raison, plus_tard = self._etat(task_id)
            self.assertEqual(statut, 'ready')
            self.assertGreater(plus_tard, MAINTENANT)
        self.assertEqual(self._fyi(), ['OpenRouter n’a plus de crédit'])

    def test_chaque_outil_est_note_au_journal(self) -> None:
        task_id = self._tache()
        appels: list[int] = []

        def model(_key, name, _messages, **_kw):
            appels.append(1)
            if len(appels) == 1:
                return self._outil(name)
            return ChatResult('{"text": "fini"}', 1, 1, name, 1)

        process_one(self.conn, 'works', now=MAINTENANT, caller=model)
        self.assertEqual(self._etat(task_id)[0], 'done')
        outil = json.loads(
            self.conn.execute(
                "SELECT payload_json FROM events WHERE type='tool.call'"
            ).fetchone()[0]
        )
        self.assertEqual(
            (outil['task'], outil['tool'], outil['args']),
            (task_id, 'lire_historique', '{"table": "x"}'),
        )


class ChienDeGardeTests(unittest.TestCase):
    def test_il_arrete_la_file_si_la_tache_ne_s_arrete_pas(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        base = Path(dossier.name) / 'serge.db'
        conn = sqlite3.connect(base)
        init_schema(conn)
        set_heartbeat(conn, True)
        conn.commit()
        arrets: list[int] = []
        fini = threading.Event()

        def arreter(code: int) -> None:
            arrets.append(code)
            fini.set()

        watchdog(base, lambda: 't_1', every_s=0.01, grace_s=0.1, stop=arreter)
        self.assertFalse(fini.wait(0.3), 'Serge en marche : rien')
        set_heartbeat(conn, False)
        conn.commit()
        conn.close()
        self.assertTrue(fini.wait(5))
        self.assertEqual(arrets, [3])


if __name__ == '__main__':
    unittest.main()
