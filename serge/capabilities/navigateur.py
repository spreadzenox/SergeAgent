#!/usr/bin/env python3
"""Les capacités du navigateur : voir une page et y agir comme un humain.

Le business, le livrable et la tâche sont des paramètres figés en base
sur l'outil : ils disent où ranger une capture gardée, quel chantier
ouvre ``http://chantier:<port>``, et quelle session (une par tâche) sert.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

_OU = (
    Param('venture_id', 'text', True, 'Le business.'),
    Param('deliverable', 'text', True, 'Le livrable : poc, produit…'),
    Param('task_id', 'text', True, 'La tâche : une session par tâche.'),
)

NAVIGATEUR: tuple[Capability, ...] = (
    Capability(
        'browser_action',
        'Agir dans une page',
        'Une action dans la page, comme un humain : ouvrir une adresse,'
        ' cliquer, taper, choisir dans une liste, appuyer sur une touche,'
        ' faire défiler, revenir, attendre un texte, passer en écran'
        ' ordinateur ou mobile. Rend la page relue en version courte (une'
        ' ligne par titre, texte, champ, bouton ou lien, avec son repère'
        ' [e7]) et les nouvelles erreurs de la page. L’adresse'
        ' http://chantier:<port> mène au chantier du business.',
        'serge/sandbox/navigateur.py',
        (
            *_OU,
            Param(
                'action',
                'text',
                True,
                'ouvrir, cliquer, taper, taper_secret, choisir, touche,'
                ' defiler, revenir, attendre ou ecran.',
            ),
            Param('ref', 'text', False, 'Le repère de l’élément : e7.'),
            Param(
                'text',
                'text',
                False,
                'L’adresse (ouvrir), le texte (taper), le nom du secret'
                ' (taper_secret), l’option (choisir),'
                ' la touche (Enter, Escape, Tab), haut ou bas (defiler), le'
                ' texte attendu (attendre), ordinateur ou mobile (ecran).',
            ),
            Param('submit', 'bool', False, 'Taper puis valider avec Entrée.'),
            Param(
                'secrets',
                'text',
                False,
                'Les secrets permis pour taper_secret (figé en base).',
            ),
        ),
    ),
    Capability(
        'browser_read',
        'Lire la page',
        'Rend la page entière, lue comme par un lecteur d’écran, et les'
        ' dernières erreurs de la page (JavaScript, requêtes ratées, codes'
        ' HTTP 400 et plus).',
        'serge/sandbox/navigateur.py',
        _OU,
    ),
    Capability(
        'browser_screenshot',
        'Prendre une capture',
        'Prend une capture de ce que montre l’écran (ou de la page entière)'
        ' et la montre au modèle comme une image. Gardée, elle est rangée'
        ' avec le livrable et a sa fiche dans les livrables (artifacts).',
        'serge/sandbox/navigateur.py',
        (
            *_OU,
            Param('keep', 'bool', False, 'La garder comme preuve.'),
            Param('full_page', 'bool', False, 'Toute la page, pas l’écran.'),
        ),
    ),
)
