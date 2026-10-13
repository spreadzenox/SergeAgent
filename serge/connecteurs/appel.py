#!/usr/bin/env python3
"""Appeler une API décrite en base : une seule capacité pour tous les
services (Q56, Q91).

Un service (``api_services``) dit son adresse, comment s'authentifier, le
fichier de secret à lire (son nom, jamais sa valeur) et le format du corps
(``form`` pour Stripe, ``json`` ailleurs). Un point d'entrée est un outil
(``api_endpoints``) : sa méthode, son chemin, ses paramètres permis. Un
paramètre du chemin (``/v1/prices/{id}``) y est remplacé ; les autres vont
dans le corps, ou dans l'adresse pour une lecture (GET). Exemple : l'outil
« Créer un prix Stripe » envoie ``POST /v1/prices`` avec ``unit_amount``,
``currency`` et ``metadata[venture_id]``, ce dernier figé en base.

Le service vient du point d'entrée, ou d'un paramètre figé ``service`` sur
l'invocation : le même outil sert en mode test et en vrai mode. Une
écriture porte une clé d'idempotence tirée de la tâche et de son contenu :
reprise après un arrêt, elle n'agit jamais deux fois. Toute erreur du
service est notée au journal avec la raison qu'il donne (Q89).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from serge.db.store import append_event
from serge.paths import config_root
from serge.secrets import read_secret_file

TIMEOUT_S = 30
# Les paramètres que l'appelant fige, sans les envoyer au service.
_REGLAGES = {'service', 'task_id'}


def journal(texte: str) -> None:
    """Une ligne dans le journal du service (lisible sur la page Health)."""
    print(f'connecteur : {texte}', file=sys.stderr, flush=True)


def _endpoint(conn: sqlite3.Connection, tool_id: str) -> tuple[str, str, str]:
    row = conn.execute(
        'SELECT service_id, method, path FROM api_endpoints WHERE tool_id=?',
        (tool_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f'point d’entrée inconnu : {tool_id}')
    return str(row[0]), str(row[1]), str(row[2])


def _params(conn: sqlite3.Connection, tool_id: str) -> dict[str, str]:
    return {
        str(name): str(kind)
        for name, kind in conn.execute(
            'SELECT name, type FROM api_endpoint_params WHERE tool_id=?',
            (tool_id,),
        ).fetchall()
    }


def api_schema(conn: sqlite3.Connection, tool_id: str) -> dict[str, Any]:
    """Le schéma d'un point d'entrée, tel qu'on le montre au modèle."""
    doc = conn.execute(
        'SELECT titre, doc_md FROM tools WHERE id=?', (tool_id,)
    ).fetchone()
    types = {'text': 'string', 'number': 'number', 'bool': 'boolean'}
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, kind, needed, description in conn.execute(
        'SELECT name, type, required, description FROM api_endpoint_params'
        ' WHERE tool_id=? ORDER BY position',
        (tool_id,),
    ).fetchall():
        prop: dict[str, Any] = {'description': str(description)}
        if kind == 'json':
            prop['description'] += ' (un objet ou une liste JSON)'
        else:
            prop['type'] = types[str(kind)]
        properties[str(name)] = prop
        if needed:
            required.append(str(name))
    return {
        'type': 'function',
        'function': {
            'name': tool_id,
            'description': f'{doc[0]}. {doc[1]}' if doc else tool_id,
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required,
            },
        },
    }


def _form(values: Mapping[str, Any]) -> bytes:
    """Le corps « form » de Stripe : un booléen s'écrit true ou false."""
    pairs = []
    for key, value in values.items():
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs).encode()


def call_api(
    conn: sqlite3.Connection,
    tool_id: str,
    args: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """Appelle le point d'entrée ``tool_id`` avec les paramètres permis."""
    default_service, method, path = _endpoint(conn, tool_id)
    service_id = str(args.get('service') or default_service)
    service = conn.execute(
        'SELECT base_url, auth, secret_file, body FROM api_services'
        ' WHERE id=?',
        (service_id,),
    ).fetchone()
    if service is None:
        return {'ok': False, 'code': 'service_inconnu', 'detail': service_id}
    base_url, auth, secret_file, body_kind = (str(x) for x in service)
    permis = _params(conn, tool_id)
    values: dict[str, Any] = {}
    for name, value in args.items():
        if name in _REGLAGES or value in (None, ''):
            continue
        if name not in permis:
            return {'ok': False, 'code': 'parametre_inconnu', 'detail': name}
        if permis[name] == 'json' and isinstance(value, str):
            value = json.loads(value)
        if '{' + name + '}' in path:
            path = path.replace(
                '{' + name + '}', urllib.parse.quote(str(value), safe='')
            )
        else:
            values[name] = value
    url = base_url.rstrip('/') + path
    headers = {'Accept': 'application/json'}
    if auth == 'bearer':
        secret = read_secret_file(config_root() / 'secrets' / secret_file)
        if not secret:
            journal(f'{service_id} : secret {secret_file} absent')
            return {
                'ok': False,
                'code': 'secret_absent',
                'detail': secret_file,
            }
        headers['Authorization'] = f'Bearer {secret}'
    data = None
    if method == 'GET':
        if values:
            url += '?' + urllib.parse.urlencode(values, doseq=True)
    else:
        if body_kind == 'form':
            data = _form(values)
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            data = json.dumps(values).encode()
            headers['Content-Type'] = 'application/json'
        empreinte = hashlib.sha256(
            f'{args.get("task_id", "")}|{tool_id}|{url}|'.encode() + data
        ).hexdigest()[:32]
        headers['Idempotency-Key'] = f'serge-{empreinte}'
    statut, reponse = _envoyer(url, method, data, headers)
    if statut >= 400 or statut == 0:
        raison = _raison(reponse)
        journal(f'{service_id} {method} {path} : HTTP {statut} {raison}')
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='api.call',
        venture_id=str(args.get('metadata[venture_id]') or ''),
        payload={
            'service': service_id,
            'method': method,
            'path': path,
            'status': statut,
        },
    )
    return {'ok': 0 < statut < 400, 'status': statut, 'data': reponse}


def _envoyer(
    url: str, method: str, data: bytes | None, headers: dict[str, str]
) -> tuple[int, Any]:
    request = urllib.request.Request(
        url, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            return response.status, _lire(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _lire(exc.read())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, {'erreur': f'service injoignable : {exc}'}


def _lire(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {'texte': raw.decode('utf-8', 'replace')[:2000]}


def _raison(reponse: Any) -> str:
    """Ce que le service dit d'une erreur (Stripe : ``error.message``)."""
    if isinstance(reponse, dict):
        erreur = reponse.get('error') or reponse.get('erreur') or reponse
        if isinstance(erreur, dict):
            return str(erreur.get('message') or erreur)[:300]
        return str(erreur)[:300]
    return str(reponse)[:300]
