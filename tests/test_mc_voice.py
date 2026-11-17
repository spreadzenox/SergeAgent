#!/usr/bin/env python3
"""MC P7 Voix : registre + rendu pont / journal / qualité."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase, McServerCase  # noqa: E402


def _journal_des_appels(dossier: str, canon: Path) -> Path:
    """Un journal des appels avec deux appels restés « en cours », un
    appel terminé et un appel refusé."""
    import sqlite3

    from serge.voice.ledger import VoiceLedger

    chemin = Path(dossier) / 'voice.db'
    VoiceLedger(chemin, canon)
    conn = sqlite3.connect(chemin)
    try:
        for numero, decision, issue in (
            ('coince_1', 'allowed', 'pending'),
            ('coince_2', 'allowed', 'pending'),
            ('fini', 'allowed', 'completed'),
            ('refuse', 'denied', 'pending'),
        ):
            conn.execute(
                'INSERT INTO calls(request_id, cdr_id, direction, to_e164,'
                ' to_hash, cli, purpose, task_id, decision, reason,'
                ' created_at, outcome) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    numero,
                    f'cdr_{numero}',
                    'outbound',
                    '+33600000001',
                    'h',
                    '+33100000000',
                    'prospection',
                    '',
                    decision,
                    decision,
                    '2026-10-08T16:46:23+00:00',
                    issue,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return chemin


def _issues(chemin: Path) -> dict[str, str]:
    import sqlite3

    conn = sqlite3.connect(chemin)
    try:
        return dict(conn.execute('SELECT request_id, outcome FROM calls'))
    finally:
        conn.close()


class DebloquerAppelsTests(McServerCase):
    def test_debloquer_ferme_les_appels_restes_en_cours(self) -> None:
        """« Débloquer les appels » : réservé au propriétaire ; les appels
        restés « en cours » passent à « échec », les autres ne changent
        pas, et l'acte est au journal."""
        import json
        from unittest import mock

        from serge.db.store import open_db

        journal = _journal_des_appels(self.tmp.name, self.db_path)
        with mock.patch(
            'serge.voice.policy.default_ledger_path', return_value=journal
        ):
            status, _, _ = self._api_post('/owner/api/voice/debloquer', {})
            self.assertEqual(status, 401)
            self.assertEqual(_issues(journal)['coince_1'], 'pending')
            cookie = self._auth_cookie()
            status, _, corps = self._api_post(
                '/owner/api/voice/debloquer', {}, cookie
            )
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(corps)['fermes'], 2)
            status, _, corps = self._api_post(
                '/owner/api/voice/debloquer', {}, cookie
            )
            self.assertEqual(json.loads(corps)['fermes'], 0)
        self.assertEqual(
            _issues(journal),
            {
                'coince_1': 'failed',
                'coince_2': 'failed',
                'fini': 'completed',
                'refuse': 'pending',
            },
        )
        conn = open_db(self.db_path)
        try:
            actes = [
                json.loads(r[0])
                for r in conn.execute(
                    "SELECT payload_json FROM events WHERE type='mc_act'"
                    ' ORDER BY id'
                )
            ]
        finally:
            conn.close()
        self.assertEqual(
            actes,
            [
                {'acte': 'appels_debloques', 'fermes': 2},
                {'acte': 'appels_debloques', 'fermes': 0},
            ],
        )


class VoiceRegistryTests(unittest.TestCase):
    def test_registre_p7(self) -> None:
        sections = PAGE_SECTIONS['p7']
        self.assertEqual(
            sections,
            ['meta', 'bridge_statut', 'cdr_appels', 'journal_voix'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('cdr_appels', SLOW_SECTIONS)
        self.assertIn('bridge_statut', SLOW_SECTIONS)
        self.assertIn('journal_voix', SLOW_SECTIONS)


class McVoiceTests(McBrowserCase):
    def _page_voice(self):
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/voice')
        from playwright.sync_api import expect

        expect(page.locator('#voice-bridge-info')).to_contain_text(
            'Pont', timeout=10000
        )
        return page

    def test_page_voice_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_voice()
        expect(page.locator('[data-section="bridge_statut"]')).to_contain_text(
            'Pont'
        )
        # Les journaux du serveur : un bloc par source, même illisible.
        journaux = page.locator('[data-section="journal_voix"]')
        expect(journaux).to_contain_text('Pont vocal')
        expect(journaux).to_contain_text('Asterisk, fichier messages')

    def test_le_bouton_debloque_les_appels(self) -> None:
        from unittest import mock

        from playwright.sync_api import expect

        journal = _journal_des_appels(self.tmp.name, self.db_path)
        with mock.patch(
            'serge.voice.policy.default_ledger_path', return_value=journal
        ):
            page = self._page_voice()
            page.get_by_role('button', name='Débloquer les appels').click()
            page.locator('.modale').get_by_role(
                'button', name='Débloquer les appels'
            ).click()
            expect(page.locator('.toast-succes')).to_contain_text(
                '2 appel(s) fermé(s).'
            )
            expect(page.locator('#voice-en-cours')).to_contain_text(
                'Appels « en cours » au journal : 0.'
            )
        self.assertEqual(_issues(journal)['coince_2'], 'failed')
