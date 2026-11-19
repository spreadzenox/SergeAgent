#!/usr/bin/env python3
"""Migration v56 : les canaux qui passent par le navigateur (lot 13).

``canaux.account`` : le compte web de Serge (``web_accounts``) avec lequel
le canal envoie et relève. Vide pour un canal porté par du code (l'e-mail,
l'appel). Exemple : le canal ``linkedin`` a le compte ``linkedin``.
``send_invocation`` et ``poll_invocation`` : les invocations à qui il
confie l'envoi d'un message et la relève de sa messagerie.

``canaux.poll_pace`` : le rythme de sa relève. ``fast`` : toutes les 2
minutes (l'e-mail) ; ``slow`` : quelques fois par jour, parce qu'une
invocation doit ouvrir la messagerie dans le navigateur ; vide : il ne se
relève pas (l'appel).

Un canal du navigateur est branché, et se relève, quand son compte est en
service. Trois déclencheurs de la base tiennent ``connected``, ``etat``,
``polls`` et ``poll_pace`` à jour dès qu'un compte est créé, change d'état
ou est retiré : rien à recalculer dans le code.
"""

from __future__ import annotations

import sqlite3

# Un canal du navigateur est branché, et se relève, quand son compte est
# en service.
_SERVICE = (
    'EXISTS (SELECT 1 FROM web_accounts a WHERE a.id = canaux.account'
    " AND a.status = 'active')"
)
SYNC = f"""
UPDATE canaux SET
    connected = {_SERVICE},
    polls = {_SERVICE},
    etat = CASE WHEN {_SERVICE} THEN 'branche' ELSE 'prevu' END,
    poll_pace = CASE WHEN {_SERVICE} THEN 'slow' ELSE '' END
WHERE account <> ''
"""

TRIGGERS = f"""
CREATE TRIGGER IF NOT EXISTS canaux_suit_compte_cree
AFTER INSERT ON web_accounts BEGIN {SYNC} AND account = NEW.id; END;
CREATE TRIGGER IF NOT EXISTS canaux_suit_compte_change
AFTER UPDATE OF status ON web_accounts BEGIN
    {SYNC} AND account = NEW.id; END;
CREATE TRIGGER IF NOT EXISTS canaux_suit_compte_retire
AFTER DELETE ON web_accounts BEGIN {SYNC} AND account = OLD.id; END;
"""


def apply_v056(connection: sqlite3.Connection) -> None:
    """Ajoute le compte et le rythme de relève d'un canal, et ce qui tient
    son état à jour."""
    have = {str(r[1]) for r in connection.execute('PRAGMA table_info(canaux)')}
    for name in ('account', 'poll_pace', 'send_invocation', 'poll_invocation'):
        if name not in have:
            connection.execute(
                f"ALTER TABLE canaux ADD COLUMN {name} TEXT NOT NULL DEFAULT ''"
            )
    connection.execute("UPDATE canaux SET poll_pace='fast' WHERE polls=1")
    connection.executescript(TRIGGERS)
