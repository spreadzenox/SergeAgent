#!/usr/bin/env python3
"""Mission Control : les tâches finies, et la réponse d'une tâche en clair.

La fiche « Tâches finies » (``#/objet/file/finies``) donne une ligne par
tâche finie, la plus récente d'abord : son heure, son état, sa durée, ce
qui l'a lancée, et ce qu'elle a rendu en une phrase. Les tâches de
routine pareilles font une seule ligne ; une tâche lancée par un bouton,
ou qui a rendu une réponse, garde la sienne. La fiche d'une tâche montre
la réponse du modèle champ par champ, pas son JSON.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.mc.proj_historique import (  # noqa: E402
    Origines,
    duree,
    extrait,
    project_taches_finies,
)
from serge.mc.proj_objet import project_objet  # noqa: E402
from serge.mc.proj_reponse import cadres_reponse  # noqa: E402
from serge.mc.proj_taches import fiche_tache  # noqa: E402
from tests.taches_fixtures import invocations, tache  # noqa: E402

REPONSE = {
    'etat': 'connecte',
    'resume': 'Les avis sont partagés : deux pour, un contre.',
    'trouvailles': [
        {'url': 'https://site.example/fil/1', 'titre': 'Un premier fil'},
        {'url': 'https://site.example/fil/2', 'titre': 'Un second fil'},
    ],
}


class TachesFiniesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        invocations(
            self.conn,
            ('relever', 'Relever les messages', 'prospection_light'),
            ('fouiller', 'Fouiller un réseau', 'prospection_light'),
            ('lire', 'Lire un flux', 'prospection_light'),
        )
        self.conn.execute(
            'INSERT INTO triggers(id, title, invocation_id, event) VALUES'
            " ('bouton_fouiller', 'Fouiller un réseau', 'fouiller',"
            " 'button'), ('releve', 'Relever chaque canal', 'relever',"
            " 'every')"
        )
        self.minute = 0

    def tearDown(self) -> None:
        self.conn.close()

    def _finie(
        self,
        invocation: str,
        *,
        erreur: str = '',
        origine: tuple[str, str] = ('trigger', 'releve:2026'),
        reponse: dict | None = None,
        secondes: int = 2,
    ) -> str:
        """Une tâche finie une minute après la précédente."""
        self.minute += 1
        ident = tache(
            self.conn,
            invocation,
            {'n': str(self.minute)},
            key=f'k{self.minute}',
            status='failed' if erreur else 'done',
            error=erreur,
        )
        self.conn.execute(
            'UPDATE tasks SET origin=?, origin_ref=?, started_at=?,'
            ' finished_at=?, answer_json=? WHERE id=?',
            (
                *origine,
                f'2026-11-21T21:{self.minute:02d}:00+00:00',
                f'2026-11-21T21:{self.minute:02d}:{secondes:02d}+00:00',
                json.dumps(reponse, ensure_ascii=False) if reponse else '',
                ident,
            ),
        )
        return ident

    def test_une_ligne_par_tache_les_routines_regroupees(self) -> None:
        for _ in range(3):
            self._finie('relever')
        fouille = self._finie(
            'fouiller',
            origine=('button', 'bouton_fouiller:2026'),
            reponse=REPONSE,
            secondes=40,
        )
        self._finie('lire', erreur='HTTP 429')
        self._finie('lire', erreur='HTTP 429')
        self._finie('lire', erreur='HTTP 404')
        derniere = self._finie('relever')
        # Une tâche qui attend n'est pas dans l'historique.
        tache(self.conn, 'relever', {'n': 'x'}, key='k-prete')
        fiche = project_taches_finies(self.conn)
        self.assertEqual(
            fiche['tableau']['colonnes'],
            [
                'Finie',
                'Tâche',
                'État',
                'Durée',
                'Lancée par',
                'Ce qu’elle a rendu',
            ],
        )
        # Les quatre relèves font une ligne, à l'heure de la dernière,
        # même si d'autres tâches sont passées entre elles.
        self.assertEqual(
            [ligne['cellules'] for ligne in fiche['tableau']['lignes']],
            [
                [
                    '2026-11-21T21:08:02+00:00',
                    'Relever les messages · 4 fois',
                    'Terminée',
                    '—',
                    'déclencheur',
                    '—',
                ],
                [
                    '2026-11-21T21:07:02+00:00',
                    'Lire un flux',
                    'Échouée',
                    '2 s',
                    'déclencheur',
                    'HTTP 404',
                ],
                [
                    '2026-11-21T21:06:02+00:00',
                    'Lire un flux · 2 fois',
                    'Échouée',
                    '—',
                    'déclencheur',
                    'HTTP 429',
                ],
                [
                    '2026-11-21T21:04:40+00:00',
                    'Fouiller un réseau',
                    'Terminée',
                    '40 s',
                    'bouton',
                    'Les avis sont partagés : deux pour, un contre.',
                ],
            ],
        )
        lignes = fiche['tableau']['lignes']
        # Un clic ouvre la fiche de la tâche (la plus récente d'un groupe).
        self.assertEqual(
            (lignes[0]['type'], lignes[0]['id']), ('task', derniere)
        )
        self.assertEqual(lignes[3]['id'], fouille)
        self.assertEqual(
            [(c['k'], c['v']) for c in fiche['champs']],
            [
                ('Terminées', '5'),
                ('Échouées', '3'),
                ('Annulées', '0'),
                ('Depuis', '2026-11-21T21:01:02+00:00'),
            ],
        )

    def test_la_fiche_des_files_y_mene_et_en_revient(self) -> None:
        self._finie('relever')
        finies = project_objet(self.conn, 'file', 'finies')
        files = project_objet(self.conn, 'file', 'canon')
        assert finies is not None and files is not None
        self.assertEqual(finies['titre'], 'Tâches finies')
        self.assertEqual(files['titre'], 'Files de tâches')
        self.assertEqual(
            [lien['id'] for lien in files['cadres'][0]['liens']], ['finies']
        )
        self.assertEqual(
            [lien['id'] for lien in finies['cadres'][0]['liens']], ['canon']
        )

    def test_une_reponse_ou_un_bouton_garde_sa_ligne(self) -> None:
        """Chaque réponse d'un modèle est à lire, et ce qu'on a lancé
        soi-même se retrouve : ces tâches ne se regroupent jamais."""
        for _ in range(2):
            self._finie('fouiller', reponse={'resume': 'Rien de neuf.'})
        for _ in range(2):
            self._finie('relever', origine=('button', 'bouton_x:2026'))
        lignes = project_taches_finies(self.conn)['tableau']['lignes']
        self.assertEqual(
            [ligne['cellules'][1] for ligne in lignes],
            [
                'Relever les messages',
                'Relever les messages',
                'Fouiller un réseau',
                'Fouiller un réseau',
            ],
        )

    def test_ce_qui_a_lance_une_tache(self) -> None:
        self.conn.execute(
            'INSERT INTO links(id, title, from_invocation_id,'
            " to_invocation_id, mode) VALUES('l1', 'Le compte est prêt',"
            " 'relever', 'fouiller', 'on_finish')"
        )
        origines = Origines(self.conn)
        self.assertEqual(
            [
                origines.long(origine, ref)
                for origine, ref in (
                    ('button', 'bouton_fouiller:2026-11-21T21:01'),
                    ('trigger', 'releve:2026-11-21T21:02:email'),
                    ('link', 'l1'),
                    ('', 'reparti:t_1'),
                    ('trigger', 'inconnu:1'),
                    ('', ''),
                )
            ],
            [
                'le bouton « Fouiller un réseau »',
                'le déclencheur « Relever chaque canal »',
                'la tâche d’avant, par le lien « Le compte est prêt »',
                '« Repartir d’ici », sur une autre tâche',
                'le déclencheur « inconnu »',
                '—',
            ],
        )
        self.assertEqual(
            origines.court('', 'reparti:t_1'), '« Repartir d’ici »'
        )
        self.assertEqual(origines.court('link', 'l1'), 'tâche d’avant')

    def test_la_duree_et_l_extrait(self) -> None:
        debut = '2026-11-21T21:00:00+00:00'
        self.assertEqual(
            [
                duree(debut, fin)
                for fin in (
                    '2026-11-21T21:00:00.400000+00:00',
                    '2026-11-21T21:00:24+00:00',
                    '2026-11-21T21:03:26+00:00',
                    '2026-11-21T22:05:00+00:00',
                    '',
                )
            ],
            ['moins d’une seconde', '24 s', '3 min 26 s', '1 h 05 min', ''],
        )
        self.assertEqual(
            extrait(json.dumps(REPONSE)),
            'Les avis sont partagés : deux pour, un contre.',
        )
        long = extrait(json.dumps({'compte_rendu': 'mot ' * 100}))
        self.assertEqual(len(long), 200)
        self.assertTrue(long.endswith('…'))
        self.assertEqual(extrait('pas du json'), '')
        self.assertEqual(extrait('[1, 2]'), '')


class ReponseEnClairTests(unittest.TestCase):
    def test_un_champ_par_ligne_et_un_cadre_par_liste(self) -> None:
        cadres = cadres_reponse(
            json.dumps(
                {
                    **REPONSE,
                    'cree': True,
                    'vide': '',
                    'mots': ['un', 'deux'],
                    'plan': {'prix_eur': 9, 'pages': ['a', 'b']},
                    'rien': [],
                },
                ensure_ascii=False,
            )
        )
        self.assertEqual(
            cadres,
            [
                {
                    'titre': 'Ce que le modèle a rendu',
                    'champs': [
                        {'k': 'Etat', 'v': 'connecte'},
                        {
                            'k': 'Resume',
                            'v': 'Les avis sont partagés : deux pour, un'
                            ' contre.',
                        },
                        {'k': 'Cree', 'v': 'oui'},
                        {'k': 'Vide', 'v': '—'},
                        {'k': 'Mots', 'v': 'un\ndeux'},
                        {'k': 'Rien', 'v': '[]'},
                    ],
                },
                {
                    'titre': 'Trouvailles (2)',
                    'groupes': [
                        [
                            {'k': 'Url', 'v': 'https://site.example/fil/1'},
                            {'k': 'Titre', 'v': 'Un premier fil'},
                        ],
                        [
                            {'k': 'Url', 'v': 'https://site.example/fil/2'},
                            {'k': 'Titre', 'v': 'Un second fil'},
                        ],
                    ],
                },
                {
                    'titre': 'Ce que le modèle a rendu : Plan',
                    'champs': [
                        {'k': 'Prix eur', 'v': '9'},
                        {'k': 'Pages', 'v': '["a", "b"]'},
                    ],
                },
            ],
        )

    def test_une_reponse_qui_n_est_pas_un_objet_reste_lisible(self) -> None:
        self.assertEqual(cadres_reponse(''), [])
        self.assertEqual(
            cadres_reponse('pas du json'),
            [{'titre': 'Ce que le modèle a rendu', 'pre': 'pas du json'}],
        )
        self.assertEqual(
            cadres_reponse('["a"]'),
            [{'titre': 'Ce que le modèle a rendu', 'pre': '["a"]'}],
        )

    def test_la_fiche_garde_le_json_exact_dans_la_preuve(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        invocations(conn, ('fouiller', 'Fouiller', 'prospection_light'))
        ident = tache(conn, 'fouiller', {'n': '1'}, key='k1', status='done')
        conn.execute(
            'UPDATE tasks SET answer_json=? WHERE id=?',
            (json.dumps(REPONSE), ident),
        )
        conn.row_factory = sqlite3.Row
        fiche = fiche_tache(conn, ident)
        assert fiche is not None
        self.assertEqual(
            [c['titre'] for c in fiche['cadres']],
            ['Ce que le modèle a rendu', 'Trouvailles (2)'],
        )
        self.assertEqual(json.loads(fiche['preuve'])['reponse'], REPONSE)


if __name__ == '__main__':
    unittest.main()
