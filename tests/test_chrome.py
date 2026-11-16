#!/usr/bin/env python3
"""Les conteneurs Chrome de Serge, lancés au besoin (décision Q97).

Docker est un faux (``tests/fake_docker.py``) ; la policy et la base sont
réelles.

Scénarios :
- le vrai Chrome : son image est construite au premier usage, puis le
  conteneur publie son débogage et son écran sur le serveur seulement,
  avec son profil gardé dans un volume ;
- au second usage, rien n'est reconstruit ni relancé ;
- ses fichiers ont changé : le conteneur est refait sur la nouvelle image ;
- Mission Control trouve l'écran quand il tourne, et rien sinon.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.sandbox import chrome  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402


class VraiChromeTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        for patcher in (
            mock.patch.dict(os.environ, faux_docker(self.dossier)),
            mock.patch.object(chrome.time, 'sleep'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        chrome._ECRAN_VU.clear()
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _appels(self, commande: str) -> list[list[str]]:
        lignes = (self.dossier / 'docker/calls.jsonl').read_text()
        appels = [json.loads(ligne) for ligne in lignes.splitlines()]
        return [a for a in appels if a[0] == commande]

    def _etat(self) -> dict:
        chemin = self.dossier / f'docker/containers/{chrome.VRAI}/state.json'
        return json.loads(chemin.read_text())

    def test_construit_lance_puis_reutilise(self) -> None:
        self.assertEqual(chrome.adresse_ecran(), '')
        adresse = chrome.endpoint(self.conn, chrome.VRAI)
        self.assertEqual(adresse, 'http://127.0.0.1:49222')
        image = chrome.image_vrai_chrome()
        (construire,) = self._appels('build')
        self.assertEqual(construire[-1], str(chrome.DOSSIER_IMAGE))
        (lancer,) = self._appels('run')
        self.assertIn(image, lancer)
        ports = [lancer[i + 1] for i, a in enumerate(lancer) if a == '-p']
        self.assertEqual(ports, ['127.0.0.1::9223/tcp', '127.0.0.1::6080/tcp'])
        self.assertIn('serge-vrai-chrome-profil:/home/chrome/profil', lancer)
        self.assertEqual(chrome.adresse_ecran(), '127.0.0.1:49222')
        chrome.endpoint(self.conn, chrome.VRAI)
        self.assertEqual(len(self._appels('build')), 1)
        self.assertEqual(len(self._appels('run')), 1)

    def test_ses_fichiers_changent_il_est_refait(self) -> None:
        chrome.endpoint(self.conn, chrome.VRAI)
        etat = self._etat()
        etat['image'] = 'serge-vrai-chrome:ancienne'
        chemin = self.dossier / f'docker/containers/{chrome.VRAI}/state.json'
        chemin.write_text(json.dumps(etat))
        chrome.endpoint(self.conn, chrome.VRAI)
        self.assertEqual(len(self._appels('rm')), 1)
        self.assertEqual(self._etat()['image'], chrome.image_vrai_chrome())

    def test_le_navigateur_sans_ecran_reste_comme_avant(self) -> None:
        chrome.endpoint(self.conn, chrome.SANS_ECRAN)
        self.assertEqual(self._appels('build'), [])
        (lancer,) = self._appels('run')
        self.assertIn('chromedp/headless-shell:stable', lancer)
        self.assertNotIn('-v', lancer)


if __name__ == '__main__':
    unittest.main()
