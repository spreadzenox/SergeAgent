#!/usr/bin/env python3
"""Projecteurs P8 Santé : charte E6, audit trail, drift versions, units systemd."""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.db.schema import SCHEMA_VERSION
from serge.mc import MC_VERSION


def project_charte_metriques(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Métriques charte E6 : LOC, plus gros fichier, tokens, requested en attente.

    Args:
        conn: Connexion canon (lecture).
        policy: Policy.
        now: Maintenant ISO.

    Returns:
        Dict {loc_total, plus_gros_fichier, tokens_par_euro, requested_pending}.
    """
    _ = (policy, now)
    root = Path(__file__).resolve().parents[2]
    loc_total = 0
    plus_gros = {'nom': '', 'lignes': 0}

    for base in ('kit', 'serge'):
        d = root / base
        if d.is_dir():
            for p in d.rglob('*.py'):
                try:
                    nb = len(p.read_text(encoding='utf-8').splitlines())
                    loc_total += nb
                    if nb > plus_gros['lignes']:
                        plus_gros = {
                            'nom': str(p.relative_to(root)),
                            'lignes': nb,
                        }
                except OSError:
                    continue

    req_pending = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE type='REQUESTED' AND state IN ('DRAFT', 'OPEN', 'DISCUSSING')"
    ).fetchone()[0]

    # Récupération ratio tokens/€
    row_tok = conn.execute(
        'SELECT COALESCE(SUM(tokens_in + tokens_out), 0) FROM llm_usage'
    ).fetchone()
    tot_tok = int(row_tok[0]) if row_tok else 0
    row_rev = conn.execute(
        "SELECT COALESCE(SUM(amount_eur), 0) FROM transactions WHERE status='paid'"
    ).fetchone()
    tot_rev = float(row_rev[0]) if row_rev else 0.0
    tok_per_eur = round(tot_tok / tot_rev, 1) if tot_rev > 0 else None

    return {
        'loc_total': loc_total,
        'plus_gros_fichier': plus_gros,
        'requested_pending': int(req_pending),
        'tokens_par_euro': tok_per_eur,
    }


def project_audit_trail(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Audit trail : 50 derniers actes owner/MC (events type mc_act).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy.
        now: Maintenant ISO.

    Returns:
        Dict {actes: [...]}.
    """
    _ = (policy, now)
    rows = conn.execute(
        "SELECT id, ts, actor, payload_json FROM events WHERE type='mc_act'"
        ' ORDER BY id DESC LIMIT 50'
    ).fetchall()

    actes = []
    for r in rows:
        try:
            ch = json.loads(str(r[3]) or '{}')
        except ValueError:
            ch = {}
        actes.append(
            {
                'id': r[0],
                'ts': str(r[1]),
                'acteur': str(r[2]),
                'acte': str(ch.get('acte') or 'inconnu'),
                'details': ch,
            }
        )

    return {'actes': actes}


def project_versions_drift(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Versions logicielles et dérive schéma / modèles.

    Args:
        conn: Connexion canon (lecture).
        policy: Policy.
        now: Maintenant ISO.

    Returns:
        Dict {mc_version, schema_version, gog_version, models}.
    """
    _ = (policy, now)
    schema_row = conn.execute(
        'SELECT version, applied_at FROM schema_version'
    ).fetchone()
    schema_db = int(schema_row[0]) if schema_row else SCHEMA_VERSION

    gog_bin = shutil.which('gog')
    gog_ver = 'non_installe'
    if gog_bin:
        try:
            res = subprocess.run(
                [gog_bin, 'version'],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            gog_ver = (
                res.stdout.strip().splitlines()[0] if res.stdout else 'ok'
            )
        except Exception:
            gog_ver = 'erreur_sonde'

    return {
        'mc_version': MC_VERSION,
        'schema_version': schema_db,
        'schema_attendu': SCHEMA_VERSION,
        'schema_ok': schema_db == SCHEMA_VERSION,
        'gog_version': gog_ver,
    }


def project_units_systemd(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Sonde lente des services systemd (timeout court, fail-soft).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy.
        now: Maintenant ISO.

    Returns:
        Dict {units: [...]}.
    """
    _ = (conn, policy, now)
    units_surveillees = [
        'serge-pipeline.service',
        'serge-discord-bot.service',
        'serge-voice-bridge.service',
        'serge-mc.service',
    ]

    resultats = []
    has_systemctl = shutil.which('systemctl') is not None

    for u in units_surveillees:
        etat = 'inconnu'
        if has_systemctl:
            try:
                p = subprocess.run(
                    ['systemctl', '--user', 'is-active', u],
                    capture_output=True,
                    text=True,
                    timeout=1.5,
                    check=False,
                )
                etat = p.stdout.strip() or 'inactive'
            except Exception:
                etat = 'non_disponible'

        resultats.append({'unit': u, 'status': etat})

    return {'units': resultats}
