#!/usr/bin/env python3
"""Installer les dépendances du serveur à chaque déploiement (lot 10).

Les services tournent avec un seul Python, celui des units. Il lui faut
les paquets de ``[project] dependencies`` dans ``pyproject.toml`` (PyYAML,
playwright…) : chaque déploiement les installe, et pip ne fait rien pour
ceux qui sont déjà là.

Si ce Python est celui du système, pip refuse d'y installer quoi que ce
soit (Debian : « externally-managed-environment »). Le déploiement crée
alors un environnement à Serge, ``~/.local/share/serge/venv``, qui voit
aussi les paquets du système (``--system-site-packages``), y installe les
dépendances, et les units passent à son Python. Exemple : le premier
déploiement après le lot 10 crée l'environnement et y installe playwright ;
les suivants le retrouvent.
"""

from __future__ import annotations

import subprocess
import tomllib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from kit.builder.guards import BuilderError

Runner = Callable[..., subprocess.CompletedProcess[str]]

VENV = Path('.local/share/serge/venv')


def _run(runner: Runner, argv: Sequence[str]) -> subprocess.CompletedProcess:
    return runner(list(argv), check=False, capture_output=True, text=True)


def _fin(done: subprocess.CompletedProcess) -> str:
    return f'{done.stdout or ""}{done.stderr or ""}'.strip()[-500:]


def dependances(pyproject: Path) -> list[str]:
    """Les paquets du serveur : ``[project] dependencies``."""
    data = tomllib.loads(pyproject.read_text(encoding='utf-8'))
    return [
        str(d) for d in (data.get('project') or {}).get('dependencies', [])
    ]


def _est_un_venv(python: str, runner: Runner) -> bool:
    done = _run(
        runner,
        [
            python,
            '-c',
            'import sys; print(int(sys.prefix != sys.base_prefix))',
        ],
    )
    return done.returncode == 0 and (done.stdout or '').strip() == '1'


def installer_dependances(
    *, python: str, pyproject: Path, home: Path, runner: Runner
) -> dict[str, Any]:
    """Installe les dépendances ; rend le Python que les units utiliseront.

    Raises:
        BuilderError: L'environnement ne se crée pas, ou pip échoue ; le
            déploiement s'arrête avant de redémarrer quoi que ce soit.
    """
    paquets = dependances(pyproject)
    cible, cree = python, False
    if not _est_un_venv(python, runner):
        venv = home / VENV
        cible = str(venv / 'bin/python')
        if not Path(cible).exists():
            done = _run(
                runner,
                [python, '-m', 'venv', '--system-site-packages', str(venv)],
            )
            if done.returncode != 0:
                raise BuilderError(
                    f'environnement Python non créé ({venv}) : {_fin(done)}'
                    ' — sur Debian, installer python3-venv'
                )
            cree = True
    if paquets:
        done = _run(
            runner,
            [
                cible,
                '-m',
                'pip',
                'install',
                '--quiet',
                '--disable-pip-version-check',
                *paquets,
            ],
        )
        if done.returncode != 0:
            raise BuilderError(f'dépendances non installées : {_fin(done)}')
    return {'python': cible, 'venv_cree': cree, 'paquets': paquets}
