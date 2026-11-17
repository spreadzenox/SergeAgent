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

_ACTION = (
    *_OU,
    Param(
        'action',
        'text',
        True,
        'ouvrir, cliquer, taper, taper_secret, choisir, touche,'
        ' defiler, revenir, attendre, ecran, accepter_dialogue ou'
        ' refuser_dialogue.',
    ),
    Param('ref', 'text', False, 'Le repère de l’élément : e7.'),
    Param(
        'text',
        'text',
        False,
        'L’adresse (ouvrir), le texte (taper), le nom du secret'
        ' (taper_secret), l’option (choisir),'
        ' la touche (Enter, Escape, Tab), haut ou bas (defiler), le'
        ' texte attendu (attendre), ordinateur ou mobile (ecran), le'
        ' texte à taper dans une boîte de saisie (accepter_dialogue).',
    ),
    Param('submit', 'bool', False, 'Taper puis valider avec Entrée.'),
    Param(
        'secrets',
        'text',
        False,
        'Les secrets permis pour taper_secret (figé en base).',
    ),
)
_CAPTURE = (
    *_OU,
    Param('keep', 'bool', False, 'La garder comme preuve.'),
    Param('full_page', 'bool', False, 'Toute la page, pas l’écran.'),
)
_VRAI = (
    ' Dans le vrai Chrome : un Chromium normal, sur un écran virtuel, pour'
    ' les pages qui refusent un navigateur sans écran (un captcha de'
    ' paiement) ; un humain peut voir cet écran et y agir depuis Mission'
    ' Control.'
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
        ' http://chantier:<port> mène au chantier du business. Une boîte'
        ' de dialogue du navigateur (un message, une question OK ou'
        ' Annuler, la saisie d’un texte) n’est pas dans la page : Serge y'
        ' répond lui-même et le dit dans le résultat (« dialogues »). Sans'
        ' réponse préparée, un message est fermé et une question ou une'
        ' saisie est refermée par « Annuler ». Pour y répondre, prépare ta'
        ' réponse avec accepter_dialogue (text : le texte à taper, pour une'
        ' saisie) ou refuser_dialogue, puis fais l’action qui ouvre la'
        ' boîte : la réponse sert une fois.',
        'serge/sandbox/navigateur.py',
        _ACTION,
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
        _CAPTURE,
    ),
    Capability(
        'real_browser_action',
        'Agir dans le vrai Chrome',
        'Comme « Agir dans une page ».' + _VRAI,
        'serge/sandbox/navigateur.py',
        _ACTION,
    ),
    Capability(
        'real_browser_read',
        'Lire la page du vrai Chrome',
        'Comme « Lire la page ».' + _VRAI,
        'serge/sandbox/navigateur.py',
        _OU,
    ),
    Capability(
        'real_browser_screenshot',
        'Capture du vrai Chrome',
        'Comme « Prendre une capture ».' + _VRAI,
        'serge/sandbox/navigateur.py',
        _CAPTURE,
    ),
    Capability(
        'human_help',
        'Appeler un humain',
        'Quand une page demande un humain (un captcha), en deux temps.'
        ' D’abord, la tâche s’arrête et un ticket demande aux'
        ' administrateurs s’ils sont prêts ; « Je suis prêt » la fait'
        ' repartir du début. Au même blocage, l’appel suivant envoie le'
        ' lien de l’écran du vrai Chrome (Mission Control) et attend'
        ' « C’est fait » quelques minutes, onglet de la tâche devant ;'
        ' sans réponse, on revient au premier temps. « Abandonner » : la'
        ' tâche continue sans humain.',
        'serge/aide_humaine.py',
        (
            Param('task_id', 'text', True, 'La tâche qui attend.'),
            Param(
                'raison',
                'text',
                True,
                'Ce qui bloque, en une phrase : « un captcha sur la page de'
                ' paiement de Stripe ».',
            ),
        ),
    ),
)
