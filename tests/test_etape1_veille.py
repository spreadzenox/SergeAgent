#!/usr/bin/env python3
"""L'étape 1 sans LLM : la veille des flux, l'oubli des pages, lire une page.

Scénarios :
- toutes les 6 heures, une tâche par flux actif lit ses pages ; une page
  déjà gardée (même adresse) ne l'est pas deux fois, un flux coupé n'est
  pas lu ;
- chaque jour, les pages « bruit » ou jamais triées de plus de 30 jours
  sont supprimées, les « besoin nouveau » jamais utilisées après 60 jours,
  jamais une preuve ;
- lire une page rend ses lignes (titre, paragraphes, éléments de liste),
  sans le menu, et refuse les adresses du serveur.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.listen.page import (  # noqa: E402
    PageError,
    check_host,
    read_page,
    text_lines,
)

NOW = '2026-09-28T10:00:00+00:00'


def _flux(url: str, source: str, max_items: int = 50) -> list[dict]:
    return [
        {
            'url': f'{url}/page{n}',
            'title': f'Page {n}',
            'excerpt': '<p>Ligne 1</p><p>Ligne 2</p><p>Ligne 3</p>',
            'published': '2026-09-27',
            'id': '',
            'source': source,
        }
        for n in range(3)
    ][:max_items]


def _vider(conn: sqlite3.Connection) -> None:
    for _ in range(10):
        if process_one(conn, 'works', now=NOW) is None:
            return


class VeilleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        self.conn.executescript(
            'INSERT INTO listen_feeds(id, url, active) VALUES'
            " ('f1', 'https://a.test/rss', 1), ('f2', 'https://b.test/rss', 0);"
            "UPDATE invocation_settings SET value='2'"
            " WHERE invocation_id='lire_un_flux' AND name='pages_par_flux';"
        )
        self.conn.commit()
        patcher = mock.patch('serge.listen.collectors.fetch_rss', _flux)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_une_tache_par_flux_actif(self) -> None:
        _vider(self.conn)
        pages = self.conn.execute(
            'SELECT url, feed_id, source, excerpt FROM listen_docs ORDER BY url'
        ).fetchall()
        self.assertEqual(
            pages,
            [
                (
                    'https://a.test/rss/page0',
                    'f1',
                    'rss',
                    'Ligne 1\nLigne 2\nLigne 3',
                ),
                (
                    'https://a.test/rss/page1',
                    'f1',
                    'rss',
                    'Ligne 1\nLigne 2\nLigne 3',
                ),
            ],
        )
        lu = self.conn.execute(
            "SELECT last_read_at<>'' FROM listen_feeds ORDER BY id"
        ).fetchall()
        self.assertEqual(lu, [(1,), (0,)])

    def test_une_page_deja_gardee_ne_l_est_pas_deux_fois(self) -> None:
        _vider(self.conn)
        self.conn.execute("UPDATE triggers SET last_fired_at=''")
        _vider(self.conn)
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM listen_docs').fetchone(),
            (2,),
        )


def _il_y_a(jours: int) -> str:
    moment = datetime.now(UTC) - timedelta(days=jours)
    return moment.isoformat()


class OubliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        pages = [
            ('bruit_vieux', 'bruit', 31),
            ('bruit_recent', 'bruit', 2),
            ('jamais_triee', '', 40),
            ('preuve_vieille', 'preuve', 400),
            ('enrichit_vieille', 'enrichit', 400),
            ('besoin_45j', 'besoin_nouveau', 45),
            ('besoin_61j', 'besoin_nouveau', 61),
        ]
        self.conn.executemany(
            'INSERT INTO listen_docs(id, source, url, label, fetched_at)'
            " VALUES(?, 'web', ?, ?, ?)",
            [
                (i, f'https://x.test/{i}', label, _il_y_a(j))
                for i, label, j in pages
            ],
        )
        self.conn.commit()

    def test_seules_les_pages_inutiles_sont_oubliees(self) -> None:
        _vider(self.conn)
        gardees = [
            r[0]
            for r in self.conn.execute(
                'SELECT id FROM listen_docs ORDER BY id'
            )
        ]
        self.assertEqual(
            gardees,
            [
                'besoin_45j',
                'bruit_recent',
                'enrichit_vieille',
                'preuve_vieille',
            ],
        )
        notes = [
            json.loads(r[0])['count']
            for r in self.conn.execute(
                "SELECT payload_json FROM events WHERE type='write.deleted'"
            )
        ]
        self.assertEqual(sorted(notes), [1, 2])


HTML = (
    '<html><head><title> Mon  devis </title><script>var x=1</script></head>'
    '<body><nav><a>Accueil</a></nav><h1>Titre</h1><p>Premier'
    ' paragraphe.</p><ul><li>Un</li><li>Deux</li></ul><footer>Bas</footer>'
    '</body></html>'
)


class LirePageTests(unittest.TestCase):
    def test_les_lignes_d_une_page(self) -> None:
        titre, lignes = text_lines(HTML)
        self.assertEqual(titre, 'Mon devis')
        self.assertEqual(
            lignes, ['Titre', 'Premier paragraphe.', 'Un', 'Deux']
        )

    def test_un_apercu_et_la_page_entiere(self) -> None:
        with (
            mock.patch('serge.listen.page.check_host'),
            mock.patch('serge.listen.page.fetch_html', return_value=HTML),
        ):
            apercu = read_page('https://x.test/devis', 2)
            entiere = read_page('https://x.test/devis', 0)
        self.assertEqual(apercu['lines'], ['Titre', 'Premier paragraphe.'])
        self.assertEqual(apercu['total_lines'], 4)
        self.assertEqual(len(entiere['lines']), 4)

    def test_les_adresses_internes_sont_refusees(self) -> None:
        for url in (
            'http://127.0.0.1:8080/owner',
            'http://localhost/',
            'http://192.168.1.10/',
            'file:///etc/passwd',
        ):
            with self.assertRaises(PageError, msg=url):
                check_host(url)
        self.assertEqual(read_page('http://127.0.0.1/', 5)['ok'], False)


if __name__ == '__main__':
    unittest.main()
