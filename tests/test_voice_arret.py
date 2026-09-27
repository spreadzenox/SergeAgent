#!/usr/bin/env python3
"""Serge arrêté : la voix ne décroche pas et aucun modèle ne parle.

Serge est arrêté par défaut ; il ne tourne que si quelqu'un l'a démarré
dans Mission Control. La voix lit cet interrupteur dans la base, en
lecture seule ; une base absente compte comme « arrêté ».
"""

from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import serge_demarre, set_heartbeat  # noqa: E402
from serge.db.store import open_db  # noqa: E402
from serge.voice import s2s, turn  # noqa: E402


class VoixArretTests(unittest.TestCase):
    def test_l_interrupteur_lu_par_la_voix(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / 'serge.db'
            self.assertFalse(serge_demarre(path))  # base absente
            conn = open_db(path)
            conn.commit()
            self.assertFalse(serge_demarre(path))  # base neuve : arrêté
            set_heartbeat(conn, True)
            conn.commit()
            self.assertTrue(serge_demarre(path))
            set_heartbeat(conn, False)
            conn.commit()
            conn.close()
            self.assertFalse(serge_demarre(path))

    def test_l_agent_vocal_ne_parle_pas(self) -> None:
        ast, autre = socket.socketpair()
        self.addCleanup(autre.close)
        with (
            mock.patch.object(s2s, 'serge_demarre', return_value=False),
            mock.patch.object(s2s, 'pump') as pump,
        ):
            s2s.handle_call(ast)
        pump.assert_not_called()
        self.assertEqual(ast.fileno(), -1)

    def test_l_appel_de_secours_raccroche(self) -> None:
        agi = mock.Mock()
        with (
            mock.patch.object(turn, 'Agi', return_value=agi),
            mock.patch.object(turn, 'serge_demarre', return_value=False),
            mock.patch.object(turn, 'VoiceTurn') as appel,
        ):
            self.assertEqual(turn.main(['inbound', '+33600000000']), 0)
        agi.hangup.assert_called_once()
        appel.assert_not_called()


if __name__ == '__main__':
    unittest.main()
