#!/usr/bin/env python3
"""Identité : lecteur unique, volet, refus, écriture instance."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.identite import (  # noqa: E402
    IdentiteError,
    ecrire_identite,
    identite_serge,
)
from serge.mc.proj_objet import project_objet  # noqa: E402


class IdentiteTests(unittest.TestCase):
    def test_basique_et_advanced(self) -> None:
        loaded = {
            'identity': {
                'prenom': 'Serge',
                'nom': 'Atelier',
                'pseudo': 'serge',
                'phone_sms_number': '+33600000001',
                'phone_voice_number': '+33162000001',
                'siret': '123',
                'iban': 'FR76',
                'adresse_facturation': '1 rue',
            },
            'mailbox': {'login': 'serge@exemple.net'},
        }
        bas = identite_serge(volet='basique', loaded=loaded)
        self.assertEqual(bas['email'], 'serge@exemple.net')
        self.assertEqual(bas['prenom'], 'Serge')
        self.assertNotIn('iban', bas)
        adv = identite_serge(volet='advanced', loaded=loaded)
        self.assertEqual(adv['iban'], 'FR76')
        with self.assertRaises(IdentiteError):
            identite_serge(volet='secret', loaded=loaded)

    def test_ecrire_puis_relire(self) -> None:
        src = ROOT / 'schemas' / 'serge.instance.example.toml'
        with tempfile.TemporaryDirectory() as tmp:
            cible = Path(tmp) / 'serge.instance.toml'
            cible.write_text(src.read_text(encoding='utf-8'), encoding='utf-8')
            ecrire_identite({'prenom': 'Ada', 'email': 'ada@x.io'}, path=cible)
            from kit.instance_file import load_toml

            lu = identite_serge(volet='basique', loaded=load_toml(cible))
            self.assertEqual(lu['prenom'], 'Ada')
            self.assertEqual(lu['email'], 'ada@x.io')
            with self.assertRaises(IdentiteError):
                ecrire_identite({'pan': '4111'}, path=cible)

    def test_fiche_objet(self) -> None:
        fiche = project_objet(None, 'identite', 'dragon')  # type: ignore[arg-type]
        self.assertIsNone(fiche)
        autre = project_objet(None, 'identite', 'serge')  # type: ignore[arg-type]
        self.assertIsNotNone(autre)
        self.assertEqual(autre['type'], 'identite')
