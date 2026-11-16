#!/usr/bin/env python3
"""Les deux conteneurs Chrome de Serge, lancés au besoin.

- **Le navigateur sans écran** (``serge-navigateur``, image du profil
  « navigateur » de la page Policy) : rapide et léger, pour essayer un
  produit.
- **Le vrai Chrome** (``serge-vrai-chrome``) : un Chromium normal, sur un
  écran virtuel. Certaines pages refusent un navigateur sans écran : le
  16 novembre 2026, le captcha de la page de paiement de Stripe ne se
  chargeait pas dans le premier. Un humain peut voir cet écran et y agir
  depuis Mission Control (``/owner/vrai-chrome``, derrière sa connexion),
  par exemple pour résoudre un captcha. Son image est construite par Serge
  au premier usage, depuis ``serge/sandbox/image_chrome/`` ; son nom
  contient l'empreinte de ces fichiers, et un changement la reconstruit.

Les ports (débogage de Chrome, écran) ne sont publiés que sur le serveur
(``127.0.0.1``), sur un port choisi par Docker.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
import urllib.request
from pathlib import Path

from serge.policy_store import policy_en_vigueur
from serge.sandbox.docker import DockerError, docker, ensure_network

SANS_ECRAN = 'serge-navigateur'
VRAI = 'serge-vrai-chrome'
DOSSIER_IMAGE = Path(__file__).with_name('image_chrome')
# Le port de débogage de chaque conteneur, et l'écran du vrai Chrome.
CDP = {SANS_ECRAN: '9222/tcp', VRAI: '9223/tcp'}
ECRAN = '6080/tcp'


def image_vrai_chrome() -> str:
    """``serge-vrai-chrome:<empreinte des fichiers de l'image>``."""
    empreinte = hashlib.sha256()
    for fichier in sorted(DOSSIER_IMAGE.iterdir()):
        empreinte.update(fichier.name.encode() + fichier.read_bytes())
    return f'{VRAI}:{empreinte.hexdigest()[:12]}'


def _etat(nom: str) -> str:
    """``running``, ``exited``…, ou ``''`` si le conteneur n'existe pas."""
    return docker(
        ['ps', '-a', '--filter', f'name=^{nom}$', '--format', '{{.State}}'],
        timeout=30,
    ).stdout.strip()


def _lancer(nom: str, image: str, memoire_mb: int, ports: list[str]) -> None:
    ensure_network()
    publies = [x for port in ports for x in ('-p', f'127.0.0.1::{port}')]
    volume = (
        ['-v', f'{VRAI}-profil:/home/chrome/profil'] if nom == VRAI else []
    )
    docker(
        [
            'run',
            '-d',
            '--init',
            '--name',
            nom,
            '--memory',
            f'{memoire_mb}m',
            '--cpus',
            '1',
            '--shm-size',
            '512m',
            *publies,
            *volume,
            '--network',
            'serge-chantiers',
            image,
        ],
        timeout=900,
    )


def _image_construite(image: str) -> None:
    """Construit l'image du vrai Chrome si elle manque (quelques minutes,
    une seule fois par version de ses fichiers)."""
    # « image ls » rend une liste vide pour une image absente ; « image
    # inspect » serait un refus de Docker, donc une panne (16 novembre 2026).
    if not docker(['image', 'ls', '-q', image], timeout=30).stdout.strip():
        docker(['build', '-t', image, str(DOSSIER_IMAGE)], timeout=1800)


def endpoint(conn: sqlite3.Connection, nom: str) -> str:
    """L'adresse de débogage d'un des deux Chrome, lancé au besoin.

    Exemple : ``http://127.0.0.1:49162``.

    Raises:
        DockerError: Docker refuse, ou le port n'est pas publié.
    """
    profil = policy_en_vigueur(conn)['sandbox']['navigateur']
    memoire = int(profil['memory_mb'])
    image = image_vrai_chrome() if nom == VRAI else str(profil['image'])
    etat = _etat(nom)
    if etat and nom == VRAI:
        actuelle = docker(
            ['inspect', '-f', '{{.Config.Image}}', nom], timeout=30
        ).stdout.strip()
        if actuelle != image:
            # Ses fichiers ont changé : on le refait (le profil reste).
            docker(['rm', '-f', nom], timeout=60)
            etat = ''
    if not etat:
        if nom == VRAI:
            _image_construite(image)
        _lancer(
            nom, image, memoire, [CDP[nom], *([ECRAN] if nom == VRAI else [])]
        )
    elif etat != 'running':
        docker(['start', nom], timeout=120)
    adresse = _port(nom, CDP[nom])
    if not adresse:
        raise DockerError(f'{nom} ne publie pas son port de débogage')
    if nom == VRAI and etat != 'running':
        _attendre_chrome(adresse)
    return f'http://{adresse}'


def _attendre_chrome(adresse: str) -> None:
    """Attend que Chromium réponde sur son port de débogage (l'écran et
    Chromium démarrent en quelques secondes ; 30 au plus)."""
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                f'http://{adresse}/json/version', timeout=2
            ):
                return
        except OSError:
            time.sleep(0.5)


def _port(nom: str, port: str) -> str:
    """``127.0.0.1:49162``, ou ``''``."""
    sortie = docker(['port', nom, port], timeout=30, check=False).stdout
    return sortie.strip().splitlines()[0] if sortie.strip() else ''


# raccourci : le port de l'écran est gardé une minute dans la mémoire du
# programme de Mission Control (une page de l'écran fait une trentaine de
# requêtes) ; un conteneur refait entre-temps donne une minute d'erreurs.
_ECRAN_VU: dict[str, tuple[float, str]] = {}


def adresse_ecran() -> str:
    """Où lire l'écran du vrai Chrome sur le serveur (``127.0.0.1:49170``),
    ou ``''`` s'il ne tourne pas."""
    vu = _ECRAN_VU.get(VRAI)
    if vu and time.monotonic() - vu[0] < 60:
        return vu[1]
    try:
        adresse = _port(VRAI, ECRAN) if _etat(VRAI) == 'running' else ''
    except DockerError:
        adresse = ''
    if adresse:
        _ECRAN_VU[VRAI] = (time.monotonic(), adresse)
    return adresse
