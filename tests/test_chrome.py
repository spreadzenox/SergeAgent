#!/usr/bin/env python3
"""Les conteneurs Chrome de Serge, lancés au besoin (décision Q97).

Docker est un faux (``tests/fake_docker.py``) ; la policy et la base sont
réelles.

Scénarios :
- le vrai Chrome : son image est construite au premier usage, puis le
  conteneur partage le réseau du VPN (Q114) et le sidecar publie son
  débogage et son écran sur le serveur seulement, avec son profil gardé
  dans un volume ;
- au second usage, rien n'est reconstruit ni relancé ;
- ses fichiers ont changé : le conteneur est refait sur la nouvelle image ;
- Mission Control trouve l'écran quand il tourne, et rien sinon ;
- le VPN désactivé (réglage ``navigateur.vpn_off``) : chaque Chrome
  reprend son réseau et publie ses ports lui-même, comme avant le VPN.
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
from serge.sandbox import chrome, vpn  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402


def instance_locale(dossier: Path) -> None:
    """Une instance d'essai : son config_root est dans le dossier temporaire
    (la copie du fichier VPN du VPN s'y écrit)."""
    config = dossier / 'config'
    config.mkdir(parents=True, exist_ok=True)
    instance = dossier / 'instance.toml'
    instance.write_text(f'[paths]\nconfig_root = "{config}"\n')
    os.environ['SERGE_INSTANCE_FILE'] = str(instance)


class VraiChromeTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        for patcher in (
            mock.patch.dict(os.environ, faux_docker(self.dossier)),
            mock.patch.object(chrome.time, 'sleep'),
            mock.patch.object(vpn.time, 'sleep'),
            mock.patch.object(chrome, '_attendre_chrome'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        instance_locale(self.dossier)
        self.addCleanup(os.environ.pop, 'SERGE_INSTANCE_FILE', None)
        secrets = self.dossier / 'config/secrets'
        secrets.mkdir(parents=True, exist_ok=True)
        (secrets / 'telecom-vpn-login').write_text('essai\n')
        (secrets / 'telecom-vpn-password').write_text('essai\n')
        chrome._ECRAN_VU.clear()
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _appels(self, commande: str) -> list[list[str]]:
        lignes = (self.dossier / 'docker/calls.jsonl').read_text()
        appels = [json.loads(ligne) for ligne in lignes.splitlines()]
        return [a for a in appels if a[0] == commande]

    def _runs(self) -> dict[str, list[str]]:
        """Les ``docker run``, par nom de conteneur."""
        return {a[a.index('--name') + 1]: a for a in self._appels('run')}

    def _etat(self) -> dict:
        chemin = self.dossier / f'docker/containers/{chrome.VRAI}/state.json'
        return json.loads(chemin.read_text())

    def test_construit_lance_puis_reutilise(self) -> None:
        self.assertEqual(chrome.adresse_ecran(self.conn), '')
        adresse = chrome.endpoint(self.conn, chrome.VRAI)
        self.assertEqual(adresse, 'http://127.0.0.1:49223')
        image = chrome.image_vrai_chrome()
        (construire,) = self._appels('build')
        self.assertEqual(construire[-1], str(chrome.DOSSIER_IMAGE))
        runs = self._runs()
        self.assertEqual(sorted(runs), sorted([vpn.CONTAINER, chrome.VRAI]))
        (lancer,) = [a for nom, a in runs.items() if nom == chrome.VRAI]
        self.assertIn(image, lancer)
        self.assertNotIn('-p', lancer)
        ident = vpn.ensure_vpn(self.conn)
        self.assertIn(f'container:{ident}', lancer)
        self.assertIn(f'CHROME_PORT={chrome.PORT_CHROME_VRAI}', lancer)
        self.assertIn(
            f'CDP_RELAY={chrome.CDP_VPN.removesuffix("/tcp")}', lancer
        )
        self.assertIn('serge-vrai-chrome-profil:/home/chrome/profil', lancer)
        self.assertEqual(chrome.adresse_ecran(self.conn), '127.0.0.1:49224')
        chrome.endpoint(self.conn, chrome.VRAI)
        self.assertEqual(len(self._appels('build')), 1)
        self.assertEqual(len(runs), 2)

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
        (lancer,) = [
            a for nom, a in self._runs().items() if nom == chrome.SANS_ECRAN
        ]
        self.assertIn('chromedp/headless-shell:stable', lancer)
        self.assertNotIn('-v', lancer)

    def test_vpn_desactive_le_comportement_d_avant(self) -> None:
        from serge.policy_store import set_setting

        self.assertEqual(
            set_setting(
                self.conn, 'sandbox.navigateur.vpn_off', 'oui', 'test'
            ),
            '',
        )
        adresse = chrome.endpoint(self.conn, chrome.VRAI)
        self.assertEqual(adresse, 'http://127.0.0.1:49222')
        runs = self._runs()
        self.assertNotIn(vpn.CONTAINER, runs)
        (lancer,) = [a for nom, a in runs.items() if nom == chrome.VRAI]
        self.assertEqual(
            [lancer[i + 1] for i, a in enumerate(lancer) if a == '-p'],
            ['127.0.0.1::9223/tcp', '127.0.0.1::6080/tcp'],
        )
        self.assertIn('--network', lancer)
        self.assertEqual(
            lancer[lancer.index('--network') + 1], 'serge-chantiers'
        )
        self.assertNotIn(
            f'CDP_RELAY={chrome.CDP_VPN.removesuffix("/tcp")}', lancer
        )

    def test_le_conteneur_au_mauvais_endroit_est_refait(self) -> None:
        chrome.endpoint(self.conn, chrome.VRAI)
        etat = self._etat()
        etat['flags']['--network'] = 'serge-chantiers'
        chemin = self.dossier / f'docker/containers/{chrome.VRAI}/state.json'
        chemin.write_text(json.dumps(etat))
        chrome.endpoint(self.conn, chrome.VRAI)
        self.assertEqual(len(self._appels('rm')), 1)
        self.assertIn(
            f'container:{vpn.ensure_vpn(self.conn)}',
            [a for a in self._runs()[chrome.VRAI]],
        )


if __name__ == '__main__':
    unittest.main()
