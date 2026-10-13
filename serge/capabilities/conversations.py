#!/usr/bin/env python3
"""Les capacités des conversations : relever, lire le fil, envoyer,
relancer, les fiches des contacts, la désinscription et les tickets.
"""

from __future__ import annotations

from serge.capabilities.model import Capability, Param

CONVERSATIONS: tuple[Capability, ...] = (
    Capability(
        'receive_messages',
        'Relever les messages d’un canal',
        'Lit les messages reçus sur un canal depuis sa dernière relève, et'
        ' rattache chacun à son contact : par le fil (il répond à un message'
        ' de Serge), sinon par l’adresse de l’expéditeur. Un message sans'
        ' contact est rendu « non rattaché ». Un message déjà relevé n’est'
        ' jamais rendu deux fois.',
        'serge/conversations/receive.py',
        (Param('channel', 'text', True, 'Le canal à relever.'),),
    ),
    Capability(
        'contact_thread',
        'Lire le fil d’un contact',
        'Rend tout ce qui s’est dit avec un contact, tous canaux confondus,'
        ' du plus ancien au plus récent : les messages partis et les'
        ' messages reçus.',
        'serge/conversations/thread.py',
        (Param('contact_id', 'text', True, 'Le contact.'),),
    ),
    Capability(
        'send_message',
        'Envoyer un message',
        'Envoie un message écrit dans les envois, par l’adaptateur de son'
        ' canal, après les garde-fous. Ne l’envoie jamais deux fois : son'
        ' état est enregistré avant et après l’envoi, et un envoi'
        ' interrompu est confirmé auprès du canal. Annule un message devenu'
        ' inutile (le contact a écrit depuis, ou s’est désinscrit).',
        'serge/conversations/send.py',
        (Param('touch_id', 'text', True, 'L’envoi à faire partir.'),),
        acts_outside=True,
    ),
    Capability(
        'due_followups',
        'Trouver les relances à faire',
        'Rend les contacts à relancer : leur dernier message est parti, ils'
        ' n’ont rien écrit depuis, le délai réglé dans la policy est passé,'
        ' et leur canal a été relevé récemment.',
        'serge/conversations/followups.py',
    ),
    Capability(
        'add_contact',
        'Créer un contact',
        'Crée la fiche d’un contact pour un business, avec son e-mail et son'
        ' numéro (mis au format international), et, au besoin, son accord'
        ' pour être appelé (consent, ou test pour un membre de l’équipe qui'
        ' essaie Serge : sa désinscription éventuelle est alors levée).'
        ' Rend la fiche créée.',
        'serge/conversations/contact.py',
        (
            Param('venture_id', 'text', True, 'Le business.'),
            Param('name', 'text', True, 'Son nom.'),
            Param('email', 'text', False, 'Son adresse e-mail.'),
            Param(
                'phone',
                'text',
                False,
                'Son numéro : +33…, ou national du pays par défaut (06…).',
            ),
            Param('call_consent', 'text', False, 'consent, test, ou vide.'),
        ),
    ),
    Capability(
        'contact_search',
        'Chercher un contact',
        'Cherche une fiche de contact par son e-mail ou son numéro, sinon par'
        ' un morceau de son nom. Rend au plus 5 fiches : numéro, nom,'
        ' business, étape ; jamais ses adresses ni son fil.',
        'serge/conversations/contact.py',
        (Param('query', 'text', True, 'Le nom, l’e-mail ou le numéro.'),),
    ),
    Capability(
        'add_contact_address',
        'Noter une adresse',
        'Ajoute une adresse e-mail ou un numéro à la fiche d’un contact, à'
        ' côté des autres : une adresse n’est jamais écrasée. L’adresse que'
        ' la personne corrige est désactivée.',
        'serge/conversations/contact.py',
        (
            Param('contact_id', 'text', True, 'Le numéro du contact.'),
            Param('channel', 'text', True, 'email ou phone.'),
            Param(
                'value', 'text', True, 'L’adresse, confirmée par la personne.'
            ),
            Param(
                'replaces',
                'text',
                False,
                'L’adresse fausse qu’elle remplace, s’il y en a une.',
            ),
        ),
    ),
    Capability(
        'unsubscribe_contact',
        'Désinscrire une personne partout',
        'Bloque toutes les adresses d’une personne, sur tous les canaux ;'
        ' passe toutes ses fiches, dans tous les business, à « Désinscrit » ;'
        ' annule ses envois en attente.',
        'serge/conversations/unsubscribe.py',
        (Param('contact_id', 'text', True, 'Le contact désinscrit.'),),
    ),
    Capability(
        'inform_owners',
        'Prévenir Julien et Clem',
        'Ouvre un ticket d’information (sans réponse attendue), visible dans'
        ' Mission Control et sur Discord.',
        'serge/tickets/inform.py',
        (
            Param('title', 'text', True, 'Le titre du ticket.'),
            Param('text', 'text', False, 'Ce qui s’est passé.'),
            Param('contact_id', 'text', False, 'Le contact concerné.'),
        ),
    ),
    Capability(
        'ask_owners',
        'Demander à Julien',
        'Ouvre un ticket qui fait attendre, envoyé à chaque administrateur :'
        ' il porte sur une ligne (un envoi qui attend), montre ce que son'
        ' type de ticket nomme en base (le business, le prospect, le fil, le'
        ' brouillon), puis pourquoi Serge demande et la question précise. Un'
        ' ticket encore ouvert sur la même ligne est mis à jour et rouvert.',
        'serge/tickets/demander.py',
        (
            Param('ticket_type', 'text', True, 'Le type de ticket.'),
            Param('ref_table', 'text', True, 'La table de la ligne.'),
            Param('ref_id', 'text', True, 'La ligne dont parle le ticket.'),
            Param('raison', 'text', True, 'Pourquoi Serge demande.'),
            Param('question', 'text', False, 'La question précise.'),
            Param('title', 'text', False, 'Le titre du ticket.'),
        ),
    ),
)
