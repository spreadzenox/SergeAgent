#!/usr/bin/env python3
"""Projecteurs P5 Policy : les réglages tels qu'ils sont en base."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.mc.proj_policy import (  # noqa: E402
    project_politique_active,
    project_reglages,
)
from serge.policy_store import set_setting  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'


class ProjPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)

    def _section(self, ident: str) -> dict:
        res = project_politique_active(self.conn, {}, NOW)
        return next(s for s in res['sections'] if s['id'] == ident)

    def test_reglages_par_famille_avec_leur_description(self) -> None:
        argent = self._section('budget')
        self.assertEqual(argent['titre'], 'Argent')
        mois = argent['reglages'][0]
        self.assertEqual(
            {k: mois[k] for k in ('id', 'titre', 'widget', 'min', 'max')},
            {
                'id': 'budget.monthly_eur',
                'titre': 'Plafond du mois',
                'widget': 'eur',
                'min': 0,
                'max': 500,
            },
        )
        self.assertEqual(mois['valeur'], 50.0)
        self.assertIsNone(mois['precedent'])
        canaux = self._section('consent')['reglages'][0]
        self.assertIn(['email', 'E-mail'], canaux['choix'])

    def test_valeur_precedente_et_verrou(self) -> None:
        set_setting(self.conn, 'budget.monthly_eur', 80.0, 'mc')
        mois = self._section('budget')['reglages'][0]
        self.assertEqual(mois['valeur'], 80.0)
        self.assertEqual(mois['precedent']['valeur'], 50.0)
        self.assertEqual(mois['precedent']['par'], 'mc')
        self.assertEqual(self._section('testing')['verrou'], '')
        self.conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            " n_target, created_at, updated_at) VALUES('c1', 'v1', 'named',"
            " 'email', 'RUNNING', 10, 't', 't')"
        )
        self.assertIn('Un essai tourne', self._section('testing')['verrou'])

    def test_reglages_d_invocation_avec_valeur_precedente(self) -> None:
        res = project_reglages(self.conn, {}, NOW)
        self.assertTrue(res['invocations'])
        self.assertIsNone(res['invocations'][0]['reglages'][0]['precedent'])
        self.assertIsNone(res['quotas'][0]['precedent'])


if __name__ == '__main__':
    unittest.main()
