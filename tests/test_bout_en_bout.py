#!/usr/bin/env python3
"""L'essai total, à partir de l'étape 2 : le POC de la calculatrice
(lot 12, décision Q99).

« Lancer l'essai total », avec l'étape de départ 2, met en base le
business d'essai « Calculatrice », son contact et son plan tout fait, puis
ouvre le ticket « Plan ». Validé, la vraie construction du POC part. Le
modèle, Docker et la réponse du produit sont des faux ; le reste est réel,
comme dans test_etape2. La suite (le test léger) est dans
test_essai_total : ici, ses tâches attendent.

Scénarios :
- le plan tout fait attend Julien, marqué « essai », sans conception ni
  critique ; validé, le constructeur le reçoit ; le POC est publié en
  staging, relu, puis le ticket « Tester le produit » s'ouvre ; validé, il
  passe en prod et le business au test léger ; tout est dans le couloir
  d'essai ;
- un second essai arrête le premier : son business neuf reprend l'adresse
  du staging, et l'ancien produit est arrêté.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.interpreter.rules import quota_usage  # noqa: E402
from serge.interpreter.triggers import fire_button  # noqa: E402
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
            fire_button(
                self.conn,
                'bouton_essai_total',
                {
                    'nom': 'Essai Testeur',
                    'e-mail': 'essai@exemple.fr',
                    'téléphone (+33…)': '+33600000001',
                    'étape de départ (1, 2, 3, 5 ou 6)': '2',
                },
            )
        )
        self.conn.commit()
        self._vider(modeles)
        # Le plan tout fait attend Julien, comme un vrai plan.
        self._repondre('PLAN_POC', 'valider')
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
        # Ni conception ni critique : le plan est tout fait.
        self.assertEqual(set(modeles.par_role), {'construire', 'relire'})
        # Tout est dans le couloir d'essai : le business, ses tickets, ses
        # tâches ; il ne prend aucune place de test.
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT trial FROM ventures WHERE id=?', (venture,)
                ).fetchone()
            ),
            (1,),
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    'SELECT DISTINCT trial FROM tickets'
                ).fetchall()
            ),
            [(1,)],
        )
        self.assertEqual(
            _t(
                self.conn.execute(
                    "SELECT COUNT(*) FROM tasks WHERE trial_run=''"
                ).fetchone()
            ),
            (0,),
        )
        self.assertEqual(quota_usage(self.conn, 'places_de_test')[0], 0)
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
