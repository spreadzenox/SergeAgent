#!/usr/bin/env python3
"""Les capacités des e-mails des produits (lot 11).

« Ma boîte e-mail » donne au relecteur son adresse pour un essai, et les
e-mails qu'elle a reçus : la boîte d'essai en staging, la réception de
Resend en prod (``serge/sandbox/courriel.py``). La tâche est un paramètre
figé en base : une adresse par essai.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

COURRIEL: tuple[Capability, ...] = (
    Capability(
        'mail_read',
        'Ma boîte e-mail',
        'Rend ton adresse e-mail pour cet essai (inscris-toi avec), et les'
        ' e-mails qu’elle a reçus, les plus récents d’abord : l’expéditeur,'
        ' l’objet, le texte et ses liens (un lien de validation, par'
        ' exemple). Attend qu’un e-mail arrive, au plus une minute environ.',
        'serge/sandbox/courriel.py',
        (
            Param(
                'task_id', 'text', True, 'La tâche : une adresse par essai.'
            ),
            Param(
                'wait',
                'bool',
                False,
                'Attendre qu’un e-mail arrive (oui par défaut ; non pour'
                ' seulement connaître ton adresse).',
            ),
        ),
    ),
)
