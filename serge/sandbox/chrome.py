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

Leur trafic web sort par le tunnel VPN de Télécom Paris (``vpn.py``) : les
deux Chrome partagent le réseau du sidecar ``serge-vpn``, et le sidecar
publie leurs ports sur le serveur. Le VPN se désactive d'un réglage de la
page Policy (``navigateur.vpn_off``) ; alors chaque Chrome reprend son
réseau et publie ses ports lui-même, comme avant le VPN.

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
from serge.sandbox import vpn
from serge.sandbox.docker import DockerError, docker, ensure_network

SANS_ECRAN = 'serge-navigateur'
VRAI = 'serge-vrai-chrome'
DOSSIER_IMAGE = Path(__file__).with_name('image_chrome')
# Le port de débogage de chaque conteneur, et l'écran du vrai Chrome.
CDP = {SANS_ECRAN: '9222/tcp', VRAI: '9223/tcp'}
ECRAN = '6080/tcp'
# Dans le réseau partagé du VPN, les deux Chrome écoutent leur débogage
# dans le même espace : le vrai Chrome laisse le 9222 au navigateur sans
# écran (son socat relaie toujours 9223).
PORT_CHROME_VRAI = '9224'


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


def _lancer(nom: str, image: str, memoire_mb: int, ident_vpn: str) -> None:
    ensure_network()
    if ident_vpn:
        reseau = ['--network', f'container:{ident_vpn}']
        publies: list[str] = []
    else:
        reseau = ['--network', 'serge-chantiers']
        ports = [CDP[nom], *([ECRAN] if nom == VRAI else [])]
        publies = [x for port in ports for x in ('-p', f'127.0.0.1::{port}')]
    volume = (
        ['-v', f'{VRAI}-profil:/home/chrome/profil'] if nom == VRAI else []
    )
    env = ['-e', f'CHROME_PORT={PORT_CHROME_VRAI}'] if nom == VRAI else []
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
            *env,
            *reseau,
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


def _au_bon_endroit(nom: str, ident_vpn: str) -> bool:
    """Le conteneur tourne-t-il où il doit : dans le réseau du VPN quand il
    sert, sur le réseau des chantiers sinon ? Un conteneur au mauvais
    endroit est refait (réglage changé, ou sidecar refait)."""
    mode = docker(
        ['inspect', '-f', '{{.HostConfig.NetworkMode}}', nom], timeout=30
    ).stdout.strip()
    attendu = f'container:{ident_vpn}' if ident_vpn else 'serge-chantiers'
    return mode == attendu


def endpoint(conn: sqlite3.Connection, nom: str) -> str:
    """L'adresse de débogage d'un des deux Chrome, lancé au besoin.

    Exemple : ``http://127.0.0.1:49162``.

    Raises:
        DockerError: Docker refuse, le port n'est pas publié, ou le VPN
            n'est pas établi (``vpn.py``).
    """
    profil = policy_en_vigueur(conn)['sandbox']['navigateur']
    memoire = int(profil['memory_mb'])
    image = image_vrai_chrome() if nom == VRAI else str(profil['image'])
    ident_vpn = '' if vpn.desactive(conn) else vpn.ensure_vpn(conn)
    etat = _etat(nom)
    if etat and nom == VRAI:
        actuelle = docker(
            ['inspect', '-f', '{{.Config.Image}}', nom], timeout=30
        ).stdout.strip()
        if actuelle != image:
            # Ses fichiers ont changé : on le refait (le profil reste).
            docker(['rm', '-f', nom], timeout=60)
            etat = ''
    if etat and not _au_bon_endroit(nom, ident_vpn):
        docker(['rm', '-f', nom], timeout=60)
        etat = ''
    if not etat:
        if nom == VRAI:
            _image_construite(image)
        _lancer(nom, image, memoire, ident_vpn)
    elif etat != 'running':
        docker(['start', nom], timeout=120)
    adresse = _port(conn, nom, CDP[nom])
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


def _port(conn: sqlite3.Connection, nom: str, port_conteneur: str) -> str:
    """``127.0.0.1:49162``, ou ``''``. Le port est publié par le sidecar
    du VPN quand il sert, par le conteneur lui-même sinon."""
    return vpn.port(conn, nom, port_conteneur)


# raccourci : le port de l'écran est gardé une minute dans la mémoire du
# programme de Mission Control (une page de l'écran fait une trentaine de
# requêtes) ; un conteneur refait entre-temps donne une minute d'erreurs.
_ECRAN_VU: dict[str, tuple[float, str]] = {}


def adresse_ecran(conn: sqlite3.Connection) -> str:
    """Où lire l'écran du vrai Chrome sur le serveur (``127.0.0.1:49170``),
    ou ``''`` s'il ne tourne pas."""
    vu = _ECRAN_VU.get(VRAI)
    if vu and time.monotonic() - vu[0] < 60:
        return vu[1]
    try:
        adresse = _port(conn, VRAI, ECRAN) if _etat(VRAI) == 'running' else ''
    except DockerError:
        adresse = ''
    if adresse:
        _ECRAN_VU[VRAI] = (time.monotonic(), adresse)
    return adresse
