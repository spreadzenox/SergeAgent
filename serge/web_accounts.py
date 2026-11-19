#!/usr/bin/env python3
"""Les comptes web de Serge : un compte par site, ses secrets, sa garde.

Un compte (``web_accounts``) est nommé d'un mot, celui du site :
``reddit``, ``linkedin``. Une invocation à qui la base donne ce nom sur
ses outils de navigateur navigue connectée : sa session s'ouvre avec les
cookies gardés, et ils sont gardés de nouveau quand elle se ferme
(``serge/sandbox/sessions.py``).

Deux secrets, chiffrés en base par la clé du coffre de l'instance
(``secrets/credential-vault.key``), jamais montrés à un modèle ni à
Mission Control :

- **le mot de passe** : Serge le choisit lui-même à la première demande
  (24 caractères au hasard) et le tape dans la page à la place du modèle ;
- **la session** : les cookies du site, et ce qu'il garde dans le
  navigateur. Avec elle, ouvrir le site suffit pour être connecté.

**La garde.** Un compte trop sollicité se fait fermer. Chaque action faite
avec un compte est comptée, et refusée au-delà du plafond du jour (page
Policy, « Comptes web »). Un compte ne sert qu'à une tâche à la fois : une
seconde attend que la première ait fini.

Exemple : la tâche « Fouiller un réseau » ouvre ``reddit`` ; elle est
connectée d'emblée, fait 40 actions, et le compteur du jour passe de 12 à
52 sur 200.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import string
from datetime import UTC, datetime, timedelta
from typing import Any

from serge.db.store import utcnow
from serge.paths import config_root
from serge.policy_store import policy_en_vigueur
from serge.secrets import CLE_DU_COFFRE

# Le nom que le modèle donne à « taper un secret » pour le mot de passe du
# compte de sa session.
PASSWORD_NAME = 'mot_de_passe_du_compte'
# Une tâche morte sans avoir rendu son compte ne le garde pas plus
# longtemps que ça.
LEASE = timedelta(minutes=45)
_SIGNS = '!#%+-=?@'


class AccountError(RuntimeError):
    """Un compte web ne peut pas servir ; le message dit pourquoi."""


def _fernet() -> Any:
    from cryptography.fernet import Fernet

    try:
        key = (config_root() / 'secrets' / CLE_DU_COFFRE).read_bytes().strip()
        return Fernet(key)
    except (OSError, ValueError) as exc:
        raise AccountError(
            f'la clé du coffre manque ou est illisible (secrets/{CLE_DU_COFFRE})'
        ) from exc


def seal(text: str) -> str:
    """Chiffre un secret pour la base."""
    return _fernet().encrypt(text.encode('utf-8')).decode('ascii')


def unseal(token: str) -> str:
    """Déchiffre un secret de la base ; ``''`` s'il n'y en a pas.

    Raises:
        AccountError: La clé du coffre a changé, ou manque.
    """
    if not token:
        return ''
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(token.encode('ascii')).decode('utf-8')
    except InvalidToken as exc:
        raise AccountError(
            'un secret de compte ne se déchiffre plus : la clé du coffre a'
            ' changé'
        ) from exc


def _row(conn: sqlite3.Connection, name: str) -> tuple[Any, ...]:
    row = conn.execute(
        'SELECT status, password_enc, session_enc, used_by, used_since'
        ' FROM web_accounts WHERE id=?',
        (name,),
    ).fetchone()
    if row is None:
        raise AccountError(
            f'pas de compte « {name} » (Mission Control, page Système,'
            ' « Comptes web »)'
        )
    return tuple(row)


def new_password() -> str:
    """Un mot de passe au hasard, qui passe les règles des sites : 24
    caractères, avec majuscule, minuscule, chiffre et signe."""
    alphabet = string.ascii_letters + string.digits + _SIGNS
    while True:
        value = ''.join(secrets.choice(alphabet) for _ in range(24))
        kinds = (
            string.ascii_lowercase,
            string.ascii_uppercase,
            string.digits,
            _SIGNS,
        )
        if all(any(c in kind for c in value) for kind in kinds):
            return value


def set_password(conn: sqlite3.Connection, name: str, value: str) -> None:
    """Range le mot de passe d'un compte, chiffré."""
    conn.execute(
        'UPDATE web_accounts SET password_enc=?, updated_at=? WHERE id=?',
        (seal(value), utcnow(), name),
    )


def password(conn: sqlite3.Connection, name: str) -> str:
    """Le mot de passe d'un compte ; choisi et gardé à la première demande
    (un compte en cours de création).

    Raises:
        AccountError: Pas de compte de ce nom, ou pas de clé du coffre.
    """
    value = unseal(str(_row(conn, name)[1]))
    if not value:
        value = new_password()
        set_password(conn, name, value)
        # Gardé tout de suite : un mot de passe tapé dans un formulaire
        # d'inscription ne doit pas se perdre si la tâche s'arrête.
        conn.commit()
    return value


def register(
    conn: sqlite3.Connection,
    name: str,
    url: str,
    login: str,
    secret: str,
) -> None:
    """Enregistre un compte créé à la main : son identifiant et son mot de
    passe. Un compte du même nom garde sa session.

    Raises:
        AccountError: Un champ manque, ou pas de clé du coffre.
    """
    name, url, login = name.strip().lower(), url.strip(), login.strip()
    if not name or not url or not login or not secret:
        raise AccountError(
            'le nom du compte, l’adresse du site, l’identifiant et le mot'
            ' de passe sont tous demandés'
        )
    now = utcnow()
    conn.execute(
        'INSERT INTO web_accounts(id, url, login, password_enc, status,'
        " created_at, updated_at) VALUES(?,?,?,?,'active',?,?)"
        ' ON CONFLICT(id) DO UPDATE SET url=excluded.url,'
        ' login=excluded.login, password_enc=excluded.password_enc,'
        " status='active', updated_at=excluded.updated_at",
        (name, url, login, seal(secret), now, now),
    )


def take(conn: sqlite3.Connection, name: str, task_id: str) -> dict[str, Any]:
    """Prend le compte pour une tâche, et rend sa session gardée (``{}`` :
    pas encore de session).

    Raises:
        AccountError: Pas de compte de ce nom, compte fermé par le site, ou
            déjà pris par une autre tâche.
    """
    status, _, session_enc, used_by, used_since = _row(conn, name)
    if status == 'blocked':
        raise AccountError(
            f'le compte « {name} » est marqué fermé par le site : un humain'
            ' doit le rouvrir (Mission Control, page Système)'
        )
    limit = (datetime.now(UTC) - LEASE).isoformat()
    if used_by and used_by != task_id and str(used_since) > limit:
        raise AccountError(
            f'le compte « {name} » sert déjà à une autre tâche : réessaie'
            ' dans quelques minutes'
        )
    now = utcnow()
    conn.execute(
        'UPDATE web_accounts SET used_by=?, used_since=?, last_used_at=?'
        ' WHERE id=?',
        (task_id, now, now, name),
    )
    # Visible tout de suite des autres files : elles attendront.
    conn.commit()
    state = unseal(str(session_enc))
    return json.loads(state) if state else {}


def release(
    conn: sqlite3.Connection,
    name: str,
    task_id: str,
    state: dict[str, Any] | None,
) -> None:
    """Rend le compte, et garde sa session (``None`` : elle n'a pas pu être
    lue, l'ancienne est gardée)."""
    now = utcnow()
    if state is not None:
        conn.execute(
            'UPDATE web_accounts SET session_enc=?, session_saved_at=?'
            ' WHERE id=?',
            (seal(json.dumps(state)), now, name),
        )
    conn.execute(
        "UPDATE web_accounts SET used_by='', used_since='' WHERE id=?"
        ' AND used_by=?',
        (name, task_id),
    )
    conn.commit()


def actions_today(conn: sqlite3.Connection, name: str) -> int:
    """Les actions déjà faites avec ce compte aujourd'hui (jour UTC)."""
    row = conn.execute(
        'SELECT actions FROM web_account_days WHERE account_id=? AND day=?',
        (name, utcnow()[:10]),
    ).fetchone()
    return int(row[0]) if row else 0


def daily_cap(conn: sqlite3.Connection) -> int:
    """Le plafond d'actions par jour d'un compte (page Policy)."""
    return int(policy_en_vigueur(conn)['web_accounts']['max_actions_per_day'])


def count_action(conn: sqlite3.Connection, name: str) -> str:
    """La garde : compte une action de plus avec ce compte, ou rend le
    refus si le plafond du jour est atteint."""
    cap, done = daily_cap(conn), actions_today(conn, name)
    if done >= cap:
        return (
            f'le compte « {name} » a fait ses {cap} actions du jour : plus'
            ' rien avec lui avant demain. Arrête-toi là et rends ce que tu'
            ' as.'
        )
    conn.execute(
        'INSERT INTO web_account_days(account_id, day, actions)'
        ' VALUES(?,?,1) ON CONFLICT(account_id, day)'
        ' DO UPDATE SET actions=actions+1',
        (name, utcnow()[:10]),
    )
    return ''
