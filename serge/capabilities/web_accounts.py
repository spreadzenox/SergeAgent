#!/usr/bin/env python3
"""Les capacités des comptes web (lot 13) : ouvrir un compte, changer
son mot de passe tant qu'il n'est pas créé, donner l'identité de Serge,
rendre ses messages de vérification.

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
        'change_web_password',
        'Changer le mot de passe du compte',
        'Choisit un nouveau mot de passe pour un compte que Serge est en'
        ' train de créer, quand le site refuse le premier (trop long, un'
        ' signe qu’il n’accepte pas) : la longueur voulue, avec ou sans'
        ' signes. Le modèle ne le voit jamais ; il le retape avec « taper'
        ' un secret ». Refuse pour un compte qui existe déjà sur son site.',
        'serge/web_accounts.py',
        (
            Param('account', 'text', True, 'Le nom du compte.', frozen=True),
            Param(
                'longueur',
                'number',
                False,
                'Le nombre de caractères que le site accepte (20 sans rien'
                ' dire, de 8 à 64).',
            ),
            Param(
                'signes',
                'bool',
                False,
                'Avec des signes (! # % + - = ? @) : oui par défaut ; non'
                ' si le site les refuse.',
            ),
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
        ' texte et ses liens ; pour un SMS : son texte, le code repéré et'
        ' ses liens. Si aucun SMS n’est jamais arrivé sur ce serveur, le'
        ' résultat le dit.'
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
