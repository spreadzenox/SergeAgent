#!/usr/bin/env python3
"""Le tunnel VPN des deux Chrome (Q114).

Docker est un faux (``tests/fake_docker.py``) ; la policy est réelle.

Scénarios :
- le sidecar du VPN se lance au premier usage : sur le réseau des
  chantiers, avec la configuration du dépôt (son adresse résolue), les
  ports des Chrome publiés sur le serveur seulement, et les secrets du
  compte VPN passés par l'environnement de Docker ;
- le sidecar déjà lancé : rien n'est relancé ;
- le réglage ``navigateur.vpn_off`` à « oui » : le VPN est désactivé ;
- le tunnel qui ne s'établit pas : l'erreur dit pourquoi, et elle est au
  journal du service ;
- les secrets du VPN absents : une erreur claire ;
- le fichier de configuration : le nom d'hôte est remplacé par son IP.
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
from serge.policy_store import set_setting  # noqa: E402
from serge.sandbox import vpn  # noqa: E402
from serge.sandbox.docker import DockerError  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402
from tests.test_chrome import instance_locale  # noqa: E402


class VpnTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        for patcher in (
            mock.patch.dict(os.environ, faux_docker(self.dossier)),
            mock.patch.object(vpn.time, 'sleep'),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        instance_locale(self.dossier)
        self.addCleanup(os.environ.pop, 'SERGE_INSTANCE_FILE', None)
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _appels(self, commande: str) -> list[list[str]]:
        lignes = (self.dossier / 'docker/calls.jsonl').read_text()
        appels = [json.loads(ligne) for ligne in lignes.splitlines()]
        return [a for a in appels if a[0] == commande]

    def _secret(self, nom: str, valeur: str) -> None:
        dossier = self.dossier / 'config/secrets'
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / nom).write_text(valeur + '\n')

    def _lance(self, **secrets: str) -> tuple[str, list[str]]:
        for nom, valeur in secrets.items():
            self._secret(nom, valeur)
        ident = vpn.ensure_vpn(self.conn)
        (lancer,) = [a for a in self._appels('run') if vpn.CONTAINER in a]
        return ident, lancer

    def test_le_sidecar_se_lance_au_premier_usage(self) -> None:
        ident, lancer = self._lance(
            **{'telecom-vpn-login': 'eleve-00', 'telecom-vpn-password': 'x'}
        )
        self.assertTrue(ident.startswith('id-'))
        self.assertIn(vpn.IMAGE, lancer)
        self.assertIn('--network', lancer)
        self.assertEqual(
            lancer[lancer.index('--network') + 1], 'serge-chantiers'
        )
        self.assertEqual(
            [lancer[i + 1] for i, a in enumerate(lancer) if a == '-p'],
            [
                '127.0.0.1::9222/tcp',
                '127.0.0.1::9225/tcp',
                '127.0.0.1::6080/tcp',
            ],
        )
        self.assertIn('NET_ADMIN', lancer)
        self.assertIn('/dev/net/tun', lancer)
        self.assertIn('unless-stopped', lancer)
        self.assertTrue(any('custom.conf:ro' in x for x in lancer))
        env = [
            a
            for a in lancer
            if '=' in a and a.startswith('FIREWALL') or a.startswith('VPN_')
        ]
        self.assertIn('VPN_SERVICE_PROVIDER=custom', env)
        self.assertIn('VPN_TYPE=openvpn', env)
        self.assertIn('FIREWALL_INPUT_PORTS=9222,9225,6080', env)
        self.assertIn('FIREWALL_OUTBOUND_SUBNETS=172.18.0.0/16', env)
        # Les secrets passent par l'environnement de Docker, jamais sur sa
        # ligne de commande.
        self.assertIn('OPENVPN_USER', lancer)
        self.assertNotIn('eleve-00', lancer)
        copie = self.dossier / 'config/vpn/telecom-paris.ovpn'
        self.assertTrue(copie.is_file())

    def test_seul_le_serveur_ouvre_une_connexion_vers_les_chrome(self) -> None:
        """Un chantier ou un produit en staging, voisins sur le réseau,
        n'atteignent ni le débogage des Chrome ni l'écran : le sidecar
        refuse toute connexion qui ne vient pas de la passerelle (les ports
        publiés sur le serveur). La règle n'est posée qu'une fois."""
        secrets = {'telecom-vpn-login': 'a', 'telecom-vpn-password': 'b'}
        self._lance(**secrets)
        vpn.ensure_vpn(self.conn)
        poses = [
            appel
            for appel in self._appels('exec')
            if appel[1:4] == [vpn.CONTAINER, 'iptables', '-I']
        ]
        self.assertEqual(len(poses), 1)
        regle = poses[0][4:]
        self.assertEqual(regle[:3], ['INPUT', '-i', 'eth0'])
        self.assertEqual(
            regle[regle.index('!') : regle.index('!') + 3],
            ['!', '-s', '172.18.0.1'],
        )
        self.assertIn('NEW', regle)
        self.assertEqual(regle[-2:], ['-j', 'DROP'])

    def test_deja_lance_rien_ne_se_refait(self) -> None:
        _ident, _lancer = self._lance(
            **{'telecom-vpn-login': 'a', 'telecom-vpn-password': 'b'}
        )
        avant = len(self._appels('run'))
        ident = vpn.ensure_vpn(self.conn)
        self.assertEqual(len(self._appels('run')), avant)
        self.assertTrue(ident.startswith('id-'))

    def test_les_ports_changees_refont_le_sidecar(self) -> None:
        self._lance(**{'telecom-vpn-login': 'a', 'telecom-vpn-password': 'b'})
        etat = self.dossier / f'docker/containers/{vpn.CONTAINER}/state.json'
        donnees = json.loads(etat.read_text())
        donnees['ports'] = {'9222/tcp': '127.0.0.1::9222/tcp'}
        etat.write_text(json.dumps(donnees))
        vpn.ensure_vpn(self.conn)
        self.assertEqual(len(self._appels('rm')), 1)
        (relance,) = [a for a in self._appels('run')[1:] if vpn.CONTAINER in a]
        ports = [relance[i + 1] for i, a in enumerate(relance) if a == '-p']
        self.assertIn('127.0.0.1::9225/tcp', ports)

    def test_le_reglage_desactive_le_vpn(self) -> None:
        self.assertEqual(
            set_setting(
                self.conn, 'sandbox.navigateur.vpn_off', 'oui', 'test'
            ),
            '',
        )
        self.assertTrue(vpn.desactive(self.conn))
        self.assertEqual(
            set_setting(
                self.conn, 'sandbox.navigateur.vpn_off', 'non', 'test'
            ),
            '',
        )
        self.assertFalse(vpn.desactive(self.conn))

    def test_le_tunnel_ne_s_etablit_pas(self) -> None:
        self._secret('telecom-vpn-login', 'a')
        self._secret('telecom-vpn-password', 'b')
        avec = mock.patch.dict(os.environ, {'FAKE_DOCKER_HEALTH': 'unhealthy'})
        petit = mock.patch.object(vpn, 'ATTENTE_S', 0.2)
        with avec, petit, self.assertRaises(DockerError) as panne:
            vpn.ensure_vpn(self.conn)
        self.assertIn('n’est pas établi', str(panne.exception))

    def test_sans_secrets_l_erreur_est_claire(self) -> None:
        with self.assertRaises(DockerError) as panne:
            vpn.ensure_vpn(self.conn)
        self.assertIn('secret absent', str(panne.exception))
        self.assertEqual(self._appels('run'), [])

    def test_la_config_dit_l_adresse_en_ip(self) -> None:
        with mock.patch.object(
            vpn.socket,
            'getaddrinfo',
            return_value=[(0, 0, 0, '', ('137.194.22.41', 0))],
        ):
            copie = vpn._config()
        texte = copie.read_text(encoding='utf-8')
        self.assertIn('remote 137.194.22.41 443', texte)
        self.assertNotIn('vpn.telecom-paris.fr', texte)
        self.assertIn('verify-x509-name', texte)


if __name__ == '__main__':
    unittest.main()
