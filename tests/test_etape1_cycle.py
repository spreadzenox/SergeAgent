#!/usr/bin/env python3
"""L'étape 1 de bout en bout, décrite en base (lot 7), avec un faux modèle.

Scénario : un business est déjà en test. Julien lance un cycle avec le
texte « artisans ». « Explorer le web » cherche (une seule recherche
permise), lit l'aperçu d'une page, garde deux pages et ajoute un flux.
Une page de flux attendait déjà. « Trier » range les trois pages par
paquets de deux : une enrichit le business en test, une montre un besoin
nouveau, une est du bruit. « Formuler A » lit la page en entier et écrit
une idée ; la page devient sa preuve. « Formuler B » voit l'idée de A et
ne reçoit plus cette page. « Choisir » prend l'idée de A et ferme le cycle.
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.flow import fire_button, trigger_refusal  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'
PAGE_ARTISANS = 'https://forum.test/artisans-devis'
PAGE_PUB = 'https://pub.test/promo'
PAGE_FLUX = 'https://flux.test/relances'


def _bloc(texte: str, debut: str) -> Any:
    """Le JSON du bloc dont le titre commence par ``debut``."""
    suite = texte.split(f'## {debut}', 1)[1].split('\n', 1)[1]
    return json.loads(suite.split('\n', 1)[0])


def _appel(nom: str, args: dict) -> ChatResult:
    return ChatResult(
        '', 1, 1, 'faux', 1, (ToolCall('c1', nom, json.dumps(args)),)
    )


def _reponse(data: dict) -> ChatResult:
    return ChatResult(json.dumps(data), 10, 10, 'faux', 1)


class FauxModele:
    """Joue chaque invocation du cycle ; garde ce que chacune a reçu."""

    def __init__(self) -> None:
        self.recu: dict[str, list[dict[str, Any]]] = {}
        self.en_test = ''

    def __call__(
        self, _key, _model, messages, tools=None, **_kw
    ) -> ChatResult:
        system, user = messages[0]['content'], messages[1]['content']
        derniers = [m for m in messages if m['role'] == 'tool']
        nom = next(
            n
            for n, marque in (
                ('explorer', 'Tu cherches sur le web'),
                ('trier', 'Tu tries des pages'),
                ('formuler', 'Tu formules des idées'),
                ('choisir', 'Tu choisis les business'),
            )
            if marque in system
        )
        if not derniers:
            self.recu.setdefault(nom, []).append(
                {'system': system, 'user': user, 'outils': tools or []}
            )
        return getattr(self, nom)(user, derniers)

    def explorer(self, _user: str, outils: list) -> ChatResult:
        if len(outils) == 0:
            return _appel('web_search', {'query': 'artisans devis'})
        if len(outils) == 1:
            return _appel('web_search', {'query': 'deuxième recherche'})
        if len(outils) == 2:
            return _appel('apercu_page', {'url': PAGE_ARTISANS})
        self.outils_explorer = [json.loads(m['content']) for m in outils]
        return _reponse(
            {
                'pages': [
                    {
                        'url': PAGE_ARTISANS,
                        'titre': 'Devis',
                        'apercu': 'Je cherche',
                    },
                    {'url': PAGE_PUB, 'titre': 'Promo', 'apercu': 'Achetez'},
                ],
                'flux': [{'url': 'https://forum.test/rss', 'titre': 'Forum'}],
            }
        )

    def trier(self, user: str, _outils: list) -> ChatResult:
        pages = _bloc(user, 'Les pages à trier')
        rangement: dict[str, Any] = {
            'enrichit': [],
            'besoin_nouveau': [],
            'bruit': [],
        }
        for page in pages:
            if page['url'] == PAGE_ARTISANS:
                rangement['besoin_nouveau'].append(page['id'])
            elif page['url'] == PAGE_FLUX:
                rangement['enrichit'].append(
                    {'page': page['id'], 'business': self.en_test}
                )
            else:
                rangement['bruit'].append(page['id'])
        return _reponse(rangement)

    def formuler(self, user: str, outils: list) -> ChatResult:
        pages = _bloc(user, 'Les pages « besoin nouveau »')
        if len(self.recu['formuler']) == 2:
            return _reponse({'fiches': []})
        if not outils:
            return _appel('lire_page_entiere', {'id': pages[0]['id']})
        return _reponse(
            {
                'fiches': [
                    {
                        'titre': 'Devis dictés',
                        'description': 'les artisans dictent leurs devis',
                        'famille': 'petits_logiciels',
                        'pages': [pages[0]['id']],
                    }
                ]
            }
        )

    def choisir(self, user: str, _outils: list) -> ChatResult:
        candidats = _bloc(user, 'Les business candidats')
        return _reponse(
            {
                'choix': [
                    {'business': candidats[0]['id'], 'raison': 'preuve nette'}
                ]
            }
        )


def _recherche(query: str, limit: int = 5) -> dict:
    return {
        'ok': True,
        'query': query,
        'results': [{'title': 'Devis', 'url': PAGE_ARTISANS, 'excerpt': '…'}],
    }


PAGES_HTML = {
    PAGE_ARTISANS: '<title>Devis</title><nav>menu</nav><p>Je cherche un'
    ' outil pour faire mes devis.</p><p>Deuxième ligne.</p><ul><li>Un</li>'
    '<li>Deux</li></ul><p>Ligne 5.</p><p>Ligne 6.</p>',
}


class CycleEtape1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        self.conn.executescript(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v_test', 'Relances clients', 'SMOKE_RUNNING', 't', 't');"
            'INSERT INTO listen_docs(id, source, url, title, excerpt,'
            " fetched_at) VALUES('p_flux', 'rss', 'https://flux.test/relances',"
            " 'Relances', 'Mes clients ne paient pas', '2026-09-27T09:00:00');"
            "UPDATE invocation_settings SET value='1'"
            " WHERE invocation_id='explorer_web' AND name='recherches_max';"
            "UPDATE invocation_settings SET value='2'"
            " WHERE invocation_id='trier_pages' AND name='taille_paquet';"
        )
        self.conn.commit()
        for cible, faux in (
            ('serge.listen.web.search_public', _recherche),
            ('serge.listen.page.fetch_html', PAGES_HTML.__getitem__),
            ('serge.listen.page.check_host', lambda _url: None),
        ):
            patcher = mock.patch(cible, faux)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.modele = FauxModele()
        self.modele.en_test = 'v_test'

    def _cycle(self) -> None:
        self.assertIsNotNone(
            fire_button(self.conn, 'lancer_cycle', {'guide': 'artisans'})
        )
        for _ in range(12):
            process_one(self.conn, 'works', now=NOW, caller=self.modele)
        echecs = self.conn.execute(
            "SELECT invocation_id, last_error FROM tasks WHERE status='failed'"
        ).fetchall()
        self.assertEqual(echecs, [])

    def _labels(self) -> dict[str, str]:
        return dict(self.conn.execute('SELECT url, label FROM listen_docs'))

    def test_le_cycle_complet(self) -> None:
        self._cycle()
        self.assertEqual(
            self._labels(),
            {
                PAGE_FLUX: 'enrichit',
                PAGE_ARTISANS: 'preuve',
                PAGE_PUB: 'bruit',
            },
        )
        idee = self.conn.execute(
            'SELECT id, name, family, lifecycle, choice_reason FROM ventures'
            " WHERE id<>'v_test'"
        ).fetchone()
        self.assertEqual(
            idee[1:],
            (
                'Devis dictés',
                'petits_logiciels',
                'POC_SELECTED',
                'preuve nette',
            ),
        )
        preuves = self.conn.execute(
            'SELECT s.venture_id, d.url FROM venture_sources s'
            ' JOIN listen_docs d ON d.id=s.doc_id ORDER BY d.url'
        ).fetchall()
        self.assertEqual(
            preuves, [('v_test', PAGE_FLUX), (idee[0], PAGE_ARTISANS)]
        )
        cycle = self.conn.execute(
            'SELECT status, guide, finished_at<>"" FROM listen_cycles'
        ).fetchone()
        self.assertEqual(cycle, ('CLOSED', 'artisans', 1))
        self.assertEqual(
            self.conn.execute(
                'SELECT url, added_by, active FROM listen_feeds'
            ).fetchall(),
            [('https://forum.test/rss', 'explorer_web', 1)],
        )

    def test_ce_que_recoit_chaque_invocation(self) -> None:
        self._cycle()
        recu = self.modele.recu
        # Une seule recherche permise ; l'aperçu s'arrête à 5 lignes.
        limite, apercu = self.modele.outils_explorer[1:]
        self.assertEqual(limite['code'], 'limite_atteinte')
        self.assertEqual(len(apercu['lines']), 5)
        self.assertNotIn('menu', apercu['lines'])
        self.assertIn(
            'Tu es « Explorer le web »', recu['explorer'][0]['system']
        )
        self.assertIn(
            'Les business (version courte', recu['explorer'][0]['user']
        )
        # Trois pages, deux par paquet : deux appels à « Trier ».
        self.assertEqual(len(recu['trier']), 2)
        self.assertIn('(paquet 1 sur 2)', recu['trier'][0]['user'])
        # B voit l'idée de A, et plus la page que A a utilisée.
        a, b = recu['formuler']
        self.assertEqual(
            len(_bloc(a['user'], 'Les pages « besoin nouveau »')), 1
        )
        self.assertEqual(_bloc(b['user'], 'Les pages « besoin nouveau »'), [])
        self.assertIn('Devis dictés', b['user'].split('version courte')[1])
        self.assertIn(
            'Serge a\n3 places de test', recu['choisir'][0]['system']
        )

    def test_le_bouton_attend_une_place_et_la_fin_du_cycle(self) -> None:
        fire_button(self.conn, 'lancer_cycle', {'guide': 'x'})
        process_one(self.conn, 'works', now=NOW, caller=self.modele)
        self.assertEqual(
            trigger_refusal(self.conn, 'lancer_cycle'),
            'Cycle d’écoute en cours : 1 sur 1'.replace('’', "'"),
        )
        self.assertIsNone(fire_button(self.conn, 'lancer_cycle', {}))
        fire_button(self.conn, 'bouton_abandonner_cycle', {})
        self.conn.execute(
            "UPDATE tasks SET status='done' WHERE invocation_id='explorer_web'"
        )
        process_one(self.conn, 'works', now=NOW, caller=self.modele)
        self.assertEqual(
            self.conn.execute('SELECT status FROM listen_cycles').fetchone(),
            ('ABANDONED',),
        )
        self.assertEqual(trigger_refusal(self.conn, 'lancer_cycle'), '')
        self.conn.executescript(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v2', 'b', 'POC_SELECTED', 't', 't'),"
            " ('v3', 'c', 'SMOKE_DONE', 't', 't');"
        )
        self.assertEqual(
            trigger_refusal(self.conn, 'lancer_cycle'),
            'Places de test occupées : 3 sur 3',
        )

    def test_effacer_les_idees(self) -> None:
        self._cycle()
        fire_button(self.conn, 'bouton_effacer_idees', {})
        process_one(self.conn, 'works', now=NOW, caller=self.modele)
        self.assertEqual(
            self.conn.execute('SELECT id FROM ventures').fetchall(),
            [('v_test',)],
        )
        self.assertEqual(
            self.conn.execute(
                'SELECT venture_id FROM venture_sources'
            ).fetchall(),
            [('v_test',)],
        )
        note = self.conn.execute(
            "SELECT payload_json FROM events WHERE type='write.deleted'"
        ).fetchone()
        self.assertEqual(json.loads(note[0])['count'], 1)
        self.assertTrue(re.search(r'"table": "ventures"', note[0]))


if __name__ == '__main__':
    unittest.main()
