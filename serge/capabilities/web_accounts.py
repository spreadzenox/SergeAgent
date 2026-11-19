#!/usr/bin/env python3
"""Les capacités des comptes web (lot 13) : ouvrir un compte, donner
l'identité de Serge, rendre ses messages de vérification.

Avec les outils du navigateur et « Appeler un humain », elles suffisent à
une invocation pour créer un compte sur un site, du formulaire au lien de
confirmation. Le compte lui-même, son mot de passe et sa session sont dans
``serge/web_accounts.py``.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

WEB_ACCOUNTS: tuple[Capability, ...] = (
    Capability(
        'open_web_account',
        'Ouvrir un compte web',
        'Prépare en base la ligne d’un compte de Serge sur un site, avant'
        ' sa création sur le site : son nom (un mot, celui du site) et'
        ' l’adresse du site. Refuse un nom mal écrit, une adresse sans'
        ' https://, et un compte qui existe déjà et sert ; une création'
        ' ratée se reprend sur la même ligne.',
        'serge/web_accounts.py',
        (
            Param('account', 'text', True, 'Le nom du compte : reddit.'),
            Param('url', 'text', True, 'L’adresse du site.'),
        ),
    ),
    Capability(
        'serge_identity',
        'L’identité de Serge',
        'Ce que Serge donne à un site pour s’y inscrire : son prénom, son'
        ' nom, son pseudo, son adresse e-mail et son numéro pour les SMS'
        ' (le fichier d’instance). Jamais son SIRET, son IBAN ni son'
        ' adresse postale.',
        'serge/identite.py',
    ),
    Capability(
        'verification_messages',
        'Mes messages de vérification',
        'Les e-mails et les SMS que Serge a reçus depuis le début de la'
        ' tâche : un code ou un lien de confirmation après une inscription'
        ' ou une connexion. Pour un e-mail : l’expéditeur, l’objet, le'
        ' texte et ses liens ; pour un SMS : son texte et le code repéré.'
        ' Seuls les e-mails qui ne viennent d’aucun contact sont rendus.'
        ' La boîte est relevée toutes les 2 minutes : l’outil attend'
        ' qu’un message arrive, quelques minutes au plus.',
        'serge/verification.py',
        (
            Param('task_id', 'text', True, 'La tâche.', frozen=True),
            Param(
                'wait',
                'bool',
                False,
                'Attendre qu’un message arrive (oui par défaut).',
            ),
        ),
    ),
)
