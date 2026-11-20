#!/usr/bin/env python3
"""Confier une mission à une autre invocation (lot 13, décision Q104).

Un vrai Chromium tient lieu du vrai Chrome, un petit site local tient lieu
d'un réseau social, et le modèle est un faux. Le reste est réel : le
pipeline, l'interpréteur, les capacités, la base.

Scénarios :
- « Explorer le web » confie une fouille de Reddit à « Fouiller un
  réseau » : la seconde navigue avec le compte de Serge et lui rend ses
  discussions, dans la même tâche ; la page est gardée comme une autre.
  Le modèle n'écrit que sa demande : ni l'invocation ni le compte ne lui
  sont proposés. Une fouille de trop est refusée, un réseau sans compte
  aussi, sans appel au modèle ;
- le bouton « Fouiller un réseau » lance la même invocation, seule ;
- une mission ne confie pas de mission.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge import missions, web_accounts  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.triggers import fire_button  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.sandbox import sessions  # noqa: E402
from tests.mc_server_case import browser_ok  # noqa: E402
from tests.test_navigateur import _chrome, _site, appel  # noqa: E402

DEMANDE = 'ce que disent les artisans de leurs devis'
TROUVAILLE = {
    'titre': 'Mes devis me prennent mes soirées',
    'extrait': '« Je passe deux heures par devis, qui a un outil simple ? »',
}


def _noms(tools: list[dict[str, Any]] | None) -> set[str]:
    return {t['function']['name'] for t in tools or []}


class FauxModeles:
    """Deux modèles en un : celui qui explore le web confie une fouille,
    celui qui fouille ouvre une page et rend une discussion. On les
    reconnaît à leurs outils."""

    def __init__(self, site: str) -> None:
        self.site = site
        self.outils_explorateur: list[dict[str, Any]] = []
        self.resultats: list[str] = []
        self.fouilles = 0

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        recus = [m for m in messages if m['role'] == 'tool']
        if 'vrai_chrome_agir' in _noms(tools) or self._fouille(messages):
            return self._fouiller(recus)
        return self._explorer(recus, tools)

    def _fouille(self, messages: list[dict[str, Any]]) -> bool:
        return 'Tu fouilles un réseau social' in str(messages[0]['content'])

    def _fouiller(self, recus: list[dict[str, Any]]) -> ChatResult:
        if not recus:
            self.fouilles += 1
            calls = (
                appel(
                    'f1',
                    'vrai_chrome_agir',
                    action='ouvrir',
                    text=f'{self.site}/autre',
                ),
            )
            return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)
        reponse = {
            'trouvailles': [{'url': f'{self.site}/autre', **TROUVAILLE}],
            'resume': 'Les artisans se plaignent du temps passé aux devis.',
        }
        return ChatResult(json.dumps(reponse), 10, 10, 'faux', 1)

    def _explorer(self, recus: list[dict[str, Any]], tools: Any) -> ChatResult:
        if not recus:
            self.outils_explorateur = tools or []
            calls = (
                appel('a', 'fouiller_reddit', mission=DEMANDE),
                appel('b', 'fouiller_reddit', mission='encore'),
                appel('c', 'fouiller_instagram', mission=DEMANDE),
            )
            return ChatResult('', 10, 10, 'faux', 1, tool_calls=calls)
        self.resultats = [str(m['content']) for m in recus]
        trouvee = json.loads(self.resultats[0])['reponse']['trouvailles'][0]
        reponse = {
            'pages': [
                {
                    'url': trouvee['url'],
                    'titre': trouvee['titre'],
                    'apercu': trouvee['extrait'],
                }
            ],
            'flux': [],
        }
        return ChatResult(json.dumps(reponse), 10, 10, 'faux', 1)


@unittest.skipUnless(browser_ok(), 'pas de Chromium pour ce test')
class MissionTests(unittest.TestCase):
    def setUp(self) -> None:
        from cryptography.fernet import Fernet

        dossier = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(dossier.cleanup)
        self.dossier = Path(dossier.name)
        secrets = self.dossier / 'config/secrets'
        secrets.mkdir(parents=True)
        (secrets / 'credential-vault.key').write_bytes(Fernet.generate_key())
        instance = self.dossier / 'instance.toml'
        instance.write_text(
            f'[paths]\nconfig_root = "{self.dossier / "config"}"\n'
        )
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_SYSTEM_ROOT': str(self.dossier),
                'SERGE_INSTANCE_FILE': str(instance),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        set_heartbeat(self.conn, True)
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at')"
        )
        proc, endpoint = _chrome(self.dossier)
        self.addCleanup(proc.wait, 10)
        self.addCleanup(proc.terminate)
        point = mock.patch.object(sessions, '_endpoint', return_value=endpoint)
        point.start()
        self.addCleanup(point.stop)
        self.addCleanup(sessions.close_sessions)
        serveur, self.site = _site()
        self.addCleanup(serveur.shutdown)
        web_accounts.register(self.conn, 'reddit', self.site, 'serge-ia', 'x')
        self.conn.commit()
        self.modeles = FauxModeles(self.site)

    def _faire(self, attendue: str) -> str:
        tache = process_one(self.conn, 'works', caller=self.modeles)
        invocation, statut, erreur = self.conn.execute(
            'SELECT invocation_id, status, last_error FROM tasks WHERE id=?',
            (tache,),
        ).fetchone()
        self.assertEqual((invocation, statut, erreur), (attendue, 'done', ''))
        return str(tache)

    def test_explorer_le_web_confie_une_fouille(self) -> None:
        self.assertIsNotNone(
            fire_button(self.conn, 'lancer_cycle', {'guide': 'les artisans'})
        )
        self.conn.commit()
        self._faire('ouvrir_cycle')
        tache = self._faire('explorer_web')
        # Le modèle n'écrit que sa demande.
        fouiller = next(
            o['function']['parameters']
            for o in self.modeles.outils_explorateur
            if o['function']['name'] == 'fouiller_reddit'
        )
        self.assertEqual(list(fouiller['properties']), ['mission'])
        # La discussion rendue est gardée comme une page.
        self.assertEqual(
            tuple(
                self.conn.execute(
                    'SELECT url, title, excerpt, source FROM listen_docs'
                ).fetchone()
            ),
            (
                f'{self.site}/autre',
                TROUVAILLE['titre'],
                TROUVAILLE['extrait'],
                'web',
            ),
        )
        # Une fouille de trop, puis un réseau sans compte : refusés sans
        # lancer de modèle.
        encore, sans_compte = self.modeles.resultats[1:]
        self.assertIn('limite', encore)
        self.assertIn('pas de compte « instagram » en service', sans_compte)
        self.assertEqual(self.modeles.fouilles, 1)
        # Tout s'est passé dans la tâche de l'exploratrice : ses appels au
        # modèle et ceux de la fouille y sont comptés.
        self.assertEqual(
            dict(
                self.conn.execute(
                    'SELECT point, COUNT(*) FROM llm_usage WHERE task_id=?'
                    ' GROUP BY point',
                    (tache,),
                ).fetchall()
            ),
            {'explorer_web': 2, 'fouiller_reseau': 2},
        )
        # La fouille a navigué avec le compte : une action comptée, et le
        # compte est rendu, sa session gardée.
        self.assertEqual(web_accounts.actions_today(self.conn, 'reddit'), 1)
        pris, garde = self.conn.execute(
            'SELECT used_by, session_enc FROM web_accounts'
        ).fetchone()
        self.assertEqual(pris, '')
        self.assertTrue(garde)

    def test_le_bouton_fouille_seul(self) -> None:
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_fouiller_reseau',
                {
                    'nom du compte (reddit, instagram, x…)': 'reddit',
                    'ce que tu cherches (« ce que les gens disent des'
                    ' calculatrices en ligne »)': DEMANDE,
                },
            )
        )
        self.conn.commit()
        tache = self._faire('fouiller_reseau')
        rendu = json.loads(
            self.conn.execute(
                'SELECT answer_json FROM tasks WHERE id=?', (tache,)
            ).fetchone()[0]
        )
        self.assertEqual(rendu['trouvailles'][0]['titre'], TROUVAILLE['titre'])

    def test_une_mission_ne_confie_pas_de_mission(self) -> None:
        refus: list[dict[str, Any]] = []

        def gourmande(conn: Any, invocation: str, task_id: str, params: Any):
            refus.append(
                missions.mission(
                    conn,
                    '',
                    {'invocation': invocation, 'mission': 'encore plus'},
                    'x',
                )
            )
            return {}

        vraie = list(missions._RUNNER)
        self.addCleanup(missions.register, vraie[0])
        missions.register(gourmande)
        dehors = missions.mission(
            self.conn,
            '',
            {'invocation': 'fouiller_reseau', 'mission': DEMANDE},
            'x',
        )
        self.assertTrue(dehors['ok'])
        self.assertEqual(refus[0]['ok'], False)
        self.assertIn('ne confie pas de mission', refus[0]['detail'])
        # Une demande vide, une invocation inconnue : refusées aussi.
        for args, raison in (
            ({'invocation': 'fouiller_reseau', 'mission': ' '}, 'écris ta'),
            ({'invocation': 'nulle_part', 'mission': 'x'}, 'n’existe pas'),
        ):
            self.assertIn(
                raison, missions.mission(self.conn, '', args, 'x')['detail']
            )


def tearDownModule() -> None:
    # Le Playwright des sessions tourne dans ce fil : arrêté, les tests
    # suivants peuvent lancer le leur.
    if 'pw' in sessions._PLAYWRIGHT:
        sessions._PLAYWRIGHT.pop('pw').stop()
    sessions._ETAT.browser = sessions._ETAT_VRAI.browser = None


if __name__ == '__main__':
    unittest.main()
