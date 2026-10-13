#!/usr/bin/env python3
"""Le journal du bot Discord : une ligne par événement ou erreur.

Le service écrit sur sa sortie d'erreur ; systemd la garde, et Mission
Control la montre sur la page Health (« Journaux du serveur »). Jamais de
token ni de secret dans une ligne.
"""

from __future__ import annotations

import sys


def journal(texte: str) -> None:
    """Une ligne dans le journal du service (lisible avec journalctl)."""
    print(f'discord : {texte}', file=sys.stderr, flush=True)
