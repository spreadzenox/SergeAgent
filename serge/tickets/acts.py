#!/usr/bin/env python3
"""Les noms des actes tickets communs à Discord et Mission Control."""

APPROVE = frozenset(
    {
        'approuver',
        'approuver_version',
        'cest_fait',
        'confirmer',
        'ouvrir',
        'tout_approuver',
    }
)
REJECT = frozenset({'rejeter', 'abandonner', 'refuser', 'annuler'})

# Tous les boutons qu'un type de ticket peut avoir, sur Discord comme dans
# Mission Control (les boutons d'une leçon, garder / modifier / jeter, sont
# propres aux lignes d'un ticket).
BOUTONS = frozenset(
    APPROVE
    | REJECT
    | {
        'editer',
        'discuter',
        'discuter_fil',
        'accuse_reception',
        'reponse_libre',
        'choix_qcm',
    }
)
