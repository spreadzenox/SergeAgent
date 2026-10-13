#!/usr/bin/env python3
"""Le chantier : un conteneur où une invocation code et lance un produit.

Un chantier par business et par livrable (table ``sandboxes``), gardé
entre deux tâches : ses fichiers sont sur un volume à lui, monté sur
``/work``. Exemple : « Construire » s'arrête le soir au plafond du jour ;
le lendemain, la tâche suivante retrouve ses fichiers.

Les chiffres d'un chantier viennent de son profil, sur la page Policy
(famille « Bac à sable ») : image, processeurs, mémoire, disque, durée
maximale d'une commande, réseau. Un seul chantier tourne à la fois :
allumer l'un éteint les autres. Docker limite la mémoire, les processeurs
et le nombre de programmes ; il ne limite pas la place sur le disque :
après chaque commande, Serge mesure ``/work`` et arrête le chantier qui
dépasse son disque permis.
"""

from __future__ import annotations

import posixpath
import re
import sqlite3
import time
import uuid
from collections.abc import Mapping
from typing import Any

from serge.db.store import append_event, utcnow
from serge.policy_store import policy_en_vigueur
from serge.sandbox.docker import (
    DockerError,
    docker,
    env_flags,
    journal,
    secret_env,
)

WORK = '/work'
# Le réseau des chantiers et du navigateur : le navigateur y ouvre
# ``http://<conteneur du chantier>:3000``. Il mène aussi à Internet.
NETWORK = 'serge-chantiers'
# Ce qu'on lit d'un fichier au plus : au-delà, il est coupé.
MAX_FILE_BYTES = 2_000_000


def _profile(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    profiles = policy_en_vigueur(conn).get('sandbox') or {}
    profile = profiles.get(name)
    if not isinstance(profile, dict):
        raise DockerError(f'profil de bac à sable inconnu : {name}')
    return profile


def ensure_network() -> None:
    """Crée le réseau des chantiers s'il n'existe pas encore."""
    found = docker(
        ['network', 'ls', '--filter', f'name=^{NETWORK}$', '-q'], timeout=30
    ).stdout.strip()
    if not found:
        docker(['network', 'create', NETWORK], timeout=60)


def _join_network(name: str) -> None:
    """Branche sur le réseau des chantiers un conteneur créé sans lui."""
    networks = docker(
        [
            'inspect',
            '-f',
            '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}',
            name,
        ],
        timeout=30,
    ).stdout.split()
    if NETWORK not in networks:
        ensure_network()
        docker(['network', 'connect', NETWORK, name], timeout=60)


def chantier_id(venture_id: str, deliverable: str) -> str:
    """Le nom d'un chantier : son business et son livrable, en minuscules.

    Exemple : ``ven_3f2a-poc``. C'est aussi le nom de son conteneur et de
    son volume, précédé de ``serge-chantier-``.
    """
    brut = f'{venture_id}-{deliverable}'.lower()
    return re.sub(r'[^a-z0-9_.-]+', '-', brut).strip('-.') or 'chantier'


def container_name(chantier: str) -> str:
    return f'serge-chantier-{chantier}'


def _stop_others(conn: sqlite3.Connection, chantier: str) -> None:
    """Éteint les autres chantiers allumés : un seul tourne à la fois."""
    for other, name in conn.execute(
        "SELECT id, container FROM sandboxes WHERE status='running' AND id<>?",
        (chantier,),
    ).fetchall():
        try:
            docker(['stop', '-t', '5', str(name)], timeout=60, check=False)
        except DockerError:
            pass  # déjà noté au journal ; on éteint quand même en base
        conn.execute(
            "UPDATE sandboxes SET status='stopped', updated_at=? WHERE id=?",
            (utcnow(), other),
        )


def ensure_chantier(
    conn: sqlite3.Connection, args: Mapping[str, Any]
) -> tuple[str, str, dict[str, Any]]:
    """Allume le chantier de la tâche (le crée au besoin).

    Returns:
        ``(chantier, conteneur, profil)``.
    """
    venture_id = str(args.get('venture_id') or '')
    deliverable = str(args.get('deliverable') or '')
    if not venture_id or not deliverable:
        raise DockerError('chantier sans business ni livrable')
    profile_name = str(args.get('profile') or 'chantier')
    profile = _profile(conn, profile_name)
    chantier = chantier_id(venture_id, deliverable)
    name = container_name(chantier)
    _stop_others(conn, chantier)
    # « running », « exited », « created »… ; rien si le conteneur n'existe
    # pas encore.
    state = docker(
        ['ps', '-a', '--filter', f'name=^{name}$', '--format', '{{.State}}'],
        timeout=30,
    ).stdout.strip()
    if not state:
        # Un secret réglé en base (la clé Stripe du mode test, pour essayer
        # un paiement) entre dans le conteneur à sa création.
        secrets = secret_env(str(args.get('env_secrets') or ''))
        flags = [
            'run',
            '-d',
            '--init',
            '--name',
            name,
            '--label',
            f'serge.chantier={chantier}',
            '--cpus',
            str(profile['cpus']),
            '--memory',
            f'{int(profile["memory_mb"])}m',
            '--pids-limit',
            '1024',
            '-v',
            f'{name}:{WORK}',
            '-w',
            WORK,
            *env_flags(secrets),
        ]
        if profile.get('network') == 'aucun':
            flags += ['--network', 'none']
        else:
            ensure_network()
            flags += ['--network', NETWORK]
        # La première fois, Docker télécharge l'image : ça peut être long.
        docker(
            [*flags, str(profile['image']), 'sleep', 'infinity'],
            timeout=900,
            secrets=secrets,
        )
    else:
        if state != 'running':
            docker(['start', name], timeout=120)
        if profile.get('network') != 'aucun':
            _join_network(name)
    now = utcnow()
    conn.execute(
        'INSERT INTO sandboxes(id, venture_id, deliverable, profile,'
        ' container, status, created_at, updated_at)'
        " VALUES(?,?,?,?,?,'running',?,?) ON CONFLICT(id) DO UPDATE SET"
        " status='running', last_error='', updated_at=excluded.updated_at",
        (chantier, venture_id, deliverable, profile_name, name, now, now),
    )
    return chantier, name, profile


def _exec(
    name: str, argv: list[str], *, timeout: float, stdin: str | None = None
):
    flags = ['exec', '-i'] if stdin is not None else ['exec']
    return docker(
        [*flags, '-w', WORK, name, *argv],
        timeout=timeout,
        stdin=stdin,
        check=False,
    )


def _measure(
    conn: sqlite3.Connection, chantier: str, name: str, profile: Mapping
) -> str:
    """Mesure ``/work`` ; arrête le chantier s'il dépasse son disque.

    Returns:
        La raison de l'arrêt, ou ``''``.
    """
    done = _exec(name, ['du', '-sm', WORK], timeout=120)
    try:
        used = int((done.stdout or '0').split()[0])
    except (IndexError, ValueError):
        used = 0
    allowed = int(profile['disk_mb'])
    raison = ''
    if used > allowed:
        raison = f'le chantier prend {used} Mo, plus que les {allowed} permis'
        journal(f'{chantier} : {raison} ; il est arrêté')
        docker(['stop', '-t', '5', name], timeout=60, check=False)
    conn.execute(
        'UPDATE sandboxes SET disk_mb=?, last_command_at=?, updated_at=?,'
        " status=CASE WHEN ?<>'' THEN 'stopped' ELSE status END,"
        ' last_error=? WHERE id=?',
        (used, utcnow(), utcnow(), raison, raison, chantier),
    )
    return raison


def _short(text: str, limit: int) -> str:
    """Une sortie trop longue garde son début et sa fin.

    La fin d'une compilation dit souvent ce qui ne va pas : on garde 2 000
    caractères du début et le reste de la place pour la fin.
    """
    if limit <= 0 or len(text) <= limit:
        return text
    head = min(2000, limit // 4)
    tail = max(0, limit - head - 100)
    coupe = len(text) - head - tail
    return f'{text[:head]}\n… ({coupe} caractères coupés) …\n{text[-tail:]}'


def _true(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {'1', 'true', 'oui'}


def _path(raw: Any) -> str:
    path = str(raw or '').strip()
    if not path:
        raise ValueError('chemin vide')
    if not path.startswith('/'):
        path = f'{WORK}/{path}'
    return posixpath.normpath(path)


def _note(
    conn: sqlite3.Connection,
    invocation_id: str,
    args: Mapping[str, Any],
    chantier: str,
    payload: dict[str, Any],
) -> None:
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='sandbox.command',
        venture_id=str(args.get('venture_id') or ''),
        payload={'chantier': chantier, **payload},
        rows=[('sandboxes', chantier)],
    )


def sandbox_command(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """Lance une commande dans le chantier ; rend sa sortie et son code."""
    command = str(args.get('command') or '').strip()
    if not command:
        return {'ok': False, 'code': 'commande_vide'}
    chantier, name, profile = ensure_chantier(conn, args)
    limit = int(profile['command_timeout_s'])
    if _true(args.get('background')):
        log = f'{WORK}/.serge/{uuid.uuid4().hex[:8]}.log'
        docker(
            [
                'exec',
                '-d',
                '-w',
                WORK,
                name,
                'sh',
                '-c',
                f'mkdir -p {WORK}/.serge && exec sh -lc "$1" > "$2" 2>&1',
                '_',
                command,
                log,
            ],
            timeout=60,
        )
        result: dict[str, Any] = {
            'ok': True,
            'background': True,
            'log': log.removeprefix(f'{WORK}/'),
        }
    else:
        started = time.monotonic()
        done = _exec(
            name,
            ['timeout', '-s', 'KILL', str(limit), 'sh', '-lc', command],
            timeout=limit + 30,
        )
        output = (done.stdout or '') + (done.stderr or '')
        if done.returncode == 137:
            output += f'\n(arrêtée : plus de {limit} s, ou plus de mémoire)'
        max_chars = int(
            policy_en_vigueur(conn)['llm_calls']['tool_result_max_chars']
        )
        result = {
            'ok': done.returncode == 0,
            'exit_code': done.returncode,
            'seconds': round(time.monotonic() - started, 1),
            'output': _short(output.strip(), int(max_chars * 0.9)),
        }
    raison = _measure(conn, chantier, name, profile)
    if raison:
        result.update(ok=False, code='disque_plein', detail=raison)
    _note(
        conn,
        invocation_id,
        args,
        chantier,
        {
            'command': command[:300],
            'exit_code': result.get('exit_code', ''),
            'background': bool(result.get('background')),
        },
    )
    return result


def _read_text(name: str, path: str) -> tuple[bool, str]:
    done = _exec(
        name,
        ['head', '-c', str(MAX_FILE_BYTES), '--', path],
        timeout=60,
    )
    if done.returncode != 0:
        return False, (done.stderr or done.stdout or '').strip()[:300]
    return True, done.stdout or ''


def sandbox_read_file(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """Rend des lignes d'un fichier du chantier."""
    _chantier, name, _profile_ = ensure_chantier(conn, args)
    path = _path(args.get('path'))
    ok, text = _read_text(name, path)
    if not ok:
        return {'ok': False, 'code': 'fichier_illisible', 'detail': text}
    lines = text.splitlines()
    start = max(1, int(args.get('start') or 1))
    count = max(1, int(args.get('lines') or 400))
    shown = lines[start - 1 : start - 1 + count]
    return {
        'ok': True,
        'path': path,
        'total_lines': len(lines),
        'start': start,
        'end': start - 1 + len(shown),
        'text': '\n'.join(shown),
    }


def _write_text(name: str, path: str, content: str) -> tuple[bool, str]:
    done = _exec(
        name,
        ['sh', '-c', 'mkdir -p "$(dirname "$1")" && cat > "$1"', '_', path],
        timeout=60,
        stdin=content,
    )
    if done.returncode != 0:
        return False, (done.stderr or done.stdout or '').strip()[:300]
    return True, ''


def sandbox_write_file(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """Écrit un fichier entier dans le chantier."""
    _chantier, name, _profile_ = ensure_chantier(conn, args)
    path = _path(args.get('path'))
    content = str(args.get('content') or '')
    ok, detail = _write_text(name, path, content)
    if not ok:
        return {'ok': False, 'code': 'ecriture_impossible', 'detail': detail}
    return {'ok': True, 'path': path, 'chars': len(content)}


def sandbox_edit_file(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """Remplace un passage exact, présent une seule fois, par un autre."""
    _chantier, name, _profile_ = ensure_chantier(conn, args)
    path = _path(args.get('path'))
    old = str(args.get('old') or '')
    if not old:
        return {'ok': False, 'code': 'passage_vide'}
    ok, text = _read_text(name, path)
    if not ok:
        return {'ok': False, 'code': 'fichier_illisible', 'detail': text}
    found = text.count(old)
    if found != 1:
        return {
            'ok': False,
            'code': 'passage_introuvable' if not found else 'passage_multiple',
            'detail': f'le passage apparaît {found} fois dans {path}',
        }
    ok, detail = _write_text(
        name, path, text.replace(old, str(args.get('new') or ''), 1)
    )
    if not ok:
        return {'ok': False, 'code': 'ecriture_impossible', 'detail': detail}
    return {'ok': True, 'path': path}
