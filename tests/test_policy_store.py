#!/usr/bin/env python3
"""Les réglages généraux en base : remplis, lus, changés, remis (Q68)."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.policy_store import (  # noqa: E402
    ensure_policy,
    policy_en_vigueur,
    previous_value,
    set_setting,
)


class PolicyStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def _valeur(self, ident: str):
        row = self.conn.execute(
            'SELECT value_json FROM policy_settings WHERE id=?', (ident,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def test_rempli_au_demarrage_avec_sa_description(self) -> None:
        pol = policy_en_vigueur(self.conn)
        self.assertEqual(pol['budget']['monthly_eur'], 50.0)
        self.assertEqual(pol['testing']['n_smoke_min'], 30)
        self.assertEqual(pol['calling_zones']['FR']['contact_per_30d'], 4)
        row = self.conn.execute(
            'SELECT title, kind, min_value, max_value FROM policy_settings'
            " WHERE id='budget.monthly_eur'"
        ).fetchone()
        self.assertEqual(tuple(row), ('Plafond du mois', 'eur', 0, 500))

    def test_changer_garde_la_valeur_precedente(self) -> None:
        ident = 'budget.monthly_eur'
        self.assertEqual(set_setting(self.conn, ident, 80.0, 'mc'), '')
        self.assertEqual(
            policy_en_vigueur(self.conn)['budget']['monthly_eur'], 80.0
        )
        self.assertEqual(previous_value(self.conn, ident), (True, 50.0))
        row = self.conn.execute(
            'SELECT updated_by, previous_by FROM policy_settings WHERE id=?',
            (ident,),
        ).fetchone()
        # Qui a remplacé la valeur précédente : Mission Control.
        self.assertEqual(tuple(row), ('mc', 'mc'))
        # Remettre la précédente : l'actuelle devient la précédente.
        self.assertEqual(set_setting(self.conn, ident, 50.0, 'mc'), '')
        self.assertEqual(previous_value(self.conn, ident), (True, 80.0))

    def test_valeur_relation_et_verrou_refuses(self) -> None:
        self.assertEqual(
            set_setting(self.conn, 'budget.monthly_eur', 900, 'mc'),
            'au plus 500',
        )
        # Le plancher du capital ne dépasse pas son plafond (1,0).
        self.assertEqual(
            set_setting(self.conn, 'standing.capital_max', 0.1, 'mc'),
            'standing.capital_min doit rester ≤ standing.capital_max',
        )
        self.conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            " n_target, created_at, updated_at) VALUES('c', 'v', 'named',"
            " 'email', 'RUNNING', 10, 't', 't')"
        )
        self.assertIn(
            'Un essai tourne',
            set_setting(self.conn, 'testing.n_smoke_min', 35, 'mc'),
        )
        self.assertEqual(self._valeur('testing.n_smoke_min'), 30)
        self.assertEqual(
            set_setting(self.conn, 'inconnu.x', 1, 'mc'), 'réglage inconnu'
        )

    def test_le_demarrage_n_ecrase_jamais_une_valeur(self) -> None:
        set_setting(self.conn, 'budget.llm_daily_eur', 9.0, 'mc')
        ensure_policy(self.conn)
        self.assertEqual(self._valeur('budget.llm_daily_eur'), 9.0)

    def test_reprise_de_l_ancienne_policy(self) -> None:
        """Après la migration v33 : les valeurs reprises sont gardées et
        décrites ; celles que plus rien ne lit sont effacées."""
        self.conn.execute('DELETE FROM policy_settings')
        for ident, value in (
            ('budget.llm_daily_eur', 7.5),
            ('quotas.llm_outil_tours_max', 12),
            ('budget.monthly_eur', -3),
        ):
            self.conn.execute(
                'INSERT INTO policy_settings(id, value_json, updated_by)'
                " VALUES(?, ?, 'owner')",
                (ident, json.dumps(value)),
            )
        ensure_policy(self.conn)
        self.assertEqual(self._valeur('budget.llm_daily_eur'), 7.5)
        self.assertIsNone(self._valeur('quotas.llm_outil_tours_max'))
        # Hors de ses bornes : la valeur de départ la remplace.
        self.assertEqual(self._valeur('budget.monthly_eur'), 50.0)
        titre = self.conn.execute(
            "SELECT title FROM policy_settings WHERE id='budget.llm_daily_eur'"
        ).fetchone()[0]
        self.assertEqual(titre, 'Modèles, par jour')

    def test_un_reglage_retire_est_efface(self) -> None:
        """Un réglage listé dans « deleted » disparaît d'une base existante,
        avec ses relations (ici, ceux que rien ne lisait, Q78)."""
        self.conn.execute(
            'INSERT INTO policy_settings(id, section_id, title, kind,'
            " value_json) VALUES('testing.n_smoke_max', 'testing',"
            " 'Petit essai, personnes au plus', 'curseur', '50')"
        )
        self.conn.execute(
            'INSERT INTO policy_relations(lower_id, upper_id)'
            " VALUES('testing.n_smoke_min', 'testing.n_smoke_max')"
        )
        ensure_policy(self.conn)
        self.assertIsNone(self._valeur('testing.n_smoke_max'))
        self.assertEqual(
            self.conn.execute(
                'SELECT COUNT(*) FROM policy_relations WHERE upper_id='
                "'testing.n_smoke_max'"
            ).fetchone()[0],
            0,
        )

    def test_un_reglage_renomme_garde_sa_valeur(self) -> None:
        """Les nouveaux essais d'une réponse mal formée ont quitté « Plafonds
        par canal » : la valeur changée sur le serveur est gardée."""
        self.conn.execute(
            "DELETE FROM policy_settings WHERE id='llm_calls.format_retries'"
        )
        self.conn.execute(
            'INSERT INTO policy_settings(id, section_id, title, kind,'
            ' value_json, previous_json, previous_at, previous_by)'
            " VALUES('quotas.llm_recalls_json', 'quotas', 'Ancien titre',"
            " 'curseur', '4', '2', '2026-10-01', 'mc')"
        )
        ensure_policy(self.conn)
        self.assertIsNone(self._valeur('quotas.llm_recalls_json'))
        self.assertEqual(self._valeur('llm_calls.format_retries'), 4)
        self.assertEqual(
            policy_en_vigueur(self.conn)['llm_calls']['format_retries'], 4
        )
        row = self.conn.execute(
            'SELECT section_id, title, previous_json FROM policy_settings'
            " WHERE id='llm_calls.format_retries'"
        ).fetchone()
        self.assertEqual(
            tuple(row),
            ('llm_calls', 'Nouveaux essais si la réponse est mal formée', '2'),
        )


if __name__ == '__main__':
    unittest.main()
