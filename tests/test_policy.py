#!/usr/bin/env python3
"""Le fichier de départ des réglages généraux : lu, vérifié, et chaque
réglage lu par un programme (décision Q68)."""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.policy import (  # noqa: E402
    PolicyError,
    Setting,
    check_value,
    is_test_env,
    load_policy,
    load_policy_seed,
)


def _feuilles(node: dict, chemin: str = ''):
    for cle, val in node.items():
        if isinstance(val, dict):
            yield from _feuilles(val, f'{chemin}{cle}.')
        else:
            yield f'{chemin}{cle}'


def _reglage(kind: str, **autres) -> Setting:
    return Setting('a.b', 'a', 0, 'B', '', kind, None, **autres)


class PolicyTests(unittest.TestCase):
    def test_prod_policy_loads_with_validated_values(self) -> None:
        with mock.patch.dict(os.environ, {'SERGE_ENV': ''}, clear=False):
            os.environ.pop('SERGE_ENV', None)
            policy = load_policy()
        self.assertEqual(policy['budget']['monthly_eur'], 50.0)
        self.assertEqual(policy['quotas']['voice_max_calls_per_day'], 50)
        self.assertEqual(policy['calling_zones']['default'], 'FR')
        self.assertEqual(policy['calling_zones']['FR']['contact_per_30d'], 4)
        self.assertEqual(policy['testing']['n_smoke_min'], 30)
        self.assertEqual(policy['standing']['cout_usage'], 0.10)
        self.assertEqual(policy['standing']['capital_min'], 0.20)

    def test_test_overlay_applies_plancher(self) -> None:
        with mock.patch.dict(os.environ, {'SERGE_ENV': 'test'}):
            self.assertTrue(is_test_env())
            policy = load_policy()
        self.assertEqual(policy['budget']['monthly_eur'], 2.0)
        self.assertEqual(policy['quotas']['email_per_mailbox_per_day'], 2)
        self.assertEqual(policy['quotas']['voice_max_calls_per_day'], 0)
        self.assertEqual(policy['quotas']['linkedin_connect_per_day'], 0)
        # Non surchargé = valeur prod conservée.
        self.assertEqual(policy['budget']['eur_per_usd'], 0.9)

    def test_chaque_sorte_verifie_sa_valeur(self) -> None:
        curseur = _reglage('curseur', min=0, max=200)
        self.assertEqual(check_value(curseur, 40), '')
        self.assertEqual(check_value(curseur, 2.5), 'un nombre entier attendu')
        self.assertEqual(check_value(curseur, 250), 'au plus 200')
        for faux in (float('nan'), float('inf'), True, '40'):
            self.assertEqual(check_value(curseur, faux), 'un nombre attendu')
        canaux = _reglage(
            'canaux', choices=(['voice', 'Voix'], ['sms', 'SMS'])
        )
        self.assertEqual(check_value(canaux, ['sms']), '')
        self.assertIn('choix', check_value(canaux, ['fax']))
        self.assertEqual(
            check_value(_reglage('fenetres'), [[23, 0, 8, 0]]), ''
        )
        self.assertIn(
            'minute', check_value(_reglage('fenetres'), [[23, 0, 8, 75]])
        )
        nombres = _reglage('nombres', min=1, max=90)
        self.assertEqual(check_value(nombres, [7, 14]), '')
        self.assertEqual(check_value(nombres, [0]), 'au moins 1')

    def test_un_fichier_faux_est_refuse(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            texte = (ROOT / 'config/policy.yaml').read_text(encoding='utf-8')
            shutil.copy(ROOT / 'config/policy.test.yaml', dossier)
            for avant, apres in (
                ('value: 50.0', 'value: 900.0'),  # au-delà du maximum
                # arrêt à 5 réponses positives = élargir à 5 : refusé
                (
                    'value: 1\n        title: Arrêt',
                    'value: 5\n        title: Arrêt',
                ),
                ('kind: eur', 'kind: inconnue'),
                ('schema_version: 2', 'schema_version: 1'),
            ):
                (dossier / 'policy.yaml').write_text(
                    texte.replace(avant, apres, 1), encoding='utf-8'
                )
                with self.assertRaises(PolicyError, msg=apres):
                    load_policy_seed(dossier)

    def test_chaque_reglage_est_lu_par_un_programme(self) -> None:
        """Un réglage que rien ne lit ment dans Mission Control (Q68)."""
        # raccourci : on cherche le nom du réglage (son dernier mot) dans le
        # code ; un nom repris ailleurs (« timezone ») peut passer à tort.
        sources = [
            p.read_text(encoding='utf-8')
            for dossier in ('serge', 'kit')
            for p in (ROOT / dossier).rglob('*')
            if p.suffix in {'.py', '.js'}
        ]
        orphelins = [
            chemin
            for chemin in _feuilles(load_policy())
            if not any(
                re.search(rf'\b{re.escape(chemin.split(".")[-1])}\b', s)
                for s in sources
            )
        ]
        self.assertEqual(orphelins, [])


if __name__ == '__main__':
    unittest.main()
