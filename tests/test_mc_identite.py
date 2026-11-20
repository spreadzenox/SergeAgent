#!/usr/bin/env python3
"""Page Identité : registre p9, et son formulaire dans le navigateur.

Scénario : la page montre l'identité lue dans le fichier d'instance ; ce
que Serge donne à un site pour s'y inscrire (e-mail, prénom, nom, pseudo)
s'y écrit ; une adresse mal écrite est refusée avec sa raison ; le journal
note quels champs ont changé, pas leur valeur.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import PAGE_SECTIONS, SLOW_SECTIONS  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402


class IdentitePageTests(unittest.TestCase):
    def test_registre_p9(self) -> None:
        sections = PAGE_SECTIONS['p9']
        self.assertEqual(sections[0], 'meta')
        self.assertIn('identite', sections)
        self.assertIn('identite', SLOW_SECTIONS)


class McIdentiteTests(McBrowserCase):
    def test_l_inscription_s_ecrit_dans_l_instance(self) -> None:
        from playwright.sync_api import expect

        instance = Path(self.tmp.name) / 'serge.instance.toml'
        modele = ROOT / 'schemas' / 'serge.instance.example.toml'
        instance.write_text(
            modele.read_text(encoding='utf-8')
            # Une instance à boîte Gmail : son adresse n'est écrite nulle
            # part, comme sur le serveur du 20 novembre 2026.
            .replace('mailbox = true', 'mailbox = false')
            .replace('login = "serge@example.net"', 'login = ""'),
            encoding='utf-8',
        )
        patcher = mock.patch.dict(
            os.environ, {'SERGE_INSTANCE_FILE': str(instance)}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/identite')
        section = page.locator('[data-section="identite"]')
        champs = section.locator('[data-list="champs"]')
        expect(champs).to_contain_text('Prénom : Serge')
        expect(champs).to_contain_text('E-mail : —')
        formulaire = section.locator('[data-identite="inscription"]')
        expect(formulaire.locator('[name="pseudo"]')).to_have_value('serge')
        # Une adresse mal écrite : refusée, rien n'est écrit.
        formulaire.locator('[name="pseudo"]').fill('serge_ia')
        formulaire.locator('[name="email"]').evaluate(
            "champ => { champ.type = 'text'; champ.value = 'pas une adresse'; }"
        )
        formulaire.locator('button[type="submit"]').click()
        expect(page.locator('.toast-erreur').last).to_contain_text(
            'adresse e-mail mal écrite'
        )
        self.assertIn('pseudo = "serge"', instance.read_text(encoding='utf-8'))
        formulaire.locator('[name="email"]').fill('serge.ia@example.net')
        formulaire.locator('button[type="submit"]').click()
        expect(page.locator('.toast-succes').last).to_contain_text(
            'Identité enregistrée.'
        )
        expect(champs).to_contain_text('Pseudo : serge_ia')
        expect(champs).to_contain_text('E-mail : serge.ia@example.net')
        texte = instance.read_text(encoding='utf-8')
        self.assertIn('pseudo = "serge_ia"', texte)
        self.assertIn('login = "serge.ia@example.net"', texte)
        conn = sqlite3.connect(self.db_path)
        try:
            journal = ' '.join(
                str(r[0])
                for r in conn.execute('SELECT payload_json FROM events')
            )
        finally:
            conn.close()
        self.assertIn('identite_changee', journal)
        self.assertIn('"champs": ["email", "pseudo"]', journal)
        self.assertNotIn('serge.ia@example.net', journal)
