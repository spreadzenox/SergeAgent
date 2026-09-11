#!/usr/bin/env python3
"""MC P8 Santé : registre + rendu charte E6 + units systemd + drift + audit trail."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class HealthRegistryTests(unittest.TestCase):
    def test_registre_p8(self) -> None:
        sections = PAGE_SECTIONS['p8']
        self.assertEqual(
            sections,
            [
                'meta',
                'charte_metriques',
                'audit_trail',
                'versions_drift',
                'units_systemd',
            ],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('charte_metriques', SLOW_SECTIONS)
        self.assertIn('audit_trail', SLOW_SECTIONS)
        self.assertIn('versions_drift', SLOW_SECTIONS)
        self.assertIn('units_systemd', SLOW_SECTIONS)


class McHealthTests(McBrowserCase):
    def _fixtures(self) -> None:
        conn = open_db(self.db_path)
        try:
            iso = datetime.now(UTC).isoformat()
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, created_at, updated_at)'
                " VALUES('req_h', 'REQUESTED', 'Filtre NAF', 'OPEN', ?, ?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO events(ts, actor, type, payload_json) VALUES(?, ?, ?, ?)',
                (
                    iso,
                    'owner',
                    'mc_act',
                    '{"acte": "kill", "point": "qualify_prospect"}',
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _page_health(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/health')
        page.locator('[data-section="charte_metriques"]').wait_for(
            timeout=10000
        )
        return page

    def test_page_health_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_health()
        expect(page.locator('#health-loc')).to_contain_text('LOC total')
        expect(page.locator('#health-requested')).to_contain_text(
            'requested en attente : 1'
        )
        expect(page.locator('[data-section="units_systemd"]')).to_contain_text(
            'serge-pipeline.service'
        )
        expect(page.locator('#health-versions')).to_contain_text(
            'Mission Control : v1'
        )
        expect(page.locator('[data-section="audit_trail"]')).to_contain_text(
            'kill'
        )
