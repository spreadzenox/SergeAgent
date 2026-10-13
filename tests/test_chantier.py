#!/usr/bin/env python3
"""Le chantier de bout en bout (lot 10, PR 1, décision Q91).

Docker et le modèle sont des faux (``tests/fake_docker.py``) ; le pipeline
en base, l'interpréteur, les outils et le journal sont réels.

Scénarios :
- « Essayer le chantier » : le modèle écrit un programme, le lance, lit et
  modifie un fichier ; le chantier d'essai est créé avec les chiffres de
  son profil (page Policy), les sorties reviennent au modèle, chaque
  commande est au journal, le compte rendu est écrit ;
- un seul chantier tourne : en allumer un éteint l'autre, et il se
  rallume ensuite avec ses fichiers ;
- un chantier qui dépasse son disque permis est arrêté, avec la raison ;
- Docker qui refuse : l'outil le dit au modèle, et la raison de Docker est
  au journal du service ;
- une modification dont le passage manque, ou revient deux fois, ne
  change rien.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.interpreter.flow import fire_button  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tools import run_capability  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.mc.proj_taches import fiche_tache  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402

ESSAI = {
    'venture_id': 'essai',
    'deliverable': 'chantier',
    'profile': 'chantier',
}


def faux_docker(dossier: Path) -> dict[str, str]:
    """Met un faux ``docker`` en tête du PATH ; rend l'environnement."""
    bin_dir = dossier / 'bin'
    bin_dir.mkdir()
    script = bin_dir / 'docker'
    script.write_text(
        '#!/bin/sh\n'
        f'exec "{sys.executable}" "{ROOT / "tests/fake_docker.py"}" "$@"\n',
        encoding='utf-8',
    )
    script.chmod(0o755)
    return {
        'PATH': f'{bin_dir}{os.pathsep}{os.environ.get("PATH", "")}',
        'FAKE_DOCKER_ROOT': str(dossier / 'docker'),
        'DOCKER_HOST': 'unix:///faux.sock',
    }


def appel(ident: str, nom: str, **args: Any) -> ToolCall:
    return ToolCall(ident, nom, json.dumps(args))


class FauxModele:
    """Écrit un programme, le lance, le modifie, le relit, puis répond."""

    def __init__(self) -> None:
        self.messages: list[list[dict[str, Any]]] = []

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        self.messages.append([dict(m) for m in messages])
        tour = len(self.messages)
        if tour == 1:
            calls = (
                appel(
                    'a',
                    'chantier_ecrire',
                    path='app/hello.py',
                    content='print("bonjour")\n',
                ),
                appel(
                    'b', 'chantier_commande', command='python3 app/hello.py'
                ),
            )
            return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)
        if tour == 2:
            calls = (
                appel(
                    'c',
                    'chantier_modifier',
                    path='app/hello.py',
                    old='bonjour',
                    new='bonsoir',
                ),
                appel('d', 'chantier_lire', path='app/hello.py'),
            )
            return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)
        reponse = {
            'marche': 'oui',
            'compte_rendu': 'Le programme dit bonsoir.',
        }
        return ChatResult(json.dumps(reponse), 10, 10, 'faux', 1)


class ChantierTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        env = {
            'SERGE_SYSTEM_ROOT': str(self.dossier),
            **faux_docker(self.dossier),
        }
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _appels_docker(self) -> list[list[str]]:
        log = self.dossier / 'docker/calls.jsonl'
        return [json.loads(line) for line in log.read_text().splitlines()]

    def _outil(self, capacite: str, **args: Any) -> dict[str, Any]:
        return run_capability(
            self.conn, capacite, '', {**ESSAI, **args}, 'essai'
        )

    def test_essayer_le_chantier(self) -> None:
        modele = FauxModele()
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_essayer_chantier',
                {'mission': 'Écris un programme qui dit bonjour.'},
            )
        )
        self.conn.commit()
        process_one(self.conn, 'works', caller=modele)
        statut, erreur = self.conn.execute(
            'SELECT status, last_error FROM tasks'
            " WHERE invocation_id='essayer_chantier'"
        ).fetchone()
        self.assertEqual((statut, erreur), ('done', ''))
        # Le programme a tourné et sa sortie est revenue au modèle.
        sorties = [
            json.loads(m['content'])
            for m in modele.messages[1]
            if m.get('role') == 'tool'
        ]
        self.assertEqual(sorties[0]['ok'], True)
        self.assertEqual(sorties[1]['exit_code'], 0)
        self.assertIn('bonjour', sorties[1]['output'])
        relu = json.loads(modele.messages[2][-1]['content'])
        self.assertEqual(relu['text'], 'print("bonsoir")')
        # Le chantier d'essai, avec les chiffres de son profil.
        run = next(a for a in self._appels_docker() if a[0] == 'run')
        self.assertEqual(run[run.index('--memory') + 1], '4096m')
        self.assertEqual(run[run.index('--cpus') + 1], '2')
        self.assertIn('node:22-bookworm', run)
        # Le réseau des chantiers et du navigateur (PR 2).
        self.assertEqual(run[run.index('--network') + 1], 'serge-chantiers')
        self.assertEqual(
            tuple(
                self.conn.execute(
                    'SELECT id, status, container FROM sandboxes'
                ).fetchone()
            ),
            ('essai-chantier', 'running', 'serge-chantier-essai-chantier'),
        )
        commandes = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type='sandbox.command'"
        ).fetchone()[0]
        self.assertEqual(commandes, 1)
        # Le compte rendu se lit sur la fiche de la tâche.
        tache = self.conn.execute(
            "SELECT id FROM tasks WHERE invocation_id='essayer_chantier'"
        ).fetchone()[0]
        fiche = fiche_tache(self.conn, tache)
        assert fiche is not None
        self.assertEqual(
            fiche['cadres'][0]['titre'], 'Ce que le modèle a rendu'
        )
        self.assertIn('Le programme dit bonsoir.', fiche['cadres'][0]['pre'])

    def test_un_seul_chantier_tourne(self) -> None:
        self._outil('sandbox_write_file', path='a.txt', content='A')
        autre = {'venture_id': 'ven_2', 'deliverable': 'poc'}
        self._outil('sandbox_command', command='true', **autre)
        etats = dict(
            self.conn.execute('SELECT id, status FROM sandboxes').fetchall()
        )
        self.assertEqual(
            etats, {'essai-chantier': 'stopped', 'ven_2-poc': 'running'}
        )
        # Rallumé, le chantier d'essai retrouve son fichier.
        relu = self._outil('sandbox_read_file', path='a.txt')
        self.assertEqual(relu['text'], 'A')
        self.assertIn(
            ['start', 'serge-chantier-essai-chantier'], self._appels_docker()
        )

    def test_un_ancien_chantier_rejoint_le_reseau(self) -> None:
        """Un chantier créé sans le réseau des chantiers (avant la PR 2) y
        est branché : le navigateur doit pouvoir l'ouvrir."""
        self._outil('sandbox_command', command='true')
        etat = self.dossier / (
            'docker/containers/serge-chantier-essai-chantier/state.json'
        )
        data = json.loads(etat.read_text())
        data['networks'] = []
        etat.write_text(json.dumps(data))
        self._outil('sandbox_command', command='true')
        self.assertIn(
            [
                'network',
                'connect',
                'serge-chantiers',
                'serge-chantier-essai-chantier',
            ],
            self._appels_docker(),
        )

    def test_un_chantier_trop_gros_est_arrete(self) -> None:
        self.assertEqual(
            set_setting(self.conn, 'sandbox.chantier.disk_mb', 1024, 'test'),
            '',
        )
        with (
            mock.patch.dict(os.environ, {'FAKE_DOCKER_DU_MB': '5000'}),
            redirect_stderr(io.StringIO()) as journal,
        ):
            resultat = self._outil('sandbox_command', command='true')
        self.assertEqual(resultat['code'], 'disque_plein')
        self.assertIn('5000 Mo', resultat['detail'])
        statut, erreur = self.conn.execute(
            'SELECT status, last_error FROM sandboxes'
        ).fetchone()
        self.assertEqual(statut, 'stopped')
        self.assertIn('plus que les 1024 permis', erreur)
        self.assertIn('arrêté', journal.getvalue())

    def test_docker_qui_refuse_est_au_journal(self) -> None:
        modele = FauxModele()
        fire_button(self.conn, 'bouton_essayer_chantier', {'mission': 'x'})
        self.conn.commit()
        with (
            mock.patch.dict(os.environ, {'FAKE_DOCKER_FAIL': 'run'}),
            redirect_stderr(io.StringIO()) as journal,
        ):
            process_one(self.conn, 'works', caller=modele)
        sortie = json.loads(modele.messages[1][-1]['content'])
        self.assertEqual(sortie['code'], 'echec')
        self.assertIn('pull access denied', sortie['detail'])
        self.assertIn('bac à sable : docker run', journal.getvalue())
        self.assertIn('pull access denied', journal.getvalue())

    def test_une_modification_ambigue_ne_change_rien(self) -> None:
        self._outil('sandbox_write_file', path='b.txt', content='x x')
        for passage, code in (
            ('x', 'passage_multiple'),
            ('y', 'passage_introuvable'),
        ):
            resultat = self._outil(
                'sandbox_edit_file', path='b.txt', old=passage, new='z'
            )
            self.assertEqual(resultat['code'], code)
        self.assertEqual(
            self._outil('sandbox_read_file', path='b.txt')['text'], 'x x'
        )


if __name__ == '__main__':
    unittest.main()
