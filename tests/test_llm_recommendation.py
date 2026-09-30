#!/usr/bin/env python3
"""Le catalogue des modèles d'OpenRouter et la recommandation par niveau.

Scénario : OpenRouter liste des modèles avec leurs tarifs et, pour beaucoup,
leur note d'intelligence (Artificial Analysis). Pour chaque niveau, on
recommande le meilleur rapport note / prix sous le prix maximum du niveau
(réglé en base, dans ``llm_models``), au mélange de jetons lus et écrits de
Serge, parmi les modèles utilisables. Sans note, rien n'est recommandé.

``tests/openrouter_models_sample.json`` est un extrait de la vraie réponse
de ``GET /api/v1/models`` (30 septembre 2026), réduit aux champs que le code
lit : ces tests vérifient le code contre la forme réelle de l'API.
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

from kit.openrouter import OpenRouterError, fetch_models  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.llm import catalog  # noqa: E402
from serge.llm.recommendation import (  # noqa: E402
    DEFAULT_INPUT_SHARE,
    effective_price,
    recommend,
    usable,
)

NOW = 1_790_000_000.0
SEPT_30 = 1_790_760_000.0
DAY = 86400
SAMPLE = ROOT / 'tests/openrouter_models_sample.json'
MIX = {'input_share': DEFAULT_INPUT_SHARE, 'tokens': 0, 'measured': False}


def model(ident: str, price: float, **others) -> dict:
    """Un modèle au format de ``fetch_models`` ; ``price`` : entrée = sortie."""
    base = {
        'id': ident,
        'name': ident.split('/')[1],
        'context_length': 200_000,
        'prompt_usd': price,
        'completion_usd': price,
        'tools': True,
        'text_out': True,
        'created': int(NOW - 30 * DAY),
        'expires': '',
        'intelligence': None,
        'cache_read_usd': None,
        'cache_write_usd': None,
    }
    return {**base, **others}


def seeded_db() -> sqlite3.Connection:
    """Une base neuve : les niveaux ont leurs réglages de départ."""
    conn = sqlite3.connect(':memory:')
    init_schema(conn)
    return conn


def seeded_tiers() -> dict[str, dict[str, float]]:
    conn = seeded_db()
    try:
        return catalog.tier_settings(conn)
    finally:
        conn.close()


class _Response:
    """Ce que ``urllib.request.urlopen`` rend."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self) -> bytes:
        return self._body


def parsed(payload: dict | bytes) -> list[dict]:
    """``fetch_models`` sur une réponse d'OpenRouter donnée."""
    body = payload if isinstance(payload, bytes) else json.dumps(payload)
    body = body if isinstance(body, bytes) else body.encode()
    with mock.patch('urllib.request.urlopen', return_value=_Response(body)):
        return fetch_models()


class TierSettingsTests(unittest.TestCase):
    def test_les_reglages_des_niveaux_sont_en_base(self) -> None:
        conn = seeded_db()
        self.addCleanup(conn.close)
        self.assertEqual(
            catalog.tier_settings(conn),
            {
                'fast': {'max_price': 0.30, 'tolerance': 0.85},
                'mid': {'max_price': 1.50, 'tolerance': 0.95},
                'smart': {'max_price': 8.00, 'tolerance': 0.95},
            },
        )
        conn.execute(
            'UPDATE llm_models SET max_price_usd=2.5, tolerance_pct=70'
            " WHERE tier='smart'"
        )
        self.assertEqual(
            catalog.tier_settings(conn)['smart'],
            {'max_price': 2.5, 'tolerance': 0.7},
        )


class RecommendationTests(unittest.TestCase):
    def test_le_meilleur_rapport_dans_la_tolerance_de_chaque_niveau(
        self,
    ) -> None:
        models = [
            # fast (maximum 0,30, tolérance 85 %) : a est le meilleur
            # rapport mais trop faible (30 < 85 % de 45) ; c bat b.
            model('a/tiny', 0.05, intelligence=30.0),
            model('b/small', 0.25, intelligence=45.0),
            model('c/cheapish', 0.12, intelligence=44.0),
            # mid (maximum 1,50, tolérance 95 %) : e note 52, sous 95 % de
            # 60 : il ne passe pas, même s'il coûte moins.
            model('d/mid', 1.2, intelligence=60.0),
            model('e/mid2', 0.9, intelligence=52.0),
            # smart (maximum 8) : g est meilleur mais au-dessus du maximum.
            model('f/big', 7.0, intelligence=75.0),
            model('g/huge', 30.0, intelligence=90.0),
        ]
        tiers = seeded_tiers()
        reco = recommend(models, tiers, now=NOW)
        self.assertEqual(reco['fast']['id'], 'c/cheapish')
        self.assertEqual(reco['mid']['id'], 'd/mid')
        self.assertEqual(reco['smart']['id'], 'f/big')
        self.assertEqual(reco['smart']['max_price'], 8.0)
        self.assertIn(
            'Note 75 pour 7,00 $/M ; la meilleure note sous 8,00 $/M est 75',
            reco['smart']['reason'],
        )
        # La tolérance est celle du niveau : à 85 %, e (52 ≥ 51) passe et
        # coûte moins que d.
        tiers['mid']['tolerance'] = 0.85
        self.assertEqual(
            recommend(models, tiers, now=NOW)['mid']['id'], 'e/mid2'
        )

    def test_un_modele_inutilisable_n_est_jamais_recommande(self) -> None:
        good = model('ok/bon', 0.2, intelligence=10.0)
        excluded = [
            model('x/sans-outils', 0.01, tools=False),
            model('x/outils-inconnus', 0.01, tools=None),
            model('x/court', 0.01, context_length=32_000),
            model('x/gratuit:free', 0.0),
            model('x/differe:batch', 0.01),
            model('x/vieux', 0.01, created=int(NOW - 400 * DAY)),
            model('x/retire', 0.01, expires='2020-01-01'),
            model('x/image', 0.01, text_out=False),
        ]
        excluded = [{**m, 'intelligence': 99.0} for m in excluded]
        for m in excluded:
            self.assertFalse(usable(m, NOW), m['id'])
        # Un modèle dont on ignore la date reste utilisable.
        self.assertTrue(usable(model('ok/sans-date', 0.2, created=0), NOW))
        reco = recommend([good, *excluded], seeded_tiers(), now=NOW)
        self.assertEqual(reco['fast']['id'], 'ok/bon')

    def test_rien_a_recommander_et_pourquoi(self) -> None:
        tiers = seeded_tiers()
        cher = model('a/cher', 3.0, intelligence=80.0)
        inconnu = model('b/inconnu', 0.1)
        # Aucune note du tout, puis aucune note sous le prix maximum.
        self.assertIn(
            'Aucun modèle noté',
            recommend([inconnu], tiers, now=NOW)['mid']['reason'],
        )
        reco = recommend([cher, inconnu], tiers, now=NOW)
        self.assertEqual(reco['fast']['id'], '')
        self.assertEqual(reco['smart']['id'], 'a/cher')
        # Un prix maximum à 0 : pas réglé.
        tiers['mid']['max_price'] = 0.0
        reco = recommend([cher], tiers, now=NOW)['mid']
        self.assertEqual(reco['id'], '')
        self.assertIn('non réglé', reco['reason'])

    def test_le_melange_de_jetons_change_le_prix_et_le_classement(
        self,
    ) -> None:
        m = model('a/b', 0, prompt_usd=1.0, completion_usd=5.0)
        self.assertAlmostEqual(effective_price(m, 0.75), 2.0)
        self.assertAlmostEqual(effective_price(m, 0.99), 1.04)
        # Même note : le moins cher au mélange de Serge gagne.
        models = [
            model('a/sortie-chere', 0, prompt_usd=1.0, completion_usd=9.0)
            | {'intelligence': 50.0},
            model('b/egal', 3.0, intelligence=50.0),
        ]
        tiers = seeded_tiers()
        lu = recommend(models, tiers, 0.9, now=NOW)['smart']
        ecrit = recommend(models, tiers, 0.3, now=NOW)['smart']
        self.assertEqual(lu['id'], 'a/sortie-chere')
        self.assertAlmostEqual(lu['price'], 1.8)
        self.assertEqual(ecrit['id'], 'b/egal')  # 6,60 contre 3,00 $/M
        # Le prix maximum compte au même mélange : 2,00 $/M à 75 % lus,
        # 1,04 à 99 %, sous le maximum du niveau moyen (1,50).
        chere = model(
            'a/chere', 0, prompt_usd=1.0, completion_usd=5.0, intelligence=50.0
        )
        self.assertEqual(
            recommend([chere], tiers, 0.75, now=NOW)['mid']['id'], ''
        )
        self.assertEqual(
            recommend([chere], tiers, 0.99, now=NOW)['mid']['id'], 'a/chere'
        )


class UsageMixTests(unittest.TestCase):
    def test_le_melange_est_mesure_sur_les_appels_des_30_derniers_jours(
        self,
    ) -> None:
        conn = seeded_db()
        self.addCleanup(conn.close)
        now = datetime.now(UTC)

        def call(read: int, written: int, *, days=1, verdict='ok') -> None:
            conn.execute(
                'INSERT INTO llm_usage(point, tier, tokens_in, tokens_out,'
                ' verdict, created_at) VALUES(?,?,?,?,?,?)',
                (
                    'x',
                    'mid',
                    read,
                    written,
                    verdict,
                    (now - timedelta(days=days)).isoformat(),
                ),
            )

        # Pas assez d'appels : le mélange par défaut, et la page le dit.
        call(50_000, 40_000)
        self.assertEqual(
            catalog.usage_mix(conn, now.timestamp()),
            {'input_share': 0.75, 'tokens': 90_000, 'measured': False},
        )
        # Assez d'appels récents ; hors fenêtre ou sans réponse : ignorés.
        call(850_000, 10_000)
        call(400_000, 50_000, days=29)
        call(9_000_000, 0, days=31)
        call(9_000_000, 0, verdict='erreur')
        mix = catalog.usage_mix(conn, now.timestamp())
        self.assertTrue(mix['measured'])
        # Les 90 000 jetons du début comptent aussi : ils sont dans la fenêtre.
        self.assertEqual(mix['tokens'], 1_400_000)
        self.assertAlmostEqual(mix['input_share'], 1_300_000 / 1_400_000)


class CatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        catalog.clear_cache()
        self.addCleanup(catalog.clear_cache)

    @staticmethod
    def fetcher(models=None, *, failure: str = ''):
        def fetch(_key: str) -> list[dict]:
            if failure:
                raise OpenRouterError(failure)
            return models or [model('a/b', 0.1)]

        return fetch

    def test_le_catalogue_est_lu_a_chaque_fois_et_le_dernier_est_garde(
        self,
    ) -> None:
        # Jamais lu, OpenRouter injoignable : rien, et pourquoi.
        down = self.fetcher(failure='OpenRouter HTTP 503')
        cat = catalog.catalog(fetcher=down, now=1000.0)
        self.assertEqual(
            (cat['models'], cat['error']), ([], 'OpenRouter HTTP 503')
        )
        # Lu : chaque appel relit, donc un changement d'OpenRouter se voit
        # tout de suite.
        cat = catalog.catalog(fetcher=self.fetcher(), now=1000.0)
        self.assertEqual((len(cat['models']), cat['error']), (1, ''))
        two = [model('a/b', 0.1), model('c/d', 0.2)]
        cat = catalog.catalog(fetcher=self.fetcher(two), now=2000.0)
        self.assertEqual(len(cat['models']), 2)
        # Injoignable ensuite : on garde le dernier catalogue lu, et on le dit.
        cat = catalog.catalog(fetcher=down, now=3000.0)
        self.assertEqual(len(cat['models']), 2)
        self.assertEqual(cat['error'], 'OpenRouter HTTP 503')
        self.assertEqual(cat['at'], 2000.0)

    def test_for_page_donne_les_tarifs_les_notes_et_les_recommandations(
        self,
    ) -> None:
        models = [
            model('z/zeta', 0.2, name='Zeta', intelligence=42.0),
            model('a/alpha', 0.1, name='Alpha', tools=False),
            model('b/beta', 0.1, name='Beta', intelligence=30.0),
        ]
        page = catalog.for_page(
            seeded_tiers(), MIX, fetcher=self.fetcher(models), now=NOW
        )
        self.assertEqual(
            [m['id'] for m in page['models']], ['a/alpha', 'b/beta', 'z/zeta']
        )
        by_id = {m['id']: m for m in page['models']}
        self.assertEqual(by_id['z/zeta']['name'], 'Zeta')
        self.assertIs(by_id['z/zeta']['tools'], True)
        self.assertEqual(
            {i: m['score'] for i, m in by_id.items()},
            {'z/zeta': 42.0, 'a/alpha': None, 'b/beta': 30.0},
        )
        self.assertEqual(page['scored'], 2)
        self.assertIn('Artificial Analysis', page['scores_source'])
        self.assertEqual(page['mix'], MIX)
        # b/beta : 30 pour 0,10 $/M bat z/zeta : 42 pour 0,20 $/M, mais 30
        # est sous 85 % de 42.
        self.assertEqual(page['recommendations']['fast']['id'], 'z/zeta')
        self.assertEqual(page['recommendations']['mid']['max_price'], 1.5)
        self.assertEqual(page['error'], '')
        self.assertTrue(page['loaded_at'].endswith('+00:00'))

    def test_check_model(self) -> None:
        models = [
            model('a/ok', 0.1),
            model('b/muet', 0.1, tools=False),
            model('c/lent:batch', 0.05),
        ]
        fetch = self.fetcher(models)
        check = catalog.check_model
        self.assertEqual(check('a/ok', fetcher=fetch), ('ok', ''))
        self.assertEqual(check('b/muet', fetcher=fetch)[0], 'no_tools')
        status, message = check('c/lent:batch', fetcher=fetch)
        self.assertEqual(status, 'deferred')
        self.assertIn('24 h', message)
        status, message = check('a/typo', fetcher=fetch)
        self.assertEqual(status, 'unknown')
        self.assertIn('a/typo', message)
        # Catalogue jamais lu : on ne bloque pas, on prévient.
        catalog.clear_cache()
        down = self.fetcher(failure='OpenRouter unreachable')
        status, message = check('a/ok', fetcher=down)
        self.assertEqual(status, 'unverified')
        self.assertIn('injoignable', message)


class FetchModelsTests(unittest.TestCase):
    def test_les_capacites_les_prix_et_la_note_sont_lus(self) -> None:
        payload = {
            'data': [
                {
                    'id': 'a/complet',
                    'name': 'Complet',
                    'created': 1_789_000_000,
                    'context_length': 200000,
                    'pricing': {
                        'prompt': '0.000001',
                        'completion': '0.000002',
                        'input_cache_read': '0.0000002',
                        'input_cache_write': '0.00000125',
                    },
                    'supported_parameters': ['temperature', 'tools'],
                    'architecture': {'output_modalities': ['text']},
                    'expiration_date': '2027-01-01',
                    'benchmarks': {
                        'design_arena': [],
                        'artificial_analysis': {
                            'intelligence_index': 51.8,
                            'coding_index': None,
                            'agentic_index': None,
                        },
                    },
                },
                {
                    'id': 'b/muet',
                    'name': 'Muet',
                    'supported_parameters': ['temperature'],
                    'architecture': {'output_modalities': ['image']},
                },
                {'id': 'c/vague', 'name': 'Vague'},
            ]
        }
        models = {m['id']: m for m in parsed(payload)}
        full = models['a/complet']
        self.assertEqual(
            (full['tools'], full['text_out'], full['created']),
            (True, True, 1_789_000_000),
        )
        self.assertEqual(full['expires'], '2027-01-01')
        self.assertEqual(full['intelligence'], 51.8)
        self.assertEqual(
            (full['cache_read_usd'], full['cache_write_usd']), (0.2, 1.25)
        )
        self.assertIs(models['b/muet']['tools'], False)
        self.assertIs(models['b/muet']['text_out'], False)
        # OpenRouter ne dit rien : on ne suppose rien.
        vague = models['c/vague']
        self.assertEqual(
            (vague['tools'], vague['text_out'], vague['created']),
            (None, None, 0),
        )
        self.assertEqual(
            (vague['intelligence'], vague['cache_read_usd']), (None, None)
        )

    def test_une_note_absente_ou_invalide_n_est_pas_une_note(self) -> None:
        def score(benchmarks) -> float | None:
            payload = {'data': [{'id': 'a/b', 'benchmarks': benchmarks}]}
            return parsed(payload)[0]['intelligence']

        def aa(value) -> dict:
            return {'artificial_analysis': {'intelligence_index': value}}

        self.assertEqual(score(aa(71)), 71.0)
        for bad in (None, 0, -2, 'haut', True):
            self.assertIsNone(score(aa(bad)), bad)
        for empty in (None, [], {}, {'design_arena': []}, 'x'):
            self.assertIsNone(score(empty), empty)


class RealCatalogTests(unittest.TestCase):
    """L'extrait de la vraie réponse d'OpenRouter (30 septembre 2026)."""

    def test_de_la_reponse_d_openrouter_aux_recommandations(self) -> None:
        models = {m['id']: m for m in parsed(SAMPLE.read_bytes())}
        # Les notes viennent de « benchmarks », les tarifs de « pricing ».
        scores = {i: m['intelligence'] for i, m in models.items()}
        self.assertEqual(
            {i: s for i, s in scores.items() if s},
            {
                'z-ai/glm-5.3-flash': 41.8,
                'z-ai/glm-5.3-flash:batch': 41.8,
                'anthropic/claude-sonnet-5.5': 56.0,
                'deepseek/deepseek-v4.1-flash': 39.5,
                'xiaomi/mimo-v2.6-pro': 46.3,
            },
        )
        sonnet = models['anthropic/claude-sonnet-5.5']
        self.assertEqual(
            (sonnet['prompt_usd'], sonnet['completion_usd']), (2.0, 10.0)
        )
        # Lire en cache coûte dix fois moins que lire normalement.
        self.assertEqual(
            (sonnet['cache_read_usd'], sonnet['cache_write_usd']), (0.2, 2.5)
        )
        self.assertIsNone(
            models['deepseek/deepseek-v4.1-flash']['cache_write_usd']
        )
        # Une variante batch (réponse sous 24 h) et un modèle gratuit ne sont
        # pas utilisables ; un modèle qui sera retiré plus tard l'est.
        self.assertFalse(usable(models['z-ai/glm-5.3-flash:batch'], SEPT_30))
        self.assertFalse(
            usable(models['inclusionai/ling-3.0-flash-sante:free'], SEPT_30)
        )
        self.assertTrue(
            usable(models['bytedance-seed/seed-2.0-code'], SEPT_30)
        )
        # Le niveau rapide cherche la valeur : deepseek (39,5 pour 0,11 $/M)
        # garde 94 % de la meilleure note (41,8, glm-5.3-flash) pour moins de
        # la moitié du prix ; le glm:batch, moins cher encore, est écarté. Les
        # deux autres visent presque la meilleure note sous leur maximum. Un
        # modèle sans note (gpt-6.1-sol-pro) n'est jamais recommandé.
        page = catalog.for_page(
            seeded_tiers(),
            MIX,
            fetcher=lambda _key: list(models.values()),
            now=SEPT_30,
        )
        reco = {t: r['id'] for t, r in page['recommendations'].items()}
        self.assertEqual(
            reco,
            {
                'fast': 'deepseek/deepseek-v4.1-flash',
                'mid': 'xiaomi/mimo-v2.6-pro',
                'smart': 'anthropic/claude-sonnet-5.5',
            },
        )
        self.assertEqual(page['scored'], 5)
        self.assertEqual(len(page['models']), len(models))


if __name__ == '__main__':
    unittest.main()
