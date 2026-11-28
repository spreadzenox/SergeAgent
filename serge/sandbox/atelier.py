#!/usr/bin/env python3
"""Trois gestes de plus dans un chantier, pour y fabriquer une vidéo.

- regarder une image du chantier : elle revient au modèle comme une
  image (une planche de relecture, une capture du produit) ;
- garder un fichier du chantier : il est sorti du conteneur, rangé avec
  le livrable (``files/<business>/<livrable>/gardes/``) et a sa fiche
  dans ``artifacts`` (la vidéo rendue, qu'un humain regarde dans Mission
  Control) ;
- dire un texte : la voix de synthèse réglée sur la page Policy (famille
  « Vidéo »), par OpenRouter ; le son est écrit dans le chantier. La clé
  ne sort jamais de Serge : aucun secret n'entre dans le conteneur.

Ce sont des capacités générales : elles ne connaissent ni la vidéo d'un
business ni une invocation.
"""

from __future__ import annotations

import base64
import hashlib
import json
import posixpath
import re
import sqlite3
import urllib.error
import urllib.request
from typing import Any

from serge.db.store import append_event, utcnow
from serge.llm.client import OPENROUTER_BASE_URL
from serge.llm.runtime import read_api_key
from serge.paths import files_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox.chantier import _exec, _path, chantier_id, ensure_chantier
from serge.sandbox.docker import DockerError, docker_bytes, journal

SORTES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
}
# Une image plus lourde coûterait trop cher à montrer au modèle.
MAX_IMAGE = 2_000_000
# Un fichier gardé : une vidéo d'une minute pèse quelques Mo.
MAX_GARDE = 200_000_000
MAX_TEXTE = 3000
DELAI_VOIX = 120.0


def _lire(name: str, path: str, limite: int) -> bytes:
    return docker_bytes(
        ['exec', name, 'head', '-c', str(limite + 1), '--', path], timeout=300
    )


def sandbox_image(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """Montre au modèle une image du chantier (clé ``image``)."""
    _chantier, name, _profil = ensure_chantier(conn, args)
    path = _path(args.get('path'))
    sorte = SORTES.get(posixpath.splitext(path)[1].lower())
    if sorte is None:
        return {
            'ok': False,
            'code': 'pas_une_image',
            'detail': 'une image png, jpg ou webp',
        }
    try:
        brut = _lire(name, path, MAX_IMAGE)
    except DockerError as exc:
        return {'ok': False, 'code': 'fichier_illisible', 'detail': str(exc)}
    if not brut:
        return {'ok': False, 'code': 'fichier_illisible', 'detail': 'vide'}
    if len(brut) > MAX_IMAGE:
        return {
            'ok': False,
            'code': 'image_trop_lourde',
            'detail': f'plus de {MAX_IMAGE // 1000} Ko : réduis-la d’abord'
            ' (ffmpeg -i image.png -vf scale=1080:-1 petite.jpg)',
        }
    return {
        'ok': True,
        'path': path,
        'image': f'data:{sorte};base64,' + base64.b64encode(brut).decode(),
    }


def sandbox_keep_file(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """Sort un fichier du chantier et le range avec le livrable."""
    chantier, name, _profil = ensure_chantier(conn, args)
    path = _path(args.get('path'))
    try:
        brut = _lire(name, path, MAX_GARDE)
    except DockerError as exc:
        return {'ok': False, 'code': 'fichier_illisible', 'detail': str(exc)}
    if not brut:
        return {'ok': False, 'code': 'fichier_illisible', 'detail': 'vide'}
    if len(brut) > MAX_GARDE:
        return {
            'ok': False,
            'code': 'fichier_trop_lourd',
            'detail': f'plus de {MAX_GARDE // 1_000_000} Mo',
        }
    venture_id = str(args.get('venture_id') or '')
    deliverable = str(args.get('deliverable') or '')
    task_id = str(args.get('task_id') or '')
    sorte = re.sub(r'[^a-z_]', '', str(args.get('kind') or '').lower())
    dossier = files_root() / chantier_id(venture_id, 'x').removesuffix('-x')
    dossier = dossier / deliverable / 'gardes'
    dossier.mkdir(parents=True, exist_ok=True)
    nom = re.sub(r'[^A-Za-z0-9_.-]+', '-', posixpath.basename(path))
    chemin = dossier / f'{task_id or "sans-tache"}-{nom}'
    chemin.write_bytes(brut)
    ident = f'art_{hashlib.sha256(str(chemin).encode()).hexdigest()[:12]}'
    conn.execute(
        'INSERT OR REPLACE INTO artifacts(id, venture_id, kind, version,'
        ' path_or_url, hash, size_bytes, task_id, created_at)'
        ' VALUES(?,?,?,1,?,?,?,?,?)',
        (
            ident,
            venture_id,
            sorte or 'fichier',
            str(chemin),
            hashlib.sha256(brut).hexdigest(),
            len(brut),
            task_id,
            utcnow(),
        ),
    )
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='sandbox.file_kept',
        venture_id=venture_id,
        payload={'chantier': chantier, 'path': path, 'artifact': ident},
        rows=[('artifacts', ident)],
    )
    return {'ok': True, 'artifact': ident, 'path': path, 'bytes': len(brut)}


def _voix(conn: sqlite3.Connection) -> dict[str, Any]:
    reglages = (policy_en_vigueur(conn).get('video') or {}).get('voix')
    return reglages if isinstance(reglages, dict) else {}


def _demander_la_voix(texte: str, reglages: dict[str, Any]) -> bytes:
    """Le son du texte, en mp3, par OpenRouter.

    Raises:
        DockerError: OpenRouter refuse ou ne répond pas ; le message dit
            pourquoi.
    """
    corps = {
        'model': str(reglages.get('model') or ''),
        'voice': str(reglages.get('voice') or ''),
        'input': texte,
        'response_format': 'mp3',
    }
    requete = urllib.request.Request(
        f'{OPENROUTER_BASE_URL}/audio/speech',
        data=json.dumps(corps).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {read_api_key()}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(requete, timeout=DELAI_VOIX) as reponse:
            return reponse.read()
    except urllib.error.HTTPError as exc:
        raison = exc.read().decode('utf-8', 'replace')[:300]
        raise DockerError(
            f'OpenRouter a répondu {exc.code} : {raison}'
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DockerError(f'OpenRouter ne répond pas : {exc}') from exc


def speech(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """Fait dire un texte par la voix réglée, et écrit le son dans le
    chantier."""
    texte = str(args.get('text') or '').strip()
    if not texte:
        return {'ok': False, 'code': 'texte_vide'}
    if len(texte) > MAX_TEXTE:
        return {
            'ok': False,
            'code': 'texte_trop_long',
            'detail': f'{len(texte)} caractères, {MAX_TEXTE} au plus',
        }
    reglages = _voix(conn)
    chantier, name, _profil = ensure_chantier(conn, args)
    path = _path(args.get('path'))
    venture_id = str(args.get('venture_id') or '')
    task_id = str(args.get('task_id') or '')
    try:
        son = _demander_la_voix(texte, reglages)
    except DockerError as exc:
        # Toute erreur d'une interface externe va au journal avec sa raison.
        journal(f'voix refusée : {exc}')
        append_event(
            conn,
            actor=f'invocation:{invocation_id}',
            type='speech.refused',
            venture_id=venture_id,
            payload={'task': task_id, 'raison': str(exc)[:300]},
        )
        return {'ok': False, 'code': 'voix_refusee', 'detail': str(exc)[:300]}
    if len(son) < 1000:
        return {'ok': False, 'code': 'voix_refusee', 'detail': 'son vide'}
    ecrit = _exec(
        name,
        [
            'sh',
            '-c',
            'mkdir -p "$(dirname "$1")" && base64 -d > "$1"',
            '_',
            path,
        ],
        timeout=60,
        stdin=base64.b64encode(son).decode(),
    )
    if ecrit.returncode != 0:
        detail = (ecrit.stderr or ecrit.stdout or '').strip()[:300]
        return {'ok': False, 'code': 'ecriture_impossible', 'detail': detail}
    # OpenRouter ne dit pas le prix d'une voix dans sa réponse : on compte
    # au tarif réglé, pour que la dépense entre dans le plafond du jour.
    cout = (
        len(texte) / 1000 * float(reglages.get('usd_par_1000_caracteres') or 0)
    )
    conn.execute(
        'INSERT INTO llm_usage(point, tier, model, tokens_in, tokens_out,'
        ' latency_ms, verdict, cost_usd, task_id, created_at, provider,'
        ' cached_tokens, cache_write_tokens)'
        " VALUES(?,'voix',?,0,0,0,'ok',?,?,?,'openrouter',0,0)",
        (
            invocation_id,
            str(reglages.get('model') or ''),
            cout,
            task_id,
            utcnow(),
        ),
    )
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='speech.generated',
        venture_id=venture_id,
        payload={
            'chantier': chantier,
            'task': task_id,
            'path': path,
            'caracteres': len(texte),
            'cout_usd': round(cout, 4),
        },
    )
    return {
        'ok': True,
        'path': path,
        'caracteres': len(texte),
        'bytes': len(son),
    }


RUNNERS = {
    'sandbox_image': sandbox_image,
    'sandbox_keep_file': sandbox_keep_file,
    'speech': speech,
}
