#!/usr/bin/env python3
"""Projecteur P1 : les îlots de la page Système, un par morceau qui tourne.

Chaque îlot dit sa santé, son activité, un résumé et ses détails : les
files de tâches (avec leurs deux services), l'e-mail, la voix (avec le
pont vocal), Discord (le bot, le forum des tickets, les administrateurs),
l'écoute du web et les garde-fous. Fenêtre de 24 h ; une tâche en cours
depuis plus de 30 min est suspecte. L'état d'un service se lit avec
``systemctl --user`` (Mission Control tourne sous le même compte).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from collections.abc import Mapping
from typing import Any

from serge.discord.forum import ECHEC, ECHEC_MODIF, forum_tickets
from serge.mc.proj_outils import avant_iso
from serge.mc.proj_taches import compte_taches, plafond_atteint, prochaines

ETATS_SERVICE = {
    'active': 'en marche',
    'inactive': 'arrêté',
    'failed': 'en panne',
    'activating': 'en démarrage',
    'inconnu': 'état inconnu',
}


def etat_service(unit: str) -> str:
    """L'état d'un service systemd (``active``, ``inactive``, ``failed``…),
    ``inconnu`` sans systemctl ou si la sonde ne répond pas en 1,5 s."""
    if shutil.which('systemctl') is None:
        return 'inconnu'
    try:
        p = subprocess.run(
            ['systemctl', '--user', 'is-active', unit],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 'inconnu'
    return p.stdout.strip() or 'inconnu'


def _service(titre: str, etat: str) -> str:
    return f'{titre} : {ETATS_SERVICE.get(etat, etat)}.'


def _arrete(etat: str) -> bool:
    """Vrai pour un service dont l'état est connu et qui ne tourne pas."""
    return etat not in ('active', 'activating', 'inconnu')


def _compte(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _ilot(
    ilot_id: str,
    label: str,
    sante: str,
    activite: float,
    resume: str,
    details: list[str],
) -> dict[str, Any]:
    return {
        'id': ilot_id,
        'label': label,
        'sante': sante,
        'activite': round(min(1.0, activite), 2),
        'resume': resume,
        'details': details,
    }


def _ilot_taches(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str, depuis: str
) -> dict[str, Any]:
    """Les deux files de tâches et leurs services."""
    ready = compte_taches(conn, 'ready')
    running = compte_taches(conn, 'running')
    plus_tard = _compte(
        conn,
        "SELECT COUNT(*) FROM tasks WHERE status='ready' AND not_before>?",
        (now,),
    )
    echouees = _compte(
        conn,
        "SELECT COUNT(*) FROM tasks WHERE status='failed' AND finished_at>?",
        (depuis,),
    )
    suspectes = _compte(
        conn,
        "SELECT COUNT(*) FROM tasks WHERE status='running' AND started_at<?",
        (avant_iso(now, minutes=30),),
    )
    servies = prochaines(conn, now, llm=not plafond_atteint(conn, policy, now))
    services = [
        ('File des conversations', 'serge-queue@conversations.service'),
        ('File des travaux', 'serge-queue@works.service'),
    ]
    etats = [(titre, etat_service(unit)) for titre, unit in services]
    details = [_service(titre, etat) for titre, etat in etats]
    if any(_arrete(etat) for _, etat in etats) or echouees:
        sante = 'erreur'
    elif suspectes or (ready - plus_tard > 0 and not servies):
        sante = 'degrade'
    else:
        sante = 'ok'
    if ready - plus_tard > 0 and not servies:
        details.append(
            'Des tâches prêtes ne partent pas (plafond, étape coupée ou'
            ' invocation éteinte) : voir En direct.'
        )
    if suspectes:
        details.append(f'{suspectes} en cours depuis plus de 30 minutes.')
    resume = f'{running} en cours, {ready} prêtes'
    resume += f', {plus_tard} en attente de leur heure' if plus_tard else ''
    resume += f', {echouees} échouées (24 h)' if echouees else ''
    return _ilot(
        'taches',
        'Files de tâches',
        sante,
        (running + ready) / 10,
        resume,
        details,
    )


def _ilot_canal(
    conn: sqlite3.Connection,
    canal: str,
    label: str,
    now: str,
    depuis: str,
    service: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """Un canal de conversation : branché ou pas sur ce serveur, ce qui est
    parti et arrivé en 24 h, sa dernière relève, et son service s'il en a
    un (le pont vocal pour la voix)."""
    row = conn.execute(
        'SELECT etat, polls, polled_at FROM canaux WHERE id=?', (canal,)
    ).fetchone()
    if row is None or str(row[0]) != 'branche':
        return _ilot(
            canal, label, 'inconnu', 0.0, 'Pas branché sur ce serveur.', []
        )
    partis = _compte(
        conn,
        "SELECT COUNT(*) FROM touches WHERE channel=? AND status='sent'"
        ' AND sent_at>?',
        (canal, depuis),
    )
    recus = _compte(
        conn,
        'SELECT COUNT(*) FROM inbound_events WHERE channel=? AND received_at>?',
        (canal, depuis),
    )
    echecs = _compte(
        conn,
        "SELECT COUNT(*) FROM touches WHERE channel=? AND status='failed'"
        ' AND updated_at>?',
        (canal, depuis),
    )
    resume = f'{partis} partis, {recus} reçus (24 h)'
    resume += f', {echecs} en échec' if echecs else ''
    sante = 'erreur' if echecs else 'ok'
    details = []
    # Un canal qui se relève : une boîte pas relevée depuis une heure est
    # le signe d'une panne (accès, réseau).
    if int(row[1]):
        relevee = str(row[2] or '')
        resume += (
            f', relevé à {relevee[11:16]}' if relevee else ', jamais relevé'
        )
        if not relevee or relevee < avant_iso(now, hours=1):
            sante = 'degrade' if sante == 'ok' else sante
    if service:
        etat = etat_service(service[1])
        details.append(_service(service[0], etat))
        if _arrete(etat):
            sante = 'erreur'
    return _ilot(canal, label, sante, (partis + recus) / 10, resume, details)


def _ilot_discord(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    """Le bot Discord : son service, le forum des tickets, les
    administrateurs, les tickets ouverts et leurs fils (ouverts, ou pas)."""
    etat = etat_service('serge-discord-bot.service')
    forum, _regle = forum_tickets(conn)
    noms = [
        str(r[0] or r[1])
        for r in conn.execute(
            'SELECT name, user_id FROM discord_admins ORDER BY added_at'
        ).fetchall()
    ]
    ouverts = _compte(
        conn,
        "SELECT COUNT(*) FROM tickets WHERE state IN ('OPEN', 'DISCUSSING')",
    )
    cartes = _compte(
        conn,
        "SELECT COUNT(*) FROM ticket_posts WHERE thread_id<>''"
        ' AND updated_at>?',
        (depuis,),
    )
    rates = _compte(
        conn,
        'SELECT COUNT(*) FROM ticket_posts WHERE shown_state IN (?, ?)',
        (ECHEC, ECHEC_MODIF),
    )
    if etat == 'inconnu' and not forum and not noms:
        return _ilot(
            'discord',
            'Discord',
            'inconnu',
            0.0,
            'Pas branché : pas de bot sur ce serveur, ni forum, ni'
            ' administrateur.',
            [],
        )
    details = [
        _service('Bot', etat),
        f'Forum des tickets : {forum}.'
        if forum
        else 'Pas de forum réglé : les tickets restent dans Mission Control'
        ' (page Décisions).',
        f'Administrateurs : {", ".join(noms)}.'
        if noms
        else 'Aucun administrateur : personne n’est mentionné, et personne'
        ' ne peut trancher sur Discord (page Décisions).',
    ]
    if rates:
        details.append(
            f'{rates} fils pas ouverts ou cartes pas mises à jour : le forum'
            ' n’existe pas, ou le bot n’a pas le droit d’y écrire. Nouvel'
            ' essai toutes les 10 minutes.'
        )
    if _arrete(etat):
        sante = 'erreur'
    elif rates or not forum or not noms:
        sante = 'degrade'
    else:
        sante = 'ok'
    resume = (
        f'{len(noms)} administrateurs, {ouverts} tickets ouverts,'
        f' {cartes} cartes envoyées ou mises à jour (24 h)'
    )
    resume += f', {rates} en échec' if rates else ''
    return _ilot(
        'discord', 'Discord', sante, (ouverts + cartes) / 10, resume, details
    )


def _ilot_ecoute(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    docs = _compte(
        conn,
        'SELECT COUNT(*) FROM listen_docs WHERE fetched_at>?',
        (depuis,),
    )
    return _ilot(
        'listen', 'Écoute', 'ok', docs / 20, f'{docs} pages lues (24 h)', []
    )


def _ilot_garde_fous(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    verdicts = 0
    refus = 0
    for row in conn.execute(
        "SELECT payload_json FROM events WHERE actor='guards' AND ts>?",
        (depuis,),
    ).fetchall():
        verdicts += 1
        try:
            payload = json.loads(row[0] or '{}')
        except ValueError:
            continue
        if isinstance(payload, dict) and not payload.get('allowed', True):
            refus += 1
    return _ilot(
        'guards',
        'Garde-fous',
        'ok',
        verdicts / 20,
        f'{verdicts} verdicts, {refus} refus (24 h)',
        [],
    )


def project_ilots(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les îlots de la page Système.

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (le plafond de dépense, pour les files).
        now: Maintenant ISO UTC.

    Returns:
        Dict {items: [{id, label, sante, activite, resume, details}]}.
    """
    depuis = avant_iso(now, hours=24)
    return {
        'items': [
            _ilot_taches(conn, policy, now, depuis),
            _ilot_canal(conn, 'email', 'E-mail', now, depuis),
            _ilot_canal(
                conn,
                'voice',
                'Voix',
                now,
                depuis,
                ('Pont vocal', 'serge-voice-bridge.service'),
            ),
            _ilot_discord(conn, depuis),
            _ilot_ecoute(conn, depuis),
            _ilot_garde_fous(conn, depuis),
        ]
    }
