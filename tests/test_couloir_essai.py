#!/usr/bin/env python3
"""Le couloir d'essai et « Repartir d'ici » (lot 12, décision Q99).

La base et l'interpréteur sont réels. Un petit pipeline de test (des
invocations sans LLM) s'ajoute au pipeline de départ, dont les
déclencheurs sont éteints ; aucun modèle n'est appelé.

Scénarios :
- un bouton d'essai lance une chaîne d'essai : son business est marqué, sa
  suite hérite du couloir, un lien « essai seulement » ne part que là, un
  réglage prend sa valeur d'essai ; le même bouton dans le vrai pipeline
  fait une vraie chaîne ;
- chacun ne voit que son couloir : une lecture, la recherche de doublons
  et une modification « tous les cycles ouverts » ne touchent jamais
  l'autre couloir ;
- une réponse à un ticket d'essai lance une tâche d'essai, suite de la
  tâche qui a ouvert le ticket ;
- un déclencheur ne part que si ses nombres de lignes sont bons, comptés
  dans son couloir ;
- relancer l'essai arrête le précédent : ses tâches en attente, ses
  tickets, son business ; la suite d'une vieille tâche ne part plus ;
- « Repartir d'ici » : l'ancienne suite en attente est annulée, une tâche
  neuve repart, et un lien déjà passé repasse.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.restart import RestartError, restart_from  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.interpreter.triggers import (  # noqa: E402
    fire_button,
    trigger_refusal,
)
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from serge.tickets.lifecycle import create_ticket, publish  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402
from serge.tickets.types import ticket_types  # noqa: E402
from serge.trial import active_run, lane  # noqa: E402
from serge.trial_run import stop_trial  # noqa: E402

MAINTENANT = '2026-11-16T18:00:00+00:00'


def _v(source: str, value: str = '') -> dict[str, str]:
    return {'source': source, 'value': value}


PIPELINE = {
    'schema_version': 1,
    'tools': [
        {
            'id': 't_business',
            'title': 'Les business',
            'capability': 'db_read',
            'read': {
                'tables': ['ventures'],
                'columns': [{'table': 'ventures', 'name': 'name'}],
            },
        }
    ],
    'invocations': [
        # Crée un business, avec un réglage qui a une valeur d'essai.
        {
            'id': 't_creer',
            'type': 'capability',
            'capability': 'echo',
            'settings': {'taille': {'value': 40, 'trial': 1}},
            'params': {
                'nom': _v('task', 'nom'),
                'taille': _v('setting', 'taille'),
            },
            'writes': [
                {
                    'table': 'ventures',
                    'operation': 'insert',
                    'dedup': False,
                    'values': {
                        'name': _v('field', 'nom'),
                        'description': _v('field', 'taille'),
                        'lifecycle': _v('fixed', 'CANDIDATE'),
                    },
                },
                {
                    'table': 'listen_docs',
                    'operation': 'insert',
                    'values': {
                        'url': _v('fixed', 'https://exemple.fr/besoin'),
                        'source': _v('fixed', 'web'),
                        'fetched_at': _v('now'),
                    },
                },
            ],
        },
        # Lit les business qu'elle voit, et choisit celui qu'on lui passe.
        {
            'id': 't_choisir',
            'type': 'capability',
            'capability': 'db_read',
            'params': {'tool_id': _v('fixed', 't_business')},
            'writes': [
                {
                    'table': 'ventures',
                    'operation': 'update',
                    'key': {
                        'column': 'id',
                        'source': 'task',
                        'value': 'venture_id',
                    },
                    'values': {'lifecycle': _v('fixed', 'POC_SELECTED')},
                }
            ],
        },
        {'id': 't_vrai_seulement', 'type': 'capability', 'capability': 'echo'},
        {
            'id': 't_essai_seulement',
            'type': 'capability',
            'capability': 'echo',
        },
        {'id': 't_suite', 'type': 'capability', 'capability': 'echo'},
        # Ferme tous les cycles ouverts (comme « Abandonner le cycle »).
        {
            'id': 't_fermer',
            'type': 'capability',
            'capability': 'echo',
            'writes': [
                {
                    'table': 'listen_cycles',
                    'operation': 'update',
                    'key': {
                        'column': 'status',
                        'source': 'fixed',
                        'value': 'OPEN',
                    },
                    'values': {'status': _v('fixed', 'ABANDONED')},
                }
            ],
        },
    ],
    'links': [
        {
            'id': 't_cree_vers_choix',
            'from': 't_creer',
            'to': 't_choisir',
            'mode': 'per_row',
            'write': 0,
            'params': {'venture_id': _v('row', 'id')},
        },
        {
            'id': 't_choix_vers_vrai',
            'from': 't_choisir',
            'to': 't_vrai_seulement',
            'mode': 'per_row',
            'write': 0,
            'lane': 'real',
            'params': {'venture_id': _v('row', 'id')},
        },
        {
            'id': 't_choix_vers_essai',
            'from': 't_choisir',
            'to': 't_essai_seulement',
            'mode': 'per_row',
            'write': 0,
            'lane': 'trial',
            'params': {'venture_id': _v('row', 'id')},
        },
    ],
    'triggers': [
        {
            'id': 't_bouton_vrai',
            'invocation': 't_creer',
            'event': 'button',
            'params': {'nom': _v('form', 'nom')},
        },
        {
            'id': 't_bouton_essai',
            'invocation': 't_creer',
            'event': 'button',
            'lane': 'trial',
            'params': {'nom': _v('form', 'nom')},
        },
        {
            'id': 't_reponse',
            'invocation': 't_suite',
            'event': 'row_written',
            'table': 'ticket_answers',
            'filter_column': 'acte',
            'filter_value': 'valider',
        },
        {
            'id': 't_bouton_compte',
            'invocation': 't_suite',
            'event': 'button',
            'only_if_rows': [
                {
                    'table': 'ventures',
                    'column': 'lifecycle',
                    'values': ['POC_SELECTED'],
                    'at_most': 0,
                    'description': 'Business en test',
                },
                {
                    'table': 'ventures',
                    'column': 'lifecycle',
                    'values': ['CANDIDATE'],
                    'at_least': 1,
                    'description': 'Business candidats',
                },
            ],
        },
    ],
}


class CouloirCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.conn.execute('UPDATE triggers SET enabled=0')
        seed_pipeline(self.conn, PIPELINE)
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _vider(self) -> None:
        for file in ('works', 'conversations'):
            while process_one(self.conn, file, now=MAINTENANT):
                pass

    def _taches(self, invocation: str) -> list[tuple]:
        return self.conn.execute(
            'SELECT status, trial_run FROM tasks WHERE invocation_id=?'
            ' ORDER BY created_at, id',
            (invocation,),
        ).fetchall()

    def _business(self) -> dict[str, tuple]:
        return {
            str(nom): (essai, statut, taille)
            for nom, essai, statut, taille in self.conn.execute(
                'SELECT name, trial, lifecycle, description FROM ventures'
            )
        }


class ChaineTests(CouloirCase):
    def test_un_essai_et_une_vraie_chaine_ne_se_touchent_pas(self) -> None:
        essai = fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul'})
        vraie = fire_button(self.conn, 't_bouton_vrai', {'nom': 'Devis'})
        self.assertEqual(active_run(self.conn), essai)
        self._vider()
        # Chaque business est de son couloir, avec la valeur de son
        # réglage : 40 en vrai, 1 dans l'essai.
        self.assertEqual(
            self._business(),
            {
                'Calcul': (1, 'POC_SELECTED', '1'),
                'Devis': (0, 'POC_SELECTED', '40'),
            },
        )
        # La même page est gardée dans chaque couloir : pas un doublon.
        self.assertEqual(
            sorted(self.conn.execute('SELECT url, trial FROM listen_docs')),
            [
                ('https://exemple.fr/besoin', 0),
                ('https://exemple.fr/besoin', 1),
            ],
        )
        # La suite hérite du couloir ; chaque lien d'un seul couloir ne
        # part que dans le sien.
        self.assertEqual(
            self._taches('t_choisir'), [('done', essai), ('done', '')]
        )
        self.assertEqual(self._taches('t_essai_seulement'), [('done', essai)])
        self.assertEqual(self._taches('t_vrai_seulement'), [('done', '')])
        self.assertNotEqual(essai, vraie)

    def test_chacun_ne_lit_que_son_couloir(self) -> None:
        from serge.db.query_builder import execute_db_read

        fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul'})
        fire_button(self.conn, 't_bouton_vrai', {'nom': 'Devis'})
        self._vider()
        vrais = execute_db_read(self.conn, 't_business', {})['data']
        self.assertEqual(vrais, [{'name': 'Devis'}])
        with lane('un_essai'):
            essais = execute_db_read(self.conn, 't_business', {})['data']
        self.assertEqual(essais, [{'name': 'Calcul'}])

    def test_fermer_les_cycles_ne_ferme_pas_celui_de_l_essai(self) -> None:
        for ident, essai in (('c_vrai', 0), ('c_essai', 1)):
            self.conn.execute(
                'INSERT INTO listen_cycles(id, status, created_at, trial)'
                " VALUES(?, 'OPEN', ?, ?)",
                (ident, MAINTENANT, essai),
            )
        enqueue_task(self.conn, 't_fermer', {})
        self._vider()
        self.assertEqual(
            dict(self.conn.execute('SELECT id, status FROM listen_cycles')),
            {'c_vrai': 'ABANDONED', 'c_essai': 'OPEN'},
        )

    def test_la_reponse_a_un_ticket_d_essai_est_de_l_essai(self) -> None:
        essai = fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul'})
        assert essai is not None
        with lane(essai, essai):
            ticket = create_ticket(
                self.conn, ticket_types(self.conn), 'FYI', 'Essai', {}
            )
            publish(self.conn, ticket)
        self.assertEqual(
            self.conn.execute(
                'SELECT trial, task_id FROM tickets WHERE id=?', (ticket,)
            ).fetchone(),
            (1, essai),
        )
        noter_reponse(self.conn, ticket, 'valider', '', 'owner')
        self.assertEqual(
            self.conn.execute(
                'SELECT trial_run, parent_id FROM tasks'
                " WHERE invocation_id='t_suite'"
            ).fetchall(),
            [(essai, essai)],
        )

    def test_un_declencheur_compte_les_lignes_de_son_couloir(self) -> None:
        self.assertIn(
            'Business candidats : 0, au moins 1',
            trigger_refusal(self.conn, 't_bouton_compte'),
        )
        fire_button(self.conn, 't_bouton_vrai', {'nom': 'Devis'})
        process_one(self.conn, 'works', now=MAINTENANT)
        self.assertEqual(trigger_refusal(self.conn, 't_bouton_compte'), '')
        # Le business de l'essai, choisi, ne compte pas pour le vrai.
        fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul'})
        process_one(self.conn, 'works', now=MAINTENANT)
        process_one(self.conn, 'works', now=MAINTENANT)
        self.assertEqual(
            self._business(),
            {
                'Devis': (0, 'POC_SELECTED', '40'),
                'Calcul': (1, 'CANDIDATE', '1'),
            },
        )
        self.assertIn(
            'Business en test : 1, au plus 0',
            trigger_refusal(self.conn, 't_bouton_compte'),
        )
        self.assertEqual(
            trigger_refusal(self.conn, 't_bouton_compte', trial=True), ''
        )


class ArretTests(CouloirCase):
    def test_relancer_l_essai_arrete_le_precedent(self) -> None:
        premier = fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul'})
        assert premier is not None
        # Sa première tâche tourne (elle n'a pas encore passé la main),
        # et un ticket d'essai attend.
        process_one(self.conn, 'works', now=MAINTENANT)
        with lane(premier, premier):
            ticket = create_ticket(
                self.conn, ticket_types(self.conn), 'FYI', 'Essai', {}
            )
            publish(self.conn, ticket)
        self.assertEqual(self._taches('t_choisir'), [('ready', premier)])
        second = fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul 2'})
        self.assertEqual(active_run(self.conn), second)
        self.assertEqual(self._taches('t_choisir'), [('cancelled', premier)])
        self.assertEqual(
            self.conn.execute(
                'SELECT state FROM tickets WHERE id=?', (ticket,)
            ).fetchone()[0],
            'CANCELLED',
        )
        self.assertEqual(self._business()['Calcul'][1], 'KILLED')
        self._vider()
        self.assertEqual(self._business()['Calcul 2'][1], 'POC_SELECTED')

    def test_la_suite_d_un_essai_arrete_ne_part_pas(self) -> None:
        essai = fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul'})
        self.assertEqual(
            stop_trial(self.conn, 'arrêté dans Mission Control'),
            {'tasks': 1, 'tickets': 0, 'ventures': 0},
        )
        self.assertEqual(active_run(self.conn), '')
        # Une tâche de cet essai qui tournait encore finit : rien ne suit.
        self.conn.execute(
            "UPDATE tasks SET status='ready' WHERE id=?", (essai,)
        )
        self._vider()
        self.assertEqual(self._taches('t_creer'), [('done', essai)])
        self.assertEqual(self._taches('t_choisir'), [])


class RepartirTests(CouloirCase):
    def test_repartir_d_une_tache_finie(self) -> None:
        depart = fire_button(self.conn, 't_bouton_vrai', {'nom': 'Devis'})
        assert depart is not None
        self._vider()
        choix = self.conn.execute(
            "SELECT id FROM tasks WHERE invocation_id='t_choisir'"
        ).fetchone()[0]
        # La suite est remise en attente, comme une tâche qui attendrait
        # son tour ; un ticket ouvert par elle attend aussi.
        suite = self.conn.execute(
            "SELECT id FROM tasks WHERE invocation_id='t_vrai_seulement'"
        ).fetchone()[0]
        self.conn.execute(
            "UPDATE tasks SET status='ready' WHERE id=?", (suite,)
        )
        with lane('', suite):
            ticket = create_ticket(
                self.conn, ticket_types(self.conn), 'FYI', 'Vu', {}
            )
            publish(self.conn, ticket)
        neuve = restart_from(self.conn, choix)
        self.assertNotEqual(neuve, choix)
        etats = dict(
            self.conn.execute(
                'SELECT id, status FROM tasks WHERE id IN (?, ?, ?)',
                (choix, suite, neuve),
            )
        )
        self.assertEqual(
            etats, {choix: 'done', suite: 'cancelled', neuve: 'ready'}
        )
        self.assertEqual(
            self.conn.execute(
                'SELECT state FROM tickets WHERE id=?', (ticket,)
            ).fetchone()[0],
            'CANCELLED',
        )
        # La tâche neuve refait son travail, et son lien repasse, pour la
        # même ligne : une nouvelle suite part.
        self._vider()
        self.assertEqual(
            [s for s, _ in self._taches('t_vrai_seulement')],
            ['cancelled', 'done'],
        )
        parents = self.conn.execute(
            'SELECT parent_id, rerun FROM tasks WHERE id=?', (neuve,)
        ).fetchone()
        self.assertEqual(parents[0], depart)
        self.assertTrue(parents[1])

    def test_une_tache_en_cours_ou_d_un_vieil_essai_ne_repart_pas(
        self,
    ) -> None:
        essai = fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul'})
        assert essai is not None
        self.conn.execute(
            "UPDATE tasks SET status='running' WHERE id=?", (essai,)
        )
        with self.assertRaisesRegex(RestartError, 'en cours'):
            restart_from(self.conn, essai)
        self.conn.execute(
            "UPDATE tasks SET status='done' WHERE id=?", (essai,)
        )
        fire_button(self.conn, 't_bouton_essai', {'nom': 'Calcul 2'})
        with self.assertRaisesRegex(RestartError, 'essai arrêté ou remplacé'):
            restart_from(self.conn, essai)


if __name__ == '__main__':
    unittest.main()
