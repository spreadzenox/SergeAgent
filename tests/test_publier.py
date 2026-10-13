#!/usr/bin/env python3
"""Publier un produit, en staging puis en prod (lot 10, PR 3, Q91).

Docker est un faux (``tests/fake_docker.py``) et le produit « répond »
par un faux ; le reste est réel : la capacité, l'interpréteur, le bouton
d'essai, l'inventaire des routes et le Caddyfile, Mission Control.

Scénarios :
- « Publier le chantier d'essai » en staging : la version v1 est figée
  sans node_modules, construite, lancée avec les limites du profil
  « produit », mise derrière Caddy sur staging-essai.<domaine>, non
  indexée ; la route de Mission Control reste ;
- en prod : la version du staging est reprise sans être reconstruite,
  sur essai.<domaine>, indexée ;
- une deuxième publication fait la v2, sur le même port ;
- une construction ratée, un produit qui ne répond pas, un chantier sans
  Dockerfile : rien n'est mis en ligne, la raison et la fin du journal
  sont rendues, et Mission Control les montre ;
- les routes déjà là (Mission Control, Stripe) gardent le même Caddyfile.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.ingress import caddy  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tools import run_capability  # noqa: E402
from serge.mc.proj_ilots import project_ilots  # noqa: E402
from serge.paths import files_root  # noqa: E402
from serge.policy_store import policy_en_vigueur  # noqa: E402
from serge.sandbox import publier  # noqa: E402
from tests.test_chantier import ESSAI, faux_docker  # noqa: E402

CHAMP = 'cible (staging ou prod)'


class PublierTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        instance = self.dossier / 'instance.toml'
        instance.write_text(
            '[identity]\npublic_hostname = "serge.exemple.fr"\n',
            encoding='utf-8',
        )
        env = {
            'SERGE_SYSTEM_ROOT': str(self.dossier),
            'SERGE_INSTANCE_FILE': str(instance),
            'SERGE_CADDY_BIN': '',
            **faux_docker(self.dossier),
        }
        for patcher in (
            mock.patch.dict(os.environ, env),
            mock.patch.object(publier, '_repond', return_value=True),
            mock.patch.object(caddy, 'reload', return_value=''),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        set_heartbeat(self.conn, True)
        self.conn.commit()
        self._ecrire('Dockerfile', 'FROM node:22\nCMD ["node", "app.js"]\n')
        self._ecrire('app.js', 'require("http").createServer().listen(8080)\n')
        self._ecrire('node_modules/lourd/index.js', 'module.exports = 1\n')

    def _ecrire(self, path: str, content: str) -> None:
        run_capability(
            self.conn,
            'sandbox_write_file',
            '',
            {**ESSAI, 'path': path, 'content': content},
            'x',
        )

    def _publier(self, cible: str) -> str:
        tache = fire_button(self.conn, 'bouton_publier_essai', {CHAMP: cible})
        self.assertIsNotNone(tache)
        self.conn.commit()
        with redirect_stderr(io.StringIO()) as self.journal:
            process_one(self.conn, 'works')
        statut, erreur = self.conn.execute(
            'SELECT status, last_error FROM tasks WHERE id=?', (tache,)
        ).fetchone()
        self.assertEqual((statut, erreur), ('done', ''))
        return str(tache)

    def _appels(self) -> list[list[str]]:
        log = self.dossier / 'docker/calls.jsonl'
        return [json.loads(line) for line in log.read_text().splitlines()]

    def _publication(self, ident: str) -> tuple:
        return tuple(
            self.conn.execute(
                'SELECT version, host_port, hostname, status, last_error'
                ' FROM deployments WHERE id=?',
                (ident,),
            ).fetchone()
        )

    def _caddyfile(self) -> str:
        return (self.dossier / 'state/web-ingress/Caddyfile').read_text()

    def test_staging_puis_prod_puis_v2(self) -> None:
        self._publier('staging')
        version = files_root() / 'essai/chantier/v1'
        self.assertTrue((version / 'Dockerfile').is_file())
        self.assertTrue((version / 'app.js').is_file())
        self.assertFalse((version / 'node_modules').exists())
        sorte, taille = self.conn.execute(
            "SELECT kind, size_bytes FROM artifacts WHERE deliverable='chantier'"
            ' AND version=1'
        ).fetchone()
        self.assertEqual(sorte, 'version')
        self.assertGreater(taille, 0)
        v, port, hote, etat, erreur = self._publication(
            'staging-essai-chantier'
        )
        self.assertEqual(
            (v, hote, etat, erreur),
            (1, 'staging-essai.serge.exemple.fr', 'running', ''),
        )
        self.assertGreaterEqual(port, publier.FIRST_PORT)
        caddyfile = self._caddyfile()
        self.assertIn(
            'staging-essai.serge.exemple.fr {\n'
            '\theader X-Robots-Tag "noindex, nofollow"\n',
            caddyfile,
        )
        self.assertIn(f'reverse_proxy 127.0.0.1:{port}', caddyfile)
        self.assertIn(
            'serge.exemple.fr {\n\treverse_proxy 127.0.0.1:8790', caddyfile
        )
        lance = next(
            a
            for a in self._appels()
            if a[0] == 'run' and 'serge-staging-essai-chantier' in a
        )
        self.assertIn(f'127.0.0.1:{port}:8080', lance)
        self.assertEqual(lance[lance.index('--memory') + 1], '512m')
        self.assertIn(
            'PUBLIC_URL=https://staging-essai.serge.exemple.fr', lance
        )
        # En prod : la même image, sans rien reconstruire.
        constructions = sum(1 for a in self._appels() if a[0] == 'build')
        self._publier('prod')
        self.assertEqual(
            sum(1 for a in self._appels() if a[0] == 'build'), constructions
        )
        v, port_prod, hote, etat, _ = self._publication('prod-essai-chantier')
        self.assertEqual(
            (v, hote, etat), (1, 'essai.serge.exemple.fr', 'running')
        )
        self.assertNotEqual(port_prod, port)
        self.assertIn(
            f'essai.serge.exemple.fr {{\n\treverse_proxy 127.0.0.1:{port_prod}\n}}',
            self._caddyfile(),
        )
        # Une nouvelle version en staging : v2, sur le même port.
        self._publier('staging')
        self.assertEqual(
            self._publication('staging-essai-chantier')[:2], (2, port)
        )
        self.assertTrue((files_root() / 'essai/chantier/v2').is_dir())
        ilot = next(
            i
            for i in project_ilots(
                self.conn,
                policy_en_vigueur(self.conn),
                '2026-10-13T12:00:00+00:00',
            )['items']
            if i['id'] == 'produits'
        )
        self.assertEqual(ilot['resume'], '2 en ligne')

    def test_ce_qui_rate_n_est_pas_mis_en_ligne(self) -> None:
        self._ecrire('ECHEC_BUILD', '')
        self._publier('staging')
        _v, _p, _h, etat, erreur = self._publication('staging-essai-chantier')
        self.assertEqual((etat, erreur), ('failed', 'docker build a échoué'))
        caddyfile = self.dossier / 'state/web-ingress/Caddyfile'
        texte = caddyfile.read_text() if caddyfile.exists() else ''
        self.assertNotIn('staging-essai', texte)
        self.assertIn('docker build a échoué', self.journal.getvalue())

    def test_un_produit_muet_rend_la_fin_de_son_journal(self) -> None:
        with (
            mock.patch.object(publier, '_repond', return_value=False),
            mock.patch.object(publier, 'ATTENTE_S', 0),
            redirect_stderr(io.StringIO()),
        ):
            resultat = run_capability(
                self.conn,
                'publish_version',
                '',
                {**ESSAI, 'target': 'staging', 'slug': 'essai'},
                'x',
            )
        self.assertEqual(resultat['code'], 'ne_repond_pas')
        self.assertIn('EADDRINUSE', resultat['log'])
        self.assertEqual(
            self._publication('staging-essai-chantier')[3], 'failed'
        )

    def test_sans_dockerfile_ou_sans_staging(self) -> None:
        resultat = run_capability(
            self.conn,
            'publish_version',
            '',
            {**ESSAI, 'target': 'prod', 'slug': 'essai'},
            'x',
        )
        self.assertEqual(resultat['code'], 'rien_en_staging')
        run_capability(
            self.conn,
            'sandbox_command',
            '',
            {**ESSAI, 'command': 'rm Dockerfile'},
            'x',
        )
        with redirect_stderr(io.StringIO()):
            resultat = run_capability(
                self.conn,
                'publish_version',
                '',
                {**ESSAI, 'target': 'staging', 'slug': 'essai'},
                'x',
            )
        self.assertEqual(resultat['code'], 'pas_de_dockerfile')

    def test_les_routes_deja_la_gardent_le_meme_caddyfile(self) -> None:
        avant = caddy.upsert(
            'serge.exemple.fr', '127.0.0.1:8788', 'stripe', '/hooks/stripe'
        )
        self.assertEqual(avant['status'], 'ok')
        self.assertEqual(
            self._caddyfile(),
            'serge.exemple.fr {\n'
            '\thandle /hooks/stripe* {\n'
            '\t\treverse_proxy 127.0.0.1:8788\n'
            '\t}\n'
            '\thandle {\n'
            '\t\treverse_proxy 127.0.0.1:8790\n'
            '\t}\n'
            '}\n',
        )


if __name__ == '__main__':
    unittest.main()
