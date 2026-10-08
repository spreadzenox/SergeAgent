#!/usr/bin/env python3
"""Projecteurs P7 Voix : CDR, audio, qualité, bridge, statut kill M9/M11."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

from serge.coupe_circuit import heartbeat_marche
from serge.paths import system_root
from serge.voice.ledger import assurer_colonnes_calls
from serge.voice.policy import default_ledger_path
from serge.voice.quality import recent_scores


def project_cdr_appels(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Liste des derniers CDR voix avec URL audio réservée à l’owner le cas échéant (P7).

    Args:
        conn: Connexion canon (ignorée pour CDR, ledger externe).
        policy: Policy.
        now: Maintenant ISO.

    Returns:
        Dict {calls: [...], total}.
    """
    _ = (policy, now)
    ledger_p = default_ledger_path()
    if not ledger_p.is_file():
        return {'calls': [], 'total': 0, 'disponible': False}

    try:
        v_conn = sqlite3.connect(ledger_p, timeout=5)
        v_conn.row_factory = sqlite3.Row
        assurer_colonnes_calls(v_conn)
        v_conn.commit()
        rows = v_conn.execute(
            'SELECT request_id, cdr_id, direction, to_e164, cli, purpose,'
            ' decision, reason, outcome, duration_s, recording_path,'
            ' transcript, created_at'
            ' FROM calls ORDER BY created_at DESC LIMIT 30'
        ).fetchall()
        tot = v_conn.execute('SELECT COUNT(*) FROM calls').fetchone()[0]
        v_conn.close()
    except sqlite3.OperationalError:
        return {'calls': [], 'total': 0, 'disponible': False}

    calls = []
    for r in rows:
        rec_path = str(r['recording_path'] or '')
        audio_url = ''
        if rec_path:
            audio_url = '/owner/api/voice/audio?' + urlencode(
                {'cdr': r['cdr_id']}
            )

        calls.append(
            {
                'request_id': str(r['request_id']),
                'cdr_id': str(r['cdr_id']),
                'direction': str(r['direction']),
                'to': str(r['to_e164']),
                'cli': str(r['cli']),
                'purpose': str(r['purpose']),
                'decision': str(r['decision']),
                'reason': str(r['reason']),
                'outcome': str(r['outcome']),
                'duration_s': int(r['duration_s']),
                'has_recording': bool(rec_path),
                'audio_url': audio_url,
                'transcript': str(r['transcript'] or ''),
                'created_at': str(r['created_at']),
            }
        )

    return {'calls': calls, 'total': int(tot), 'disponible': True}


def project_qualite_voix(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Métriques qualité voix F4c : scores récents, moyenne, drapeaux.

    Args:
        conn: Connexion canon.
        policy: Policy (qualite window).
        now: Maintenant ISO.

    Returns:
        Dict {scores: [...], note_moyenne, total_notes}.
    """
    _ = now
    scores = recent_scores(conn, window=20)
    notes = [s['note'] for s in scores if s.get('note') is not None]
    moyenne = round(sum(notes) / len(notes), 2) if notes else None

    return {
        'scores': scores,
        'note_moyenne': moyenne,
        'total_notes': len(notes),
    }


def project_bridge_statut(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """État du bridge voix, trunk Asterisk et kill-switch M9/M11.

    Args:
        conn: Connexion canon.
        policy: Policy.
        now: Maintenant ISO.

    Returns:
        Dict {kill_switch_active, mode, trunk_status}.
    """
    _ = policy
    # Même levier que partout : Serge arrêté en entier.
    is_killed = not heartbeat_marche(conn, now)

    # Récupération fail-soft du statut bridge
    from serge.voice.bridge import health as bridge_health

    try:
        b_info = bridge_health()
    except Exception:
        b_info = {'status': 'inconnu'}

    return {
        'kill_switch': is_killed,
        'bridge': b_info,
    }


# Ce qui raconte un appel : le pont vocal (la voix en direct), Asterisk (la
# ligne, et le secours tour par tour qu'il lance), et le fichier d'Asterisk.
JOURNAUX_VOIX = (
    ('serge-voice-bridge.service', 'Pont vocal'),
    ('serge-asterisk.service', 'Asterisk et le secours tour par tour'),
)
LIGNES_JOURNAL = 150


def _journal_service(unit: str) -> tuple[list[str], str]:
    """Les dernières lignes du journal d'un service ; ``(lignes, erreur)``."""
    if shutil.which('journalctl') is None:
        return [], 'journalctl absent sur ce serveur'
    try:
        p = subprocess.run(
            [
                'journalctl',
                '--user',
                '--unit',
                unit,
                '--lines',
                str(LIGNES_JOURNAL),
                '--no-pager',
                '--output',
                'short-iso',
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [], f'journal illisible ({type(exc).__name__})'
    lignes = p.stdout.splitlines()
    if p.returncode != 0 and not lignes:
        return [], (p.stderr.strip() or f'journalctl a rendu {p.returncode}')[
            :300
        ]
    return lignes, ''


def _fichier_asterisk() -> tuple[list[str], str]:
    """La fin du fichier ``messages`` d'Asterisk ; ``(lignes, erreur)``."""
    chemin = system_root() / 'logs/asterisk/messages'
    if not chemin.is_file():
        return [], 'pas de fichier messages'
    try:
        texte = chemin.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        return [], f'fichier illisible ({type(exc).__name__})'
    return texte.splitlines()[-LIGNES_JOURNAL:], ''


def project_journal_voix(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les derniers journaux du pont vocal et d'Asterisk, lus sur le serveur.

    Mission Control tourne sous le même compte que ces services : un appel
    qui échoue se lit ici, sans accès à la machine. Un journal illisible le
    dit, sans casser la page.

    Args:
        conn: Connexion canon (ignorée).
        policy: Policy (ignorée).
        now: Maintenant ISO (ignoré).

    Returns:
        Dict {blocs: [{titre, lignes, erreur}]}, les lignes les plus
        récentes en dernier.
    """
    _ = (conn, policy, now)
    blocs = []
    for unit, titre in JOURNAUX_VOIX:
        lignes, erreur = _journal_service(unit)
        blocs.append({'titre': titre, 'lignes': lignes, 'erreur': erreur})
    lignes, erreur = _fichier_asterisk()
    blocs.append(
        {
            'titre': 'Asterisk, fichier messages',
            'lignes': lignes,
            'erreur': erreur,
        }
    )
    return {'blocs': blocs}
