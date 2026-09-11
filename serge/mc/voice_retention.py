#!/usr/bin/env python3
"""Purge de rétention des enregistrements audio voix (RGPD / policy.voice)."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from serge.db.store import append_event


def purger_audio_voix(
    conn: sqlite3.Connection,
    dossier_audio: Path,
    retention_jours: int = 30,
    now_iso: str | None = None,
) -> dict[str, Any]:
    """Supprime les fichiers audio expirés et met à jour les CDR.

    Args:
        conn: Connexion canon (ou voice ledger).
        dossier_audio: Dossier contenant les fichiers audio .wav.
        retention_jours: Délai de rétention en jours.
        now_iso: Maintenant ISO (défaut : UTC now).

    Returns:
        Dict {fichiers_supprimes, octets_liberes, seuil_iso}.
    """
    moment = datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)
    seuil = (moment - timedelta(days=retention_jours)).isoformat()

    fichiers_supprimes = 0
    octets_liberes = 0

    if dossier_audio.exists():
        for racine, _, fichiers in os.walk(dossier_audio):
            for nom in fichiers:
                if nom.endswith(('.wav', '.mp3', '.ogg')):
                    chemin = Path(racine) / nom
                    try:
                        mtime = datetime.fromtimestamp(
                            chemin.stat().st_mtime, tz=UTC
                        )
                        if mtime.isoformat() < seuil:
                            taille = chemin.stat().st_size
                            chemin.unlink()
                            fichiers_supprimes += 1
                            octets_liberes += taille
                    except OSError:
                        continue

    # Nettoyage des références dans la table calls si existante
    try:
        conn.execute(
            "UPDATE calls SET recording_path='' WHERE created_at<? AND recording_path<>''",
            (seuil,),
        )
    except sqlite3.OperationalError:
        pass

    append_event(
        conn,
        actor='voice_retention',
        type='voice.purged',
        payload={
            'fichiers': fichiers_supprimes,
            'octets': octets_liberes,
            'seuil': seuil,
        },
    )

    return {
        'fichiers_supprimes': fichiers_supprimes,
        'octets_liberes': octets_liberes,
        'seuil_iso': seuil,
    }
