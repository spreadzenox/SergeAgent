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
    Param(
        'account',
        'text',
        False,
        'Le compte web de la session : elle s’ouvre connectée à ce compte'
        ' (ses cookies gardés en base), et chaque action passe par la'
        ' garde du compte. Figé en base.',
        frozen=True,
    ),
)

_ACTION = (
    *_OU,
    Param(
        'action',
        'text',
        True,
        'ouvrir, cliquer, double_cliquer, clic_droit, survoler, glisser,'
        ' taper, taper_secret, choisir, touche, defiler, revenir,'
        ' recharger, attendre, ecran, deposer_fichier, lire_telechargement,'
        ' fermer_onglet, accepter_dialogue, refuser_dialogue,'
        ' passer_au_vrai_chrome ou garder_cle (garde la clé d’API'
        ' affichée dans l’élément visé par ref, sans la recopier : pour'
        ' une tâche qui branche un service).',
    ),
    Param(
        'ref',
        'text',
        False,
        'Le repère de l’élément visé : e7 (e7.e2 dans un cadre intégré).',
    ),
    Param(
        'text',
        'text',
        False,
        'L’adresse (ouvrir) ; le texte visible de ce qui est visé, quand il'
        ' n’a pas de repère (cliquer, double_cliquer, clic_droit,'
        ' survoler) ; le texte (taper) ; le nom du secret (taper_secret) ;'
        ' l’option (choisir) ; la touche ou le raccourci (Enter, Escape,'
        ' Tab, Control+A) ; haut ou bas (defiler) ; le texte attendu'
        ' (attendre) ; ordinateur ou mobile (ecran) ; le nom du fichier'
        ' (deposer_fichier, lire_telechargement) ; le texte à taper dans'
        ' une boîte de saisie (accepter_dialogue).',
    ),
    Param(
        'x',
        'number',
        False,
        'Avec y : un point de l’écran, en pixels depuis le coin en haut à'
        ' gauche, lu sur une capture de l’écran. Pour viser ce qui n’a ni'
        ' repère ni texte (un dessin, une carte).',
    ),
    Param('y', 'number', False, 'Voir x.'),
    Param(
        'to',
        'text',
        False,
        'Où déposer ce qu’on glisse : un repère (e9), un texte visible ou un'
        ' point (640,300).',
    ),
    Param(
        'content',
        'text',
        False,
        'Le contenu du fichier à déposer (deposer_fichier) ; sans lui, un'
        ' fichier téléchargé dans la session, par son nom.',
    ),
    Param(
        'line',
        'number',
        False,
        'La première ligne à lire (lire_telechargement).',
    ),
    Param('submit', 'bool', False, 'Taper puis valider avec Entrée.'),
    Param(
        'service',
        'text',
        False,
        'Le service externe que la tâche branche : garder_cle range sa clé'
        ' pour lui. Figé en base.',
        frozen=True,
    ),
    Param(
        'secrets',
        'text',
        False,
        'Les secrets permis pour taper_secret (figé en base).',
        frozen=True,
    ),
    Param(
        'secret_sites',
        'text',
        False,
        'Les sites où taper_secret peut taper ces secrets, séparés par des'
        ' virgules : stripe.com vaut aussi pour checkout.stripe.com. Vide :'
        ' partout. Figé en base.',
        frozen=True,
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
        'Une action dans la page, comme une personne avec une souris et un'
        ' clavier : ouvrir une adresse, cliquer (aussi double clic et clic'
        ' droit), survoler, glisser et déposer, taper, choisir dans une'
        ' liste, appuyer sur une touche, faire défiler, revenir, recharger,'
        ' attendre un texte, déposer un fichier, passer en écran ordinateur'
        ' ou mobile. Ce qui est visé se désigne par son repère (ref), sinon'
        ' par son texte visible (text), sinon par un point de l’écran (x,'
        ' y) lu sur une capture. Sans repère, taper écrit au clavier, là où'
        ' est le curseur. Rend la page relue en version courte (une'
        ' ligne par titre, texte, champ, bouton, lien ou élément cliquable,'
        ' avec son repère [e7] ; le contenu d’un cadre intégré est sous sa'
        ' ligne) et les nouvelles erreurs de la page. L’adresse'
        ' http://chantier:<port> mène au chantier du business. Le résultat'
        ' dit aussi ce qui arrive hors de la page. « telechargements » :'
        ' un fichier téléchargé, son nom, sa taille et son début ;'
        ' lire_telechargement lit la suite. « onglets » : un nouvel onglet'
        ' s’est ouvert, tu y es ; fermer_onglet revient au précédent.'
        ' « dialogues » : une boîte de dialogue du navigateur (un message,'
        ' une question OK ou Annuler, la saisie d’un texte), à laquelle'
        ' Serge a répondu. Sans réponse préparée, un message est fermé et'
        ' une question ou une saisie est refermée par « Annuler ». Pour y'
        ' répondre, prépare ta réponse avec accepter_dialogue (text : le'
        ' texte à taper, pour une saisie) ou refuser_dialogue, puis fais'
        ' l’action qui ouvre la boîte : la réponse sert une fois. Si une'
        ' page refuse ce navigateur sans écran (page blanche, captcha),'
        ' passer_au_vrai_chrome continue la session dans le vrai Chrome, à'
        ' la même adresse et avec la même connexion.',
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
        'serge/sandbox/captures.py',
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
        'serge/sandbox/captures.py',
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
