#!/usr/bin/env python3
"""Mission Control, page Carte : tout le pipeline à plat.

La carte est lue en base : chaque invocation avec ce qui la lance, les
tables qu'elle lit et celles où elle écrit, ses outils, les liens vers les
suivantes et les missions qu'elle confie ; et, à part, sa dernière
exécution. Deux onglets : le pipeline principal, rangé par étape, et les
essais et boutons, une bande par petite chaîne.

Scénarios :
- le pipeline de départ : « Explorer le web » est à sa place, avec ses
  tables, ses outils et sa mission ; aucune case n'en chevauche une autre ;
- l'onglet des essais montre l'essai total et les boutons des réseaux, et
  en fantôme les invocations du pipeline principal qu'ils rejoignent ;
- une invocation, un lien et une écriture ajoutés en base apparaissent sur
  la carte, sans rien changer au code ;
- la dernière exécution : la dernière tâche partie, pas celle qui attend ;
- dans un vrai navigateur : la carte se dessine, se tire à la souris, se
  zoome à la molette, un clic ouvre le détail d'une invocation puis d'une
  table, et la carte suit la base sans recharger la page.
"""

from __future__ import annotations

import re
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.mc.carte_plan import rangs  # noqa: E402
from serge.mc.proj_carte import project_carte, project_carte_etat  # noqa: E402
from serge.mc.projectors import PAGE_SECTIONS, PROJECTORS  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402
from tests.taches_fixtures import tache  # noqa: E402

# Une invocation de plus, comme l'écrirait config/pipeline.yaml.
EN_PLUS = {
    'schema_version': 1,
    'invocations': [
        {
            'id': 'noter_les_pages',
            'title': 'Noter les pages',
            'role': 'Donne une note à chaque page gardée. Invocation de test.',
            'type': 'capability',
            'capability': 'echo',
            'step': 'pre_prospection',
            'writes': [
                {
                    'table': 'listen_docs',
                    'operation': 'update',
                    'key': {'column': 'id', 'source': 'task', 'value': 'doc'},
                    'values': {'label': {'source': 'fixed', 'value': 'bruit'}},
                }
            ],
        }
    ],
    'links': [
        {
            'id': 'tri_vers_note',
            'title': 'Les pages triées sont notées',
            'from': 'trier_pages',
            'to': 'noter_les_pages',
            'condition': {'field': 'pages', 'op': 'non_vide'},
        }
    ],
}


def _chevauchements(onglet: dict) -> list[tuple[str, str]]:
    cases = onglet['noeuds']
    return [
        (a['id'], b['id'])
        for n, a in enumerate(cases)
        for b in cases[n + 1 :]
        if a['x'] < b['x'] + b['w']
        and b['x'] < a['x'] + a['w']
        and a['y'] < b['y'] + b['h']
        and b['y'] < a['y'] + a['h']
    ]


class CarteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _carte(self) -> dict:
        return project_carte(self.conn, {}, '')

    def _case(self, onglet: dict, ident: str) -> dict:
        return next(c for c in onglet['noeuds'] if c['id'] == ident)

    def test_la_page_a_ses_deux_sections(self) -> None:
        self.assertEqual(PAGE_SECTIONS['p2'], ['meta', 'carte', 'carte_etat'])
        self.assertIs(PROJECTORS['carte'], project_carte)

    def test_le_pipeline_principal_range_par_etape(self) -> None:
        principal = self._carte()['principal']
        self.assertEqual(
            [b['titre'] for b in principal['bandes']][:2],
            ['1. Pré-prospection', '2. Conception d’un PoC'],
        )
        self.assertEqual(principal['bandes'][-1]['titre'], 'Hors étape')
        self.assertEqual(_chevauchements(principal), [])
        explorer = self._case(principal, 'explorer_web')
        ouvrir = self._case(principal, 'ouvrir_cycle')
        # Dans sa bande, une invocation est à droite de celle qui y mène.
        bande = principal['bandes'][0]
        self.assertTrue(bande['y'] < explorer['y'] < bande['y'] + bande['h'])
        self.assertGreater(explorer['x'], ouvrir['x'])
        self.assertEqual(explorer['sorte'], 'llm')
        # Ce qu'elle lit (par un outil, ou pour comparer) et où elle écrit.
        self.assertEqual(
            [(t['table'], t['par']) for t in explorer['lit']],
            [
                ('listen_cycles', ['Le cycle en cours']),
                ('ventures', ['pour comparer']),
            ],
        )
        pages = explorer['ecrit'][0]
        self.assertEqual(
            (pages['table'], pages['titre']),
            ('listen_docs', 'Les pages gardées'),
        )
        regle = pages['regles'][0]
        self.assertEqual(
            (regle['operation'], regle['pour_chaque']), ('insert', 'pages')
        )
        self.assertIn(
            {'colonne': 'url', 'source': 'field', 'valeur': 'pages.url'},
            regle['colonnes'],
        )
        # Ses outils, avec leur capacité ; une mission est un trait vers
        # l'invocation qui la fait, rangée « Hors étape ».
        self.assertIn(
            ('Chercher sur le web public', 'Chercher sur le web'),
            [(o['titre'], o['capacite']) for o in explorer['outils']],
        )
        missions = [
            lien
            for lien in principal['liens']
            if lien['sorte'] == 'mission' and lien['de'] == 'explorer_web'
        ]
        self.assertEqual([m['vers'] for m in missions], ['fouiller_reseau'])
        self.assertIn('Fouiller Reddit', missions[0]['titre'])
        self.assertTrue(
            self._case(principal, 'fouiller_reseau')['mission_seule']
        )
        # Ce qui lance une invocation : un bouton, une horloge, une ligne.
        self.assertEqual(
            [(d['sorte'], d['texte']) for d in ouvrir['lance']][:1],
            [('bouton', "bouton « Lancer un cycle d'écoute »")],
        )
        self.assertEqual(
            {d['sorte'] for d in ouvrir['lance']}, {'bouton', 'ligne'}
        )
        releve = self._case(principal, 'relever_messages')
        self.assertIn(
            'toutes les 2 min', [d['texte'] for d in releve['lance']]
        )
        # Un lien dit sa condition ; aucun ne pointe hors de l'onglet.
        ids = {c['id'] for c in principal['noeuds']}
        for lien in principal['liens']:
            self.assertIn(lien['de'], ids)
            self.assertIn(lien['vers'], ids)
            self.assertNotEqual(lien.get('couloir'), 'trial')

    def test_les_essais_et_les_boutons(self) -> None:
        carte = self._carte()
        essais = carte['essais']
        titres = [b['titre'] for b in essais['bandes']]
        self.assertEqual(titres[0], "Lancer l'essai total")
        self.assertIn("Envoyer un message d'essai sur un réseau", titres)
        self.assertEqual(titres[-1], 'Couloir d’essai')
        self.assertEqual(_chevauchements(essais), [])
        # L'essai total rejoint le pipeline principal : ces invocations
        # sont là en fantôme, sans leurs rangées.
        cycle = self._case(essais, 'ouvrir_cycle')
        self.assertTrue(cycle['fantome'])
        self.assertEqual((cycle['lit'], cycle['ecrit']), ([], []))
        self.assertFalse(self._case(essais, 'lancer_essai_total')['fantome'])
        # La boucle du message d'essai : l'envoi, son compteur, et retour.
        boucle = {
            (lien['de'], lien['vers'])
            for lien in essais['liens']
            if 'compter_rappels_contact' in (lien['de'], lien['vers'])
        }
        self.assertEqual(
            boucle,
            {
                ('envoyer_par_le_web', 'compter_rappels_contact'),
                ('compter_rappels_contact', 'envoyer_par_le_web'),
            },
        )
        # Une invocation lancée seulement par un bouton d'essai n'est pas
        # dans le pipeline principal.
        principal = {c['id'] for c in carte['principal']['noeuds']}
        self.assertNotIn('lancer_essai_total', principal)
        self.assertNotIn('compter_rappels_contact', principal)

    def test_ce_qui_est_ajoute_en_base_est_sur_la_carte(self) -> None:
        avant = self._carte()['principal']
        self.assertNotIn('noter_les_pages', [c['id'] for c in avant['noeuds']])
        seed_pipeline(self.conn, EN_PLUS)
        apres = self._carte()['principal']
        neuve = self._case(apres, 'noter_les_pages')
        self.assertEqual(neuve['etape'], 'pre_prospection')
        self.assertEqual(
            [
                (t['table'], t['regles'][0]['operation'])
                for t in neuve['ecrit']
            ],
            [('listen_docs', 'update')],
        )
        lien = next(
            lien for lien in apres['liens'] if lien['id'] == 'tri_vers_note'
        )
        self.assertEqual(
            (lien['de'], lien['vers'], lien['condition']),
            ('trier_pages', 'noter_les_pages', 'pages non_vide'),
        )
        self.assertGreater(neuve['x'], self._case(apres, 'trier_pages')['x'])
        self.assertEqual(_chevauchements(apres), [])
        # Supprimée dans Mission Control, elle quitte la carte.
        self.conn.execute(
            "UPDATE invocations SET deleted_at='t' WHERE id='noter_les_pages'"
        )
        self.assertNotIn(
            'noter_les_pages',
            [c['id'] for c in self._carte()['principal']['noeuds']],
        )

    def test_la_derniere_execution_de_chaque_invocation(self) -> None:
        self.assertEqual(
            project_carte_etat(self.conn, {}, ''), {'invocations': {}}
        )
        tache(self.conn, 'trier_pages', {'n': '1'}, key='k1', status='done')
        rate = tache(
            self.conn,
            'trier_pages',
            {'n': '2'},
            key='k2',
            status='failed',
            error='réponse mal formée',
        )
        # Une tâche qui attend son tour n'est pas une exécution.
        tache(self.conn, 'trier_pages', {'n': '3'}, key='k3')
        tache(
            self.conn, 'explorer_web', {'n': '4'}, key='k4', status='running'
        )
        etats = project_carte_etat(self.conn, {}, '')['invocations']
        self.assertEqual(sorted(etats), ['explorer_web', 'trier_pages'])
        self.assertEqual(
            (
                etats['trier_pages']['tache'],
                etats['trier_pages']['statut'],
                etats['trier_pages']['erreur'],
            ),
            (rate, 'failed', 'réponse mal formée'),
        )
        self.assertEqual(etats['explorer_web']['statut'], 'running')

    def test_une_boucle_ne_fait_pas_tourner_le_rangement(self) -> None:
        """Critiquer, puis corriger, puis critiquer : le lien de retour ne
        compte pas, chacun garde son rang."""
        self.assertEqual(
            rangs(
                ['a', 'b', 'c', 'd'],
                [('a', 'b'), ('b', 'c'), ('c', 'b'), ('c', 'd'), ('x', 'a')],
            ),
            {'a': 0, 'b': 1, 'c': 2, 'd': 3},
        )


class CarteDansLeNavigateurTests(McBrowserCase):
    def _vue(self, page) -> str:
        return page.evaluate(
            "document.querySelector('[data-carte=plan]').style.transform"
        )

    def test_la_carte_se_parcourt_et_suit_la_base(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        page.set_viewport_size({'width': 1500, 'height': 900})
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/carte')
        case = page.locator('.carte-case[data-id="explorer_web"]')
        expect(case).to_be_visible(timeout=15000)
        expect(page.locator('.carte-bande h3').first).to_have_text(
            '1. Pré-prospection'
        )
        expect(case.locator('.carte-derniere')).to_have_text('jamais lancée')
        # Tirer le fond déplace la carte ; la molette zoome.
        depart = self._vue(page)
        boite = page.locator('[data-carte="vue"]').bounding_box()
        assert boite is not None
        x, y = (
            boite['x'] + boite['width'] - 40,
            boite['y'] + boite['height'] - 40,
        )
        page.mouse.move(x, y)
        page.mouse.down()
        page.mouse.move(x - 180, y - 90, steps=4)
        page.mouse.up()
        tiree = self._vue(page)
        self.assertNotEqual(tiree, depart)
        self.assertIn('scale(0.8)', tiree)
        page.mouse.wheel(0, -300)
        self.assertNotIn('scale(0.8)', self._vue(page))
        # Un clic sur une carte : son détail, à droite.
        page.locator('[data-carte="chercher"]').fill('explorer le web')
        expect(page.locator('[data-carte="trouvees"]')).to_have_text(
            '1 trouvée(s)'
        )
        case.locator('.carte-carte').click()
        fiche = page.locator('[data-carte="fiche"]')
        expect(fiche).to_contain_text('Cherche sur le web des pages')
        expect(fiche).to_contain_text('Sa dernière exécution')
        expect(fiche).to_contain_text('Fouiller un réseau')
        expect(case).to_have_class(re.compile(r'\bchoisie\b'))
        # Un clic sur une table où elle écrit : ce qu'elle y écrit, et qui
        # d'autre la touche.
        case.locator('.carte-tables.ecrit .carte-table').first.click()
        expect(fiche.locator('h3')).to_have_text('listen_docs')
        expect(fiche).to_contain_text('ajoute une ligne pour chaque « pages »')
        expect(fiche).to_contain_text('Qui la lit')
        # La base change : la carte suit, sans recharger la page.
        conn = sqlite3.connect(self.db_path)
        try:
            seed_pipeline(conn, EN_PLUS)
            tache(
                conn,
                'explorer_web',
                {'n': '1'},
                key='k1',
                status='failed',
                error='boum',
            )
            conn.commit()
        finally:
            conn.close()
        expect(
            page.locator('.carte-case[data-id="noter_les_pages"]')
        ).to_be_visible(timeout=15000)
        expect(case.locator('.carte-derniere')).to_contain_text(
            'en échec', timeout=15000
        )
        # L'autre onglet : les essais et les boutons.
        page.get_by_role('tab', name='Essais et boutons').click()
        expect(page.locator('.carte-bande h3').first).to_have_text(
            "Lancer l'essai total"
        )
        expect(
            page.locator('.carte-case[data-id="ouvrir_cycle"]')
        ).to_have_class(re.compile(r'\bfantome\b'))


if __name__ == '__main__':
    unittest.main()
