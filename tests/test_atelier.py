#!/usr/bin/env python3
"""L'atelier : voir, garder et faire dire dans un chantier (décision Q121).

Docker est un faux (``tests/fake_docker.py``) et OpenRouter aussi ; la
base, les réglages, le journal et les fiches sont réels.

Scénarios :
- le profil « video » nomme une image maison : le premier chantier la
  construit depuis ``serge/sandbox/image_video/``, le suivant la retrouve ;
- une image du chantier revient au modèle comme une image ; un fichier qui
  n'en est pas une, ou trop lourd, est refusé avec la raison ;
- un fichier gardé sort du chantier, est rangé sous ``files/`` et a sa
  fiche ; Mission Control le sert ;
- « Dire un texte » écrit le son dans le chantier avec la voix réglée, et
  compte sa dépense ; un refus d'OpenRouter est rendu au modèle et noté au
  journal, sans rien écrire.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.interpreter.tools import run_capability  # noqa: E402
from serge.paths import files_root  # noqa: E402
from serge.sandbox import atelier  # noqa: E402
from serge.sandbox.images import empreinte, image_du_profil  # noqa: E402
from tests.test_chantier import faux_docker  # noqa: E402

VIDEO = {'venture_id': 'essai', 'deliverable': 'videos', 'profile': 'video'}
PNG = bytes.fromhex('89504e470d0a1a0a') + b'\x00' * 64


class _Reponse:
    def __init__(self, corps: bytes) -> None:
        self._corps = corps

    def read(self) -> bytes:
        return self._corps

    def __enter__(self) -> _Reponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None


class AtelierTests(unittest.TestCase):
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
        self.conn.commit()

    def _appels_docker(self) -> list[list[str]]:
        log = self.dossier / 'docker/calls.jsonl'
        return [json.loads(line) for line in log.read_text().splitlines()]

    def _outil(self, capacite: str, **args: Any) -> dict[str, Any]:
        return run_capability(
            self.conn, capacite, '', {**VIDEO, **args}, 'essai'
        )

    def _volume(self) -> Path:
        return self.dossier / 'docker/volumes/serge-chantier-essai-videos'

    def test_le_profil_video_construit_son_image_une_fois(self) -> None:
        dossier = ROOT / 'serge/sandbox/image_video'
        attendue = f'serge-atelier-video:{empreinte(dossier)}'
        fait = self._outil('sandbox_command', command='echo pret')
        self.assertTrue(fait['ok'], fait)
        appels = self._appels_docker()
        constructions = [a for a in appels if a[:1] == ['build']]
        self.assertEqual(
            constructions, [['build', '-t', attendue, str(dossier)]]
        )
        lancement = next(a for a in appels if a[:1] == ['run'])
        self.assertIn(attendue, lancement)
        # Les chiffres du profil « video » de la page Policy.
        self.assertEqual(lancement[lancement.index('--cpus') + 1], '3')
        self.assertEqual(lancement[lancement.index('--memory') + 1], '6144m')
        # La seconde fois, l'image est là : rien n'est reconstruit.
        self.assertEqual(image_du_profil('serge-atelier-video'), attendue)
        encore = [a for a in self._appels_docker() if a[:1] == ['build']]
        self.assertEqual(len(encore), 1)
        # Une image publique passe telle quelle.
        self.assertEqual(
            image_du_profil('node:22-bookworm'), 'node:22-bookworm'
        )

    def test_une_image_du_chantier_revient_comme_une_image(self) -> None:
        self._outil('sandbox_command', command='mkdir -p revue')
        (self._volume() / 'revue/planche.png').write_bytes(PNG)
        vue = self._outil('sandbox_image', path='revue/planche.png')
        self.assertTrue(vue['ok'], vue)
        self.assertTrue(
            vue['image'].startswith('data:image/png;base64,iVBORw0KGgo')
        )
        (self._volume() / 'notes.txt').write_text('bonjour')
        refus = self._outil('sandbox_image', path='notes.txt')
        self.assertEqual(refus['code'], 'pas_une_image')
        absente = self._outil('sandbox_image', path='revue/absente.png')
        self.assertEqual(absente['code'], 'fichier_illisible')
        (self._volume() / 'revue/lourde.png').write_bytes(
            b'x' * (atelier.MAX_IMAGE + 10)
        )
        lourde = self._outil('sandbox_image', path='revue/lourde.png')
        self.assertEqual(lourde['code'], 'image_trop_lourde')

    def test_un_fichier_garde_sort_du_chantier_avec_sa_fiche(self) -> None:
        self._outil('sandbox_command', command='mkdir -p v1/sortie')
        (self._volume() / 'v1/sortie/video.mp4').write_bytes(
            b'\x00\x01video' * 400
        )
        garde = self._outil(
            'sandbox_keep_file',
            path='v1/sortie/video.mp4',
            kind='video',
            task_id='tsk_1',
        )
        self.assertTrue(garde['ok'], garde)
        fiche = self.conn.execute(
            'SELECT venture_id, kind, path_or_url, size_bytes, task_id FROM artifacts WHERE id=?',
            (garde['artifact'],),
        ).fetchone()
        self.assertEqual(fiche[0], 'essai')
        self.assertEqual(fiche[1], 'video')
        chemin = Path(fiche[2])
        self.assertTrue(chemin.is_relative_to(files_root()))
        self.assertEqual(chemin.name, 'tsk_1-video.mp4')
        self.assertEqual(chemin.read_bytes(), b'\x00\x01video' * 400)
        self.assertEqual((fiche[3], fiche[4]), (2800, 'tsk_1'))
        journal = self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE type='sandbox.file_kept'"
        ).fetchone()[0]
        self.assertEqual(journal, 1)
        vide = self._outil('sandbox_keep_file', path='v1/sortie/absent.mp4')
        self.assertEqual(vide['code'], 'fichier_illisible')

    def test_dire_un_texte_ecrit_le_son_et_compte_la_depense(self) -> None:
        (self.dossier / 'config/secrets').mkdir(parents=True, exist_ok=True)
        vus: list[dict[str, Any]] = []
        son = b'ID3' + b'\x07' * 4000

        def faux(requete: Any, timeout: float = 0) -> _Reponse:
            vus.append(
                {
                    'url': requete.full_url,
                    'corps': json.loads(requete.data),
                    'cle': requete.get_header('Authorization'),
                }
            )
            return _Reponse(son)

        with (
            mock.patch.object(
                atelier, 'read_api_key', return_value='cle-essai'
            ),
            mock.patch.object(atelier.urllib.request, 'urlopen', faux),
        ):
            dit = self._outil(
                'speech',
                text='Un coach pour refaire ton CV : cent cinquante euros.',
                path='v1/assets/voix.mp3',
                task_id='tsk_2',
            )
        self.assertTrue(dit['ok'], dit)
        self.assertEqual(
            (self._volume() / 'v1/assets/voix.mp3').read_bytes(), son
        )
        self.assertEqual(
            vus[0]['url'], 'https://openrouter.ai/api/v1/audio/speech'
        )
        self.assertEqual(vus[0]['corps']['model'], 'elevenlabs/eleven-v4')
        self.assertEqual(vus[0]['corps']['voice'], 'brian')
        self.assertEqual(vus[0]['cle'], 'Bearer cle-essai')
        # La clé n'entre jamais dans le conteneur.
        self.assertNotIn('cle-essai', json.dumps(self._appels_docker()))
        cout = self.conn.execute(
            "SELECT cost_usd, task_id FROM llm_usage WHERE tier='voix'"
        ).fetchone()
        self.assertAlmostEqual(cout[0], 52 / 1000 * 0.1, places=5)
        self.assertEqual(cout[1], 'tsk_2')

    def test_une_voix_refusee_est_dite_et_notee(self) -> None:
        def refus(requete: Any, timeout: float = 0) -> _Reponse:
            raise urllib.error.HTTPError(
                requete.full_url,
                402,
                'Payment Required',
                None,
                io.BytesIO(b'{"error": "credits"}'),
            )

        with (
            mock.patch.object(
                atelier, 'read_api_key', return_value='cle-essai'
            ),
            mock.patch.object(atelier.urllib.request, 'urlopen', refus),
        ):
            dit = self._outil(
                'speech', text='Bonjour.', path='v1/assets/voix.mp3'
            )
        self.assertFalse(dit['ok'])
        self.assertEqual(dit['code'], 'voix_refusee')
        self.assertIn('402', dit['detail'])
        self.assertFalse((self._volume() / 'v1/assets/voix.mp3').exists())
        raison = self.conn.execute(
            "SELECT payload_json FROM events WHERE type='speech.refused'"
        ).fetchone()
        self.assertIn('402', raison[0])
        self.assertEqual(
            self._outil('speech', text='  ', path='x.mp3')['code'],
            'texte_vide',
        )


if __name__ == '__main__':
    unittest.main()
