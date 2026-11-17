#!/usr/bin/env python3
"""Les noms des actes tickets communs à Discord et Mission Control."""

APPROVE = frozenset(
    {
        'approuver',
        'cest_fait',
        'envoyer_brouillon',
        'passer',
        'valider',
        'faire_sans',
        'pret',
    }
)
REJECT = frozenset(
    {
        'rejeter',
        'abandonner',
        'ne_rien_envoyer',
        'ne_pas_passer',
        'arreter_business',
        'aucun',
    }
)
# Les boutons qui demandent un texte, et ce qu'ils font du ticket : le
# trancher en le modifiant (le texte est la note), y répondre librement, ou
# en discuter sans le trancher (« Réécrire » : Serge réécrit, puis le
# nouveau brouillon revient dans le même ticket, décision Q85).
EDITER = frozenset({'editer', 'ma_reponse', 'a_corriger', 'choisir_autre'})
REPONDRE = frozenset({'reponse_libre'})
DISCUTER = frozenset({'discuter', 'discuter_fil', 'reecrire'})

# Tous les boutons qu'un type de ticket peut avoir, sur Discord comme dans
# Mission Control.
BOUTONS = frozenset(
    APPROVE
    | REJECT
    | {
        'editer',
        'discuter',
        'discuter_fil',
        'reponse_libre',
        'ma_reponse',
        'reecrire',
        'a_corriger',
        'choisir_autre',
    }
)
