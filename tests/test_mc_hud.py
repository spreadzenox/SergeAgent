#!/usr/bin/env python3
"""MC HUD : fonctions pures, T3 (tick rejoué = 0 mutation), T4 (stable/animé).

+ anti-fuite rAF en navigation (compteur hudActives).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mc_server_case import McBrowserCase  # noqa: E402


class McHudTests(McBrowserCase):
    def test_hud_pures(self) -> None:
        ctx = self._browser.new_context()
        self.addCleanup(ctx.close)
        page = ctx.new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner/login')
        got = page.evaluate("""(async () => {
          const hud = await import('/static/mc/hud.js');
          return {
            etats: [
              hud.etatSysteme({urgents: 0, running: null, echecRecent: false}),
              hud.etatSysteme({urgents: 0, running: {}, echecRecent: false}),
              hud.etatSysteme({urgents: 2, running: {}, echecRecent: false}),
              hud.etatSysteme({urgents: 0, running: null, echecRecent: true}),
            ],
            rayon: hud.noyauParams('travail', 0).rayon,
            densite: hud.densite24h(
              [{ts: new Date(Date.now() - 3600000).toISOString()}, {ts: 'x'}],
              Date.now(),
            ),
          };
        })()""")
        self.assertEqual(
            got['etats'], ['calme', 'travail', 'urgent', 'erreur']
        )
        self.assertEqual(got['rayon'], 0.5)
        self.assertEqual(got['densite'], [0] * 22 + [1, 0])

    def test_t3_tick_rejoue_zero_mutation(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        self._wait_for(page, 'window.__MC && window.__MC.stats.applied >= 1')
        page.get_by_text('File vide').wait_for(timeout=5000)  # mount fait
        page.wait_for_timeout(1000)  # tweens boot terminés
        page.evaluate("""() => {
          window.__mutations = 0;
          window.__obs = new MutationObserver((muts) => {
            window.__mutations += muts.length;
          });
          window.__obs.observe(document.getElementById('page'), {
            childList: true,
            subtree: true,
            attributes: true,
            characterData: true,
          });
        }""")
        page.wait_for_timeout(5000)  # 2 ticks SSE, DB figée
        self.assertEqual(page.evaluate('window.__mutations'), 0)

    def test_t4_zones_stables_fixes_canvas_anime(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        self._wait_for(page, 'window.__MC && window.__MC.stats.applied >= 1')
        page.get_by_text('File vide').wait_for(timeout=5000)  # mount fait
        page.wait_for_timeout(1000)
        zone_file = page.locator('[data-section="file"]')
        noyau = page.locator('[data-hud="noyau"]')
        capture_file_1 = zone_file.screenshot()
        capture_noyau_1 = noyau.screenshot()
        page.wait_for_timeout(6500)  # 3 ticks, DB figée
        self.assertEqual(zone_file.screenshot(), capture_file_1)
        self.assertNotEqual(noyau.screenshot(), capture_noyau_1)

    def test_pas_de_fuite_raf_en_navigation(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        self._wait_for(page, 'window.__MC && window.__MC.stats.applied >= 1')
        page.get_by_text('File vide').wait_for(timeout=5000)  # mount fait
        compte = (
            "(async () => (await import('/static/mc/hud.js')).hudActives())()"
        )
        self.assertEqual(page.evaluate(compte), 1)
        liens = page.locator('.barre-laterale nav a')
        liens.nth(1).click()
        page.get_by_text('Cette page arrive dans un prochain lot.').wait_for(
            timeout=5000
        )
        self.assertEqual(page.evaluate(compte), 0)
        liens.nth(0).click()
        page.get_by_text('File vide').wait_for(timeout=5000)
        self.assertEqual(page.evaluate(compte), 1)
