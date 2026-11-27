#!/usr/bin/env python3
"""Les services externes gratuits d'un produit (décision Q118).

Un produit peut avoir besoin d'un service d'un autre site : une API de
cartes, de conversion de fichiers, de météo. Le constructeur le demande
avec « Brancher un service gratuit » ; sa tâche attend, pendant que
d'autres invocations créent le compte de Serge sur ce site (le système
des comptes web : le vrai Chrome, l'identité de Serge, un humain au
captcha) puis vont chercher une clé d'API dans son tableau de bord. La
clé est gardée ici, chiffrée ; le produit la lit dans une variable
d'environnement (``SERVICE_<NOM>_KEY``), dans le chantier, en staging et
en prod.

Les garde-fous :

- **un service est autorisé par un humain** : soit le plan qu'un humain
  a validé le nomme (une ligne « nom | adresse | pourquoi | offre
  gratuite »), soit un ticket « Service » demande l'accord pendant la
  construction. Un plan appliqué tout seul après 48 heures n'autorise
  rien ;
- **gratuit seulement** : les invocations qui créent le compte et la clé
  n'ont pas d'outil pour payer ;
- **un seul compte de Serge par site**, quel que soit le produit : le
  compte porte le nom du service ;
- **un nombre de services par produit**, réglé page Policy ;
- **la clé ne se montre pas** : gardée chiffrée, jamais rendue au modèle
  ni écrite dans un ticket, masquée dans ce que le chantier affiche.

Exemple : le plan validé de « Tournées » porte la ligne
« openrouteservice | https://openrouteservice.org | calculer un trajet |
2 000 requêtes par jour ». Le constructeur appelle l'outil avec ce nom et
cette adresse : la ligne ``product_services`` passe à ``connecting``, sa
tâche attend, et repart avec « le service est branché : variable
SERVICE_OPENROUTESERVICE_KEY ».
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Any
from urllib.parse import urlparse

from serge import web_accounts
from serge.db.store import append_event, utcnow
from serge.interpreter.tasks import thaw_task
from serge.interpreter.triggers import notify_rows_written
from serge.policy_store import policy_en_vigueur

ASKED, CONNECTING, CONNECTED = 'asked', 'connecting', 'connected'
FAILED, REFUSED = 'failed', 'refused'
# Les plans d'un business, par livrable du chantier.
_KINDS = {'poc': 'poc', 'produit': 'product', 'product': 'product'}
_NAME = re.compile(r'[a-z0-9][a-z0-9_-]{0,30}')
_URL = re.compile(r'https://[^\s|<>)\]]+')
# Une clé d'API : d'un seul tenant, assez longue pour ne pas être un mot.
_KEY = re.compile(r'\S{12,512}')


def env_name(name: str) -> str:
    """La variable d'un service : ``mapbox`` → ``SERVICE_MAPBOX_KEY``."""
    return f'SERVICE_{re.sub(r"[^A-Z0-9]", "_", name.upper())}_KEY'


def _host(url: str) -> str:
    return (urlparse(url).hostname or '').removeprefix('www.').lower()


def planned_hosts(plan: str) -> set[str]:
    """Les sites des services que nomme un plan : ses lignes « nom |
    adresse | … ». Une adresse citée ailleurs dans le plan ne compte pas."""
    return {
        _host(url)
        for line in plan.splitlines()
        if '|' in line
        for url in _URL.findall(line)
    } - {''}


def _in_plan(
    conn: sqlite3.Connection, venture: str, kind: str, url: str
) -> bool:
    """Vrai si le dernier plan validé du business nomme ce site (le même,
    ou un de ses sous-domaines : ``account.mapbox.com`` pour
    ``mapbox.com``), et si un humain l'a validé. Un plan qui s'est
    appliqué tout seul, faute de réponse à son ticket, n'autorise aucun
    compte : le service passe alors par un ticket « Service »."""
    row = conn.execute(
        'SELECT id, plan FROM product_plans WHERE venture_id=? AND kind=?'
        " AND status='validated' ORDER BY created_at DESC, rowid DESC"
        ' LIMIT 1',
        (venture, kind),
    ).fetchone()
    if row is None:
        return False
    par_un_humain = conn.execute(
        "SELECT 1 FROM ticket_answers WHERE ref_table='product_plans'"
        " AND ref_id=? AND acte='valider' AND answered_by<>'serge'",
        (str(row[0]),),
    ).fetchone()
    host = _host(url)
    return bool(host and par_un_humain) and any(
        host == known
        or host.endswith(f'.{known}')
        or known.endswith(f'.{host}')
        for known in planned_hosts(str(row[1] or ''))
    )


def _service(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    cursor = conn.execute(
        'SELECT * FROM product_services WHERE id=?', (ident,)
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cursor.description], row, strict=True))


def _waiting(name: str, ticket: str = '') -> dict[str, Any]:
    """Ce que l'outil rend quand la tâche doit attendre le service."""
    return {
        'ok': True,
        'gel': True,
        'ticket_id': ticket,
        'attente': f'en attente du service « {name} »'
        + (f' (ticket {ticket})' if ticket else ' (compte et clé en cours)'),
        'detail': 'la tâche attend que le service soit branché',
    }


def _ask(conn: sqlite3.Connection, service: dict[str, Any], inv: str) -> str:
    """Le ticket « Service » : un service que le plan validé ne nomme pas
    attend l'accord d'un humain."""
    from serge.tickets.lifecycle import create_ticket, publish
    from serge.tickets.types import ticket_types

    business = conn.execute(
        'SELECT name FROM ventures WHERE id=?', (service['venture_id'],)
    ).fetchone()
    nom = str(business[0]) if business else str(service['venture_id'])
    ticket = create_ticket(
        conn,
        ticket_types(conn),
        'SERVICE',
        f'{nom} demande un service gratuit : {service["name"]}'[:80],
        {
            'en_bref': f'Le produit « {nom} » demande un compte sur'
            f' {service["url"]} ({service["name"]}), pour une clé d’API'
            ' gratuite.',
            'demande': str(service['purpose']) or '—',
            'contexte': 'Ce service n’est pas dans le plan validé.'
            ' « Valider » : Serge crée son compte sur ce site et va y'
            ' chercher une clé gratuite. « Rejeter » : le constructeur'
            ' fait sans.',
            'point_llm': inv,
        },
        creator=f'llm:{inv}',
    )
    conn.execute(
        "UPDATE tickets SET ref_table='product_services', ref_id=?,"
        ' venture_id=? WHERE id=?',
        (service['id'], service['venture_id'], ticket),
    )
    publish(conn, ticket)
    return ticket


def connect_service(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Brancher un service gratuit » : ``{nom, adresse,
    besoin}``, plus le business, le livrable et la tâche, figés en base.

    Rend ``{ok, variable}`` si le service est déjà branché ; sinon gèle la
    tâche (``gel``) le temps que le compte et la clé soient faits, ou
    refuse avec la raison.
    """
    venture = str(args.get('venture_id') or '')
    task = str(args.get('task_id') or '')
    name = str(args.get('nom') or '').strip().lower()
    url = str(args.get('adresse') or '').strip()
    kind = _KINDS.get(str(args.get('deliverable') or ''), 'poc')
    if not _NAME.fullmatch(name):
        return {
            'ok': False,
            'detail': 'le nom du service est un mot en minuscules, celui du'
            f' site : mapbox, openrouteservice. Reçu : « {name} »',
        }
    if not _URL.fullmatch(url) or not _host(url):
        return {
            'ok': False,
            'detail': 'l’adresse du service commence par https:// :'
            f' https://openrouteservice.org. Reçu : « {url} »',
        }
    row = conn.execute(
        'SELECT id, status, reason FROM product_services WHERE venture_id=?'
        ' AND name=?',
        (venture, name),
    ).fetchone()
    if row is not None:
        ident, status, reason = str(row[0]), str(row[1]), str(row[2])
        if status == CONNECTED:
            return {'ok': True, 'deja': True, 'variable': env_name(name)}
        if status in (FAILED, REFUSED):
            return {
                'ok': False,
                'detail': f'ce service n’a pas pu être branché : {reason}.'
                ' Fais sans lui, et dis-le dans ton compte rendu',
            }
        conn.execute(
            'UPDATE product_services SET task_id=?, updated_at=? WHERE id=?',
            (task, utcnow(), ident),
        )
        ticket = conn.execute(
            "SELECT id FROM tickets WHERE ref_table='product_services'"
            ' AND ref_id=? ORDER BY created_at DESC LIMIT 1',
            (ident,),
        ).fetchone()
        return _waiting(name, str(ticket[0]) if ticket else '')
    cap = int(policy_en_vigueur(conn)['web_accounts']['services_per_product'])
    have = conn.execute(
        'SELECT COUNT(*) FROM product_services WHERE venture_id=?'
        ' AND status<>?',
        (venture, REFUSED),
    ).fetchone()[0]
    if int(have) >= cap:
        return {
            'ok': False,
            'detail': f'ce produit a déjà {have} service(s) externe(s), le'
            f' maximum est {cap} (page Policy) : fais sans celui-ci',
        }
    planned = _in_plan(conn, venture, kind, url)
    now = utcnow()
    service = {
        'id': f'svc_{uuid.uuid4().hex[:12]}',
        'venture_id': venture,
        'name': name,
        'url': url,
        'purpose': str(args.get('besoin') or '').strip(),
        'env_name': env_name(name),
        'status': CONNECTING if planned else ASKED,
        'task_id': task,
        'created_at': now,
        'updated_at': now,
    }
    conn.execute(
        f'INSERT INTO product_services({", ".join(service)})'
        f' VALUES({", ".join("?" * len(service))})',
        list(service.values()),
    )
    append_event(
        conn,
        actor=f'invocation:{inv}',
        type='service.asked',
        venture_id=venture,
        payload={'service': name, 'url': url, 'in_plan': planned},
        rows=[('product_services', service['id'])],
    )
    if not planned:
        return _waiting(name, _ask(conn, service, inv))
    # La ligne « à brancher » réveille le pipeline : le compte, puis la clé.
    notify_rows_written(conn, 'product_services', [str(service['id'])])
    return _waiting(name)


def open_service_account(
    conn: sqlite3.Connection, tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Ouvrir le compte d'un service » : ``{account, url}``.

    Rend ``etat`` : ``actif`` (Serge a déjà son compte sur ce site, on va
    droit à la clé), ``a_creer`` (la ligne du compte est prête, il reste à
    le créer sur le site) ou ``refuse``, avec la raison.
    """
    name = str(args.get('account') or '').strip().lower()
    row = conn.execute(
        'SELECT status FROM web_accounts WHERE id=?', (name,)
    ).fetchone()
    if row is not None and row[0] == 'active':
        return {'ok': True, 'etat': 'actif', 'compte': name}
    opened = web_accounts.open_account(conn, tool, args, inv)
    if not opened.get('ok'):
        raison = str(opened.get('detail') or 'compte refusé')
        return {'ok': False, 'etat': 'refuse', 'raison': raison}
    return {'ok': True, 'etat': 'a_creer', 'compte': name}


def keep_key(conn: sqlite3.Connection, service_id: str, value: str) -> str:
    """Garde la clé d'un service, chiffrée ; rend ``''``, ou la raison du
    refus. La clé n'est écrite nulle part ailleurs."""
    value = value.strip()
    if _service(conn, service_id) is None:
        return 'aucun service à brancher pour cette tâche'
    if not _KEY.fullmatch(value):
        return (
            'ce qui est visé ne ressemble pas à une clé d’API (d’un seul'
            ' tenant, au moins 12 caractères) : vise le champ ou le texte'
            ' qui contient la clé, et elle seule'
        )
    conn.execute(
        'UPDATE product_services SET key_enc=?, updated_at=? WHERE id=?',
        (web_accounts.seal(value), utcnow(), service_id),
    )
    return ''


def finish_service(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Finir le branchement d'un service » : ``{service_id,
    ok, raison}``. Note le résultat et fait repartir la tâche de
    construction qui attendait, avec ce résultat.

    Un service dit branché sans clé gardée ne l'est pas.
    """
    service = _service(conn, str(args.get('service_id') or ''))
    if service is None:
        return {'ok': False, 'branche': 'non', 'raison': 'service inconnu'}
    raison = str(args.get('raison') or '').strip()
    done = str(args.get('ok') or '') == 'oui'
    if done and not service['key_enc']:
        done, raison = False, 'la clé n’a pas été gardée'
    garde = raison
    if service['status'] == REFUSED:
        # Ce que l'humain a écrit en refusant reste la raison en base.
        garde = str(service['reason'])
        raison = 'un humain l’a refusé' + (f' ({garde})' if garde else '')
        done = False
    status = CONNECTED if done else service['status']
    if not done and status != REFUSED:
        status = FAILED
    conn.execute(
        'UPDATE product_services SET status=?, reason=?, updated_at=?'
        ' WHERE id=?',
        (status, '' if done else garde[:500], utcnow(), service['id']),
    )
    name, variable = str(service['name']), str(service['env_name'])
    if done:
        message = (
            f'Le service « {name} » est branché : sa clé est dans la'
            f' variable d’environnement {variable}, dans le chantier, en'
            ' staging et en prod. Lis-la au démarrage, ne l’écris nulle part.'
        )
    else:
        message = (
            f'Le service « {name} » n’a pas pu être branché : {raison}.'
            ' Fais sans lui, et dis-le dans ton compte rendu.'
        )
    woken = bool(service['task_id']) and thaw_task(
        conn,
        str(service['task_id']),
        f'{message}\nNe redemande pas ce service.',
    )
    append_event(
        conn,
        actor=f'invocation:{inv}',
        type='service.connected' if done else 'service.failed',
        venture_id=str(service['venture_id']),
        payload={'service': name, 'raison': '' if done else raison[:500]},
        rows=[('product_services', service['id'])],
    )
    return {
        'ok': True,
        'branche': 'oui' if done else 'non',
        'service': name,
        'titre': f'Un service est branché : {name}'
        if done
        else f'Un service n’a pas pu être branché : {name}',
        'raison': message,
        'tache_relancee': woken,
    }


def service_keys(conn: sqlite3.Connection, venture: str) -> dict[str, str]:
    """Les clés des services branchés d'un business, par variable
    d'environnement. Une clé illisible (le coffre a changé) est sautée."""
    keys = {}
    for variable, sealed in conn.execute(
        'SELECT env_name, key_enc FROM product_services WHERE venture_id=?'
        " AND status=? AND key_enc<>''",
        (venture, CONNECTED),
    ):
        try:
            keys[str(variable)] = web_accounts.unseal(str(sealed))
        except web_accounts.AccountError:
            continue
    return keys
