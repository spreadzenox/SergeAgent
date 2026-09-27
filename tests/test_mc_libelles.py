#!/usr/bin/env python3
"""Libellés FR : événements, phrase noyau, dates, anti-jargon DOM."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.libelles import (  # noqa: E402
    phrase_noyau,
    phrase_recit,
    verbe,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class LibellesUnitTests(unittest.TestCase):
    def test_verbe_humain(self) -> None:
        self.assertEqual(verbe('task.failed'), 'Tâche échouée')
        self.assertEqual(verbe('write.skipped'), 'Doublon écarté')
        self.assertEqual(verbe('inconnu.x'), 'inconnu · x')

    def test_phrase_noyau(self) -> None:
        self.assertIn('urgent', phrase_noyau(2, None, 0))
        self.assertIn(
            'envoyer un e-mail',
            phrase_noyau(0, {'kind': 'Envoyer un e-mail'}, 0),
        )
        self.assertIn('encaissé', phrase_noyau(0, None, 100))
        self.assertIn('arrêté', phrase_noyau(2, None, 100, demarre=False))

    def test_recit(self) -> None:
        self.assertIn(
            'touchées', phrase_recit('Atelier', 'SMOKE_RUNNING', 5, 2, 1, 80)
        )


class LibellesDomTests(McBrowserCase):
    def test_pas_de_jargon_brut(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        page.get_by_text('File vide').wait_for(timeout=10000)
        texte = page.locator('#page').inner_text()
        for interdit in (
            'inbound.classify',
            'work.enqueued',
            'listen.collect',
            'Serveur : en ligne',
        ):
            self.assertNotIn(interdit, texte)
