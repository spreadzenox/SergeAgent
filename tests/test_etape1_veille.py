#!/usr/bin/env python3
"""L'étape 1 sans LLM : la veille des flux, l'oubli des pages, lire une page.

Scénarios :
- toutes les 6 heures, une tâche par flux actif lit ses pages ; une page
  déjà gardée (même adresse) ne l'est pas deux fois, un flux coupé n'est
  pas lu ;
- un site qui n'accepte qu'une lecture par minute (Reddit) répond 429 aux
  autres : elles repartent après l'attente qu'il demande, et tous ses flux
  sont lus ; un site qui refuse toujours laisse la tâche en échec, avec la
  raison, dans la base et dans le journal de la file ;
- chaque jour, les pages « bruit » ou jamais triées de plus de 30 jours
  sont supprimées, les « besoin nouveau » jamais utilisées après 60 jours,
  jamais une preuve ;
- lire une page rend ses lignes (titre, paragraphes, éléments de liste),
  sans le menu, et refuse les adresses du serveur.
"""

from __future__ import annotations

import io
import json
import sqlite3
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr
from datetime import UTC, datetime, timedelta
from http.client import HTTPMessage
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
from serge.policy import load_policy  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'


# Les réglages « Lecture du web » de départ (page Policy).
WEB = load_policy()['web']


def _flux(
    url: str, source: str, *, timeout: float, max_items: int
) -> list[dict]:
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


def _vider(conn: sqlite3.Connection, now: str = NOW) -> None:
    for _ in range(10):
        if process_one(conn, 'works', now=now) is None:
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


# Un flux Atom comme ceux de Reddit : le lien est dans ``href``, le texte
# dans ``content``.
ATOM = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<feed xmlns="http://www.w3.org/2005/Atom"><title>forum</title>'
    '<entry><title>Avis PEA</title><link href="{flux}comments/1/"/>'
    '<content type="html">&lt;p&gt;Bonjour, un avis ?&lt;/p&gt;</content>'
    '<updated>2026-09-28T09:00:00+00:00</updated></entry></feed>'
)


class _SiteLimite:
    """Un faux site qui accepte ``par_minute`` lecture par minute et
    répond 429 aux autres, avec l'attente dans ``x-ratelimit-reset``."""

    def __init__(self, par_minute: int) -> None:
        self.par_minute = par_minute
        self.minute = 0
        self.lues: list[tuple[int, str]] = []
        self.refus = 0

    def __call__(self, request, timeout: float) -> io.BytesIO:
        flux = request.full_url
        servies = sum(1 for minute, _ in self.lues if minute == self.minute)
        if servies >= self.par_minute:
            self.refus += 1
            entetes = HTTPMessage()
            entetes['x-ratelimit-reset'] = '41'
            raise urllib.error.HTTPError(
                flux, 429, 'Too Many Requests', entetes, None
            )
        self.lues.append((self.minute, flux))
        return io.BytesIO(ATOM.format(flux=flux[:-4]).encode())


class VeilleSiteLimiteTests(unittest.TestCase):
    """Trois flux du même site, lus à la même seconde (le serveur, du 29
    septembre au 16 novembre 2026 : 1 lecture finie et 4 en échec à chaque
    passage, et aucune page gardée)."""

    FLUX = [f'https://forum.test/r/{nom}/.rss' for nom in 'abc']

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        self.conn.executemany(
            'INSERT INTO listen_feeds(id, url, active) VALUES(?, ?, 1)',
            [(f'f{n}', url) for n, url in enumerate(self.FLUX)],
        )
        self.conn.commit()
        # Pas de réseau en test : l'adresse est jugée publique.
        patcher = mock.patch('serge.listen.page.check_host')
        patcher.start()
        self.addCleanup(patcher.stop)

    def _passer(self, site: _SiteLimite, minutes: int) -> str:
        """Vide la file ``minutes`` minutes après le déclencheur ; rend ce
        que la file a écrit dans son journal."""
        site.minute = minutes
        moment = datetime.fromisoformat(NOW) + timedelta(minutes=minutes)
        with (
            mock.patch('urllib.request.urlopen', site),
            redirect_stderr(io.StringIO()) as journal,
        ):
            _vider(self.conn, moment.isoformat())
        return journal.getvalue()

    def _taches(self) -> list[tuple[str, str, str]]:
        return self.conn.execute(
            'SELECT t.status, t.not_before, t.last_error FROM tasks t'
            ' JOIN task_params p ON p.task_id=t.id'
            " WHERE t.invocation_id='lire_un_flux' AND p.name='url'"
            ' ORDER BY p.value'
        ).fetchall()

    def test_les_lectures_refusees_repartent_et_tous_les_flux_sont_lus(
        self,
    ) -> None:
        site = _SiteLimite(par_minute=1)
        journal = self._passer(site, 0)
        # Une lecture passe ; les deux autres attendent 41 s plus une de
        # marge, sans être en échec.
        plus_tard = '2026-09-28T10:00:42+00:00'
        self.assertEqual(
            self._taches(),
            [
                ('done', '', ''),
                ('ready', plus_tard, ''),
                ('ready', plus_tard, ''),
            ],
        )
        self.assertIn(
            'remise à plus tard (42 s) : NETWORK: HTTP 429 Too Many Requests'
            f' ({self.FLUX[1]})',
            journal,
        )
        refus = [
            json.loads(r[0])
            for r in self.conn.execute(
                "SELECT payload_json FROM events WHERE type='task.too_fast'"
            )
        ]
        self.assertEqual(
            [(r['not_before'], r['error']) for r in refus],
            [
                (
                    plus_tard,
                    f'NETWORK: HTTP 429 Too Many Requests ({flux})',
                )
                for flux in self.FLUX[1:]
            ],
        )
        # Une minute après, le site en accepte une de plus ; puis la
        # dernière.
        self._passer(site, 1)
        self.assertEqual(
            [t[0] for t in self._taches()], ['done', 'done', 'ready']
        )
        self._passer(site, 2)
        self.assertEqual([t[0] for t in self._taches()], ['done'] * 3)
        self.assertEqual(site.lues, list(enumerate(self.FLUX)))
        self.assertEqual(site.refus, 3)
        # Chaque flux a ramené sa page, lue dans le format Atom.
        pages = self.conn.execute(
            'SELECT feed_id, url, title, excerpt FROM listen_docs'
            ' ORDER BY feed_id'
        ).fetchall()
        self.assertEqual(
            pages,
            [
                (
                    f'f{n}',
                    f'{flux[:-4]}comments/1/',
                    'Avis PEA',
                    'Bonjour, un avis ?',
                )
                for n, flux in enumerate(self.FLUX)
            ],
        )
        lus = self.conn.execute(
            "SELECT COUNT(*) FROM listen_feeds WHERE last_read_at<>''"
        ).fetchone()
        self.assertEqual(lus, (3,))

    def test_un_site_qui_refuse_toujours_laisse_un_echec_avec_la_raison(
        self,
    ) -> None:
        self.conn.execute(
            "UPDATE policy_settings SET value_json='1'"
            " WHERE id='web.feed_retries'"
        )
        self.conn.execute("UPDATE listen_feeds SET active=0 WHERE id<>'f0'")
        self.conn.commit()
        site = _SiteLimite(par_minute=0)
        self._passer(site, 0)
        self.assertEqual([t[0] for t in self._taches()], ['ready'])
        journal = self._passer(site, 1)
        raison = (
            f'NETWORK: HTTP 429 Too Many Requests ({self.FLUX[0]}),'
            ' refusé 2 fois de suite'
        )
        self.assertEqual(self._taches(), [('failed', mock.ANY, raison)])
        self.assertIn(f'« Lire un flux RSS » en échec : {raison}', journal)
        self.assertEqual(site.refus, 2)
        self.assertEqual(
            self.conn.execute(
                'SELECT (SELECT COUNT(*) FROM listen_docs),'
                " (SELECT COUNT(*) FROM listen_feeds WHERE last_read_at<>'')"
            ).fetchone(),
            (0, 0),
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
        titre, lignes = text_lines(HTML, 300)
        self.assertEqual(titre, 'Mon devis')
        self.assertEqual(
            lignes, ['Titre', 'Premier paragraphe.', 'Un', 'Deux']
        )

    def test_une_ligne_a_une_longueur_maximale(self) -> None:
        """Une page dont le texte n'est pas rangé en paragraphes ne tient
        pas en une seule ligne géante (premier cycle en production)."""
        texte = ' '.join(f'mot{n}' for n in range(20000))
        _, lignes = text_lines(f'<div><span>{texte}</span></div>', 300)
        self.assertGreater(len(lignes), 100)
        self.assertTrue(all(len(ligne) <= 300 for ligne in lignes))
        self.assertEqual(' '.join(lignes), texte)

    def test_un_apercu_et_la_page_entiere(self) -> None:
        with (
            mock.patch('serge.listen.page.check_host'),
            mock.patch('serge.listen.page.fetch_html', return_value=HTML),
        ):
            apercu = read_page('https://x.test/devis', 2, WEB)
            entiere = read_page('https://x.test/devis', 0, WEB)
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
        self.assertEqual(read_page('http://127.0.0.1/', 5, WEB)['ok'], False)


if __name__ == '__main__':
    unittest.main()
