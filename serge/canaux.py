#!/usr/bin/env python3
"""Le catalogue des canaux : une ligne de ``canaux`` par canal connu.

Deux sortes de canaux :

- **porté par du code** (l'e-mail, l'appel) : son adaptateur est dans
  ``serge/channels/adapters.py`` (``ADAPTERS``). Il est **branché** quand
  il est configuré sur ce serveur. Exemple : l'e-mail est seulement
  **prévu** sur une instance sans boîte Gmail ni SMTP/IMAP ;
- **par le navigateur** (LinkedIn, Instagram, X, lot 13) : il est décrit
  en base (section ``web_channels`` de ``config/pipeline.yaml``), avec le
  compte web de Serge qui lui sert (``account``). Il est branché quand ce
  compte est en service ; la base tient cet état à jour toute seule
  (``serge/db/v056.py``). Son adaptateur est le même pour tous
  (``serge/channels/web.py``).

La ligne dit aussi la sorte d'adresse du canal, s'il se relève et à quel
rythme (``poll_pace`` : ``fast``, toutes les 2 minutes ; ``slow``, quelques
fois par jour). Une fiche « prévu » dit ce qui manque dans Mission
Control. Le catalogue est rempli au démarrage ; la dernière relève
(``polled_at``) est gardée.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.channels.adapters import ADAPTERS
from serge.db.v056 import SYNC


def ensure_canaux(conn: sqlite3.Connection) -> None:
    """Remplit le catalogue : un canal par adaptateur du code.

    Le titre et le texte ne sont posés qu'à la création ; l'état, la sorte
    d'adresse et le fait de se relever suivent le code.

    Args:
        conn: Connexion à la base (commit par l'appelant).
    """
    known = {
        a.id: (a.title, a.doc, a.address_channel, a.code_path, a.poll)
        for a in ADAPTERS.values()
    }
    for ident, (titre, doc, address, path, poll) in known.items():
        branche = ADAPTERS[ident].ready()
        releve = branche and poll is not None
        values = (
            path,
            'branche' if branche else 'prevu',
            address,
            int(branche),
            int(releve),
            'fast' if releve else '',
        )
        if conn.execute(
            'SELECT 1 FROM canaux WHERE id=?', (ident,)
        ).fetchone():
            conn.execute(
                'UPDATE canaux SET code_path=?, etat=?, address_channel=?,'
                ' connected=?, polls=?, poll_pace=? WHERE id=?',
                (*values, ident),
            )
            continue
        conn.execute(
            'INSERT INTO canaux(id, titre, doc_md, code_path, etat,'
            ' address_channel, connected, polls, poll_pace)'
            ' VALUES(?,?,?,?,?,?,?,?,?)',
            (ident, titre, doc, *values),
        )
    # Un canal du navigateur n'a pas d'adaptateur à lui : il reste.
    holes = ','.join('?' * len(known))
    conn.execute(
        f"DELETE FROM canaux WHERE account='' AND id NOT IN ({holes})",
        tuple(known),
    )
    conn.execute(SYNC)


def seed_web_channels(conn: sqlite3.Connection, items: Any) -> None:
    """Ajoute les canaux du navigateur décrits dans ``pipeline.yaml`` :
    ``{id, title, doc, account, send, poll}`` (``send`` et ``poll`` : les
    invocations qui envoient et qui relèvent). Un canal déjà en base n'est
    pas touché.

    Raises:
        ValueError: Un canal mal décrit, ou du même nom qu'un canal du code.
    """
    for item in items or []:
        ident, account = (
            str(item.get('id') or ''),
            str(item.get('account') or ''),
        )
        if not ident or not account or ident in ADAPTERS:
            raise ValueError(f'web_channels : canal mal décrit ({item})')
        conn.execute(
            'INSERT OR IGNORE INTO canaux(id, titre, doc_md, code_path, etat,'
            ' address_channel, connected, polls, poll_pace, account,'
            ' send_invocation, poll_invocation)'
            " VALUES(?,?,?,'serge/channels/web.py','prevu',?,0,1,'slow',?,?,?)",
            (
                ident,
                str(item.get('title') or ident),
                str(item.get('doc') or ''),
                ident,
                account,
                str(item.get('send') or ''),
                str(item.get('poll') or ''),
            ),
        )
    conn.execute(SYNC)


def canal_par_id(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Une ligne canaux, ou None."""
    ensure_canaux(conn)
    row = conn.execute(
        'SELECT id, titre, doc_md, code_path, code_sha, etat,'
        ' files_sha, updated_at, account FROM canaux WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    return {
        'id': str(row[0]),
        'titre': str(row[1]),
        'doc_md': str(row[2]),
        'code_path': str(row[3] or ''),
        'code_sha': str(row[4] or ''),
        'etat': str(row[5]),
        'files_sha': str(row[6] or ''),
        'updated_at': str(row[7] or ''),
        'account': str(row[8] or ''),
    }


def fiche_canal(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Fiche Mission Control d'un canal.

    Args:
        conn: Connexion à la base.
        ident: Id du canal.

    Returns:
        Contenu de la fiche, ou None.
    """
    found = canal_par_id(conn, ident)
    if found is None:
        return None
    champs = [{'k': 'État', 'v': found['etat']}]
    if found['account']:
        champs.append({'k': 'Compte web', 'v': found['account']})
    if found['code_path']:
        champs.append({'k': 'Fichier', 'v': found['code_path']})
    champs.append(
        {'k': 'Dernière modification', 'v': found['updated_at'] or '—'}
    )
    cadres = []
    if found['etat'] == 'prevu' and found['account']:
        cadres.append(
            {
                'titre': 'État',
                'todo': 'Pas branché : Serge n’a pas de compte'
                f' « {found["account"]} » en service. Le créer ou'
                ' l’enregistrer : page Système, « Comptes web ».',
            }
        )
    elif found['etat'] == 'prevu':
        cadres.append(
            {
                'titre': 'État',
                'todo': 'Pas branché sur ce serveur : son adaptateur'
                ' n’existe pas encore dans le code (serge/channels/), ou'
                ' le canal n’est pas configuré (pour l’e-mail : une boîte'
                ' Gmail ou SMTP/IMAP dans le fichier d’instance).',
            }
        )
    return {
        'type': 'canal',
        'id': found['id'],
        'titre': found['titre'],
        'pourquoi': found['doc_md'],
        'champs': champs,
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
