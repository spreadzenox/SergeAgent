#!/usr/bin/env python3
"""Les adresses de connexion d'un compte web, validées par un humain.

Le mot de passe d'un compte ne se tape que sur le site du compte
(``serge/web_accounts.py``). Quelques sites font pourtant leur connexion
sur un autre domaine : un compte sur ``outlook.com`` se connecte sur
``login.live.com``. Un compte garde donc ses adresses de connexion
validées (``web_accounts.login_hosts``, des hôtes), et son mot de passe se
tape sur son site ou sur l'une d'elles, nulle part ailleurs.

Une adresse n'entre dans cette liste que par un humain. Quand le mot de
passe est refusé sur un autre domaine, un ticket « Adresse de connexion »
demande : « Le compte « outlook » se connecte sur login.live.com. Est-ce
bien sa page de connexion ? ». La tâche s'arrête et attend. « Oui, c'est
sa connexion » : l'hôte est gardé pour ce compte, la tâche repart du début
et Serge tape lui-même. « Non » : rien n'y sera tapé, et la question n'est
plus posée pour cette adresse.

L'hôte est celui du cadre où est le champ, lu par le code dans le
navigateur : un modèle ne le choisit pas, et aucune invocation n'écrit la
liste. Le mot de passe n'est montré à personne, ni dans le ticket ni
ailleurs.
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow
from serge.interpreter.tasks import thaw_task
from serge.tickets.lifecycle import OPENISH, create_ticket, publish
from serge.tickets.types import ticket_types
from serge.web_accounts import meme_site, site

# Le type du ticket, et ses deux boutons.
TICKET = 'CONNEXION_COMPTE'
OUI, NON = 'cest_sa_connexion', 'non'
TITRE_MAX = 80
# Un hôte tel que le navigateur le rend : des lettres sans accent (un nom
# accentué arrive en « xn-- »), des chiffres, des points et des tirets.
_HOTE = re.compile(r'[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?')
_DU_TICKET = (
    " FROM tickets t WHERE t.type=? AND t.ref_table='web_accounts'"
    " AND t.ref_id=? AND json_extract(t.payload_json, '$.hote')=?"
)


def validated(conn: sqlite3.Connection, account: str) -> list[str]:
    """Les adresses de connexion validées d'un compte, dans l'ordre où
    elles l'ont été."""
    row = conn.execute(
        'SELECT login_hosts FROM web_accounts WHERE id=?', (account,)
    ).fetchone()
    return [h for h in str(row[0] if row else '').split(',') if h]


def check(
    conn: sqlite3.Connection, account: str, host: str, task_id: str
) -> tuple[str, str]:
    """Le mot de passe du compte peut-il se taper sur une page de cet hôte ?

    Returns:
        ``('', '')`` si oui. Sinon le refus à dire au modèle, et le ticket
        qui vient de poser la question à un humain (la tâche l'attend), ou
        ``''`` : la question est déjà posée, ou un humain a déjà dit non.
    """
    host = host.lower()
    du_compte = site(conn, account)
    if meme_site(host, du_compte) or host in validated(conn, account):
        return '', ''
    refus = (
        f'mot de passe non tapé : cette page est sur {host or "?"}, et le'
        f' compte « {account} » sur {du_compte}'
    )
    if not _HOTE.fullmatch(host) or TICKET not in ticket_types(conn):
        return f'{refus}. Reviens sur le site du compte', ''
    cible = (TICKET, account, host)
    reponse = conn.execute(
        'SELECT a.acte FROM ticket_answers a WHERE a.acte IN (?, ?)'
        " AND a.answered_by<>'serge' AND a.ticket_id IN (SELECT t.id"
        f'{_DU_TICKET}) ORDER BY a.created_at DESC, a.rowid DESC LIMIT 1',
        (OUI, NON, *cible),
    ).fetchone()
    if reponse is not None and reponse[0] == NON:
        return (
            f'{refus}. Un humain a répondu que ce n’est pas sa page de'
            ' connexion : n’y tape rien, et reviens sur le site du compte',
            '',
        )
    if conn.execute(
        f'SELECT 1{_DU_TICKET}'
        f' AND t.state IN ({",".join("?" * len(OPENISH))})',
        (*cible, *sorted(OPENISH)),
    ).fetchone():
        return (
            f'{refus}. Un ticket demande déjà à un humain si c’est bien sa'
            ' page de connexion : d’ici sa réponse, ne t’y connecte pas, et'
            ' dis-le dans ta réponse',
            '',
        )
    return (
        f'{refus}. Un ticket demande à un humain si c’est bien sa page de'
        ' connexion : la tâche attend sa réponse',
        _ask(conn, account, host, du_compte, task_id),
    )


def _ask(
    conn: sqlite3.Connection,
    account: str,
    host: str,
    du_compte: str,
    task_id: str,
) -> str:
    """Ouvre le ticket « Adresse de connexion » ; rend son numéro."""
    ticket_id = create_ticket(
        conn,
        ticket_types(conn),
        TICKET,
        f'Le compte « {account} » se connecte sur {host} ?'[:TITRE_MAX],
        {
            'La question': f'Le compte « {account} » se connecte sur {host}.'
            ' Est-ce bien sa page de connexion ?',
            'Le compte': f'« {account} », sur {du_compte}',
            'Pourquoi': 'Serge ne tape le mot de passe d’un compte que sur'
            ' le site de ce compte, et cette page est sur un autre domaine.'
            ' « Oui, c’est sa connexion » : cette adresse est gardée pour ce'
            ' compte, la tâche repart et Serge tape lui-même. « Non » : rien'
            ' n’y sera tapé. Ne réponds oui que si tu reconnais l’adresse de'
            ' connexion officielle du site. Le mot de passe n’est montré à'
            ' personne.',
            # Lu par le code quand un humain répond : jamais par un modèle.
            'hote': host,
        },
        creator='serge',
    )
    # Le ticket parle du compte, et garde la tâche à faire repartir.
    conn.execute(
        "UPDATE tickets SET ref_table='web_accounts', ref_id=?, task_id=?"
        ' WHERE id=?',
        (account, task_id, ticket_id),
    )
    publish(conn, ticket_id)
    _note(conn, 'serge', 'account.login_host_asked', account, host, ticket_id)
    return ticket_id


def _note(
    conn: sqlite3.Connection,
    actor: str,
    kind: str,
    account: str,
    host: str,
    ticket_id: str,
) -> None:
    append_event(
        conn,
        actor=actor,
        type=kind,
        payload={'account': account, 'host': host, 'ticket': ticket_id},
        rows=[('web_accounts', account)],
    )


def answer(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Appliquer la réponse sur une adresse de connexion » :
    ``{answer}``, une réponse à un ticket « Adresse de connexion » (une
    ligne de ``ticket_answers``).

    Le compte et l'hôte sont lus dans le ticket, où le code les a écrits.
    Seul le « oui » d'un humain ajoute l'hôte au compte : son « non », ou
    un ticket expiré sans réponse (la décision par défaut, notée par
    Serge), ne valide rien. Dans tous les cas, la tâche qui attendait
    repart, avec ce qui a été répondu.
    """
    row = conn.execute(
        'SELECT a.acte, a.answered_by, a.ticket_id, t.ref_id, t.task_id,'
        ' t.payload_json FROM ticket_answers a JOIN tickets t'
        ' ON t.id=a.ticket_id WHERE a.id=? AND t.type=?'
        " AND t.ref_table='web_accounts'",
        (str(args.get('answer') or ''), TICKET),
    ).fetchone()
    if row is None:
        return {'ok': False, 'detail': 'pas une réponse à ce ticket'}
    acte, par, ticket_id, account, task_id, payload = (str(x) for x in row)
    host = str(json.loads(payload or '{}').get('hote') or '')
    if not _HOTE.fullmatch(host):
        return {'ok': False, 'detail': 'ticket sans adresse'}
    humain = par != 'serge'
    valide, refuse = humain and acte == OUI, humain and acte == NON
    reste = (
        f' la page de connexion du compte « {account} » : n’y tape rien.'
        ' Reviens sur le site du compte ; si tu ne peux pas t’y connecter,'
        ' dis-le dans ta réponse.'
    )
    if valide:
        hosts = validated(conn, account)
        if host not in hosts:
            conn.execute(
                'UPDATE web_accounts SET login_hosts=?, updated_at=?'
                ' WHERE id=?',
                (','.join([*hosts, host]), utcnow(), account),
            )
        message = (
            f'Un humain a validé {host} comme page de connexion du compte'
            f' « {account} » : refais ton parcours ; cette fois, le mot de'
            ' passe s’y tapera.'
        )
    elif refuse:
        message = f'Un humain a répondu que {host} n’est pas{reste}'
    else:
        message = f'Personne n’a dit si {host} est{reste}'
    suite = 'validated' if valide else 'refused' if refuse else 'unanswered'
    _note(conn, par, f'account.login_host_{suite}', account, host, ticket_id)
    return {
        'ok': True,
        'compte': account,
        'adresse': host,
        'validee': 'oui' if valide else 'non',
        'tache_relancee': bool(task_id) and thaw_task(conn, task_id, message),
    }
