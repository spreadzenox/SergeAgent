#!/usr/bin/env python3
"""Identité : lecteur unique, volet, refus, écriture instance.

Scénarios du 20 novembre 2026 (création d'un compte web) :
- l'outil « L'identité de Serge » lit le fichier d'instance d'un service,
  qui ne sait pas déchiffrer les secrets, et dit ce qui reste à remplir ;
- la page Identité de Mission Control écrit l'e-mail, le prénom, le nom et
  le pseudo, et rien d'autre ; l'e-mail d'une boîte SMTP/IMAP ne se change
  pas là ;
- une valeur mal écrite est refusée et laisse le fichier d'instance tel
  quel : Serge peut toujours redémarrer.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.identite import (  # noqa: E402
    IdentiteError,
    ecrire_identite,
    identite_serge,
    identity_read,
    modifier_inscription,
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


class InstanceDUnServiceTests(unittest.TestCase):
    """Le fichier d'instance tel qu'un service le voit : les secrets sont
    à côté, chiffrés, et le service n'a pas de quoi les lire."""

    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.cible = Path(dossier.name) / 'serge.instance.toml'
        modele = ROOT / 'schemas' / 'serge.instance.example.toml'
        self.cible.write_text(
            modele.read_text(encoding='utf-8'), encoding='utf-8'
        )
        (Path(dossier.name) / 'serge.secrets.age').write_bytes(b'chiffre')
        env = {
            k: v for k, v in os.environ.items() if k != 'SERGE_AGE_IDENTITY'
        }
        env['SERGE_INSTANCE_FILE'] = str(self.cible)
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _remplacer(self, ancien: str, nouveau: str) -> None:
        texte = self.cible.read_text(encoding='utf-8')
        self.assertIn(ancien, texte)
        self.cible.write_text(texte.replace(ancien, nouveau), encoding='utf-8')

    def test_l_outil_lit_l_identite_sans_les_secrets(self) -> None:
        rendu = identity_read(
            None, 'identite_de_serge', {}, 'creer_compte_web'
        )
        self.assertEqual(
            rendu,
            {
                'ok': True,
                'prenom': 'Serge',
                'nom': 'Atelier',
                'pseudo': 'serge',
                'email': 'serge@example.net',
                'telephone_pour_les_sms': '+33600000001',
            },
        )
        # Des champs vides : l'outil dit lesquels, et où les remplir.
        self._remplacer('prenom = "Serge"', 'prenom = ""')
        self._remplacer('login = "serge@example.net"', 'login = ""')
        self._remplacer('mailbox = true', 'mailbox = false')
        rendu = identity_read(
            None, 'identite_de_serge', {}, 'creer_compte_web'
        )
        self.assertEqual(
            rendu['manque'],
            'adresse e-mail, prénom : à remplir par un humain dans Mission'
            ' Control, page Identité',
        )
        # Sans fichier d'instance, un refus qui dit pourquoi.
        self.cible.unlink()
        rendu = identity_read(
            None, 'identite_de_serge', {}, 'creer_compte_web'
        )
        self.assertEqual(
            rendu,
            {
                'ok': False,
                'detail': 'identité illisible : fichier d’instance introuvable',
            },
        )

    def test_mission_control_ecrit_l_inscription(self) -> None:
        ecrits = modifier_inscription(
            {
                'prenom': ' Ada ',
                'pseudo': 'ada_ia',
                'nom': 'Atelier',
                'iban': 'FR76',
            }
        )
        # Seuls les champs changés sont écrits ; l'IBAN ne passe pas par là.
        self.assertEqual(ecrits, {'prenom': 'Ada', 'pseudo': 'ada_ia'})
        lu = identite_serge(volet='advanced')
        self.assertEqual(
            (lu['prenom'], lu['pseudo'], lu['nom'], lu['iban']),
            ('Ada', 'ada_ia', 'Atelier', ''),
        )
        with self.assertRaisesRegex(IdentiteError, 'rien à changer'):
            modifier_inscription({'prenom': 'Ada'})
        # L'adresse d'une boîte SMTP/IMAP est son identifiant : pas ici.
        with self.assertRaisesRegex(IdentiteError, 'identifiant de la boîte'):
            modifier_inscription({'email': 'autre@example.net'})
        self._remplacer('mailbox = true', 'mailbox = false')
        with self.assertRaisesRegex(IdentiteError, 'mal écrite'):
            modifier_inscription({'email': 'pas une adresse'})
        self.assertEqual(
            modifier_inscription({'email': 'serge.ia@example.net'}),
            {'email': 'serge.ia@example.net'},
        )
        self.assertEqual(identite_serge()['email'], 'serge.ia@example.net')

    def test_une_valeur_mal_ecrite_laisse_l_instance_telle_quelle(
        self,
    ) -> None:
        avant = self.cible.read_bytes()
        for valeur in ('Ada\nmode = "live"', 'A' * 201):
            with self.assertRaisesRegex(IdentiteError, 'une seule ligne'):
                ecrire_identite({'prenom': valeur}, path=self.cible)
        self.assertEqual(self.cible.read_bytes(), avant)
        # Une instance valide le reste : la boîte SMTP/IMAP garde son
        # identifiant.
        self._remplacer('discord = true', 'discord = false')
        avant = self.cible.read_bytes()
        with self.assertRaisesRegex(IdentiteError, 'ne serait plus valide'):
            ecrire_identite({'email': ''}, path=self.cible)
        self.assertEqual(self.cible.read_bytes(), avant)
        # Des guillemets et une barre oblique s'écrivent et se relisent.
        ecrire_identite({'prenom': 'Ada "la" \\ Vraie'}, path=self.cible)
        self.assertEqual(identite_serge()['prenom'], 'Ada "la" \\ Vraie')
        self.assertFalse(
            self.cible.with_name('serge.instance.toml.neuf').exists()
        )


if __name__ == '__main__':
    unittest.main()
