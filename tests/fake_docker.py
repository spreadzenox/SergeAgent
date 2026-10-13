#!/usr/bin/env python3
"""Un faux ``docker`` pour les tests : les commandes dont Serge se sert.

Chaque conteneur est un dossier de ``$FAKE_DOCKER_ROOT`` ; son volume,
monté sur ``/work``, est un autre dossier. Une commande lancée « dans » un
conteneur tourne sur la machine de test, dans ce dossier, avec ``/work``
remplacé par son chemin. Chaque appel est noté dans ``calls.jsonl``.

Pour essayer les pannes : ``FAKE_DOCKER_FAIL=run`` fait refuser
``docker run`` comme Docker le ferait ; ``FAKE_DOCKER_DU_MB=5000`` fait
mesurer 5 000 Mo à ``du``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ['FAKE_DOCKER_ROOT'])


def _state(name: str) -> dict | None:
    path = ROOT / 'containers' / name / 'state.json'
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _save(name: str, state: dict) -> None:
    folder = ROOT / 'containers' / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'state.json').write_text(json.dumps(state), encoding='utf-8')


def _refuse(message: str, code: int = 125) -> int:
    print(f'Error response from daemon: {message}', file=sys.stderr)
    return code


def _ps(args: list[str]) -> int:
    wanted = ''
    for i, arg in enumerate(args):
        if arg == '--filter':
            wanted = args[i + 1].removeprefix('name=^').removesuffix('$')
    state = _state(wanted)
    if state is not None:
        print(state['state'])
    return 0


def _run(args: list[str]) -> int:
    if os.environ.get('FAKE_DOCKER_FAIL') == 'run':
        return _refuse(
            'pull access denied for image, repository does not exist'
        )
    flags: dict[str, str] = {}
    i = 0
    while i < len(args) and args[i].startswith('-'):
        if args[i] in ('-d', '--init'):
            i += 1
            continue
        flags[args[i]] = args[i + 1]
        i += 2
    image, command = args[i], args[i + 1 :]
    volume, _, _target = flags['-v'].partition(':')
    (ROOT / 'volumes' / volume).mkdir(parents=True, exist_ok=True)
    _save(
        flags['--name'],
        {
            'state': 'running',
            'image': image,
            'volume': volume,
            'flags': flags,
            'command': command,
        },
    )
    print(f'id-{flags["--name"]}')
    return 0


def _set(name: str, value: str) -> int:
    state = _state(name)
    if state is None:
        return _refuse(f'No such container: {name}', 1)
    state['state'] = value
    _save(name, state)
    return 0


def _exec(args: list[str]) -> int:
    detach = stdin = False
    i = 0
    while args[i].startswith('-'):
        if args[i] == '-d':
            detach = True
        elif args[i] == '-i':
            stdin = True
        elif args[i] == '-w':
            i += 1
        i += 1
    name, argv = args[i], args[i + 1 :]
    state = _state(name)
    if state is None:
        return _refuse(f'No such container: {name}', 1)
    if state['state'] != 'running':
        return _refuse(f'container {name} is not running', 1)
    work = str(ROOT / 'volumes' / state['volume'])
    argv = [a.replace('/work', work) for a in argv]
    if argv[:2] == ['du', '-sm'] and os.environ.get('FAKE_DOCKER_DU_MB'):
        print(f'{os.environ["FAKE_DOCKER_DU_MB"]}\t{work}')
        return 0
    if detach:
        subprocess.Popen(argv, cwd=work, start_new_session=True)
        return 0
    done = subprocess.run(
        argv,
        cwd=work,
        input=sys.stdin.read() if stdin else None,
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    return done.returncode


def main(args: list[str]) -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    with (ROOT / 'calls.jsonl').open('a', encoding='utf-8') as log:
        log.write(json.dumps(args) + '\n')
    command, rest = args[0], args[1:]
    if command == 'ps':
        return _ps(rest)
    if command == 'run':
        return _run(rest)
    if command == 'start':
        return _set(rest[-1], 'running')
    if command == 'stop':
        return _set(rest[-1], 'exited')
    if command == 'exec':
        return _exec(rest)
    return _refuse(f'commande inconnue du faux docker : {command}')


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
