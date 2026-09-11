#!/usr/bin/env python3
"""Projecteurs P7 Voix : CDR, audio, qualité, bridge, statut kill M9/M11."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.signedlinks import signer_url
from serge.paths import system_root
from serge.voice.policy import default_ledger_path, kill_switch_active
from serge.voice.quality import recent_scores


def project_cdr_appels(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Liste des derniers CDR voix avec URL audio signée le cas échéant (P7).

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
        rows = v_conn.execute(
            'SELECT request_id, cdr_id, direction, to_e164, cli, purpose,'
            ' decision, outcome, duration_s, recording_path, created_at'
            ' FROM calls ORDER BY created_at DESC LIMIT 30'
        ).fetchall()
        tot = v_conn.execute('SELECT COUNT(*) FROM calls').fetchone()[0]
        v_conn.close()
    except sqlite3.OperationalError:
        return {'calls': [], 'total': 0, 'disponible': False}

    secret = 'serge_mc_voice_signed_audio'
    calls = []
    for r in rows:
        rec_path = str(r['recording_path'] or '')
        audio_url = ''
        if rec_path:
            url_brute = f'/owner/api/voice/audio?cdr={r["cdr_id"]}'
            audio_url = signer_url(url_brute, secret, ttl_s=3600)

        calls.append(
            {
                'request_id': str(r['request_id']),
                'cdr_id': str(r['cdr_id']),
                'direction': str(r['direction']),
                'to': str(r['to_e164']),
                'cli': str(r['cli']),
                'purpose': str(r['purpose']),
                'decision': str(r['decision']),
                'outcome': str(r['outcome']),
                'duration_s': int(r['duration_s']),
                'has_recording': bool(rec_path),
                'audio_url': audio_url,
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
    _ = (conn, policy, now)
    root = system_root()
    is_killed = kill_switch_active(root)

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
