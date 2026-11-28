#!/usr/bin/env python3
"""Les capacités des services externes gratuits d'un produit (décision
Q118) : les demander, ouvrir le compte de Serge, finir le branchement.

Le business, le livrable et la tâche sont des paramètres figés en base :
le modèle ne choisit jamais à quel produit va une clé.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

SERVICES: tuple[Capability, ...] = (
    Capability(
        'connect_service',
        'Brancher un service gratuit',
        'Demande, pour un produit, un service gratuit d’un autre site qui'
        ' exige un compte et une clé d’API : son nom (un mot, celui du'
        ' site), son adresse et à quoi il sert. Si le plan validé nomme ce'
        ' service, Serge crée son compte sur le site et va chercher une'
        ' clé ; sinon un ticket « Service » demande d’abord l’accord d’un'
        ' humain. La tâche attend et repart avec le résultat : le nom de'
        ' la variable d’environnement où le produit lira sa clé, ou la'
        ' raison de l’échec. La clé n’est jamais rendue. Refuse au-delà du'
        ' nombre de services par produit réglé page Policy.',
        'serge/product_services.py',
        (
            Param('nom', 'text', True, 'Le nom du service : mapbox.'),
            Param('adresse', 'text', True, 'Son adresse, en https://.'),
            Param(
                'besoin',
                'text',
                True,
                'À quoi il sert dans le produit, et ce qu’il faut y obtenir.',
            ),
            Param('venture_id', 'text', True, 'Le business.', frozen=True),
            Param(
                'deliverable',
                'text',
                True,
                'Le livrable : poc ou produit.',
                frozen=True,
            ),
            Param('task_id', 'text', True, 'La tâche.', frozen=True),
        ),
    ),
    Capability(
        'open_service_account',
        'Ouvrir le compte d’un service',
        'Prépare le compte de Serge sur le site d’un service à brancher :'
        ' rend « actif » si Serge y a déjà un compte en service (un seul'
        ' compte par site, quel que soit le produit), « a_creer » si la'
        ' ligne du compte est prête, ou « refuse » avec la raison.',
        'serge/product_services.py',
        (
            Param('account', 'text', True, 'Le nom du compte : mapbox.'),
            Param('url', 'text', True, 'L’adresse du site.'),
        ),
    ),
    Capability(
        'finish_service',
        'Finir le branchement d’un service',
        'Note si le service est branché (sa clé est gardée) ou non, avec'
        ' la raison, et fait repartir la tâche de construction qui'
        ' attendait, avec ce résultat. Un service dit branché sans clé'
        ' gardée ne l’est pas.',
        'serge/product_services.py',
        (
            Param('service_id', 'text', True, 'Le service.'),
            Param('ok', 'text', False, 'oui si la clé est gardée.'),
            Param('raison', 'text', False, 'Le compte rendu, ou la raison.'),
        ),
    ),
)
