#!/usr/bin/env python3
"""Renderer Caddy : inventaire + Caddyfile, sans recharger Caddy."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.ingress import caddy  # noqa: E402


def _toml(public: str) -> str:
    return (
        'schema_version = 1\n'
        'instance_id = "caddy-test"\n'
        'mode = "sandbox"\n'
        '[identity]\n'
        f'public_hostname = "{public}"\n'
        '[paths]\n'
        'home = "/tmp/x"\n'
        'system_root = "/tmp/x"\n'
        'policy = "/tmp/x/mandate.yaml"\n'
    )


class IngressCaddyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = {
            key: os.environ.get(key)
            for key in ('SERGE_SYSTEM_ROOT', 'SERGE_INSTANCE_FILE')
        }

    def tearDown(self) -> None:
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_upsert_writes_inventory_and_caddyfile(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml('owner.example.net'), encoding='utf-8')
            os.environ['SERGE_SYSTEM_ROOT'] = str(tmp)
            os.environ['SERGE_INSTANCE_FILE'] = str(instance)
            result = caddy.upsert(
                'sms.owner.example.net',
                '127.0.0.1:8787',
                'serge-phone-sms',
            )
            self.assertEqual(result['status'], 'ok')
            inventory = json.loads(
                (tmp / 'state/web-ingress/inventory.json').read_text()
            )
            hosts = [route['hostname'] for route in inventory['routes']]
            self.assertIn('owner.example.net', hosts)
            self.assertIn('sms.owner.example.net', hosts)
            text = (tmp / 'state/web-ingress/Caddyfile').read_text()
            self.assertIn('sms.owner.example.net', text)
            self.assertIn('reverse_proxy 127.0.0.1:8787', text)
            rendered = caddy.render()
            self.assertEqual(rendered['routes'], 2)

    def test_path_route_shares_mc_hostname(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml('owner.example.net'), encoding='utf-8')
            os.environ['SERGE_SYSTEM_ROOT'] = str(tmp)
            os.environ['SERGE_INSTANCE_FILE'] = str(instance)
            caddy.upsert(
                'owner.example.net',
                '127.0.0.1:8788',
                'serge-collect-stripe',
                '/hooks/stripe',
            )
            text = (tmp / 'state/web-ingress/Caddyfile').read_text()
            self.assertIn('handle /hooks/stripe*', text)
            self.assertIn('reverse_proxy 127.0.0.1:8788', text)
            self.assertIn('reverse_proxy 127.0.0.1:8790', text)

    def test_une_route_mal_formee_ou_reservee_est_refusee(self) -> None:
        """Rien de ce qu'un plan de produit propose ne s'écrit tel quel
        dans le Caddyfile : un hôte qui n'est pas un nom de domaine, une
        cible hors du serveur, et l'adresse de Mission Control ou des SMS
        sont refusés ; le Caddyfile reste celui d'avant."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            instance = tmp / 'serge.instance.toml'
            instance.write_text(_toml('owner.example.net'), encoding='utf-8')
            os.environ['SERGE_SYSTEM_ROOT'] = str(tmp)
            os.environ['SERGE_INSTANCE_FILE'] = str(instance)
            caddy.upsert(
                'sms.owner.example.net', '127.0.0.1:8787', 'serge-phone-sms'
            )
            caddy.upsert('calc.owner.example.net', '127.0.0.1:18001', 'ven_a')
            fichier = tmp / 'state/web-ingress/Caddyfile'
            avant = fichier.read_text(encoding='utf-8')
            refuses = (
                # L'adresse de Mission Control, puis celle des SMS.
                ('owner.example.net', '127.0.0.1:18002', 'ven_b', ''),
                ('sms.owner.example.net', '127.0.0.1:18002', 'ven_b', ''),
                # Un retour à la ligne écrirait des directives.
                (
                    'x.example.net {\n\troot * /\n}\ny.example.net',
                    '127.0.0.1:18002',
                    'ven_b',
                    '',
                ),
                ('pas un domaine', '127.0.0.1:18002', 'ven_b', ''),
                ('x.example.net', 'evil.example:80', 'ven_b', ''),
                ('x.example.net', '127.0.0.1:2019\n', 'ven_b', ''),
                ('x.example.net', '127.0.0.1:18002', 'ven_b', '/a {\n'),
            )
            for hote, cible, business, chemin in refuses:
                self.assertTrue(caddy.refus(hote, cible, business, chemin))
                with self.assertRaises(ValueError):
                    caddy.upsert(hote, cible, business, chemin)
            self.assertEqual(fichier.read_text(encoding='utf-8'), avant)
            # Un autre business reprend l'adresse d'un produit : permis.
            self.assertEqual(
                caddy.refus(
                    'calc.owner.example.net', '127.0.0.1:18003', 'ven_b'
                ),
                '',
            )
            # Serge remplace ses propres routes.
            self.assertEqual(
                caddy.refus(
                    'owner.example.net',
                    '127.0.0.1:8788',
                    'serge-stripe',
                    '/hooks/stripe',
                ),
                '',
            )

    def test_cli_render_empty(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            os.environ['SERGE_SYSTEM_ROOT'] = str(tmp)
            os.environ.pop('SERGE_INSTANCE_FILE', None)
            code = caddy.main(['render'])
            self.assertEqual(code, 0)
            self.assertTrue((tmp / 'state/web-ingress/Caddyfile').is_file())


if __name__ == '__main__':
    unittest.main()
