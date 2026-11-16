#!/usr/bin/env python3
"""Un domaine reçoit-il des e-mails ?

Gratuit, sans service payant (décision Q48) : une question DNS posée en
HTTPS à un résolveur public. Un domaine reçoit des e-mails s'il a un
serveur de courrier (``MX``), ou à défaut une adresse (``A``). Si le
résolveur ne répond pas, on ne sait pas : l'adresse n'est pas refusée
pour autant, et la panne est rendue à l'appelant, qui la note.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

RESOLVER = 'https://cloudflare-dns.com/dns-query'
# Les sortes d'enregistrement DNS : un serveur de courrier, une adresse.
_MX, _A = 15, 1

Resolver = Callable[[str, str], dict]


def _ask(domain: str, kind: str) -> dict:
    query = urllib.parse.urlencode({'name': domain, 'type': kind})
    request = urllib.request.Request(  # noqa: S310 — adresse fixe, en HTTPS
        f'{RESOLVER}?{query}', headers={'Accept': 'application/dns-json'}
    )
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310
        return json.loads(response.read().decode('utf-8'))


def receives_mail(
    domain: str, resolver: Resolver | None = None
) -> tuple[bool | None, str]:
    """``(oui, non ou None si on ne sait pas, la raison)``.

    Exemple : ``(False, 'le domaine n’existe pas')`` pour un domaine
    inventé ; ``(None, 'résolveur DNS injoignable : …')`` sans réseau.
    """
    ask = resolver or _ask
    try:
        for kind, wanted in (('MX', _MX), ('A', _A)):
            answer = ask(domain, kind)
            if int(answer.get('Status', 0)) == 3:
                return False, 'le domaine n’existe pas'
            if any(
                int(r.get('type', 0)) == wanted
                for r in answer.get('Answer') or []
            ):
                return True, ''
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return None, f'résolveur DNS injoignable : {type(exc).__name__}: {exc}'
    return False, 'le domaine ne reçoit pas d’e-mails'
