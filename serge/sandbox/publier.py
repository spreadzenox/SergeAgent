#!/usr/bin/env python3
"""Publier un produit : une version figée, en staging ou en prod.

Une **version** est une copie du dossier du chantier, sans ce qui se
reconstruit (``node_modules``, ``.git``…), rangée dans
``files/<business>/<livrable>/v<N>/`` avec sa fiche dans ``artifacts`` :
elle n'est jamais modifiée (décision Q40). Publier en staging :

1. fige la version et construit l'image du produit à partir de son
   ``Dockerfile`` (la seule règle imposée au constructeur, Q91) ;
2. remplace le conteneur du staging par un neuf, avec les limites du
   profil « produit » (page Policy), son volume de données (``/data``,
   gardé d'une version à l'autre) et un port fixe sur ``127.0.0.1`` ;
3. attend que le produit réponde sur ce port ;
4. ajoute la route dans Caddy (le staging n'est pas indexé par les
   moteurs de recherche) et fait relire Caddy, sans coupure ;
5. note la publication dans ``deployments``.

Publier en prod reprend telle quelle l'image de la version passée en
staging : rien n'est reconstruit. Adresses : ``staging-<produit>.<domaine>``,
``<produit>.<domaine>`` en prod, ou le domaine acheté pour le produit fini.
"""

from __future__ import annotations

import hashlib
import io
import re
import socket
import sqlite3
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from serge.db.store import append_event, utcnow
from serge.ingress import caddy
from serge.paths import files_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox.chantier import chantier_id, ensure_chantier
from serge.sandbox.docker import DockerError, docker, docker_bytes, journal

PORT = 8080
# Les ports des produits sur 127.0.0.1 : un par publication, gardé d'une
# version à l'autre pour que la route de Caddy reste juste après un
# redémarrage du serveur.
FIRST_PORT = 18000
# Ce qui ne part pas dans une version : ça se reconstruit.
EXCLUS = ('node_modules', '.git', '.serge', '.venv', '__pycache__')
# Combien de temps on attend qu'un produit réponde après son lancement.
ATTENTE_S = 60


def slug(text: str) -> str:
    """Un nom court pour une adresse : ``Devis Artisan`` → ``devis-artisan``."""
    brut = re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return brut[:40].strip('-') or 'produit'


def _snapshot(
    conn: sqlite3.Connection,
    name: str,
    venture_id: str,
    deliverable: str,
    task_id: str,
) -> tuple[int, Path, str]:
    """Fige le chantier en version N ; rend ``(N, dossier, fiche)``."""
    archive = docker_bytes(
        [
            'exec',
            name,
            'tar',
            '-C',
            '/work',
            *(f'--exclude={e}' for e in EXCLUS),
            '-cf',
            '-',
            '.',
        ],
        timeout=600,
    )
    row = conn.execute(
        "SELECT MAX(version) FROM artifacts WHERE kind='version'"
        ' AND venture_id=? AND deliverable=?',
        (venture_id, deliverable),
    ).fetchone()
    version = int(row[0] or 0) + 1
    dossier = files_root() / slug(venture_id) / deliverable / f'v{version}'
    dossier.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(dossier, filter='data')
    ident = f'art_{hashlib.sha256(str(dossier).encode()).hexdigest()[:12]}'
    conn.execute(
        'INSERT INTO artifacts(id, venture_id, deliverable, kind, version,'
        ' path_or_url, hash, size_bytes, task_id, created_at)'
        " VALUES(?,?,?,'version',?,?,?,?,?,?)",
        (
            ident,
            venture_id,
            deliverable,
            version,
            str(dossier),
            hashlib.sha256(archive).hexdigest(),
            len(archive),
            task_id,
            utcnow(),
        ),
    )
    return version, dossier, ident


def _port(conn: sqlite3.Connection, deployment: str) -> int:
    """Le port de cette publication : le même qu'avant, sinon un libre."""
    row = conn.execute(
        'SELECT host_port FROM deployments WHERE id=?', (deployment,)
    ).fetchone()
    if row and int(row[0]):
        return int(row[0])
    pris = {
        int(r[0]) for r in conn.execute('SELECT host_port FROM deployments')
    }
    port = FIRST_PORT
    while port in pris or not _libre(port):
        port += 1
    return port


def _libre(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def _repond(port: int) -> bool:
    """Le produit répond-il sur son port ? (une erreur HTTP compte : il
    écoute ; seul un refus de connexion ou un délai n'est pas une réponse)"""
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=3):
            return True
    except urllib.error.HTTPError:
        return True
    except (urllib.error.URLError, OSError):
        return False


def _attendre(port: int) -> bool:
    fin = time.monotonic() + ATTENTE_S
    while time.monotonic() < fin:
        if _repond(port):
            return True
        time.sleep(2)
    return False


def _queue(text: str, limite: int = 3000) -> str:
    return text if len(text) <= limite else '…' + text[-limite:]


def _hostname(args: dict[str, Any], target: str) -> str:
    domaine = str(args.get('domain') or '').strip().lower()
    if domaine and target == 'prod':
        return domaine
    base = caddy.public_hostname()
    if not base:
        raise DockerError(
            "pas de domaine pour les produits : l'instance n'a pas de"
            ' public_hostname'
        )
    produit = slug(str(args.get('slug') or args.get('venture_id') or ''))
    return (
        f'staging-{produit}.{base}'
        if target == 'staging'
        else (f'{produit}.{base}')
    )


def publish_version(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """Publie le produit du chantier en staging, ou sa version en prod."""
    venture_id = str(args.get('venture_id') or '')
    deliverable = str(args.get('deliverable') or '')
    target = str(args.get('target') or '')
    if target not in ('staging', 'prod'):
        return {'ok': False, 'code': 'cible_inconnue', 'detail': target}
    chantier = chantier_id(venture_id, deliverable)
    deployment = f'{target}-{chantier}'
    if target == 'staging':
        _c, name, _p = ensure_chantier(conn, {**args, 'profile': 'chantier'})
        version, dossier, artifact = _snapshot(
            conn, name, venture_id, deliverable, str(args.get('task_id') or '')
        )
        if not (dossier / 'Dockerfile').is_file():
            return _rate(
                conn,
                deployment,
                args,
                version,
                'pas_de_dockerfile',
                'le chantier n’a pas de Dockerfile à sa racine (/work)',
                '',
            )
        image = f'serge-produit-{chantier}:v{version}'
        built = docker(
            ['build', '-t', image, str(dossier)], timeout=1800, check=False
        )
        if built.returncode != 0:
            return _rate(
                conn,
                deployment,
                args,
                version,
                'construction_ratee',
                'docker build a échoué',
                _queue((built.stdout or '') + (built.stderr or '')),
            )
    else:
        row = conn.execute(
            'SELECT version, image FROM deployments WHERE id=?',
            (f'staging-{chantier}',),
        ).fetchone()
        if row is None:
            return {
                'ok': False,
                'code': 'rien_en_staging',
                'detail': 'aucune version en staging à passer en prod',
            }
        version, image, artifact = int(row[0]), str(row[1]), ''
    return _lancer(
        conn, invocation_id, args, target, deployment, version, image, artifact
    )


def _lancer(
    conn: sqlite3.Connection,
    invocation_id: str,
    args: dict[str, Any],
    target: str,
    deployment: str,
    version: int,
    image: str,
    artifact: str,
) -> dict[str, Any]:
    profile = policy_en_vigueur(conn)['sandbox']['produit']
    hostname = _hostname(args, target)
    url = f'https://{hostname}'
    port = _port(conn, deployment)
    container = f'serge-{deployment}'
    docker(['rm', '-f', container], timeout=120, check=False)
    docker(
        [
            'run',
            '-d',
            '--name',
            container,
            '--restart',
            'unless-stopped',
            '--cpus',
            str(profile['cpus']),
            '--memory',
            f'{int(profile["memory_mb"])}m',
            '--pids-limit',
            '512',
            '-e',
            f'PORT={PORT}',
            '-e',
            'DATA_DIR=/data',
            '-e',
            f'PUBLIC_URL={url}',
            '-p',
            f'127.0.0.1:{port}:{PORT}',
            '-v',
            f'serge-donnees-{deployment}:/data',
            '--label',
            f'serge.produit={deployment}',
            image,
        ],
        timeout=300,
    )
    if not _attendre(port):
        logs = docker(
            ['logs', '--tail', '60', container], timeout=60, check=False
        )
        return _rate(
            conn,
            deployment,
            args,
            version,
            'ne_repond_pas',
            f'le produit ne répond pas sur le port {PORT} après {ATTENTE_S} s',
            _queue((logs.stdout or '') + (logs.stderr or '')),
            image=image,
            port=port,
            hostname=hostname,
        )
    caddy.upsert(
        hostname,
        f'127.0.0.1:{port}',
        str(args.get('venture_id') or ''),
        noindex=target == 'staging',
    )
    rechargement = caddy.reload()
    _noter(
        conn, deployment, args, version, 'running', '', image, port, hostname
    )
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='product.published',
        venture_id=str(args.get('venture_id') or ''),
        payload={
            'target': target,
            'version': version,
            'url': url,
            'caddy': rechargement or 'relu',
        },
        rows=[('deployments', deployment)]
        + ([('artifacts', artifact)] if artifact else []),
    )
    result: dict[str, Any] = {
        'ok': True,
        'target': target,
        'version': version,
        'url': url,
    }
    if rechargement:
        result['caddy'] = rechargement
    return result


def _noter(
    conn: sqlite3.Connection,
    deployment: str,
    args: dict[str, Any],
    version: int,
    status: str,
    erreur: str,
    image: str,
    port: int,
    hostname: str,
) -> None:
    now = utcnow()
    target = deployment.split('-', 1)[0]
    conn.execute(
        'INSERT INTO deployments(id, venture_id, deliverable, target,'
        ' version, image, container, host_port, hostname, status,'
        ' last_error, created_at, updated_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET'
        ' version=excluded.version, image=excluded.image,'
        ' host_port=excluded.host_port, hostname=excluded.hostname,'
        ' status=excluded.status, last_error=excluded.last_error,'
        ' updated_at=excluded.updated_at',
        (
            deployment,
            str(args.get('venture_id') or ''),
            str(args.get('deliverable') or ''),
            target,
            version,
            image,
            f'serge-{deployment}',
            port,
            hostname,
            status,
            erreur,
            now,
            now,
        ),
    )


def _rate(
    conn: sqlite3.Connection,
    deployment: str,
    args: dict[str, Any],
    version: int,
    code: str,
    detail: str,
    log: str,
    *,
    image: str = '',
    port: int = 0,
    hostname: str = '',
) -> dict[str, Any]:
    """Une publication ratée : notée (Mission Control la montre), et rendue
    au modèle avec la fin du journal, pour qu'il corrige."""
    journal(f'{deployment} v{version} : {detail}')
    row = conn.execute(
        'SELECT image, host_port, hostname FROM deployments WHERE id=?',
        (deployment,),
    ).fetchone()
    _noter(
        conn,
        deployment,
        args,
        version,
        'failed',
        detail,
        image or (str(row[0]) if row else ''),
        port or (int(row[1]) if row else 0),
        hostname or (str(row[2]) if row else ''),
    )
    return {'ok': False, 'code': code, 'detail': detail, 'log': log}
