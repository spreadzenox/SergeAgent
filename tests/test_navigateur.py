#!/usr/bin/env python3
"""L'interface web des invocations (lot 10, PR 2, décision Q91).

Un vrai Chromium (celui des tests de Mission Control) tient lieu du
conteneur du navigateur, et une petite page locale tient lieu d'un
produit ; le modèle est un faux. Le reste est réel : les capacités,
l'interpréteur, la fiche de la tâche, le serveur de Mission Control.

Scénarios :
- lire une page comme un lecteur d'écran, taper, cliquer, voir l'effet et
  l'erreur de la page ; une capture gardée est rangée sous files/ avec sa
  fiche ; une session ne survit pas à sa tâche ;
- « Essayer l'interface web » : la capture part au modèle comme une image,
  jamais en texte ; avec « captures gardées » à 1, la plus ancienne est
  retirée de l'historique ; la fiche de la tâche montre les captures ;
- Mission Control sert une capture à une session connectée, et rien hors
  de files/ ;
- l'adresse http://chantier:3000 mène au conteneur du chantier de la tâche.
"""

from __future__ import annotations

import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db, utcnow  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tools import run_capability  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.mc.proj_taches import fiche_tache  # noqa: E402
from serge.paths import files_root  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.sandbox import navigateur  # noqa: E402
from tests.mc_server_case import McServerCase, _ci, browser_ok  # noqa: E402

PAGE = """<!doctype html><html lang="fr"><head><title>Devis</title></head>
<body><h1>Créez votre devis</h1><p>Un devis en deux minutes.</p>
<label for="email">E-mail</label><input id="email" type="email">
<button onclick="document.getElementById('r').textContent =
  'Merci ' + document.getElementById('email').value; console.error('oups')"
>Créer un compte</button><p id="r"></p><a href="/tarifs">Tarifs</a>
</body></html>"""


class _Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        corps = PAGE.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *_args: Any) -> None:
        pass


def _site() -> tuple[http.server.HTTPServer, str]:
    serveur = http.server.HTTPServer(('127.0.0.1', 0), _Page)
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    return serveur, f'http://127.0.0.1:{serveur.server_address[1]}'


def _executable() -> str:
    """Le Chromium de Playwright, cherché une fois au chargement : ensuite,
    le Playwright du navigateur de Serge tourne dans ce même fil."""
    if not browser_ok():
        return ''
    from playwright.sync_api import sync_playwright

    with sync_playwright() as handle:
        return handle.chromium.executable_path


CHROME = _executable()


def _chrome(dossier: Path) -> tuple[subprocess.Popen, str]:
    """Un Chromium sans écran, pilotable comme le conteneur du navigateur."""
    profil = dossier / 'chrome'
    args = [
        CHROME,
        '--headless=new',
        '--remote-debugging-port=0',
        f'--user-data-dir={profil}',
        '--no-first-run',
        'about:blank',
    ]
    if _ci():
        args[1:1] = ['--no-sandbox', '--disable-dev-shm-usage']
    proc = subprocess.Popen(
        args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    fichier = profil / 'DevToolsActivePort'
    fin = time.monotonic() + 20
    while not fichier.is_file() and time.monotonic() < fin:
        time.sleep(0.1)
    port = fichier.read_text().splitlines()[0]
    return proc, f'http://127.0.0.1:{port}'


def appel(ident: str, nom: str, **args: Any) -> ToolCall:
    return ToolCall(ident, nom, json.dumps(args))


class FauxTesteur:
    """Ouvre la page, prend deux captures gardées, puis répond."""

    def __init__(self, adresse: str) -> None:
        self.adresse = adresse
        self.messages: list[list[dict[str, Any]]] = []

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        self.messages.append(json.loads(json.dumps(messages)))
        tour = len(self.messages)
        if tour == 1:
            calls = (
                appel(
                    'a', 'navigateur_agir', action='ouvrir', text=self.adresse
                ),
            )
        elif tour in (2, 3):
            calls = (appel(f'c{tour}', 'navigateur_capture', keep=True),)
        else:
            reponse = {'marche': 'oui', 'compte_rendu': 'Vu, deux captures.'}
            return ChatResult(json.dumps(reponse), 10, 10, 'faux', 1)
        return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)


def _images(messages: list[dict[str, Any]]) -> list[str]:
    sortes = []
    for message in messages:
        if isinstance(message.get('content'), list):
            sortes += [p['type'] for p in message['content']]
    return sortes


@unittest.skipUnless(CHROME, 'Chromium indisponible')
class NavigateurTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        patcher = mock.patch.dict(
            os.environ, {'SERGE_SYSTEM_ROOT': str(self.dossier)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        set_heartbeat(self.conn, True)
        self.conn.commit()
        proc, endpoint = _chrome(self.dossier)
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        point = mock.patch.object(
            navigateur, '_endpoint', return_value=endpoint
        )
        point.start()
        self.addCleanup(point.stop)
        self.addCleanup(navigateur.close_sessions)
        serveur, self.site = _site()
        self.addCleanup(serveur.shutdown)

    def _outil(self, capacite: str, **args: Any) -> dict[str, Any]:
        lieu = {'venture_id': 'ven_t', 'deliverable': 'poc', 'task_id': 't1'}
        return run_capability(self.conn, capacite, '', {**lieu, **args}, 'x')

    def test_lire_taper_cliquer_et_garder_une_capture(self) -> None:
        page = self._outil(
            'browser_action', action='ouvrir', text=f'{self.site}/'
        )['page']
        self.assertIn('# Créez votre devis', page)
        self.assertIn('Un devis en deux minutes.', page)
        champ = re.search(r'\[(e\d+)\] champ email « E-mail »', page)
        bouton = re.search(r'\[(e\d+)\] bouton « Créer un compte »', page)
        assert champ and bouton, page
        tape = self._outil(
            'browser_action', action='taper', ref=champ[1], text='a@b.fr'
        )
        self.assertIn('= a@b.fr', tape['page'])
        clic = self._outil('browser_action', action='cliquer', ref=bouton[1])
        self.assertTrue(clic['ok'])
        self.assertIn('Merci a@b.fr', clic['page'])
        self.assertTrue(any('oups' in e for e in clic['nouvelles_erreurs']))
        self.assertFalse(
            self._outil('browser_action', action='cliquer', ref='e999')['ok']
        )
        self.assertTrue(
            self._outil('browser_action', action='ecran', text='mobile')['ok']
        )
        capture = self._outil('browser_screenshot', keep=True)
        self.assertTrue(capture['image'].startswith('data:image/jpeg;base64,'))
        sorte, tache, taille, chemin = self.conn.execute(
            'SELECT kind, task_id, size_bytes, path_or_url FROM artifacts'
            ' WHERE id=?',
            (capture['gardee'],),
        ).fetchone()
        self.assertEqual((sorte, tache), ('capture', 't1'))
        self.assertGreater(taille, 1000)
        self.assertTrue(Path(chemin).is_relative_to(files_root() / 'ven_t'))
        self.assertTrue(Path(chemin).is_file())
        lue = self._outil('browser_read')
        self.assertTrue(any('oups' in e for e in lue['erreurs']))
        navigateur.close_sessions()
        self.assertEqual(navigateur._ETAT.sessions, {})

    def test_essayer_l_interface_web(self) -> None:
        self.assertEqual(
            set_setting(self.conn, 'llm_calls.screenshots_kept', 1, 'test'),
            '',
        )
        testeur = FauxTesteur(f'{self.site}/')
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_essayer_navigateur',
                {'adresse': self.site, 'mission': 'Crée un compte.'},
            )
        )
        self.conn.commit()
        tache = process_one(self.conn, 'works', caller=testeur)
        statut, erreur = self.conn.execute(
            'SELECT status, last_error FROM tasks WHERE id=?', (tache,)
        ).fetchone()
        self.assertEqual((statut, erreur), ('done', ''))
        # La capture part comme une image ; le texte de l'outil ne la porte
        # jamais.
        apres_une = testeur.messages[2]
        resultat = next(
            m
            for m in apres_une
            if m['role'] == 'tool' and 'c2' in m['tool_call_id']
        )
        self.assertNotIn('base64', resultat['content'])
        self.assertIn('montrée', resultat['content'])
        self.assertEqual(_images(apres_une).count('image_url'), 1)
        # Deux captures, une seule gardée dans l'historique.
        apres_deux = testeur.messages[3]
        self.assertEqual(_images(apres_deux).count('image_url'), 1)
        self.assertTrue(
            any(
                'capture retirée' in p.get('text', '')
                for m in apres_deux
                if isinstance(m.get('content'), list)
                for p in m['content']
            )
        )
        fiche = fiche_tache(self.conn, str(tache))
        assert fiche is not None
        cadres = {c['titre']: c for c in fiche['cadres']}
        self.assertIn(
            'Vu, deux captures.', cadres['Ce que le modèle a rendu']['pre']
        )
        images = cadres['Captures gardées']['images']
        self.assertEqual(len(images), 2)
        self.assertTrue(
            images[0]['src'].startswith('/owner/api/fichier?id=art_')
        )

    def test_l_adresse_du_chantier(self) -> None:
        self.assertEqual(
            navigateur._vers_chantier(
                'http://chantier:3000/x?y=1',
                {'venture_id': 'essai', 'deliverable': 'chantier'},
            ),
            'http://serge-chantier-essai-chantier:3000/x?y=1',
        )
        self.assertEqual(
            navigateur._vers_chantier('https://exemple.fr/', {}),
            'https://exemple.fr/',
        )


class FichierMcTests(McServerCase):
    """Mission Control sert une capture rangée sous files/, et rien d'autre."""

    def test_une_capture_et_rien_hors_de_files(self) -> None:
        patcher = mock.patch.dict(
            os.environ, {'SERGE_SYSTEM_ROOT': self.tmp.name}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        image = files_root() / 'ven_t/poc/captures/t1-1.jpg'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'\xff\xd8jpeg')
        dehors = Path(self.tmp.name) / 'secret.jpg'
        dehors.write_bytes(b'secret')
        conn = open_db(self.db_path)
        for ident, chemin in (('art_a', image), ('art_b', dehors)):
            conn.execute(
                'INSERT INTO artifacts(id, venture_id, kind, version,'
                " path_or_url, hash, created_at) VALUES(?, 'ven_t',"
                " 'capture', 1, ?, '', ?)",
                (ident, str(chemin), utcnow()),
            )
        conn.commit()
        conn.close()
        cookie = {'Cookie': self._auth_cookie()}
        statut, tetes, corps = self._request(
            'GET', '/owner/api/fichier?id=art_a', headers=cookie
        )
        self.assertEqual((statut, corps), (200, b'\xff\xd8jpeg'))
        self.assertEqual(tetes['content-type'], 'image/jpeg')
        statut, _, corps = self._request(
            'GET', '/owner/api/fichier?id=art_b', headers=cookie
        )
        self.assertEqual(statut, 404)
        self.assertNotIn(b'secret', corps)
        statut, _, _ = self._request('GET', '/owner/api/fichier?id=art_a')
        self.assertNotEqual(statut, 200)


def tearDownModule() -> None:
    if navigateur._ETAT.playwright is not None:
        navigateur._ETAT.playwright.stop()
        navigateur._ETAT.playwright = navigateur._ETAT.browser = None


if __name__ == '__main__':
    unittest.main()
