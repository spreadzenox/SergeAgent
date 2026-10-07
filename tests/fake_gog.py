#!/usr/bin/env python3
"""Un faux ``gog`` pour les tests : une boîte Gmail dans un fichier JSON.

Il répond aux commandes dont le canal e-mail se sert (``gmail send``,
``gmail search``, ``gmail get``), comme l'API Gmail : un message envoyé
reçoit un identifiant et un ``Message-ID`` choisis par « Gmail ». La boîte
est le fichier ``FAKE_GOG_STATE`` : ``{inbox: [...], sent: [...]}``, chaque
message ``{id, from, to, subject, body, message_id, in_reply_to, date}``.
``FAKE_GOG_REFUSE`` : le destinataire refusé (code de sortie 1).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path


def _flag(args: list[str], name: str) -> str:
    return args[args.index(name) + 1] if name in args else ''


def _message(msg: dict) -> dict:
    headers = {
        'From': msg['from'],
        'To': msg['to'],
        'Subject': msg['subject'],
        'Message-ID': msg['message_id'],
        'In-Reply-To': msg.get('in_reply_to', ''),
        'References': msg.get('in_reply_to', ''),
    }
    data = base64.urlsafe_b64encode(msg['body'].encode()).decode()
    return {
        'id': msg['id'],
        'payload': {
            'mimeType': 'text/plain',
            'headers': [{'name': k, 'value': v} for k, v in headers.items()],
            'body': {'data': data},
        },
    }


def _search(state: dict, query: str) -> list[dict]:
    every = state['inbox'] + state['sent']
    if query.startswith('rfc822msgid:'):
        wanted = query.split(':', 1)[1]
        return [m for m in every if m['message_id'].strip('<>') == wanted]
    if query.startswith('in:sent to:'):
        address = query.split()[1][len('to:') :]
        return [m for m in state['sent'] if m['to'] == address]
    if query.startswith('in:inbox after:'):
        start = int(query.split()[1][len('after:') :])
        return [m for m in state['inbox'] if m['date'] >= start]
    return list(state['inbox'])


def main(args: list[str]) -> int:
    path = Path(os.environ['FAKE_GOG_STATE'])
    state = json.loads(path.read_text(encoding='utf-8'))
    state.setdefault('calls', []).append(args)
    command = args[1]
    if command == 'send':
        to = _flag(args, '--to')
        if to == os.environ.get('FAKE_GOG_REFUSE'):
            path.write_text(json.dumps(state), encoding='utf-8')
            print('invalid recipient', file=sys.stderr)
            return 1
        ident = f's{len(state["sent"]) + 1}'
        parent = _flag(args, '--reply-to-message-id')
        quoted = next(
            (m for m in state['inbox'] + state['sent'] if m['id'] == parent),
            None,
        )
        state['sent'].append(
            {
                'id': ident,
                'from': 'serge@gmail.test',
                'to': to,
                'subject': _flag(args, '--subject'),
                'body': _flag(args, '--body')
                + (f'\n\n> {quoted["body"]}' if quoted else ''),
                'message_id': f'<{ident}@gmail.test>',
                'in_reply_to': quoted['message_id'] if quoted else '',
                'date': int(time.time()),
            }
        )
        output: dict = {'id': ident, 'threadId': 'fil'}
    elif command == 'search':
        found = _search(state, args[2])[: int(_flag(args, '--max') or 50)]
        output = {'messages': [{'id': m['id']} for m in found]}
    else:
        msg = next(
            m for m in state['inbox'] + state['sent'] if m['id'] == args[2]
        )
        output = _message(msg)
    path.write_text(json.dumps(state), encoding='utf-8')
    print(json.dumps(output))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
