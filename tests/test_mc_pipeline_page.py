#!/usr/bin/env python3
"""MC : la page Pipeline, vue d'ensemble du pipeline tel qu'il est en base.

Scénario : sur une base neuve (le demi-cycle de démonstration), la page
montre les liens, les déclencheurs, les outils, les capacités et ce que
les invocations voient des tables. Julien cherche un modèle dans la liste
d'OpenRouter, prend la recommandation du niveau moyen et réécrit le texte
« Qui est Serge » ; l'invocation suivante les reçoit. Il règle le prix
maximum et la tolérance d'un niveau, qui vivent en base avec son modèle. Un
identifiant qu'OpenRouter ne connaît pas est refusé. Un clic sur un lien
ouvre sa fiche.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.openrouter import OpenRouterError  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.run import resolve_model  # noqa: E402
from serge.llm import catalog  # noqa: E402
from serge.mc.proj_pipeline import project_pipeline  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402


class ProjectionPipelineTests(unittest.TestCase):
    def test_tout_le_pipeline_de_la_base(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = project_pipeline(conn, {}, '')
        liens = {lien['id']: lien for lien in data['liens']}
        self.assertEqual(
            liens['formuler_b_vers_choix']['chemin'],
            'Formuler des business B → Choisir les business à tester',
        )
        self.assertEqual(
            liens['formuler_b_vers_choix']['passage'], 'automatique'
        )
        quand = {d['id']: d['quand'] for d in data['declencheurs']}
        self.assertEqual(quand['lancer_cycle'], 'un bouton de Mission Control')
        self.assertEqual(quand['veille_flux'], 'toutes les 360 minutes')
        outils = {o['id']: o for o in data['outils']}
        self.assertEqual(
            outils['lire_tables_vues']['utilise_par'],
            'toutes les invocations LLM',
        )
        self.assertEqual(
            outils['current_listen_cycle']['utilise_par'], '1 invocation(s)'
        )
        capacites = {c['id']: c for c in data['capacites']}
        self.assertTrue(capacites['seen_table_read']['disponible'])
        tables = {t['table']: t for t in data['tables']}
        self.assertEqual(tables['ventures']['courte'], 'id, name')
        self.assertEqual(
            [m['tier'] for m in data['modeles']], ['fast', 'mid', 'smart']
        )
        textes = {t['id']: t for t in data['textes']}
        self.assertIn(
            'opérateur économique autonome', textes['presentation']['valeur']
        )
        self.assertEqual(
            textes['format_retry']['titre'], 'Quand la réponse est mal formée'
        )
        # Les réglages qui touchent au modèle sont sur cette page (Q68).
        self.assertEqual(
            [s['id'] for s in data['reglages']],
            ['llm_calls', 'tools', 'model_choice'],
        )


def _modele(ident: str, prix: float, **autres) -> dict:
    base = {
        'id': ident,
        'name': ident.split('/')[1].title(),
        'context_length': 200_000,
        'prompt_usd': prix,
        'completion_usd': prix,
        'tools': True,
        'text_out': True,
        'created': 0,
        'expires': '',
        'intelligence': None,
        'cache_read_usd': None,
        'cache_write_usd': None,
    }
    return {**base, **autres}


# Le catalogue d'OpenRouter, avec la note d'Artificial Analysis qu'il donne :
# deux modèles du niveau moyen, un modèle sans outils ni note, deux « gpt » et
# une variante « batch » (réponse sous 24 h) moins chère que le modèle normal.
CATALOGUE = [
    _modele('deepseek/deepseek-flash', 0.10, intelligence=40.0),
    _modele('deepseek/deepseek-flash:batch', 0.05, intelligence=40.0),
    _modele('mistralai/mistral-small', 0.90, intelligence=52.0),
    _modele('google/gemini-mid', 1.20, intelligence=60.0),
    _modele('openai/gpt-mini', 0.40, intelligence=38.0),
    _modele('openai/gpt-muet', 0.05, tools=False),
]


class PipelinePageTests(McBrowserCase):
    def setUp(self) -> None:
        super().setUp()
        catalog.clear_cache()
        self.addCleanup(catalog.clear_cache)
        self.reponse_openrouter: object = CATALOGUE
        self.appels_openrouter = 0
        patcher = mock.patch(
            'serge.llm.catalog._read_openrouter', self._openrouter
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _openrouter(self, _cle: str) -> list[dict]:
        self.appels_openrouter += 1
        if isinstance(self.reponse_openrouter, Exception):
            raise self.reponse_openrouter
        return self.reponse_openrouter  # type: ignore[return-value]

    def _get(self, chemin: str, cookie: str) -> tuple[int, dict]:
        statut, _, corps = self._request(
            'GET', chemin, None, {'Cookie': cookie}
        )
        return statut, json.loads(corps or b'{}')

    def _base(self, sql: str) -> list[tuple]:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_regler_le_modele_et_le_texte(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/pipeline')
        section = page.locator('[data-section="pipeline"]')
        for texte in (
            'Les idées passent au choix',
            'Lancer un cycle d’écoute'.replace('’', "'"),
            'Lire les tables que je vois',
            'Lire l’historique d’une ligne',
            'id, name',
        ):
            expect(section).to_contain_text(texte, timeout=10000)
        expect(section).to_contain_text(
            '6 modèles d’OpenRouter', timeout=10000
        )
        expect(section).to_contain_text(
            '5 modèles notés sur 6 (indice d’intelligence d’Artificial'
            ' Analysis, donné par OpenRouter)'
        )
        # Niveau rapide : la variante batch, moins chère, est écartée.
        expect(page.locator('[data-reco="fast"]')).to_contain_text(
            'Recommandé (plafond 0,30 $/M) : deepseek/deepseek-flash.'
        )
        # Niveaux moyen et intelligent : presque la meilleure note (60).
        reco = page.locator('[data-reco="mid"]')
        expect(reco).to_contain_text(
            'Recommandé (plafond 1,50 $/M) : google/gemini-mid.'
        )
        champ = page.locator('[data-tier="mid"]')
        reco.get_by_role('button', name='Utiliser').click()
        expect(champ).to_have_value('google/gemini-mid')
        # La variante batch est proposée en dernier, et dite différée.
        flash = page.locator('[data-tier="fast"]')
        flash.fill('deepseek')
        liste = flash.locator('xpath=../../..').locator('.proposition')
        expect(liste).to_have_count(2)
        expect(liste.first).to_contain_text('entrée 0,100 · sortie 0,100 $/M')
        expect(liste.last).to_contain_text('batch : réponse différée')
        # Sans assez d'appels enregistrés, le mélange est celui par défaut.
        expect(section).to_contain_text('Mélange supposé : 75 % de jetons lus')
        # Chercher : les modèles sans outils passent après les autres.
        autre = page.locator('[data-tier="smart"]')
        autre.fill('gpt')
        propositions = autre.locator('xpath=../../..').locator('.proposition')
        expect(propositions).to_have_count(2)
        expect(propositions.first).to_contain_text('openai/gpt-mini')
        expect(propositions.last).to_contain_text('sans outils')
        propositions.first.click()
        expect(autre).to_have_value('openai/gpt-mini')
        expect(propositions).to_have_count(0)
        # Le prix maximum et la tolérance vivent avec le modèle du niveau.
        prix = page.locator('[data-max-price="mid"]')
        tolerance = page.locator('[data-tolerance="mid"]')
        expect(prix).to_have_value('1.5')
        expect(tolerance).to_have_value('95')
        expect(page.locator('[data-max-price="fast"]')).to_have_value('0.3')
        expect(page.locator('[data-tolerance="fast"]')).to_have_value('85')
        prix.fill('2')
        tolerance.fill('90')
        bouton = champ.locator('xpath=../..').get_by_role(
            'button', name='Enregistrer'
        )
        with page.expect_response('**/owner/api/pipeline/modele') as reponse:
            bouton.click()
        self.assertTrue(reponse.value.ok)
        conn = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(
                resolve_model(conn, 'mid')[0], 'google/gemini-mid'
            )
        finally:
            conn.close()
        self.assertEqual(
            self._base(
                'SELECT max_price_usd, tolerance_pct FROM llm_models'
                " WHERE tier='mid'"
            ),
            [(2.0, 90)],
        )
        # La recommandation se recalcule avec le nouveau prix maximum.
        expect(reco).to_contain_text('Recommandé (plafond 2,00 $/M)')
        texte = page.locator('[data-texte="presentation"]')
        texte.locator('textarea').fill('Serge, version de Julien.')
        with page.expect_response('**/owner/api/reglage') as reponse:
            texte.get_by_role('button', name='Enregistrer').click()
        self.assertTrue(reponse.value.ok)
        self.assertEqual(
            self._base("SELECT body FROM serge_texts WHERE id='presentation'"),
            [('Serge, version de Julien.',)],
        )
        expect(
            texte.get_by_role('button', name='Remettre le texte précédent')
        ).to_be_visible(timeout=10000)
        # Un réglage des appels au modèle, sur la même page.
        page.locator(
            '[data-pipeline="reglages"] button.onglet-policy',
            has_text='Appels au modèle',
        ).click()
        attente = page.locator(
            '.champ-policy[data-chemin="llm_calls.timeout_s"]'
        )
        attente.locator('input[type="number"]').fill('240')
        with page.expect_response('**/owner/api/reglage') as reponse:
            attente.get_by_role('button', name='Enregistrer').click()
        self.assertTrue(reponse.value.ok)
        self.assertEqual(
            self._base(
                "SELECT value_json FROM policy_settings WHERE id='llm_calls.timeout_s'"
            ),
            [('240',)],
        )
        page.locator(
            '[data-pipeline="liens"] tr', has_text='Les idées passent au choix'
        ).click()
        expect(page.locator('#page')).to_contain_text('Ce qui attend un clic')

    def test_valeurs_refusees(self) -> None:
        cookie = self._auth_cookie()
        reglages = (
            {'max_price': -1},
            {'max_price': 'cher'},
            {'max_price': 5000},
            {'max_price': True},
            {'tolerance': 0},
            {'tolerance': 101},
            {'tolerance': 90.5},
            {'tolerance': True},
        )
        for corps, attendu in (
            ({'tier': 'mid', 'model': 'rm -rf /; x'}, 400),
            ({'tier': 'ultra', 'model': 'x'}, 409),
            *(({'tier': 'mid', 'model': '', **r}, 400) for r in reglages),
        ):
            status, _, _ = self._api_post(
                '/owner/api/pipeline/modele', corps, cookie
            )
            self.assertEqual(status, attendu, corps)
        status, _, _ = self._api_post(
            '/owner/api/reglage',
            {'cible': 'texte', 'id': 'presentation', 'value': '   '},
            cookie,
        )
        self.assertEqual(status, 400)
        self.assertEqual(
            self._base(
                'SELECT model, max_price_usd, tolerance_pct FROM llm_models'
                " WHERE tier='mid'"
            ),
            [('', 1.5, 95)],
        )

    def test_l_enregistrement_verifie_le_modele(self) -> None:
        cookie = self._auth_cookie()

        def enregistrer(tier: str, model: str) -> tuple[int, dict]:
            status, _, brut = self._api_post(
                '/owner/api/pipeline/modele',
                {'tier': tier, 'model': model},
                cookie,
            )
            return status, json.loads(brut)

        # Un identifiant qu'OpenRouter ne connaît pas est refusé.
        status, corps = enregistrer('mid', 'mistralai/mistral-smal')
        self.assertEqual(status, 409)
        self.assertEqual(corps['erreur'], 'Modèle inconnu chez OpenRouter.')
        self.assertIn('mistral-smal', corps['aide'])
        self.assertEqual(
            self._base("SELECT model FROM llm_models WHERE tier='mid'"),
            [('',)],
        )
        # Sans outils, ou en variante batch : accepté, avec un avertissement.
        status, corps = enregistrer('fast', 'openai/gpt-muet')
        self.assertEqual(status, 200)
        self.assertIn('appeler d’outils', corps['warning'])
        status, corps = enregistrer('fast', 'deepseek/deepseek-flash:batch')
        self.assertEqual(status, 200)
        self.assertIn('24 h', corps['warning'])
        # OpenRouter jamais joint : la saisie n'est pas bloquée.
        catalog.clear_cache()
        self.reponse_openrouter = OpenRouterError('OpenRouter unreachable')
        status, corps = enregistrer('mid', 'nimporte/quoi')
        self.assertEqual(status, 200)
        self.assertIn('non vérifié', corps['warning'])

    def test_le_journal_garde_les_anciennes_valeurs(self) -> None:
        cookie = self._auth_cookie()
        for corps in (
            {'tier': 'mid', 'model': 'openai/gpt-mini'},
            {'tier': 'mid', 'model': 'google/gemini-mid'},
            {'tier': 'mid', 'model': ''},
            {'tier': 'smart', 'model': '', 'max_price': 0.5, 'tolerance': 90},
            # Sans réglage : ceux de la base ne changent pas.
            {'tier': 'smart', 'model': ''},
        ):
            status, _, _ = self._api_post(
                '/owner/api/pipeline/modele', corps, cookie
            )
            self.assertEqual(status, 200, corps)
        evenements = [
            json.loads(ligne[0])
            for ligne in self._base(
                "SELECT payload_json FROM events WHERE type='pipeline.model'"
                ' ORDER BY id'
            )
        ]
        self.assertEqual(
            [(e['tier'], e['ancien'], e['model']) for e in evenements[:3]],
            [
                ('mid', '', 'openai/gpt-mini'),
                ('mid', 'openai/gpt-mini', 'google/gemini-mid'),
                ('mid', 'google/gemini-mid', ''),
            ],
        )
        self.assertEqual(
            [
                (
                    e['ancien_max_price'],
                    e['max_price'],
                    e['ancien_tolerance'],
                    e['tolerance'],
                )
                for e in evenements[3:]
            ],
            [(8.0, 0.5, 95, 90), (0.5, 0.5, 90, 90)],
        )
        # La recommandation se recalcule avec le nouveau prix maximum : sous
        # 0,50 $/M, deepseek-flash tient à 90 % de la meilleure note.
        _, page = self._get('/owner/api/pipeline/modeles', cookie)
        smart = page['recommendations']['smart']
        self.assertEqual(smart['id'], 'deepseek/deepseek-flash')
        self.assertEqual(smart['max_price'], 0.5)

    def test_la_liste_des_modeles_et_le_melange_de_jetons(self) -> None:
        from datetime import UTC, datetime

        statut, _ = self._get('/owner/api/pipeline/modeles', '')
        self.assertEqual(statut, 401)
        self.assertEqual(self.appels_openrouter, 0)
        cookie = self._auth_cookie()
        # Le catalogue est lu à chaque appel, avec le mélange par défaut.
        _, page = self._get('/owner/api/pipeline/modeles', cookie)
        self.assertEqual((len(page['models']), page['scored']), (6, 5))
        self.assertFalse(page['mix']['measured'])
        _, page = self._get('/owner/api/pipeline/modeles', cookie)
        self.assertEqual(self.appels_openrouter, 2)
        # Sans aucune note, rien n'est recommandé.
        self.reponse_openrouter = [_modele('a/un', 0.10)]
        _, page = self._get('/owner/api/pipeline/modeles', cookie)
        self.assertEqual(page['scored'], 0)
        self.assertEqual(
            {r['id'] for r in page['recommendations'].values()}, {''}
        )
        # Des appels enregistrés : le mélange mesuré change le prix affiché.
        self.reponse_openrouter = [
            _modele(
                'a/asymetrique',
                0,
                prompt_usd=1.0,
                completion_usd=5.0,
                cache_read_usd=0.1,
                cache_write_usd=1.25,
                intelligence=50.0,
            )
        ]
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO llm_usage(point, tier, tokens_in, tokens_out,'
                " verdict, created_at) VALUES('x', 'mid', 1900000, 100000,"
                " 'ok', ?)",
                (datetime.now(UTC).isoformat(),),
            )
            conn.commit()
        finally:
            conn.close()
        _, page = self._get('/owner/api/pipeline/modeles', cookie)
        self.assertEqual(page['mix']['tokens'], 2_000_000)
        self.assertTrue(page['mix']['measured'])
        self.assertAlmostEqual(page['mix']['input_share'], 0.95)
        (modele,) = page['models']
        # Les vrais tarifs, tels qu'OpenRouter les donne, et le prix au
        # mélange mesuré : 0,95 × 1 + 0,05 × 5.
        self.assertEqual(
            (modele['input'], modele['cache_read'], modele['cache_write']),
            (1.0, 0.1, 1.25),
        )
        self.assertEqual(modele['output'], 5.0)
        self.assertAlmostEqual(modele['price'], 1.2)


if __name__ == '__main__':
    unittest.main()
