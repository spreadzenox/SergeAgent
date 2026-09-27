#!/usr/bin/env python3
"""La règle : le code n'est qu'un interpréteur de la base.

Le nom d'une invocation n'apparaît que dans `config/pipeline.yaml`, le
fichier qui remplit une nouvelle instance. Ce test échoue si l'un de ces
noms apparaît dans le code (`serge/`, `scripts/`, `kit/`) : il manque alors
une capacité générale ou un réglage en base. `pas_encore_branche/` et
`tests/` ne sont pas regardés.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.policy import read_yaml_file  # noqa: E402

DOSSIERS = ('serge', 'scripts', 'kit', 'bin')
SUFFIXES = {'.py', '.js', '.html', '.in', '.sh', ''}


class RegleTests(unittest.TestCase):
    def test_aucun_nom_d_invocation_dans_le_code(self) -> None:
        pipeline = read_yaml_file(ROOT / 'config/pipeline.yaml')
        noms = [str(inv['id']) for inv in pipeline.get('invocations') or []]
        self.assertTrue(noms)
        motif = re.compile(r'\b(' + '|'.join(map(re.escape, noms)) + r')\b')
        trouves = []
        for dossier in DOSSIERS:
            for path in sorted((ROOT / dossier).rglob('*')):
                if not path.is_file() or path.suffix not in SUFFIXES:
                    continue
                texte = path.read_text(encoding='utf-8', errors='ignore')
                for numero, ligne in enumerate(texte.splitlines(), 1):
                    if motif.search(ligne):
                        trouves.append(
                            f'{path.relative_to(ROOT)}:{numero}: {ligne.strip()}'
                        )
        self.assertEqual(trouves, [], 'code propre à une invocation')


if __name__ == '__main__':
    unittest.main()
