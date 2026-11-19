#!/usr/bin/env python3
"""Ce qu'est une capacité, pour le code qui les déclare.

Une capacité est un savoir-faire général du code, réglé par des
paramètres lus en base. Chaque famille de capacités est déclarée dans son
fichier de ce dossier ; ``serge.capabilities`` les réunit.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    name: str
    type: str
    required: bool
    description: str
    # Seulement figé en base, sur l'outil d'une invocation : le modèle ne
    # le voit pas et ne peut pas le donner. Exemple : les secrets permis,
    # le compte web de la session.
    frozen: bool = False


@dataclass(frozen=True)
class Capability:
    id: str
    title: str
    doc_md: str
    code_path: str
    params: tuple[Param, ...] = field(default_factory=tuple)
    # Elle agit hors de Serge (envoyer, payer) : elle enregistre en base
    # pendant la tâche, pour qu'un arrêt ne la fasse jamais agir deux fois.
    acts_outside: bool = False
