#!/usr/bin/env python3
"""Docker, par sa ligne de commande.

Serge parle au Docker rootless de son compte : la commande ``docker``
trouve le service par ``DOCKER_HOST`` ou, à défaut, par la socket du
compte (``$XDG_RUNTIME_DIR/docker.sock``). Une commande refusée lève
``DockerError`` avec ce que Docker a répondu, et la note au journal du
service, lisible sur la page Health (décision Q89) : on ne devine jamais
une panne.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from serge.paths import config_root
from serge.secrets import read_secret_file


class DockerError(RuntimeError):
    """Docker a refusé une commande, ou ne répond pas."""


def journal(texte: str) -> None:
    """Une ligne dans le journal du service (lisible avec journalctl)."""
    print(f'bac à sable : {texte}', file=sys.stderr, flush=True)


def secret_env(spec: str) -> dict[str, str]:
    """Les secrets à donner à un conteneur, d'après leur réglage en base.

    ``spec`` liste des paires ``VARIABLE=fichier`` séparées par des
    virgules, par exemple ``STRIPE_SECRET_KEY=stripe-test.key`` : la
    valeur est lue dans les secrets de l'instance. Elle passe au conteneur
    par l'environnement de la commande ``docker`` (``-e VARIABLE``), jamais
    sur sa ligne de commande.

    Raises:
        DockerError: Un fichier de secret est absent ; la raison est notée
            au journal.
    """
    values: dict[str, str] = {}
    for pair in spec.split(','):
        name, _, fichier = pair.strip().partition('=')
        if not name:
            continue
        valeur = read_secret_file(config_root() / 'secrets' / fichier.strip())
        if not valeur:
            message = f'secret absent sur ce serveur : {fichier.strip()}'
            journal(message)
            raise DockerError(message)
        values[name.strip()] = valeur
    return values


def env_flags(values: Mapping[str, str]) -> list[str]:
    """``-e VARIABLE`` pour chaque secret : Docker lit la valeur dans son
    propre environnement."""
    return [flag for name in values for flag in ('-e', name)]


def _env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env.update(extra or {})
    if not env.get('DOCKER_HOST'):
        runtime = env.get('XDG_RUNTIME_DIR') or f'/run/user/{os.getuid()}'
        socket = Path(runtime) / 'docker.sock'
        if socket.exists():
            env['DOCKER_HOST'] = f'unix://{socket}'
    return env


def _refus_du_service(done: subprocess.CompletedProcess[str]) -> bool:
    """Vrai si c'est Docker qui a refusé, pas la commande lancée dedans.

    Exemple : « Error response from daemon: No such container ». Une
    commande lancée dans un conteneur qui échoue (code 1, « fichier
    introuvable ») n'est pas une panne de Docker.
    """
    texte = f'{done.stderr or ""}{done.stdout or ""}'
    return done.returncode == 125 or 'Error response from daemon' in texte


def docker(
    args: list[str],
    *,
    timeout: float,
    stdin: str | None = None,
    check: bool = True,
    secrets: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Lance ``docker <args>`` et rend son résultat.

    Avec ``check``, tout code de retour non nul est une panne ; sans, seul
    un refus de Docker lui-même en est une (voir ``_refus_du_service``) :
    le résultat d'une commande lancée dans un conteneur est rendu tel quel.
    ``secrets`` : des variables pour ``-e VARIABLE`` (voir ``secret_env``).

    Raises:
        DockerError: Docker absent, muet ou qui refuse ; la raison est
            notée au journal.
    """
    binary = shutil.which('docker')
    if binary is None:
        message = 'docker absent de ce serveur'
        journal(message)
        raise DockerError(message)
    try:
        done = subprocess.run(
            [binary, *args],
            input=stdin,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            env=_env(secrets),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        message = f'docker {args[0]} : pas de réponse en {timeout:.0f} s'
        journal(message)
        raise DockerError(message) from exc
    except OSError as exc:
        message = f'docker {args[0]} : {exc}'
        journal(message)
        raise DockerError(message) from exc
    if (check and done.returncode != 0) or _refus_du_service(done):
        raison = (done.stderr or done.stdout or '').strip()[-500:]
        message = f'docker {args[0]} : {raison or f"code {done.returncode}"}'
        journal(message)
        raise DockerError(message)
    return done


def docker_bytes(args: list[str], *, timeout: float) -> bytes:
    """Lance ``docker <args>`` et rend sa sortie brute (une archive tar).

    Raises:
        DockerError: Docker absent, muet ou qui refuse ; la raison est
            notée au journal.
    """
    binary = shutil.which('docker')
    if binary is None:
        journal('docker absent de ce serveur')
        raise DockerError('docker absent de ce serveur')
    try:
        done = subprocess.run(
            [binary, *args],
            capture_output=True,
            timeout=timeout,
            env=_env(),
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        message = f'docker {args[0]} : {exc}'
        journal(message)
        raise DockerError(message) from exc
    if done.returncode != 0:
        raison = done.stderr.decode('utf-8', 'replace').strip()[-500:]
        message = f'docker {args[0]} : {raison or f"code {done.returncode}"}'
        journal(message)
        raise DockerError(message)
    return done.stdout
