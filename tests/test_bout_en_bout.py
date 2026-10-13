#!/usr/bin/env python3
"""Les essais de bout en bout de Mission Control (lot 10, Q91).

« Bout en bout : le POC d'une calculatrice » met en base un business
tout prêt (fiche produit, questions, campagne, plan validé) et lance la
vraie construction du POC. Le modèle, Docker et la réponse du produit sont
des faux ; le reste est réel, comme dans test_etape2.

Scénarios :
- un clic : la calculatrice est en base, choisie pour un POC, sans
  conception ni critique ; le constructeur reçoit le plan tout fait ; le
  POC est publié en staging, relu, puis le ticket « Tester le produit »
  s'ouvre ; validé, il passe en prod et le business au test léger ;
- un second essai crée un business neuf (pas écarté comme doublon) ; sa
  publication reprend l'adresse du staging et arrête l'ancien produit.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.interpreter.flow import fire_button  # noqa: E402
from tests import test_etape2  # noqa: E402
from tests.test_etape2 import FauxModeles, _t  # noqa: E402


class _Constructeur(FauxModeles):
    """Garde ce que le constructeur a reçu."""

    def __init__(self, relectures: list[str]) -> None:
        super().__init__([], relectures)
        self.recu: list[str] = []

    def __call__(self, _key, model, messages, tools=None, **_kw):
        if 'Tu construis le POC' in messages[0]['content']:
            self.recu.append(str(messages))
        return super().__call__(_key, model, messages, tools, **_kw)


class BoutEnBoutTests(test_etape2.Etape2Tests):
    # Les scénarios de l'étape 2 tournent déjà dans test_etape2.
    test_du_choix_au_test_leger = None  # type: ignore[assignment]
    test_arreter_le_business_libere_sa_place = None  # type: ignore[assignment]
    test_sans_reponse_sous_48_heures_le_plan_s_applique = None  # type: ignore[assignment]
    test_a_corriger_au_test_relance_la_construction = None  # type: ignore[assignment]

    def _calculatrice(self, modeles: FauxModeles) -> str:
        self.assertIsNotNone(
            fire_button(self.conn, 'bouton_bout_en_bout_poc', {})
        )
        self.conn.commit()
        self._vider(modeles)
        row = self.conn.execute(
            "SELECT id FROM ventures WHERE name='Calculatrice'"
            ' ORDER BY rowid DESC'
        ).fetchone()
        return str(row[0])

    def test_le_poc_d_une_calculatrice(self) -> None:
        modeles = _Constructeur(['bon'])
        venture = self._calculatrice(modeles)
        self.assertEqual(self._echecs(), [])
        # Ni conception ni critique : le plan tout fait est déjà validé.
        self.assertEqual(set(modeles.par_role), {'construire', 'relire'})
        self.assertIn('0,1 + 0,2', modeles.recu[0])
        self.assertIn('lisible sur ordinateur et sur mobile', modeles.recu[0])
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT kind, status FROM product_plans WHERE venture_id=?',
                    (venture,),
                ).fetchall()
            ),
            [('poc', 'validated')],
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT pass, status, verdict FROM builds'
                    ' WHERE venture_id=?',
                    (venture,),
                ).fetchall()
            ),
            [(1, 'reviewed', 'bon')],
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT hostname, status FROM deployments'
                    " WHERE venture_id=? AND target='staging'",
                    (venture,),
                ).fetchone()
            ),
            ('staging-calculatrice.serge.exemple.fr', 'running'),
        )
        self._repondre('TEST_POC', 'valider')
        self._vider(modeles)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT lifecycle FROM ventures WHERE id=?', (venture,)
                ).fetchone()
            ),
            ('SMOKE_READY',),
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT hostname, status FROM deployments'
                    " WHERE venture_id=? AND target='prod'",
                    (venture,),
                ).fetchone()
            ),
            ('calculatrice.serge.exemple.fr', 'running'),
        )

    def test_un_second_essai_reprend_l_adresse(self) -> None:
        premier = self._calculatrice(FauxModeles([], ['bon']))
        second = self._calculatrice(FauxModeles([], ['bon']))
        self.assertNotEqual(premier, second)
        self.assertEqual(self._echecs(), [])
        etats = dict(
            self.conn.execute(
                'SELECT venture_id, status FROM deployments'
                " WHERE target='staging'"
            ).fetchall()
        )
        self.assertEqual(etats, {premier: 'stopped', second: 'running'})
        raison = self.conn.execute(
            'SELECT last_error FROM deployments WHERE venture_id=?',
            (premier,),
        ).fetchone()[0]
        self.assertIn('remplacé par', raison)


if __name__ == '__main__':
    import unittest

    unittest.main()
