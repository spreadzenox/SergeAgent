#!/usr/bin/env python3
"""Le tunnel VPN des deux Chrome de Serge : Télécom Paris.

Un sidecar ``serge-vpn`` (image gluetun) se connecte au VPN de Télécom
Paris et partage son réseau avec le navigateur sans écran et le vrai
Chrome (``--network container:``) : tout leur trafic web sort par le
tunnel, et rien d'autre du serveur. Si le tunnel tombe, gluetun coupe la
sortie : les pages ne se chargent plus, et l'IP du serveur ne fuit pas.

Les ports des Chrome (débogage des deux, écran du vrai Chrome) sont
publiés sur ``127.0.0.1`` par le sidecar, qui partage leur réseau ; les
Chrome n'en publient plus eux-mêmes. L'écran reste servi au serveur par
l'IP du VPS : le trafic de l'humain qui vient résoudre un captcha n'a
rien à voir avec la sortie web des Chrome.

Le VPN se désactive avec le réglage ``navigateur.vpn_off`` (page Policy,
« Bac à sable ») : « oui », les Chrome tournent comme avant le VPN, sur
le réseau des chantiers. Le changement vaut au prochain lancement d'un
des deux Chrome. Sans les secrets du VPN (``telecom-vpn-login`` et
``telecom-vpn-password``), le lancement échoue : rien ne navigue en
direct sans le dire.

Gluetun refuse un nom d'hôte dans sa configuration OpenVPN : à chaque
lancement du sidecar, l'adresse du serveur est résolue et une copie du
fichier du dépôt est écrite avec l'IP (dans ``config_root`` ; le fichier
du dépôt reste public, sans secret dedans).
"""

from __future__ import annotations

import socket
import sqlite3
import time
from pathlib import Path

from serge.paths import config_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox.chantier import ensure_network
from serge.sandbox.docker import (
    DockerError,
    docker,
    env_flags,
    journal,
    secret_env,
)

CONTAINER = 'serge-vpn'
# L'image, épinglée par son empreinte (une mise à jour se décide ici).
IMAGE = 'qmcgaw/gluetun@sha256:08f6770a4b157787690dcd2d4ddb3560ec28860102530b5cdc4f632f24bfae9e'
# Le fichier du dépôt, et son nom dans config_root (la copie avec l'IP).
SOURCE = Path(__file__).resolve().parents[2] / 'config/vpn/telecom-paris.ovpn'
COPIE = 'telecom-paris.ovpn'
# Les ports des Chrome publiés par le sidecar : le débogage du navigateur
# sans écran, le débogage du vrai Chrome, l'écran du vrai Chrome.
PORTS = ('9222/tcp', '9223/tcp', '6080/tcp')
# Combien de temps on attend la connexion (l'authentification fait deux
# essais chez Télécom Paris avant d'abandonner).
ATTENTE_S = 120.0


def desactive(conn: sqlite3.Connection) -> bool:
    """Le VPN est-il désactivé (réglage ``navigateur.vpn_off``) ?"""
    return (
        str(policy_en_vigueur(conn)['sandbox']['navigateur']['vpn_off'])
        == 'oui'
    )


def _etat() -> str:
    """``running``, ``exited``…, ou ``''`` si le conteneur n'existe pas."""
    return docker(
        [
            'ps',
            '-a',
            '--filter',
            f'name=^{CONTAINER}$',
            '--format',
            '{{.State}}',
        ],
        timeout=30,
    ).stdout.strip()


def _config() -> Path:
    """La copie du fichier du dépôt, avec l'adresse du serveur résolue."""
    texte = SOURCE.read_text(encoding='utf-8')
    remote = next(
        ligne for ligne in texte.splitlines() if ligne.startswith('remote ')
    )
    _, hote, port = remote.split()
    try:
        essais = socket.getaddrinfo(
            hote, None, socket.AF_INET, socket.SOCK_STREAM
        )
    except OSError as exc:
        journal(f'adresse du VPN introuvable : {hote} ({exc})')
        raise DockerError(f'adresse du VPN introuvable : {hote}') from exc
    ip = essais[0][4][0]
    copie = config_root() / 'vpn' / COPIE
    copie.parent.mkdir(parents=True, exist_ok=True)
    copie.write_text(
        texte.replace(remote, f'remote {ip} {port}'), encoding='utf-8'
    )
    return copie


def _lancer() -> None:
    creds = secret_env(
        'OPENVPN_USER=telecom-vpn-login,OPENVPN_PASSWORD=telecom-vpn-password'
    )
    ensure_network()
    docker(
        [
            'run',
            '-d',
            '--init',
            '--name',
            CONTAINER,
            '--restart',
            'unless-stopped',
            '--cap-add',
            'NET_ADMIN',
            '--device',
            '/dev/net/tun',
            '-e',
            'VPN_SERVICE_PROVIDER=custom',
            '-e',
            'VPN_TYPE=openvpn',
            '-e',
            'OPENVPN_CUSTOM_CONFIG=/gluetun/custom.conf',
            '-e',
            'FIREWALL_INPUT_PORTS='
            + ','.join(p.removesuffix('/tcp') for p in PORTS),
            '-e',
            'FIREWALL_OUTBOUND_SUBNETS=172.18.0.0/16',
            *env_flags(creds),
            *[x for p in PORTS for x in ('-p', f'127.0.0.1::{p}')],
            '--network',
            'serge-chantiers',
            '-v',
            f'{_config()}:/gluetun/custom.conf:ro',
            IMAGE,
        ],
        timeout=300,
        secrets=creds,
    )


def _sain() -> str:
    return docker(
        ['inspect', '-f', '{{.State.Health.Status}}', CONTAINER], timeout=30
    ).stdout.strip()


def _raison() -> str:
    """Ce que gluetun a dit en dernier (sans secret dedans)."""
    fait = docker(['logs', '--tail', '8', CONTAINER], timeout=30, check=False)
    lignes = [
        ligne
        for ligne in (fait.stdout + fait.stderr).splitlines()
        if ligne.strip()
    ]
    return ' | '.join(lignes)[-300:]


def ensure_vpn(conn: sqlite3.Connection) -> str:
    """Le sidecar, lancé au besoin et sain ; rend l'identifiant de son
    conteneur (celui du ``--network container:`` des Chrome).

    Raises:
        DockerError: Docker refuse, ou le tunnel n'est pas établi à temps ;
            la raison de gluetun est notée au journal.
    """
    etat = _etat()
    if not etat:
        _lancer()
    elif etat != 'running':
        docker(['start', CONTAINER], timeout=120)
    fin = time.monotonic() + ATTENTE_S
    while time.monotonic() < fin:
        if _sain() == 'healthy':
            identifiant = docker(
                ['inspect', '-f', '{{.Id}}', CONTAINER], timeout=30
            ).stdout
            return identifiant.strip()
        time.sleep(2.0)
    journal(f'le VPN n’est pas établi : {_raison()}')
    raise DockerError(f'le VPN ({CONTAINER}) n’est pas établi : {_raison()}')


def port(conn: sqlite3.Connection, nom: str, port_conteneur: str) -> str:
    """``127.0.0.1:49162`` pour un port d'un Chrome : le sidecar le publie
    quand le VPN sert, le conteneur lui-même sinon."""
    editeur = CONTAINER if not desactive(conn) else nom
    sortie = docker(
        ['port', editeur, port_conteneur], timeout=30, check=False
    ).stdout
    return sortie.strip().splitlines()[0] if sortie.strip() else ''
