#!/usr/bin/env python3
"""Les images Docker maison des chantiers.

Un profil de bac à sable nomme son image (page Policy). Un nom public,
comme ``node:22-bookworm``, est téléchargé par Docker. Un nom maison,
comme ``serge-atelier-video``, désigne un dossier de ``serge/sandbox/`` :
Serge construit l'image au premier usage, et de nouveau quand un fichier
du dossier change (son étiquette est l'empreinte de ces fichiers).

Exemple : le profil « video » a l'image ``serge-atelier-video`` ; le
premier chantier vidéo construit ``serge-atelier-video:3f2a…`` depuis
``serge/sandbox/image_video/`` (une dizaine de minutes, une seule fois).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from serge.sandbox.docker import docker, journal

# Le nom d'une image maison, et son dossier à côté de ce fichier.
MAISON = {'serge-atelier-video': 'image_video'}
# Construire l'atelier vidéo télécharge un Chrome, PyTorch et un modèle de
# 1,2 Go : on lui laisse une heure.
DUREE_CONSTRUCTION = 3600


def empreinte(dossier: Path) -> str:
    """L'empreinte des fichiers d'un dossier d'image, noms compris."""
    somme = hashlib.sha256()
    for fichier in sorted(p for p in dossier.rglob('*') if p.is_file()):
        somme.update(str(fichier.relative_to(dossier)).encode())
        somme.update(fichier.read_bytes())
    return somme.hexdigest()[:12]


def image_du_profil(nom: str) -> str:
    """L'image à lancer pour ce nom ; une image maison est construite si
    elle manque.

    Raises:
        DockerError: La construction a échoué ; la raison est au journal.
    """
    dossier = MAISON.get(nom)
    if dossier is None:
        return nom
    racine = Path(__file__).with_name(dossier)
    image = f'{nom}:{empreinte(racine)}'
    # « image ls » rend une liste vide pour une image absente.
    if not docker(['image', 'ls', '-q', image], timeout=30).stdout.strip():
        journal(f'construction de {image} (une fois par version)')
        docker(['build', '-t', image, str(racine)], timeout=DUREE_CONSTRUCTION)
    return image
