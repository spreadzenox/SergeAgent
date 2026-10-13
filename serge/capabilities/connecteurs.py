#!/usr/bin/env python3
"""La capacité des connecteurs : appeler un service décrit en base.

Un connecteur n'est pas du code (Q56) : le service et ses points d'entrée
sont décrits en base (``api_services``, ``api_endpoints``). Chaque point
d'entrée est un outil ; ses paramètres permis forment son schéma.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

CONNECTEURS: tuple[Capability, ...] = (
    Capability(
        'call_api',
        'Appeler une API',
        'Appelle un point d’entrée d’un service décrit en base (Stripe…),'
        ' avec le secret du service lu dans les secrets de l’instance, et'
        ' rend sa réponse. Seuls les paramètres permis du point d’entrée'
        ' partent ; ceux figés en base ne sont pas choisis par le modèle.'
        ' Une écriture porte une clé d’idempotence : reprise après un arrêt,'
        ' elle n’agit jamais deux fois. Une erreur du service est notée au'
        ' journal avec sa raison.',
        'serge/connecteurs/appel.py',
        (
            Param('service', 'text', False, 'Le service (mode test, vrai).'),
            Param('task_id', 'text', False, 'La tâche, pour l’idempotence.'),
        ),
        acts_outside=True,
    ),
)
