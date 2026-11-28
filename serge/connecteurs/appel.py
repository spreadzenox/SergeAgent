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
l'invocation : le même outil sert en mode test et en vrai mode. Un point
d'entrée payant peut porter un verrou de prix (``api_endpoints.guard``) :
avant de l'appeler, « Appeler une API » vérifie le prix par un autre point
d'entrée et refuse au-dessus d'un plafond, un réglage de l'invocation qui
appelle (page Policy) ; un modèle ne peut pas passer outre. Un verrou de
préfixe (``prefixe``) oblige un paramètre choisi par le modèle à commencer
par un paramètre figé (voir ``_prefixe``). Un chemin
peut porter une valeur propre à l'instance, lue sur le serveur et jamais
écrite dans le dépôt : ``{config:cloudflare-account-id}`` est la première
ligne du fichier ``config_root/cloudflare-account-id``. Une
écriture porte une clé d'idempotence tirée de la tâche et de son contenu :
reprise après un arrêt, elle n'agit jamais deux fois. Toute erreur du
service est notée au journal avec la raison qu'il donne (Q89).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from serge.db.store import append_event
from serge.interpreter.settings import load_settings
from serge.paths import config_root
from serge.secrets import read_secret_file

TIMEOUT_S = 30
# Le nom du client dans chaque requête. Sans lui, Python envoie le sien
# (« Python-urllib »), que le pare-feu de certains services refuse : Resend,
# derrière Cloudflare, répondait « Error 1010: Access denied » (16 novembre
# 2026).
USER_AGENT = 'SergeAgent/1.0'
# Une valeur propre à l'instance, dans un chemin : {config:<fichier>}.
_CONFIG = re.compile(r'\{config:([A-Za-z0-9_.-]+)\}')
# Les paramètres que l'appelant fige, sans les envoyer au service.
_REGLAGES = {'service', 'task_id'}


def journal(texte: str) -> None:
    """Une ligne dans le journal du service (lisible sur la page Health)."""
    print(f'connecteur : {texte}', file=sys.stderr, flush=True)


def _endpoint(
    conn: sqlite3.Connection, tool_id: str
) -> tuple[str, str, str, str]:
    row = conn.execute(
        'SELECT service_id, method, path, guard FROM api_endpoints'
        ' WHERE tool_id=?',
        (tool_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f'point d’entrée inconnu : {tool_id}')
    return str(row[0]), str(row[1]), str(row[2]), str(row[3] or '')


def _chemin(data: Any, chemin: str) -> Any:
    """Une valeur d'une réponse JSON : ``result.domains.0.registrable``."""
    for part in chemin.split('.'):
        if isinstance(data, list) and part.isdigit() and int(part) < len(data):
            data = data[int(part)]
        elif isinstance(data, dict):
            data = data.get(part)
        else:
            return None
    return data


def _remplir(modele: Any, args: Mapping[str, Any]) -> Any:
    """Les paramètres de la vérification, tirés de ceux de l'appel :
    ``{domain_name}`` devient la valeur de ``domain_name``."""
    if isinstance(modele, str):
        nom = re.fullmatch(r'\{([A-Za-z0-9_\[\].-]+)\}', modele)
        return args.get(nom.group(1), '') if nom else modele
    if isinstance(modele, list):
        return [_remplir(x, args) for x in modele]
    if isinstance(modele, Mapping):
        return {k: _remplir(v, args) for k, v in modele.items()}
    return modele


def _verrou(
    conn: sqlite3.Connection,
    garde: Mapping[str, Any],
    args: Mapping[str, Any],
    invocation_id: str,
) -> str:
    """Pourquoi le verrou de prix refuse l'appel, ou ``''``. Sans réponse
    sûre (vérification ratée, prix introuvable, plafond absent), il refuse.

    Exemple, pour l'achat d'un domaine : la vérification de Cloudflare doit
    dire le nom libre et pas premium, et ses deux prix, en dollars fois
    1,10, ne pas dépasser le réglage « prix_max_eur » de l'invocation.
    """
    nom_plafond = str(garde.get('plafond') or '')
    try:
        plafond = float(load_settings(conn, invocation_id)[nom_plafond])
    except (KeyError, ValueError):
        return f'plafond {nom_plafond} absent de {invocation_id}'
    verification = call_api(
        conn,
        str(garde.get('verifier') or ''),
        {
            **_remplir(garde.get('avec') or {}, args),
            'task_id': args.get('task_id', ''),
        },
        invocation_id,
    )
    if not verification.get('ok'):
        return 'vérification impossible : ' + str(
            verification.get('code') or f'HTTP {verification.get("status")}'
        )
    data = verification.get('data')
    for chemin, attendu in (garde.get('exiger') or {}).items():
        if _chemin(data, chemin) != attendu:
            return f'{chemin} vaut {_chemin(data, chemin)!r}, pas {attendu!r}'
    for chemin, refuse in (garde.get('refuser') or {}).items():
        if _chemin(data, chemin) == refuse:
            return f'{chemin} vaut {refuse!r}'
    taux = float(garde.get('taux') or 1)
    for chemin in garde.get('prix') or []:
        try:
            prix = float(_chemin(data, chemin)) * taux
        except (TypeError, ValueError):
            return f'prix introuvable ({chemin})'
        if prix > plafond + 1e-9:
            return (
                f'{prix:.2f} € dépasse le plafond de {plafond:g} €'
                f' ({nom_plafond})'
            )
    return ''


def _prefixe(regle: Mapping[str, Any], values: Mapping[str, Any]) -> str:
    """Pourquoi le verrou de préfixe refuse l'appel, ou ``''``.

    ``{param, de}`` : la valeur de ``param``, choisie par le modèle, doit
    commencer par celle de ``de``, figée en base, suivie de « _ ». Exemple :
    la clé de recherche du prix d'une offre commence par le numéro de son
    business (``ven_12_pro``) : un modèle ne peut pas prendre la clé du
    prix d'un autre business.
    """
    if not regle:
        return ''
    debut = str(values.get(str(regle.get('de') or '')) or '')
    valeur = str(values.get(str(regle.get('param') or '')) or '')
    if debut and valeur.startswith(f'{debut}_') and valeur != f'{debut}_':
        return ''
    return f'{regle.get("param")} doit commencer par « {debut}_ »'


def _params(conn: sqlite3.Connection, tool_id: str) -> dict[str, str]:
    return {
        str(name): str(kind)
        for name, kind in conn.execute(
            'SELECT name, type FROM api_endpoint_params WHERE tool_id=?',
            (tool_id,),
        ).fetchall()
    }


def nom_pour_le_modele(nom: str) -> str:
    """Un nom de paramètre que tous les modèles acceptent : les crochets des
    paramètres de Stripe deviennent des points (``line_items[0][price]`` →
    ``line_items.0.price``). Anthropic refuse un nom avec des crochets dans
    le schéma d'un outil (16 novembre 2026, le paiement test) ; l'appel
    repart avec le vrai nom (``call_api``)."""
    return re.sub(r'\[([^\]]*)\]', r'.\1', nom)


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
        properties[nom_pour_le_modele(str(name))] = prop
        if needed:
            required.append(nom_pour_le_modele(str(name)))
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


def _typer(kind: str, value: Any) -> Any:
    """Une valeur à son type : un paramètre figé en base arrive en texte
    (« false », « 1 ») et doit partir en booléen ou en nombre dans un corps
    JSON."""
    if not isinstance(value, str):
        return value
    if kind == 'json':
        return json.loads(value)
    if kind == 'bool':
        return value.strip().lower() in ('true', '1', 'oui')
    if kind == 'number':
        try:
            return int(value)
        except ValueError:
            return float(value)
    return value


def _valeurs_d_instance(path: str) -> tuple[str, str]:
    """Remplace ``{config:<fichier>}`` par sa valeur ; rend ``(chemin,
    fichier manquant)``."""
    for fichier in _CONFIG.findall(path):
        try:
            lignes = (config_root() / fichier).read_text().splitlines()
        except OSError:
            lignes = []
        valeur = lignes[0].strip() if lignes else ''
        if not valeur:
            return path, fichier
        path = path.replace('{config:' + fichier + '}', valeur)
    return path, ''


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
    default_service, method, path, garde = _endpoint(conn, tool_id)
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
    # Le modèle donne les noms du schéma (des points), la base les vrais.
    vrais = {nom_pour_le_modele(n): n for n in permis}
    values: dict[str, Any] = {}
    for name, value in args.items():
        name = vrais.get(name, name)
        if name in _REGLAGES or value in (None, ''):
            continue
        if name not in permis:
            return {'ok': False, 'code': 'parametre_inconnu', 'detail': name}
        value = _typer(permis[name], value)
        if '{' + name + '}' in path:
            path = path.replace(
                '{' + name + '}', urllib.parse.quote(str(value), safe='')
            )
        else:
            values[name] = value
    path, manquant = _valeurs_d_instance(path)
    if manquant:
        journal(f'{service_id} : réglage {manquant} absent de config_root')
        return {'ok': False, 'code': 'config_absente', 'detail': manquant}
    url = base_url.rstrip('/') + path
    if garde:
        regles = json.loads(garde)
        refus, sorte = _prefixe(regles.get('prefixe') or {}, values), 'préfixe'
        if not refus and regles.get('verifier'):
            refus, sorte = _verrou(conn, regles, args, invocation_id), 'prix'
        if refus:
            journal(
                f'{service_id} {method} {path} : verrou de {sorte}, {refus}'
            )
            append_event(
                conn,
                actor=f'invocation:{invocation_id}',
                type='api.refused',
                payload={
                    'service': service_id,
                    'method': method,
                    'path': path,
                    'raison': refus,
                },
            )
            return {'ok': False, 'code': 'verrou', 'detail': refus}
    headers = {'Accept': 'application/json', 'User-Agent': USER_AGENT}
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
            query = {
                k: ('true' if v else 'false') if isinstance(v, bool) else v
                for k, v in values.items()
            }
            url += '?' + urllib.parse.urlencode(query, doseq=True)
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
        raison = raison_du_service(reponse)
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


def raison_du_service(reponse: Any) -> str:
    """Ce que le service dit d'une erreur : ``error.message`` (Stripe),
    ``message`` (Resend), ou ``title`` et ``detail`` (une page d'erreur de
    Cloudflare, devant un service : « Error 1010: Access denied »)."""
    if isinstance(reponse, dict):
        erreur = reponse.get('error') or reponse.get('erreur') or reponse
        if isinstance(erreur, dict):
            texte = erreur.get('message') or ' : '.join(
                str(erreur[k]) for k in ('title', 'detail') if erreur.get(k)
            )
            return str(texte or erreur)[:300]
        return str(erreur)[:300]
    return str(reponse)[:300]
