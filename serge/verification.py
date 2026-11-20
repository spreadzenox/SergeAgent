#!/usr/bin/env python3
"""Ce que Serge a reçu pendant une tâche : les e-mails et les SMS de
vérification.

Créer un compte sur un site, ou s'y reconnecter, demande souvent un code
ou un lien envoyé par e-mail ou par SMS. Cette capacité rend ce que Serge a
reçu depuis le début de la tâche, et rien d'autre :

- **les e-mails** de sa boîte que la relève n'a rattachés à aucun contact
  (``inbound_events``, état ``unattached``) : l'e-mail d'un prospect ou
  d'un client ne passe donc jamais par ici ;
- **les SMS** reçus sur son numéro (``state/sms/inbound.db``), avec le code
  que Serge y a repéré et les liens de leur texte. Ils n'arrivent que si
  le téléphone qui porte la carte SIM les transmet au serveur : quand
  aucun n'est jamais arrivé, la capacité le dit, pour que l'invocation
  n'attende pas un code qui ne viendra pas.

La boîte est relevée toutes les 2 minutes : la capacité attend qu'un
message arrive, au plus le temps réglé (page Policy, « Comptes web »).

Exemple : après « S'inscrire » sur un forum, l'invocation l'appelle et
reçoit ``{emails: [{de: 'noreply@forum.example', objet: 'Confirmez votre
adresse', liens: ['https://forum.example/confirm?t=…']}], sms: []}``.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from serge.db.store import utcnow
from serge.paths import system_root
from serge.policy_store import policy_en_vigueur
from serge.sandbox.courriel import LIENS, TEXTE_MAX

# Au plus tant de messages de chaque sorte, les plus récents.
LIMITE = 5


def _emails(conn: sqlite3.Connection, since: str) -> list[dict[str, Any]]:
    return [
        {
            'de': str(address),
            'objet': str(subject),
            'date': str(received),
            'texte': str(body)[:TEXTE_MAX],
            'liens': list(dict.fromkeys(LIENS.findall(str(body)))),
        }
        for address, subject, body, received in conn.execute(
            'SELECT address, subject, body, received_at FROM inbound_events'
            " WHERE channel='email' AND status='unattached'"
            ' AND received_at>=? ORDER BY received_at DESC LIMIT ?',
            (since, LIMITE),
        )
    ]


def _base_sms() -> Path:
    return system_root() / 'state/sms/inbound.db'


def _jamais_de_sms() -> bool:
    """Vrai tant qu'aucun SMS n'est arrivé sur ce serveur."""
    base = _base_sms()
    if not base.is_file():
        return True
    with closing(sqlite3.connect(f'file:{base}?mode=ro', uri=True)) as sms:
        return (
            sms.execute('SELECT 1 FROM inbound_sms LIMIT 1').fetchone() is None
        )


def _sms(since: str) -> list[dict[str, Any]]:
    base = _base_sms()
    if not base.is_file():
        return []
    debut = datetime.fromisoformat(since)
    messages = []
    with closing(sqlite3.connect(f'file:{base}?mode=ro', uri=True)) as sms:
        for sender, body, otp, received in sms.execute(
            'SELECT sender, body, otp, received_at FROM inbound_sms'
            ' ORDER BY received_at DESC LIMIT 50'
        ):
            quand = datetime.fromisoformat(
                str(received).replace('Z', '+00:00')
            )
            if quand.astimezone(UTC) >= debut:
                messages.append(
                    {
                        'de': str(sender),
                        'texte': str(body),
                        'code': str(otp or ''),
                        'liens': list(dict.fromkeys(LIENS.findall(str(body)))),
                        'date': str(received),
                    }
                )
    return messages[:LIMITE]


def received_since_task(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    _invocation_id: str,
) -> dict[str, Any]:
    """Capacité « Mes messages de vérification » : les e-mails et les SMS
    arrivés depuis le début de la tâche ; attend qu'il en arrive un."""
    row = conn.execute(
        'SELECT started_at FROM tasks WHERE id=?',
        (str(args.get('task_id') or ''),),
    ).fetchone()
    since = str(row[0]) if row and row[0] else utcnow()
    attendre = args.get('wait') not in (False, 'false', '0', 'non')
    reglages = policy_en_vigueur(conn)['web_accounts']
    fin = time.monotonic() + (
        float(reglages['verification_wait_s']) if attendre else 0
    )
    while True:
        # Ce que la relève vient d'écrire depuis une autre file se lit
        # après avoir rendu la main à la base.
        conn.commit()
        emails, sms = _emails(conn, since), _sms(since)
        if emails or sms or time.monotonic() >= fin:
            break
        time.sleep(5)
    resultat: dict[str, Any] = {'ok': True, 'emails': emails, 'sms': sms}
    if not emails and not sms:
        resultat['detail'] = (
            'rien reçu depuis le début de la tâche ; la boîte e-mail est'
            ' relevée toutes les 2 minutes : rappelle cet outil pour'
            ' attendre encore'
        )
    if not sms and _jamais_de_sms():
        resultat['sms_jamais_recu'] = (
            'aucun SMS n’est encore arrivé sur ce serveur : si tu attends'
            ' un code par SMS, le téléphone qui porte la carte SIM ne l’a'
            ' pas transmis ; ne redonne pas le numéro, dis-le dans ton'
            ' compte rendu'
        )
    return resultat
