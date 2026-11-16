#!/usr/bin/env python3
"""Appeler un humain quand une page le demande (un captcha), décision Q97.

Le modèle est un faux, l'écran du vrai Chrome aussi ; la file,
l'interpréteur, les tickets et la base sont réels. Les réponses de
l'humain sont écrites comme le fait le bot Discord (``noter_reponse``).

Scénarios :
- au captcha, la tâche s'arrête et un ticket demande si un humain est
  prêt ; « Je suis prêt » la fait repartir ; au même blocage, un second
  ticket envoie le lien de l'écran, et « C'est fait » la laisse finir ;
- sans « C'est fait » à temps, le ticket est annulé et la tâche s'arrête
  de nouveau, avec un nouveau « êtes-vous prêts ? » ;
- « Abandonner » : la tâche repart et continue sans humain ;
- sans onglet du vrai Chrome, l'outil le dit au modèle.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge import aide_humaine  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402

MAINTENANT = '2026-11-16T15:00:00+00:00'


class FauxPayeur:
    """Appelle « Appeler un humain » au captcha, puis répond ce que
    l'outil lui a dit."""

    def __init__(self) -> None:
        self.resultats: list[dict[str, Any]] = []

    def __call__(self, _key, name, messages, **_kw) -> ChatResult:
        dernier = messages[-1]
        if dernier.get('role') == 'tool':
            resultat = json.loads(dernier['content'])
            self.resultats.append(resultat)
            texte = json.dumps({'text': json.dumps(resultat)})
            return ChatResult(texte, 1, 1, name, 1)
        appel = ToolCall(
            'h',
            'appeler_un_humain',
            json.dumps({'raison': 'un captcha sur la page de Stripe'}),
        )
        return ChatResult('', 1, 1, name, 1, (appel,))


class FausseHorloge:
    """Le temps de l'outil : chaque pause avance de 5 secondes, et peut
    faire répondre l'humain."""

    def __init__(self, pendant_la_pause: Any = None) -> None:
        self.t = 0.0
        self.pendant_la_pause = pendant_la_pause

    def monotonic(self) -> float:
        return self.t

    def sleep(self, secondes: float) -> None:
        self.t += secondes
        if self.pendant_la_pause is not None:
            self.pendant_la_pause()


class AideHumaineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    {
                        'id': 'payeur',
                        'type': 'llm',
                        'prompt': 'Paie.',
                        'tools': [
                            {
                                'tool': 'appeler_un_humain',
                                'mode': 'callable',
                                'params': {
                                    'task_id': {
                                        'source': 'task',
                                        'value': 'task_id',
                                    }
                                },
                            }
                        ],
                    }
                ],
            },
        )
        self.conn.execute('UPDATE triggers SET enabled=0')
        set_heartbeat(self.conn, True)
        self.task_id = str(enqueue_task(self.conn, 'payeur', {'cle': 'a'}))
        self.conn.commit()
        self.modele = FauxPayeur()
        self.ecran = mock.patch.object(
            aide_humaine, 'montrer', return_value=True
        )
        self.montrer = self.ecran.start()
        self.addCleanup(self.ecran.stop)

    def _tourner(self, horloge: FausseHorloge | None = None) -> None:
        with mock.patch.object(
            aide_humaine, 'time', horloge or FausseHorloge()
        ):
            process_one(self.conn, 'works', now=MAINTENANT, caller=self.modele)

    def _statut(self) -> str:
        return str(
            self.conn.execute(
                'SELECT status FROM tasks WHERE id=?', (self.task_id,)
            ).fetchone()[0]
        )

    def _tickets(self) -> list[tuple[str, str]]:
        return [
            (str(r[0]), str(r[1]))
            for r in self.conn.execute(
                'SELECT type, state FROM tickets WHERE type LIKE ?'
                ' ORDER BY created_at, rowid',
                ('GUICHET%',),
            )
        ]

    def _dernier(self, kind: str) -> str:
        return str(
            self.conn.execute(
                'SELECT id FROM tickets WHERE type=?'
                ' ORDER BY created_at DESC, rowid DESC LIMIT 1',
                (kind,),
            ).fetchone()[0]
        )

    def _repondre(self, kind: str, acte: str) -> None:
        noter_reponse(self.conn, self._dernier(kind), acte, '', 'discord:1')
        self.conn.commit()

    def test_pret_puis_c_est_fait(self) -> None:
        self._tourner()
        self.assertEqual(self._statut(), 'blocked')
        self.assertEqual(self._tickets(), [('GUICHET_PRET', 'OPEN')])
        self._repondre('GUICHET_PRET', 'pret')
        self.assertEqual(self._statut(), 'ready')
        reponses = self.conn.execute(
            'SELECT value FROM task_params WHERE task_id=?'
            " AND name='reponses_de_julien'",
            (self.task_id,),
        ).fetchone()[0]
        self.assertIn('rappelle le même outil', reponses)
        self.assertNotIn('Ne redemande pas', reponses)

        horloge = FausseHorloge(lambda: self._repondre('GUICHET', 'cest_fait'))
        self._tourner(horloge)
        self.assertEqual(self._statut(), 'done')
        self.assertTrue(self.modele.resultats[-1]['ok'])
        self.montrer.assert_called_with(self.task_id)
        charge = json.loads(
            self.conn.execute(
                'SELECT payload_json FROM tickets WHERE id=?',
                (self._dernier('GUICHET'),),
            ).fetchone()[0]
        )
        self.assertTrue(charge['lien_stream'].endswith('/owner/vrai-chrome'))
        etapes = [
            json.loads(r[0])['etape']
            for r in self.conn.execute(
                "SELECT payload_json FROM events WHERE type='human.help'"
                ' ORDER BY rowid'
            )
        ]
        self.assertEqual(etapes, ['pret', 'ecran', 'fait'])

    def test_sans_reponse_a_temps_on_redemande(self) -> None:
        self._tourner()
        self._repondre('GUICHET_PRET', 'pret')
        self._tourner(FausseHorloge())
        self.assertEqual(self._statut(), 'blocked')
        # Le premier a sa réponse ; le lien de l'écran est annulé ; un
        # nouveau « êtes-vous prêts ? » attend.
        self.assertEqual(
            self._tickets()[1:],
            [('GUICHET', 'CANCELLED'), ('GUICHET_PRET', 'OPEN')],
        )

    def test_abandonner_la_tache_continue_sans_humain(self) -> None:
        self._tourner()
        self._repondre('GUICHET_PRET', 'abandonner')
        self.assertEqual(self._statut(), 'ready')
        self._tourner()
        self.assertEqual(self._statut(), 'done')
        self.assertEqual(self.modele.resultats[-1]['code'], 'sans_humain')

    def test_sans_onglet_du_vrai_chrome_l_outil_le_dit(self) -> None:
        self._tourner()
        self._repondre('GUICHET_PRET', 'pret')
        self.montrer.return_value = False
        self._tourner()
        self.assertEqual(self._statut(), 'done')
        self.assertEqual(self.modele.resultats[-1]['code'], 'pas_d_ecran')


if __name__ == '__main__':
    unittest.main()
