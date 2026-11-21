#!/usr/bin/env python3
"""Libellés FR Mission Control : événements, états, phrases pédagogiques."""

from __future__ import annotations

from serge.funnels.points import texte_points

EVENTS = {
    'cycle': 'Cycle',
    'guard': 'Garde-fou',
    'created': 'Créé',
    'sent': 'Envoyé',
    'email.sent': 'E-mail envoyé',
    'email.delivered': 'E-mail livré',
    'email.queued': 'E-mail en file',
    'sms.sent': 'SMS envoyé',
    'sms.received': 'SMS reçu',
    'sms.refused': 'SMS refusé à l’arrivée',
    'task.done': 'Tâche terminée',
    'task.failed': 'Tâche échouée',
    'task.restarted': 'Chaîne repartie d’une tâche',
    'task.cancelled': 'Tâche annulée',
    'task.resumed': 'Tâche reprise après un arrêt',
    'task.cut': 'Tâche arrêtée par le coupe-circuit',
    'task.frozen': 'Tâche gelée : elle attend Julien',
    'task.thawed': 'Tâche repartie avec la réponse de Julien',
    'task.no_credit': 'Tâche remise à plus tard : plus de crédit chez le fournisseur du modèle',
    'tool.call': 'Outil appelé',
    'sandbox.command': 'Commande lancée dans un chantier',
    'browser.capture': 'Capture gardée',
    'api.call': 'Appel à un service',
    'human.help': 'Un humain appelé (captcha)',
    'trial.started': 'Essai total lancé',
    'trial.stopped': 'Essai total arrêté',
    'prospect.added': 'Prospect ajouté à une campagne',
    'prospect.domain_unchecked': 'Domaine d’un prospect non vérifié (résolveur DNS injoignable)',
    'contact.customer': 'Contact devenu client',
    'write.inserted': 'Ligne ajoutée',
    'write.updated': 'Ligne modifiée',
    'write.refused': 'Écriture refusée',
    'write.skipped': 'Doublon écarté',
    'invocation.compare': 'Tables à comparer changées',
    'invocation.prompt': 'Consigne d’une invocation changée',
    'link.passed': 'Passage à la main',
    'link.auto': 'Passage automatique changé',
    'pipeline.model': 'Modèle d’un niveau changé',
    'pipeline.text': 'Texte « Qui est Serge » changé',
    'feed.toggled': 'Flux RSS coupé ou rallumé',
    'write.deleted': 'Lignes supprimées',
    'mc_act': 'Acte owner',
    'transition.approved': 'Approuvé',
    'transition.rejected': 'Rejeté',
}

TYPES_TICKET = {
    'GUICHET': 'Guichet',
    'FYI': 'Pour info',
    'REQUESTED': 'Demande d’évolution',
}

LIFECYCLE = {
    'CANDIDATE': 'Candidat',
    'POC_SELECTED': 'Choisi pour un test',
    'SMOKE_READY': 'Test léger prêt',
    'SMOKE_RUNNING': 'Test léger en cours',
    'SMOKE_DONE': 'Test léger retenu',
    'PARKED': 'Mis de côté',
    'PRODUCT_BUILDING': 'Produit en construction',
    'PRODUCT_READY': 'Produit en vente',
    'FULL_RUNNING': 'Prospection lourde en cours',
    'KILLED': 'Arrêté',
    'TEST': 'Business d’essai',
}

FUNNEL = {
    'NEW': 'Nouveau',
    'QUALIFIED': 'Qualifié',
    'CONTACTING': 'En prise de contact',
    'ENGAGED': 'Engagé',
    'INTENT': 'Intention d’achat',
    'MEETING': 'Rendez-vous',
    'CUSTOMER': 'Client',
    'REJECTED': 'Écarté',
    'UNREACHABLE': 'Injoignable',
    'OPTED_OUT': 'Désinscrit',
    'STOPPED': 'Arrêté',
    'BLOCKED': 'Bloqué',
    'INVALID': 'Fiche invalide',
}

REGIMES = {'OUTBOUND': 'Sortant', 'INBOUND': 'Entrant'}

ORBITES = {
    'sqlite': {
        'titre': 'SQLite',
        'pourquoi': 'Une seule vérité. Tout le reste est un miroir.',
    },
    'scheduler': {
        'titre': 'Files de tâches',
        'pourquoi': 'Le prochain travail est une requête, pas une intuition.',
    },
    'mail': {
        'titre': 'Mail',
        'pourquoi': 'Le canal nommé le plus fréquent : toucher et répondre.',
    },
    'discord': {
        'titre': 'Discord',
        'pourquoi': 'Même tickets qu’ici : tu tranches, Serge exécute.',
    },
    'voix': {
        'titre': 'Voix',
        'pourquoi': 'Appels quand le canal l’exige, avec garde-fous FR.',
    },
    'memoire': {
        'titre': 'Mémoire',
        'pourquoi': 'Leçons et pièges pour ne pas refaire la même erreur.',
    },
    'policy': {
        'titre': 'Policy',
        'pourquoi': 'Les nombres qui autorisent ou refusent un acte.',
    },
    'stripe': {
        'titre': 'Stripe',
        'pourquoi': 'Le rail d’encaissement. Pas de full sans caisse prête.',
    },
}

ETATS_CAMPAGNE = {
    'DRAFT': 'Brouillon',
    'READY': 'Prête',
    'RUNNING': 'En cours',
    'FINISHED': 'Terminée',
    'CANCELLED': 'Annulée',
}

ETATS_TICKET = {
    'DRAFT': 'Brouillon',
    'OPEN': 'Ouvert',
    'DISCUSSING': 'En discussion',
    'APPROVED': 'Approuvé',
    'REJECTED': 'Rejeté',
    'EXPIRED': 'Expiré',
    'EDITED': 'Édité',
}

CANAUX = {
    'email': 'e-mail',
    'voice': 'voix',
    'sms': 'SMS',
    'discord': 'Discord',
}

ETATS_FACTURE = {
    'paid': 'Payée',
    'draft': 'Brouillon',
    'failed': 'Échouée',
    'open': 'Ouverte',
}


def verbe(kind: str) -> str:
    """Libellé humain d’un événement (jamais le brut)."""
    return EVENTS.get(kind) or kind.replace('.', ' · ')


def phrase_noyau(
    urgents: int, running: dict | None, paid: float, demarre: bool = True
) -> str:
    """Une phrase à la première personne pour le noyau."""
    if not demarre:
        return 'Je suis arrêté. Je ne travaille qu’après « Démarrer Serge ».'
    if urgents:
        return f'J’attends ta décision — {urgents} urgent(s) me bloquent.'
    if running:
        return f'Je travaille : {verbe(str(running.get("kind", ""))).lower()}.'
    if paid > 0:
        euros = f'{paid:.0f}'.replace('.', ',')
        return f'J’ai encaissé {euros} € sur le test en cours.'
    return 'Je scrute. Rien d’urgent — le prochain travail viendra tout seul.'


def phrase_recit(
    nom: str,
    lifecycle: str,
    u1: int,
    u2: int,
    u3: int,
    paid: float,
    points: float = 0.0,
    par_euro: float | None = None,
) -> str:
    """Phrase métier pour un étranger : touche → réponse → points → euro."""
    cycle = LIFECYCLE.get(lifecycle, lifecycle)
    euros = f'{paid:.0f}'.replace('.', ',')
    repondu = 'a répondu' if u2 == 1 else 'ont répondu'
    oui = 'a dit oui' if u3 == 1 else 'ont dit oui'
    total = texte_points(points)
    rendement = (
        f' ({texte_points(par_euro)} par euro dépensé)'
        if par_euro is not None
        else ''
    )
    return (
        f'{nom} — {cycle}. {u1} personnes touchées, {u2} {repondu},'
        f' {u3} {oui}, {total} points{rendement}. {euros} € encaissés.'
    )


# Les niveaux de modèle d'une invocation.
NIVEAUX = {
    'fast': 'Rapide — un réflexe (classer, extraire). Le moins cher.',
    'mid': 'Moyen — assez malin pour rédiger ou comparer.',
    'smart': 'Intelligent — plans, arbitrages.',
    'code': 'Code — construire un produit. Le meilleur modèle, qui lit les'
    ' images ; le plus cher (décision Q91).',
    'web': 'Web — voir et cliquer des pages comme un humain : essayer un'
    ' produit, payer. Un modèle qui lit les images, moins cher que « code »'
    ' (décision Q96).',
}
