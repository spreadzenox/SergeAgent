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
        'envoyer_brouillon',
        'passer',
    }
)
REJECT = frozenset(
    {
        'rejeter',
        'abandonner',
        'refuser',
        'annuler',
        'ne_rien_envoyer',
        'ne_pas_passer',
    }
)
# Les boutons qui demandent un texte, et ce qu'ils font du ticket : le
# trancher en le modifiant (le texte est la note), y répondre librement, ou
# en discuter sans le trancher (« Réécrire » : Serge réécrit, puis le
# nouveau brouillon revient dans le même ticket, décision Q85).
EDITER = frozenset({'editer', 'ma_reponse'})
REPONDRE = frozenset({'reponse_libre', 'choix_qcm'})
DISCUTER = frozenset({'discuter', 'discuter_fil', 'reecrire'})

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
        'ma_reponse',
        'reecrire',
    }
)
