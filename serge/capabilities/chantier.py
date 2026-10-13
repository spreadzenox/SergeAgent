#!/usr/bin/env python3
"""Les capacités du chantier : le bac à sable où l'on code un produit.

Un chantier est un conteneur Docker, un par business et par livrable,
gardé entre deux tâches. Les paramètres ``venture_id``, ``deliverable``
et ``profile`` sont figés en base sur l'outil : le modèle ne choisit
jamais dans quel chantier il travaille.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

_OU = (
    Param('venture_id', 'text', True, 'Le business du chantier.'),
    Param('deliverable', 'text', True, 'Le livrable : poc, produit…'),
    Param('profile', 'text', True, 'Le profil du bac à sable (Policy).'),
)

CHANTIER: tuple[Capability, ...] = (
    Capability(
        'sandbox_command',
        'Lancer une commande dans le chantier',
        'Lance une commande shell dans le chantier du business (dossier'
        ' /work) et rend sa sortie et son code de retour, coupés à la taille'
        ' maximale d’un résultat d’outil. En arrière-plan (un serveur de'
        ' développement), elle rend la main tout de suite et sa sortie va'
        ' dans un fichier. Allumer un chantier éteint les autres : un seul'
        ' tourne à la fois. Un chantier qui dépasse son disque permis est'
        ' arrêté.',
        'serge/sandbox/chantier.py',
        (
            *_OU,
            Param('command', 'text', True, 'La commande, lancée par sh.'),
            Param(
                'background',
                'bool',
                False,
                'Vrai pour la laisser tourner (un serveur).',
            ),
        ),
    ),
    Capability(
        'sandbox_read_file',
        'Lire un fichier du chantier',
        'Rend des lignes d’un fichier du chantier : à partir d’une ligne, et'
        ' au plus tant de lignes, pour ne pas renvoyer un gros fichier.',
        'serge/sandbox/chantier.py',
        (
            *_OU,
            Param('path', 'text', True, 'Le fichier, relatif à /work.'),
            Param('start', 'number', False, 'La première ligne (1).'),
            Param('lines', 'number', False, 'Le nombre de lignes (400).'),
        ),
    ),
    Capability(
        'sandbox_write_file',
        'Écrire un fichier du chantier',
        'Écrit un fichier entier dans le chantier (ses dossiers sont créés).',
        'serge/sandbox/chantier.py',
        (
            *_OU,
            Param('path', 'text', True, 'Le fichier, relatif à /work.'),
            Param('content', 'text', True, 'Tout le contenu du fichier.'),
        ),
    ),
    Capability(
        'sandbox_edit_file',
        'Modifier un fichier du chantier',
        'Remplace un passage exact d’un fichier du chantier par un autre.'
        ' Le passage doit apparaître une seule fois : sinon rien ne change'
        ' et l’outil dit pourquoi.',
        'serge/sandbox/chantier.py',
        (
            *_OU,
            Param('path', 'text', True, 'Le fichier, relatif à /work.'),
            Param('old', 'text', True, 'Le passage exact à remplacer.'),
            Param('new', 'text', True, 'Le nouveau passage.'),
        ),
    ),
)
