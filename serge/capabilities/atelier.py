#!/usr/bin/env python3
"""Les capacités de l'atelier : voir, garder et faire dire, dans un chantier.

Elles complètent celles du chantier (``chantier.py``) pour fabriquer autre
chose que du code : une vidéo, par exemple. Leurs paramètres
``venture_id``, ``deliverable`` et ``profile`` sont figés en base, comme
ceux du chantier.
"""

from __future__ import annotations

from serge.capabilities.chantier import _OU
from serge.capabilities.model import Capability, Param

_TACHE = Param(
    'task_id', 'text', False, 'La tâche, pour sa fiche.', frozen=True
)

ATELIER: tuple[Capability, ...] = (
    Capability(
        'sandbox_image',
        'Regarder une image du chantier',
        'Montre au modèle une image du chantier (png, jpg ou webp, 2 Mo au'
        ' plus) : une planche de relecture, une capture. Elle arrive comme'
        ' une image dans le message suivant, pas comme du texte.',
        'serge/sandbox/atelier.py',
        (
            *_OU,
            Param('path', 'text', True, 'L’image, relative à /work.'),
        ),
    ),
    Capability(
        'sandbox_keep_file',
        'Garder un fichier du chantier',
        'Sort un fichier du chantier, le range avec le livrable et lui fait'
        ' une fiche (table artifacts) : un humain le voit ensuite dans'
        ' Mission Control. 200 Mo au plus.',
        'serge/sandbox/atelier.py',
        (
            *_OU,
            Param('path', 'text', True, 'Le fichier, relatif à /work.'),
            Param(
                'kind',
                'text',
                False,
                'La sorte de fichier sur sa fiche : video…',
            ),
            _TACHE,
        ),
    ),
    Capability(
        'speech',
        'Dire un texte',
        'Fait dire un texte par la voix de synthèse réglée sur la page'
        ' Policy (famille « Vidéo ») et écrit le son, en mp3, dans le'
        ' chantier. 3 000 caractères au plus. Les nombres s’écrivent en'
        ' lettres, comme on les dit.',
        'serge/sandbox/atelier.py',
        (
            *_OU,
            Param('text', 'text', True, 'Le texte à dire.'),
            Param('path', 'text', True, 'Où écrire le son, relatif à /work.'),
            _TACHE,
        ),
        acts_outside=True,
    ),
)
