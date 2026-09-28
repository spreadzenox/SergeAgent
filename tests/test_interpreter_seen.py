#!/usr/bin/env python3
"""Ce que voit une invocation, sur l'étape 1 décrite en base (lot 7).

Scénario : « Formuler des business A » écrit des business. Elle reçoit
donc d'office la version courte des business déjà connus (numéro et nom),
les plus récents d'abord, avec le compte exact de ceux laissés de côté ;
ses leçons ; et le bloc « Qui est Serge » avec sa place dans la chaîne.
Avec « Lire les tables que je vois », elle lit la fiche complète d'un
business, mais pas une table qu'elle ne voit pas ni une colonne non
lisible. Avec « Lire l'historique », « Choisir les business à tester »
voit ce qui est arrivé à un business.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.seen import read_seen_table, row_history  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.memory.lessons import add_lesson, set_lesson_status  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'
COURTE = 'Les business (version courte, pour comparer)'


def _bloc(texte: str, titre: str) -> Any:
    """Les lignes d'un bloc donné d'office (« ## titre » puis du JSON)."""
    suite = texte.split(f'## {titre}\n', 1)[1]
    return json.loads(suite.split('\n', 1)[0])


class Modele:
    """Joue A, B et « Choisir » sans rien écrire, après avoir appelé les
    outils demandés (pour A). Garde ce que chaque invocation a reçu."""

    def __init__(self, appels: list[tuple[str, dict]] | None = None) -> None:
        self.appels = list(appels or [])
        self.recu: dict[str, dict[str, Any]] = {}
        self.reponses: list[dict] = []

    def __call__(self, _key, model, messages, tools=None, **_kw) -> ChatResult:
        system = messages[0]['content']
        nom = next(
            (
                n
                for n in ('A', 'B')
                if f'« Formuler des business {n} »' in system
            ),
            'choisir',
        )
        self.recu.setdefault(
            nom,
            {
                'system': system,
                'user': messages[1]['content'],
                'outils': {
                    t['function']['name']: t['function'] for t in tools or []
                },
            },
        )
        if messages[-1]['role'] == 'tool':
            self.reponses.append(json.loads(messages[-1]['content']))
        if nom == 'A' and self.appels:
            outil, args = self.appels.pop(0)
            appel = ToolCall(f'c{len(self.appels)}', outil, json.dumps(args))
            return ChatResult('', 1, 1, model, 1, (appel,))
        reponse = {'choix': []} if nom == 'choisir' else {'fiches': []}
        return ChatResult(json.dumps(reponse), 10, 10, model, 1)


class CeQueVoitUneInvocationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _business(self, n: int, **colonnes: str) -> None:
        for i in range(n):
            valeurs = {
                'id': f'v{i}',
                'name': f'Business {i}',
                'lifecycle': 'CANDIDATE',
                'created_at': f'2026-09-27T10:{i // 60:02d}:{i % 60:02d}',
                'updated_at': 't',
                **colonnes,
            }
            self.conn.execute(
                f'INSERT INTO ventures({", ".join(valeurs)})'
                f' VALUES({", ".join("?" for _ in valeurs)})',
                list(valeurs.values()),
            )

    def _lancer(self, modele: Modele) -> None:
        """A, puis B, puis « Choisir », pour le cycle c1."""
        self.conn.execute(
            'INSERT INTO listen_cycles(id, guide, status, created_at)'
            " VALUES('c1', 'artisans', 'OPEN', 't')"
        )
        enqueue_task(self.conn, 'formuler_a', {'cycle_id': 'c1'})
        for _ in range(8):
            if process_one(self.conn, 'works', now=NOW, caller=modele) is None:
                break

    def _vu(self, invocation: str) -> list[tuple]:
        return self.conn.execute(
            'SELECT s.table_name, s.rows_given, s.rows_left_out'
            ' FROM task_seen_tables s JOIN tasks t ON t.id=s.task_id'
            ' WHERE t.invocation_id=? ORDER BY s.table_name',
            (invocation,),
        ).fetchall()

    def test_la_version_courte_des_tables_ou_elle_ecrit(self) -> None:
        self._business(250)
        modele = Modele()
        self._lancer(modele)
        courte = _bloc(modele.recu['A']['user'], COURTE)
        self.assertEqual(len(courte), 100)
        self.assertEqual(courte[0], {'id': 'v249', 'name': 'Business 249'})
        self.assertIn(
            '150 autres lignes ne sont pas montrées', modele.recu['A']['user']
        )
        self.assertEqual(self._vu('formuler_a'), [('ventures', 100, 150)])

    def test_le_compte_des_lectures_est_juste_au_dela_de_200(self) -> None:
        self._business(250)
        self._lancer(Modele())
        recu = self.conn.execute(
            'SELECT it.label, i.rows_given, i.rows_left_out FROM task_inputs i'
            ' JOIN tasks t ON t.id=i.task_id'
            ' JOIN invocation_tools it ON it.id=i.invocation_tool_id'
            " WHERE t.invocation_id='choisir_business' ORDER BY it.position"
        ).fetchall()
        # 250 candidats ; 50 montrés au plus (le maximum de l'invocation).
        self.assertIn(('Les business candidats', 50, 200), recu)

    def test_qui_est_serge_et_sa_place(self) -> None:
        modele = Modele()
        self._lancer(modele)
        system = modele.recu['A']['system']
        for texte in (
            'La chaîne : 1. Pré-prospection → 2. Conception d’un PoC',
            '8. Caisse.',
            'Tu es « Formuler des business A », dans l’étape 1'
            ' « Pré-prospection ».',
            'Avant toi : « Trier les pages » (« Les besoins nouveaux vont à'
            ' A »).',
            'Après toi : « Formuler des business B » (« Puis à B, qui voit'
            ' les idées de A »).',
        ):
            self.assertIn(texte, system)

    def test_ses_lecons_les_plus_fiables_d_abord(self) -> None:
        add_lesson(self.conn, 'Pour tout Serge', confidence=0.9)
        add_lesson(
            self.conn,
            'Pour l’étape',
            confidence=0.4,
            scope='etape:pre_prospection',
        )
        add_lesson(
            self.conn,
            'Pour moi',
            confidence=0.3,
            scope='invocation:formuler_a',
        )
        add_lesson(self.conn, 'Pour une autre', scope='invocation:formuler_b')
        depassee = add_lesson(self.conn, 'Dépassée', confidence=1.0)
        set_lesson_status(self.conn, depassee, 'deprecated')
        modele = Modele()
        self._lancer(modele)
        user = modele.recu['A']['user']
        lecons = user.split('## Tes leçons (les plus fiables d’abord)\n')[1]
        self.assertEqual(
            lecons.splitlines()[:3],
            [
                '- Pour moi (pour toi, fiabilité 0.3)',
                '- Pour l’étape (pour ton étape, fiabilité 0.4)',
                '- Pour tout Serge (pour tout Serge, fiabilité 0.9)',
            ],
        )
        self.assertNotIn('Pour une autre', user)
        self.assertNotIn('Dépassée', user)
        self.assertIn(('lessons', 3, 0), self._vu('formuler_a'))

    def test_les_outils_construits_pour_elle(self) -> None:
        modele = Modele()
        self._lancer(modele)
        outils = modele.recu['A']['outils']
        lire = outils['lire_tables_vues']['parameters']['properties']
        self.assertEqual(lire['table']['enum'], ['ventures'])
        self.assertIn(
            'Colonnes : id, name, description',
            outils['lire_tables_vues']['description'],
        )
        historique = outils['lire_historique']['parameters']['properties']
        self.assertEqual(
            historique['table']['enum'], ['ventures', 'listen_docs']
        )
        self.assertIn('demande_capacite', outils)
        # Les paramètres figés (la table des pages, le nombre de lignes)
        # ne sont pas montrés : le modèle ne donne que le numéro.
        page = outils['lire_page_entiere']['parameters']['properties']
        self.assertEqual(sorted(page), ['id'])

    def test_lire_la_fiche_complete_d_un_business(self) -> None:
        self._business(1, description='des devis au micro', dedup_key='x')
        modele = Modele(
            [
                (
                    'lire_tables_vues',
                    {'table': 'ventures', 'column': 'id', 'value': 'v0'},
                )
            ]
        )
        self._lancer(modele)
        fiche = modele.reponses[0]['rows'][0]
        self.assertEqual(fiche['description'], 'des devis au micro')
        self.assertEqual(fiche['lifecycle'], 'CANDIDATE')
        self.assertNotIn('dedup_key', fiche)

    def test_ce_qu_elle_ne_voit_pas_est_refuse(self) -> None:
        self._business(250)
        lire = read_seen_table
        refus = lire(self.conn, 'x', {'table': 'listen_cycles'}, 'formuler_a')
        self.assertEqual(refus['code'], 'table_non_vue')
        refus = lire(
            self.conn,
            'x',
            {'table': 'ventures', 'column': 'dedup_key', 'value': ''},
            'formuler_a',
        )
        self.assertEqual(refus['code'], 'colonne_non_lisible')
        page = lire(
            self.conn, 'x', {'table': 'ventures', 'page': 3}, 'formuler_a'
        )
        self.assertEqual(
            (len(page['rows']), page['pages'], page['total']), (50, 3, 250)
        )
        self.assertEqual(page['rows'][-1]['id'], 'v0')

    def test_ajouter_ou_retirer_une_table_a_comparer(self) -> None:
        self.conn.executemany(
            'INSERT INTO invocation_compare_tables(invocation_id, table_name,'
            " included) VALUES('formuler_a', ?, ?)",
            [('listen_cycles', 1), ('ventures', 0)],
        )
        modele = Modele()
        self._lancer(modele)
        user = modele.recu['A']['user']
        self.assertNotIn(COURTE, user)
        cycles = _bloc(
            user, "Les cycles d'écoute (version courte, pour comparer)"
        )
        self.assertEqual(cycles[0]['guide'], 'artisans')
        lire = modele.recu['A']['outils']['lire_tables_vues']
        self.assertEqual(
            lire['parameters']['properties']['table']['enum'],
            ['listen_cycles'],
        )

    def test_l_historique_d_un_business(self) -> None:
        from serge.db.store import append_event

        self._business(1)
        append_event(
            self.conn,
            actor='invocation:formuler_a',
            type='write.inserted',
            payload={'table': 'ventures', 'id': 'v0'},
            rows=[('ventures', 'v0')],
        )
        append_event(
            self.conn, actor='owner', type='decision.poc', venture_id='v0'
        )
        historique = row_history(
            self.conn,
            'x',
            {'table': 'ventures', 'id': 'v0'},
            'choisir_business',
        )
        self.assertEqual(
            [e['quoi'] for e in historique['rows']],
            ['decision.poc', 'write.inserted'],
        )
        self.assertEqual(historique['rows'][1]['qui'], 'invocation:formuler_a')
        refus = row_history(
            self.conn,
            'x',
            {'table': 'listen_cycles', 'id': 'c1'},
            'choisir_business',
        )
        self.assertEqual(refus['code'], 'table_non_vue')


if __name__ == '__main__':
    unittest.main()
