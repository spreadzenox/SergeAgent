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
- l'adresse http://chantier:3000 mène au conteneur du chantier de la tâche ;
- taper un secret : seuls les secrets figés en base sont permis ; la page
  relue, même remise en forme, et une capture ne montrent jamais sa valeur ;
- une boîte de dialogue du navigateur (saisie, question, message) : sans
  réponse préparée, elle est refermée et le résultat dit comment y
  répondre ; une réponse préparée sert une fois, à la boîte suivante ;
- tout ce qui se clique a un repère, où qu'il soit : un bouton dans un
  titre, un bloc cliquable, un composant web, une fenêtre modale, et le
  contenu d'un cadre intégré ;
- viser sans repère : par un texte visible, par un point de l'écran ;
  double clic, clic droit, survol, glisser et déposer, taper au clavier ;
- un fichier téléchargé est gardé avec le livrable et se lit ; un fichier
  se dépose dans un champ ou par le bouton qui ouvre le choix ;
- un nouvel onglet est suivi, et fermé on revient au précédent ;
- passer au vrai Chrome en cours de tâche garde l'adresse et la connexion ;
- un compte web (lot 13) : sa session s'ouvre à part, Serge tape son mot de
  passe sans que le modèle le voie, ses cookies sont gardés chiffrés en
  base et reconnectent la tâche suivante ; un compte ne sert qu'à une
  tâche à la fois, et pas au-delà de ses actions du jour ; un modèle ne
  peut se donner ni un compte ni des secrets.
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

from serge import web_accounts  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db, utcnow  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tools import (  # noqa: E402
    RUNNERS,
    run_capability,
    run_tool,
    tool_schema,
)
from serge.interpreter.triggers import fire_button  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.mc.proj_taches import fiche_tache  # noqa: E402
from serge.paths import files_root  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.sandbox import navigateur, sessions  # noqa: E402
from serge.web_accounts import PASSWORD_NAME  # noqa: E402
from tests.boutons_d_essai import poser  # noqa: E402
from tests.mc_server_case import McServerCase, _ci, browser_ok  # noqa: E402

PAGE = """<!doctype html><html lang="fr"><head><title>Devis</title></head>
<body><h1>Créez votre devis</h1><p>Un devis en deux minutes.</p>
<label for="email">E-mail</label><input id="email" type="email">
<button onclick="document.getElementById('r').textContent =
  'Merci ' + document.getElementById('email').value; console.error('oups')"
>Créer un compte</button><p id="r"></p><a href="/tarifs">Tarifs</a>
</body></html>"""


# Un produit qui demande un nom dans une boîte de saisie du navigateur,
# confirme avant d'effacer, et félicite par un message.
PAGE_DIALOGUES = """<!doctype html><html lang="fr"><head><title>Calculs
</title></head><body><h1>Mes calculs</h1>
<button onclick="const n = prompt('Nom du calcul ?', 'Sans nom');
  if (n) document.getElementById('liste').textContent = 'Enregistré : ' + n;"
>Enregistrer</button>
<button onclick="if (confirm('Tout effacer ?'))
  document.getElementById('liste').textContent = 'Effacé';">Effacer</button>
<button onclick="alert('Bravo');
  document.getElementById('liste').textContent = 'Vu';">Féliciter</button>
<p id="liste">Aucun calcul</p></body></html>"""


# Un produit qui a tout ce qu'une page peut avoir de difficile à lire ou à
# manier : des boutons dans des titres, un bloc cliquable, un composant
# web, une fenêtre modale dans une racine haute de 0, un menu au survol, un
# cadre intégré, un dessin, un champ fichier caché, un lien qui télécharge,
# un fichier fabriqué par la page, un lien qui ouvre un autre onglet.
PAGE_ATELIER = """<!doctype html><html lang="fr"><head><title>Atelier</title>
<style>.carte{cursor:pointer;width:200px} #menu{width:200px}
#menu ul{display:none} #menu:hover ul{display:block} #racine{height:0}
#fenetre{position:fixed;top:10px;right:10px;width:200px;height:40px}
.zone{width:120px;height:40px;border:1px solid}</style></head><body>
<h1>Atelier</h1>
<canvas id="dessin" width="200" height="60" style="border:1px solid"></canvas>
<h2>Mes calculs <button onclick="note('enregistré')">Enregistrer</button></h2>
<h2>Historique <span><a href="/export.csv">Exporter en CSV</a>
<button onclick="note('vidé')">Vider l'historique</button></span></h2>
<h2><a href="/autre">Un titre qui est un lien</a></h2>
<p id="journal">rien</p>
<div class="carte" id="carte">Carte cliquable</div>
<div style="display:contents"><button onclick="note('sans boîte')"
>Dans un bloc sans boîte</button></div>
<div style="height:0;overflow:hidden"><button>Dans un volet replié</button>
</div>
<div id="racine"><div id="fenetre"><button onclick="note('fenêtre')"
>Fermer la fenêtre</button></div></div>
<div id="menu">Menu<ul><li><button onclick="note('survol')">Entrée cachée
</button></li></ul></div>
<a href="/autre" target="_blank">Ouvrir ailleurs</a>
<button onclick="fabriquer()">Exporter un fichier fabriqué</button>
<label for="f">Pièce jointe</label><input id="f" type="file"
onchange="note('reçu ' + this.files[0].name + ' ' + this.files[0].size)">
<input id="cache" type="file" style="display:none"
onchange="this.files[0].text().then(t => note('importé ' + t))">
<button onclick="document.getElementById('cache').click()">Importer</button>
<div id="colis" class="zone" draggable="true"
ondragstart="event.dataTransfer.setData('text', 'colis')">Colis</div>
<div id="depot" class="zone" ondragover="event.preventDefault()"
ondrop="event.preventDefault();
note('déposé ' + event.dataTransfer.getData('text'))">Dépôt</div>
<div id="editeur" contenteditable="true" aria-label="Note libre"
style="min-height:20px;width:200px;border:1px solid"></div>
<span role="tab" onclick="note('onglet')">Réglages</span>
<mon-bouton></mon-bouton>
<iframe src="/cadre" title="Paiement" width="300" height="90"></iframe>
<script>
const note = (t) => { document.getElementById('journal').textContent = t; };
const carte = document.getElementById('carte');
carte.addEventListener('click', () => note('carte'));
carte.addEventListener('dblclick', () => note('double'));
carte.addEventListener('contextmenu', (e) => {
  e.preventDefault(); note('droit'); });
document.getElementById('dessin').addEventListener('click', (e) =>
  note('dessin ' + Math.round(e.offsetX) + ',' + Math.round(e.offsetY)));
document.getElementById('editeur').addEventListener('input', (e) =>
  note('écrit ' + e.target.innerText));
function fabriquer() {
  const adresse = URL.createObjectURL(
    new Blob(['a;b\\n1;2\\n'], {type: 'text/csv'}));
  const lien = document.createElement('a');
  lien.href = adresse; lien.download = 'fabrique.csv'; lien.click();
  URL.revokeObjectURL(adresse);
}
customElements.define('mon-bouton', class extends HTMLElement {
  connectedCallback() {
    const racine = this.attachShadow({mode: 'open'});
    racine.innerHTML = '<button>Dans un composant</button>';
    racine.querySelector('button').onclick = () => note('composant');
  }
});
</script></body></html>"""
CADRE = """<!doctype html><html lang="fr"><body><p>Carte bancaire</p>
<input aria-label="Numéro"><button onclick="document.getElementById('r')
.textContent = 'payé ' + document.querySelector('input').value">Payer
</button><p id="r"></p></body></html>"""
AUTRE = """<!doctype html><html lang="fr"><head><title>Autre</title></head>
<body><h1>Autre page</h1></body></html>"""
EXPORT = ''.join(f'ligne;{n}\n' for n in range(1, 61))
# Un site où il faut un compte : sans son cookie, il demande de se
# connecter ; le bouton pose le cookie, comme un vrai site après le mot de
# passe.
COMPTE_A_CONNECTER = """<!doctype html><html lang="fr"><head>
<title>Forum</title></head><body><h1>Connectez-vous</h1>
<label for="mdp">Mot de passe</label><input id="mdp" type="password">
<button onclick="document.cookie = 'forum=jeton-de-session; path=/';
  location.reload()">Se connecter</button></body></html>"""
COMPTE_CONNECTE = """<!doctype html><html lang="fr"><head>
<title>Forum</title></head><body><h1>Bonjour serge-ia</h1>
<p>Vos messages privés</p></body></html>"""
PAGES = {
    '/dialogues': PAGE_DIALOGUES,
    '/atelier': PAGE_ATELIER,
    '/cadre': CADRE,
    '/autre': AUTRE,
}


class _Page(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == '/export.csv':
            corps = EXPORT.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv; charset=utf-8')
            self.send_header(
                'Content-Disposition', 'attachment; filename="export.csv"'
            )
            self.send_header('Content-Length', str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
            return
        if self.path == '/compte':
            connecte = 'forum=' in (self.headers.get('Cookie') or '')
            page = COMPTE_CONNECTE if connecte else COMPTE_A_CONNECTER
        else:
            page = PAGES.get(self.path, PAGE)
        corps = page.encode('utf-8')
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
    """Ouvre la page, prend trois captures gardées, puis répond."""

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
        elif tour in (2, 3, 4):
            calls = (appel(f'c{tour}', 'navigateur_capture', keep=True),)
        else:
            reponse = {'marche': 'oui', 'compte_rendu': 'Vu, trois captures.'}
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
        poser(self.conn)
        set_heartbeat(self.conn, True)
        self.conn.commit()
        proc, endpoint = _chrome(self.dossier)
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        point = mock.patch.object(sessions, '_endpoint', return_value=endpoint)
        point.start()
        self.addCleanup(point.stop)
        self.addCleanup(sessions.close_sessions)
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
        sessions.close_sessions()
        self.assertEqual(sessions._ETAT.sessions, {})

    def test_repondre_a_une_boite_de_dialogue_du_navigateur(self) -> None:
        """Le relecteur d'un produit, le 17 novembre 2026 : « Enregistrer »
        ouvre une saisie du navigateur, qu'il ne voit pas et où il ne peut
        rien taper. Serge la referme et dit comment y répondre ; la réponse
        préparée est tapée dans la boîte suivante, une fois."""
        page = self._outil(
            'browser_action', action='ouvrir', text=f'{self.site}/dialogues'
        )['page']
        self.assertIn('Aucun calcul', page)

        def cliquer(bouton: str) -> dict[str, Any]:
            vue = self._outil('browser_read')['page']
            repere = re.search(rf'\[(e\d+)\] bouton « {bouton} »', vue)
            assert repere, vue
            return self._outil(
                'browser_action', action='cliquer', ref=repere[1]
            )

        # Sans réponse préparée : refermée, rien n'est enregistré.
        clic = cliquer('Enregistrer')
        self.assertTrue(clic['ok'])
        (boite,) = clic['dialogues']
        self.assertTrue(
            boite.startswith(
                'saisie « Nom du calcul ? » : refermée sans réponse.'
            ),
            boite,
        )
        self.assertIn('accepter_dialogue', boite)
        self.assertIn('Aucun calcul', clic['page'])
        # La réponse préparée est tapée, une seule fois.
        prete = self._outil(
            'browser_action', action='accepter_dialogue', text='Devis Dupont'
        )
        self.assertTrue(prete['ok'])
        self.assertNotIn('dialogues', prete)
        clic = cliquer('Enregistrer')
        self.assertEqual(
            clic['dialogues'],
            ['saisie « Nom du calcul ? » : répondu « Devis Dupont »'],
        )
        self.assertIn('Enregistré : Devis Dupont', clic['page'])
        self.assertIn(
            'refermée sans réponse', cliquer('Enregistrer')['dialogues'][0]
        )
        # Une question : refusée, puis acceptée.
        self.assertIn(
            'question « Tout effacer ? » : refermée sans réponse',
            cliquer('Effacer')['dialogues'][0],
        )
        self._outil('browser_action', action='refuser_dialogue')
        clic = cliquer('Effacer')
        self.assertEqual(
            clic['dialogues'],
            ['question « Tout effacer ? » : refusée (Annuler)'],
        )
        self.assertIn('Enregistré : Devis Dupont', clic['page'])
        self._outil('browser_action', action='accepter_dialogue')
        clic = cliquer('Effacer')
        self.assertEqual(
            clic['dialogues'], ['question « Tout effacer ? » : acceptée (OK)']
        )
        self.assertIn('Effacé', clic['page'])
        # Un message est fermé, et la page continue.
        clic = cliquer('Féliciter')
        self.assertEqual(clic['dialogues'], ['message « Bravo » : fermé (OK)'])
        self.assertIn('Vu', clic['page'])

    def _atelier(self) -> str:
        return self._outil(
            'browser_action', action='ouvrir', text=f'{self.site}/atelier'
        )['page']

    def _repere(self, page: str, ligne: str) -> str:
        """Le repère de la ligne « [e7] <ligne> » de la page lue."""
        trouve = re.search(rf'\[([e\d.]+)\] {re.escape(ligne)}', page)
        assert trouve, f'{ligne} absent de :\n{page}'
        return trouve[1]

    def _journal(self, resultat: dict[str, Any]) -> str:
        """Ce que la page d'essai dit du dernier geste."""
        self.assertTrue(resultat['ok'], resultat.get('detail'))
        lignes = resultat['page'].splitlines()
        return lignes[lignes.index('## Un titre qui est un lien') + 2]

    def test_tout_ce_qui_se_clique_a_un_repere(self) -> None:
        """Le relecteur d'un produit, le 17 novembre 2026 : « Enregistrer »,
        dans un titre, n'avait pas de repère. Tout ce sur quoi on peut agir
        en a un, où qu'il soit, et le contenu d'un cadre intégré se lit sous
        la ligne du cadre."""
        page = self._atelier()
        self.assertIn('## Mes calculs\n', page)
        self.assertIn('## Historique\n', page)
        self.assertIn('lien « Exporter en CSV » → /export.csv', page)
        # Un titre qui n'est qu'un lien garde son texte, et le lien son repère.
        self.assertIn('## Un titre qui est un lien\n', page)
        self._repere(page, 'lien « Un titre qui est un lien » → /autre')
        self.assertIn('zone de dessin, de (', page)
        # Ce qu'un volet replié cache ne se lit pas.
        self.assertNotIn('Dans un volet replié', page)
        self._repere(page, 'champ fichier « Pièce jointe » (vide)')
        self._repere(page, 'lien « Ouvrir ailleurs » → /autre')
        for ligne, effet in (
            ('bouton « Enregistrer »', 'enregistré'),
            ("bouton « Vider l'historique »", 'vidé'),
            ('élément cliquable « Carte cliquable »', 'carte'),
            ('bouton « Dans un bloc sans boîte »', 'sans boîte'),
            ('bouton « Fermer la fenêtre »', 'fenêtre'),
            ('onglet « Réglages »', 'onglet'),
            ('bouton « Dans un composant »', 'composant'),
        ):
            clic = self._outil(
                'browser_action',
                action='cliquer',
                ref=self._repere(self._outil('browser_read')['page'], ligne),
            )
            self.assertEqual(self._journal(clic), effet, ligne)
        # Une zone qu'on édite dans la page se remplit comme un champ.
        zone = self._repere(page, 'zone de texte « Note libre » (vide)')
        tape = self._outil(
            'browser_action', action='taper', ref=zone, text='bonjour'
        )
        self.assertEqual(self._journal(tape), 'écrit bonjour')
        # Le cadre intégré : son contenu sous sa ligne, ses repères à lui.
        cadre = self._repere(page, 'cadre « Paiement »')
        self.assertIn(f'  [{cadre}.e1] champ text « Numéro » (vide)', page)
        self._outil(
            'browser_action', action='taper', ref=f'{cadre}.e1', text='4242'
        )
        paye = self._outil(
            'browser_action', action='cliquer', ref=f'{cadre}.e2'
        )
        self.assertTrue(paye['ok'], paye.get('detail'))
        self.assertIn('  payé 4242', paye['page'])

    def test_viser_par_un_texte_ou_par_un_point(self) -> None:
        """Sans repère : un texte visible, ou un point de l'écran lu sur
        une capture. Et les autres gestes d'une souris et d'un clavier."""
        page = self._atelier()

        def geste(action: str, **args: Any) -> str:
            return self._journal(
                self._outil('browser_action', action=action, **args)
            )

        self.assertEqual(geste('cliquer', text="Vider l'historique"), 'vidé')
        self.assertEqual(
            geste('double_cliquer', text='Carte cliquable'), 'double'
        )
        self.assertEqual(geste('clic_droit', text='Carte cliquable'), 'droit')
        # Le dessin n'a pas de repère : la page dit où il est à l'écran.
        coin = re.search(r'zone de dessin, de \((\d+), (\d+)\)', page)
        assert coin, page
        gauche, haut = int(coin[1]), int(coin[2])
        self.assertEqual(
            geste('cliquer', x=gauche + 50, y=haut + 20), 'dessin 49,19'
        )
        capture = self._outil('browser_screenshot')
        self.assertEqual(capture['ecran'], '1280 x 800')
        # Le menu ne montre son entrée qu'au survol.
        self.assertNotIn('Entrée cachée', page)
        survol = self._outil('browser_action', action='survoler', text='Menu')
        self.assertIn('bouton « Entrée cachée »', survol['page'])
        # Un élément de plus dans la page : les autres gardent leur repère.
        self.assertEqual(
            self._repere(survol['page'], 'bouton « Enregistrer »'),
            self._repere(page, 'bouton « Enregistrer »'),
        )
        self.assertEqual(geste('cliquer', text='Entrée cachée'), 'survol')
        # Taper au clavier, là où est le curseur.
        zone = self._repere(page, 'zone de texte « Note libre » (vide)')
        self._outil('browser_action', action='cliquer', ref=zone)
        self.assertEqual(geste('taper', text='au clavier'), 'écrit au clavier')
        self.assertEqual(geste('recharger'), 'rien')
        # Glisser et déposer : d'un point à un point, puis d'un repère à un
        # texte visible.
        page = self._outil('browser_read')['page']
        colis = self._repere(page, 'élément à glisser « Colis »')
        self.assertEqual(geste('cliquer', text='Enregistrer'), 'enregistré')
        boites = sessions._session(self.conn, 't1').page.evaluate(
            """() => ['colis', 'depot'].map((nom) => {
                const b = document.getElementById(nom).getBoundingClientRect();
                return [b.left + b.width / 2, b.top + b.height / 2];
            })"""
        )
        depot = f'{boites[1][0]},{boites[1][1]}'
        self.assertEqual(
            geste('glisser', x=boites[0][0], y=boites[0][1], to=depot),
            'déposé colis',
        )
        geste('cliquer', text='Enregistrer')
        self.assertEqual(
            geste('glisser', ref=colis, to='Dépôt'), 'déposé colis'
        )
        # Un geste qui ne vise rien le dit.
        rien = self._outil('browser_action', action='cliquer')
        self.assertFalse(rien['ok'])
        self.assertIn(
            'un repère (ref), un texte visible (text)', rien['detail']
        )

    def test_un_fichier_telecharge_se_lit_et_se_depose(self) -> None:
        """« Exporter en CSV » : le fichier est gardé avec le livrable, son
        début revient au modèle, la suite se lit. Un fichier fabriqué par
        la page aussi. Un fichier se dépose dans un champ, ou par le bouton
        qui ouvre le choix d'un fichier."""
        page = self._atelier()
        clic = self._outil(
            'browser_action',
            action='cliquer',
            ref=self._repere(page, 'lien « Exporter en CSV » → /export.csv'),
        )
        self.assertTrue(clic['ok'], clic.get('detail'))
        (recu,) = clic['telechargements']
        self.assertEqual(
            (recu['nom'], recu['taille'], recu['lignes']),
            ('export.csv', f'{len(EXPORT)} octets', 60),
        )
        self.assertEqual(recu['debut'].splitlines()[0], 'ligne;1')
        self.assertEqual(len(recu['debut'].splitlines()), 40)
        self.assertIn('line 41', recu['suite'])
        garde = files_root() / 'ven_t/poc/telechargements/t1/export.csv'
        self.assertEqual(garde.read_text(encoding='utf-8'), EXPORT)
        self.assertEqual(
            tuple(
                self.conn.execute(
                    'SELECT task_id, size_bytes FROM artifacts'
                    " WHERE kind='telechargement'"
                ).fetchone()
            ),
            ('t1', len(EXPORT)),
        )
        suite = self._outil(
            'browser_action',
            action='lire_telechargement',
            text='export.csv',
            line=41,
        )['fichier']
        self.assertEqual(
            suite['a_partir_de_la_ligne_41'].splitlines(),
            [f'ligne;{n}' for n in range(41, 61)],
        )
        self.assertNotIn('suite', suite)
        inconnu = self._outil(
            'browser_action', action='lire_telechargement', text='absent.csv'
        )['fichier']
        self.assertIn('connus : export.csv', inconnu['echec'])
        # Un fichier fabriqué par la page, dont l'adresse ne vit qu'un instant.
        fabrique = self._outil(
            'browser_action',
            action='cliquer',
            text='Exporter un fichier fabriqué',
        )
        (recu,) = fabrique['telechargements']
        self.assertEqual(
            (recu['nom'], recu['debut']), ('fabrique.csv', 'a;b\n1;2')
        )
        # Déposer : un fichier écrit par le modèle, puis un fichier téléchargé.
        champ = self._repere(page, 'champ fichier « Pièce jointe » (vide)')
        depot = self._outil(
            'browser_action',
            action='deposer_fichier',
            ref=champ,
            text='devis.txt',
            content='bonjour',
        )
        self.assertEqual(self._journal(depot), 'reçu devis.txt 7')
        self.assertIn(
            'champ fichier « Pièce jointe » = devis.txt', depot['page']
        )
        depot = self._outil(
            'browser_action',
            action='deposer_fichier',
            ref=champ,
            text='export.csv',
        )
        self.assertEqual(
            self._journal(depot), f'reçu export.csv {len(EXPORT)}'
        )
        # Par le bouton qui ouvre le choix d'un fichier (le champ est caché).
        bouton = self._repere(depot['page'], 'bouton « Importer »')
        importe = self._outil(
            'browser_action',
            action='deposer_fichier',
            ref=bouton,
            text='liste.csv',
            content='x;y',
        )
        self.assertEqual(self._journal(importe), 'importé x;y')
        refus = self._outil(
            'browser_action',
            action='deposer_fichier',
            ref=champ,
            text='rien.txt',
        )
        self.assertFalse(refus['ok'])

    def test_un_nouvel_onglet_est_suivi(self) -> None:
        """Un lien qui ouvre un autre onglet : la session y passe, et le
        résultat le dit ; fermé, elle revient au précédent."""
        page = self._atelier()
        seul = self._outil('browser_action', action='fermer_onglet')
        self.assertFalse(seul['ok'])
        clic = self._outil(
            'browser_action',
            action='cliquer',
            ref=self._repere(page, 'lien « Ouvrir ailleurs » → /autre'),
        )
        self.assertTrue(clic['ok'], clic.get('detail'))
        self.assertIn('un nouvel onglet s’est ouvert', clic['onglets'][0])
        self.assertIn('# Autre page', clic['page'])
        self.assertIn('# Autre page', self._outil('browser_read')['page'])
        retour = self._outil('browser_action', action='fermer_onglet')
        self.assertTrue(retour['ok'], retour.get('detail'))
        self.assertIn('revenu au précédent', retour['onglets'][0])
        self.assertIn('# Atelier', retour['page'])
        self.assertEqual(len(sessions._session(self.conn, 't1').pages), 1)
        # Une page qui ferme son dernier onglet : la suite repart d'un
        # onglet neuf, au lieu d'échouer.
        sessions._session(self.conn, 't1').page.close()
        neuf = self._outil(
            'browser_action', action='ouvrir', text=f'{self.site}/autre'
        )
        self.assertTrue(neuf['ok'], neuf.get('detail'))
        self.assertIn('# Autre page', neuf['page'])

    def test_passer_au_vrai_chrome_en_cours_de_tache(self) -> None:
        """Une page qui refuse le navigateur sans écran : la tâche passe
        au vrai Chrome, à la même adresse, avec ses cookies et ce que la
        page gardait dans le navigateur. La suite s'y fait, avec les mêmes
        outils."""
        self._atelier()
        sessions._session(self.conn, 't1').page.evaluate(
            """() => { document.cookie = 'session=abc';
                localStorage.setItem('panier', '3'); }"""
        )
        passe = self._outil('browser_action', action='passer_au_vrai_chrome')
        self.assertTrue(passe['ok'], passe.get('detail'))
        self.assertIn('# Atelier', passe['page'])
        self.assertNotIn('t1', sessions._ETAT.sessions)
        vrai = sessions._ETAT_VRAI.sessions['t1']
        self.assertIs(vrai.context, sessions._ETAT_VRAI.browser.contexts[0])
        self.assertEqual(
            vrai.page.evaluate(
                '() => [document.cookie, localStorage.getItem("panier")]'
            ),
            ['session=abc', '3'],
        )
        # Les outils du navigateur sans écran agissent maintenant là-bas.
        clic = self._outil(
            'browser_action', action='cliquer', text='Enregistrer'
        )
        self.assertEqual(self._journal(clic), 'enregistré')
        self.assertEqual(
            vrai.page.evaluate(
                '() => document.getElementById("journal").textContent'
            ),
            'enregistré',
        )
        self.assertIn('enregistré', self._outil('browser_read')['page'])
        self.assertNotIn('t1', sessions._ETAT.sessions)
        deja = self._outil('browser_action', action='passer_au_vrai_chrome')
        self.assertFalse(deja['ok'])
        sessions.close_sessions()
        self.assertEqual(sessions._PASSEES, set())

    def test_le_vrai_chrome_garde_son_profil_et_montre_l_onglet(self) -> None:
        """Le vrai Chrome (Q97) : mêmes actions, dans le profil du
        navigateur ; à la fin de la tâche, seul l'onglet se ferme."""
        page = self._outil(
            'real_browser_action', action='ouvrir', text=f'{self.site}/'
        )['page']
        self.assertIn('# Créez votre devis', page)
        session = sessions._ETAT_VRAI.sessions['t1']
        profil = sessions._ETAT_VRAI.profil
        self.assertIs(session.context, profil)
        self.assertEqual(sessions._ETAT.sessions, {}, 'pas l’autre')
        capture = self._outil('real_browser_screenshot')
        self.assertTrue(capture['image'].startswith('data:image/jpeg;base64,'))
        self.assertIn(
            'Créez votre devis', self._outil('real_browser_read')['page']
        )
        self.assertTrue(sessions.montrer('t1'))
        self.assertFalse(sessions.montrer('t2'))
        sessions.close_sessions()
        self.assertTrue(session.page.is_closed())
        self.assertIn(profil, sessions._ETAT_VRAI.browser.contexts)

    def _coffre(self) -> None:
        """Une instance avec la clé du coffre, qui chiffre les secrets."""
        from cryptography.fernet import Fernet

        secrets = self.dossier / 'config/secrets'
        secrets.mkdir(parents=True)
        (secrets / 'credential-vault.key').write_bytes(
            Fernet.generate_key() + b'\n'
        )
        instance = self.dossier / 'instance.toml'
        instance.write_text(
            f'[paths]\nconfig_root = "{self.dossier / "config"}"\n'
        )
        patcher = mock.patch.dict(
            os.environ, {'SERGE_INSTANCE_FILE': str(instance)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _avec_le_compte(self, tache: str, **args: Any) -> dict[str, Any]:
        return self._outil(
            'real_browser_action', task_id=tache, account='forum', **args
        )

    def test_un_compte_web_garde_sa_connexion(self) -> None:
        """Un compte web (lot 13, Q104) : la première tâche se connecte,
        Serge tape le mot de passe ; la suivante est connectée d'emblée."""
        self._coffre()
        adresse = f'{self.site}/compte'
        self.conn.execute(
            'INSERT INTO web_accounts(id, url, login, created_at, updated_at)'
            " VALUES('forum', ?, 'serge-ia', ?, ?)",
            (self.site, utcnow(), utcnow()),
        )
        page = self._avec_le_compte('t1', action='ouvrir', text=adresse)[
            'page'
        ]
        self.assertIn('# Connectez-vous', page)
        session = sessions._ETAT_VRAI.sessions['t1@forum']
        profil = sessions._ETAT_VRAI.profil
        self.assertIsNotNone(profil)
        self.assertIsNot(session.context, profil, 'une session à part')
        # Serge choisit le mot de passe et le tape : le modèle ne nomme que
        # « mot_de_passe_du_compte », sans avoir à y être autorisé.
        champ = re.search(r'\[(e\d+)\] champ password', page)
        assert champ, page
        tape = self._avec_le_compte(
            't1', action='taper_secret', ref=champ[1], text=PASSWORD_NAME
        )
        self.assertTrue(tape['ok'], tape)
        choisi = web_accounts.password(self.conn, 'forum')
        self.assertEqual(len(choisi), web_accounts.LONGUEUR)
        self.assertEqual(session.page.input_value('#mdp'), choisi)
        self.assertNotIn(choisi, json.dumps(tape))
        connecte = self._avec_le_compte(
            't1', action='cliquer', text='Se connecter'
        )
        self.assertIn('# Bonjour serge-ia', connecte['page'])
        self.assertEqual(web_accounts.actions_today(self.conn, 'forum'), 3)
        sessions.close_sessions(self.conn)
        # En base : tout est chiffré, et le compte est rendu.
        mdp, garde, pris = self.conn.execute(
            'SELECT password_enc, session_enc, used_by FROM web_accounts'
        ).fetchone()
        self.assertTrue(mdp and garde)
        self.assertNotIn(choisi, mdp)
        self.assertNotIn('jeton-de-session', garde)
        self.assertEqual(pris, '')
        # La tâche suivante est connectée sans rien taper.
        suite = self._avec_le_compte('t2', action='ouvrir', text=adresse)
        self.assertIn('# Bonjour serge-ia', suite['page'])
        # Une tâche sans ce compte n'a pas ses cookies : ni dans le profil
        # du vrai Chrome, ni dans le navigateur sans écran.
        for capacite in ('real_browser_action', 'browser_action'):
            sans = self._outil(
                capacite, task_id='t3', action='ouvrir', text=adresse
            )
            self.assertIn('# Connectez-vous', sans['page'], capacite)
        # Hors de la session d'un compte, son mot de passe n'existe pas.
        champ = re.search(r'\[(e\d+)\] champ password', sans['page'])
        assert champ, sans['page']
        refus = self._outil(
            'browser_action',
            task_id='t3',
            action='taper_secret',
            ref=champ[1],
            text=PASSWORD_NAME,
        )
        self.assertIn('secret non permis', refus['detail'])

    def test_un_compte_connecte_avec_google_vit_dans_le_profil(self) -> None:
        """Un compte créé par un humain avec « Continuer avec Google »
        (décision Q113) : il s'est connecté à la main dans le vrai Chrome.
        Les tâches du compte s'ouvrent dans ce profil, déjà connectées ;
        rien de sa session n'est copié en base ; il n'a pas de mot de
        passe."""
        self._coffre()
        adresse = f'{self.site}/compte'
        web_accounts.register(
            self.conn, 'forum', self.site, 'serge-ia', '', 'google'
        )
        # L'humain s'est connecté dans le profil du vrai Chrome.
        avant = self._outil(
            'real_browser_action', task_id='t0', action='ouvrir', text=adresse
        )
        self.assertIn('# Connectez-vous', avant['page'])
        profil = sessions._ETAT_VRAI.profil
        assert profil is not None
        profil.add_cookies(
            [{'name': 'forum', 'value': 'jeton-de-session', 'url': self.site}]
        )
        page = self._avec_le_compte('t1', action='ouvrir', text=adresse)
        self.assertIn('# Bonjour serge-ia', page['page'])
        session = sessions._ETAT_VRAI.sessions['t1@forum']
        self.assertIs(session.context, profil)
        # Pas de mot de passe : le refus dit comment se reconnecter.
        refus = self._avec_le_compte(
            't1', action='taper_secret', ref='e1', text=PASSWORD_NAME
        )
        self.assertFalse(refus['ok'])
        self.assertIn('Continuer avec Google', refus['detail'])
        sessions.close_sessions(self.conn)
        self.assertEqual(
            tuple(
                self.conn.execute(
                    'SELECT password_enc, session_enc, used_by'
                    ' FROM web_accounts'
                ).fetchone()
            ),
            ('', '', ''),
        )
        # Le profil est toujours là : la tâche suivante y est connectée.
        suite = self._avec_le_compte('t2', action='ouvrir', text=adresse)
        self.assertIn('# Bonjour serge-ia', suite['page'])
        # Ses actions sont comptées comme celles de tout compte.
        self.assertEqual(web_accounts.actions_today(self.conn, 'forum'), 3)
        # Dans le navigateur sans écran, ce compte ne sert pas.
        sessions.close_sessions(self.conn)
        ailleurs = self._outil(
            'browser_action',
            task_id='t3',
            account='forum',
            action='ouvrir',
            text=adresse,
        )
        self.assertFalse(ailleurs['ok'])
        self.assertIn('il ne sert que dans le vrai Chrome', ailleurs['detail'])
        self.assertEqual(
            self.conn.execute('SELECT used_by FROM web_accounts').fetchone()[
                0
            ],
            '',
        )

    def test_la_garde_d_un_compte_web(self) -> None:
        """Un compte ne sert qu'à une tâche à la fois, pas au-delà de ses
        actions du jour, et pas s'il est fermé par le site."""
        self._coffre()
        adresse = f'{self.site}/compte'
        self.conn.execute(
            'INSERT INTO web_accounts(id, url, login, created_at, updated_at)'
            " VALUES('forum', ?, 'serge-ia', ?, ?)",
            (self.site, utcnow(), utcnow()),
        )
        self.assertTrue(
            self._avec_le_compte('t1', action='ouvrir', text=adresse)['ok']
        )
        pris = self._avec_le_compte('t2', action='ouvrir', text=adresse)
        self.assertEqual((pris['ok'], pris['code']), (False, 'compte'))
        self.assertIn('sert déjà à une autre tâche', pris['detail'])
        self.assertNotIn('t2@forum', sessions._ETAT_VRAI.sessions)
        # Au plafond du jour, plus aucune action : la page ne bouge pas.
        self.conn.execute(
            'UPDATE web_account_days SET actions=?',
            (web_accounts.daily_cap(self.conn),),
        )
        plein = self._avec_le_compte(
            't1', action='cliquer', text='Se connecter'
        )
        self.assertFalse(plein['ok'])
        self.assertIn('200 actions du jour', plein['detail'])
        self.assertIn('# Connectez-vous', plein['page'])
        # Lire la page ne coûte rien : elle reste lisible.
        lue = self._outil('real_browser_read', task_id='t1', account='forum')
        self.assertIn('# Connectez-vous', lue['page'])
        sessions.close_sessions(self.conn)
        self.conn.execute("UPDATE web_accounts SET status='blocked'")
        ferme = self._avec_le_compte('t3', action='ouvrir', text=adresse)
        self.assertIn('fermé par le site', ferme['detail'])
        # Un compte qui n'existe pas est dit, sans rien ouvrir.
        inconnu = self._outil(
            'real_browser_action',
            task_id='t4',
            account='ailleurs',
            action='ouvrir',
            text=adresse,
        )
        self.assertIn('pas de compte « ailleurs »', inconnu['detail'])

    def test_un_modele_ne_se_donne_ni_compte_ni_secrets(self) -> None:
        """Le compte et les secrets permis ne viennent que de la base :
        un modèle qui les donne lui-même n'est pas écouté, et son outil ne
        les lui propose pas."""
        recus: list[dict[str, Any]] = []

        def note(_conn: Any, _tool: str, args: dict[str, Any], _inv: str):
            recus.append(args)
            return {'ok': True}

        lien = self.conn.execute(
            'SELECT id, invocation_id FROM invocation_tools'
            " WHERE tool_id='navigateur_agir' ORDER BY id LIMIT 1"
        ).fetchone()
        with mock.patch.dict(RUNNERS, {'browser_action': note}):
            run_tool(
                self.conn,
                str(lien[1]),
                int(lien[0]),
                'navigateur_agir',
                {
                    'action': 'taper_secret',
                    'account': 'forum',
                    'secrets': 'stripe-live.key',
                },
                {'task_id': 't1', 'venture_id': 'ven_t'},
            )
        self.assertEqual(recus[0]['action'], 'taper_secret')
        self.assertNotIn('account', recus[0])
        self.assertNotIn('secrets', recus[0])
        schema = tool_schema(self.conn, 'navigateur_agir', set())
        assert schema is not None
        montres = schema['function']['parameters']['properties']
        self.assertIn('action', montres)
        self.assertNotIn('account', montres)
        self.assertNotIn('secrets', montres)

    def test_taper_un_secret_sans_le_montrer(self) -> None:
        config = self.dossier / 'config'
        (config / 'secrets').mkdir(parents=True)
        (config / 'secrets/carte-numero.key').write_text('4242424242424242\n')
        instance = self.dossier / 'instance.toml'
        instance.write_text(f'[paths]\nconfig_root = "{config}"\n')
        patcher = mock.patch.dict(
            os.environ, {'SERGE_INSTANCE_FILE': str(instance)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        page = self._outil(
            'browser_action', action='ouvrir', text=f'{self.site}/'
        )['page']
        champ = re.search(r'\[(e\d+)\] champ email « E-mail »', page)
        assert champ, page
        tape = self._outil(
            'browser_action',
            action='taper_secret',
            ref=champ[1],
            text='carte-numero.key',
            secrets='carte-numero.key',
        )
        self.assertTrue(tape['ok'])
        self.assertIn('= ••••', tape['page'])
        self.assertNotIn('4242424242424242', json.dumps(tape))
        refus = self._outil(
            'browser_action',
            action='taper_secret',
            ref=champ[1],
            text='stripe-live.key',
            secrets='carte-numero.key',
        )
        self.assertFalse(refus['ok'])
        self.assertIn('secret non permis', refus['detail'])
        # Remis en forme par la page, le numéro reste caché.
        self.assertEqual(
            navigateur.masquer(
                'n° 4242 4242 4242 4242, exp. 12 / 34', {'4242424242424242'}
            ),
            'n° ••••, exp. 12 / 34',
        )

    def test_taper_un_champ_de_la_carte_chiffree(self) -> None:
        # La carte de Serge reste chiffrée sur le serveur (payment-card.enc,
        # clé du coffre) : Serge la déchiffre au moment de taper.
        from cryptography.fernet import Fernet

        secrets = self.dossier / 'config/secrets'
        secrets.mkdir(parents=True)
        cle = Fernet.generate_key()
        (secrets / 'credential-vault.key').write_bytes(cle + b'\n')
        carte = {
            'pan': '4000002500003155',
            'exp_month': '8',
            'exp_year': '2029',
            'cvc': '123',
            'cardholder_name': 'Serge Work',
        }
        (secrets / 'payment-card.enc').write_bytes(
            Fernet(cle).encrypt(json.dumps(carte).encode())
        )
        instance = self.dossier / 'instance.toml'
        instance.write_text(
            f'[paths]\nconfig_root = "{self.dossier / "config"}"\n'
        )
        patcher = mock.patch.dict(
            os.environ, {'SERGE_INSTANCE_FILE': str(instance)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        page = self._outil(
            'browser_action', action='ouvrir', text=f'{self.site}/'
        )['page']
        champ = re.search(r'\[(e\d+)\] champ email « E-mail »', page)
        assert champ, page
        permis = 'payment-card.enc#pan,payment-card.enc#expiration'
        onglet = sessions._session(self.conn, 't1').page
        for nom, attendu in (
            ('payment-card.enc#pan', '4000002500003155'),
            ('payment-card.enc#expiration', '08/29'),
        ):
            tape = self._outil(
                'browser_action',
                action='taper_secret',
                ref=champ[1],
                text=nom,
                secrets=permis,
            )
            self.assertTrue(tape['ok'], tape)
            self.assertNotIn(attendu, json.dumps(tape))
            self.assertEqual(onglet.input_value('#email'), attendu)
        refus = self._outil(
            'browser_action',
            action='taper_secret',
            ref=champ[1],
            text='payment-card.enc#cvc',
            secrets=permis,
        )
        self.assertIn('secret non permis', refus['detail'])

    def test_une_capture_ne_montre_pas_un_secret(self) -> None:
        config = self.dossier / 'config'
        (config / 'secrets').mkdir(parents=True)
        (config / 'secrets/carte-a.key').write_text('4242424242424242\n')
        instance = self.dossier / 'instance.toml'
        instance.write_text(f'[paths]\nconfig_root = "{config}"\n')
        patcher = mock.patch.dict(
            os.environ, {'SERGE_INSTANCE_FILE': str(instance)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        page = self._outil(
            'browser_action', action='ouvrir', text=f'{self.site}/'
        )['page']
        champ = re.search(r'\[(e\d+)\] champ email « E-mail »', page)
        assert champ, page
        self._outil(
            'browser_action',
            action='taper_secret',
            ref=champ[1],
            text='carte-a.key',
            secrets='carte-a.key',
        )
        onglet = sessions._session(self.conn, 't1').page
        style = (
            '() => getComputedStyle(document.getElementById("email"))'
            '.webkitTextSecurity'
        )
        vu: list[str] = []
        vraie = onglet.screenshot

        def capture(**kwargs: Any) -> bytes:
            vu.append(onglet.evaluate(style))
            return vraie(**kwargs)

        # Pendant la capture, le champ qui a reçu le secret montre des
        # points, comme un mot de passe ; après, il redevient normal.
        with mock.patch.object(onglet, 'screenshot', capture):
            self.assertTrue(self._outil('browser_screenshot')['ok'])
        self.assertEqual(vu, ['disc'])
        self.assertEqual(onglet.evaluate(style), 'none')

    def test_sans_son_paquet_le_navigateur_le_dit(self) -> None:
        # Un serveur où le paquet Python manque : l'outil le dit clairement,
        # et la raison va au journal.
        with (
            mock.patch.object(sessions._ETAT, 'browser', None),
            mock.patch.dict(sys.modules, {'playwright.sync_api': None}),
            self.assertRaises(sessions.NavigateurAbsent) as refus,
        ):
            sessions._browser(self.conn, sessions._ETAT)
        self.assertIn('playwright manque sur ce serveur', str(refus.exception))

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
        # Avec 1 capture gardée : deux restent (le double), rien ne change
        # dans l'historique, et le cache sert ; la troisième fait retirer
        # les deux plus anciennes d'un coup.
        apres_deux = testeur.messages[3]
        self.assertEqual(_images(apres_deux).count('image_url'), 2)
        apres_trois = testeur.messages[4]
        self.assertEqual(_images(apres_trois).count('image_url'), 1)
        retirees = [
            p
            for m in apres_trois
            if isinstance(m.get('content'), list)
            for p in m['content']
            if 'capture retirée' in p.get('text', '')
        ]
        self.assertEqual(len(retirees), 2)
        fiche = fiche_tache(self.conn, str(tache))
        assert fiche is not None
        cadres = {c['titre']: c for c in fiche['cadres']}
        self.assertIn(
            'Vu, trois captures.',
            [c['v'] for c in cadres['Ce que le modèle a rendu']['champs']],
        )
        images = cadres['Captures gardées']['images']
        self.assertEqual(len(images), 3)
        self.assertTrue(
            images[0]['src'].startswith('/owner/api/fichier?id=art_')
        )
        # Un fichier téléchargé pendant la tâche est sur sa fiche aussi.
        self.conn.execute(
            'INSERT INTO artifacts(id, venture_id, kind, version,'
            ' path_or_url, hash, size_bytes, task_id, created_at)'
            " VALUES('art_csv', 'ven_t', 'telechargement', 1,"
            " '/x/telechargements/export.csv', 'h', 5, ?, ?)",
            (str(tache), utcnow()),
        )
        fiche = fiche_tache(self.conn, str(tache))
        assert fiche is not None
        cadres = {c['titre']: c for c in fiche['cadres']}
        self.assertEqual(
            cadres['Fichiers téléchargés']['fichiers'],
            [{'src': '/owner/api/fichier?id=art_csv', 'nom': 'export.csv'}],
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
    if 'pw' in sessions._PLAYWRIGHT:
        sessions._PLAYWRIGHT.pop('pw').stop()
    sessions._ETAT.browser = sessions._ETAT_VRAI.browser = None


if __name__ == '__main__':
    unittest.main()
