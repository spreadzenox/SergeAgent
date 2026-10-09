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
    'task.done': 'Tâche terminée',
    'task.failed': 'Tâche échouée',
    'task.relaunched': 'Tâche relancée',
    'task.cancelled': 'Tâche annulée',
    'task.resumed': 'Tâche reprise après un arrêt',
    'write.inserted': 'Ligne ajoutée',
    'write.updated': 'Ligne modifiée',
    'write.refused': 'Écriture refusée',
    'write.skipped': 'Doublon écarté',
    'invocation.compare': 'Tables à comparer changées',
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
    'VETO_AMONT': 'Veto amont',
    'ALERT': 'Alerte',
    'HYPOTHESIS': 'Idée de business',
    'MEMORY': 'Mémoire',
    'POLICY': 'Policy',
    'FYI': 'Pour info',
    'QNA': 'Question',
    'PUBLICATION': 'Publication',
    'R1_OVERRIDE': 'Dépassement R1',
    'REQUESTED': 'Demande d’évolution',
    'OWNER_ORDER': 'Ordre owner',
}

LIFECYCLE = {
    'CANDIDATE': 'Candidat',
    'POC_SELECTED': 'Choisi pour un test',
    'SMOKE_READY': 'Smoke prêt',
    'SMOKE_RUNNING': 'Smoke en cours',
    'SMOKE_DONE': 'Smoke terminé',
    'FULL_READY': 'Full prêt',
    'FULL_RUNNING': 'Full en cours',
    'SCALE': 'Passage à l’échelle',
    'PIVOT': 'Pivot',
    'EXTEND': 'Extension',
    'KILLED': 'Arrêté',
    'INVALID_RETRY': 'À refaire',
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
    'RUNNING': 'En cours',
    'PAUSED': 'En pause',
    'DONE': 'Terminé',
    'DRAFT': 'Brouillon',
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
) -> str:
    """Phrase métier pour un étranger : touche → réponse → points → euro."""
    cycle = LIFECYCLE.get(lifecycle, lifecycle)
    euros = f'{paid:.0f}'.replace('.', ',')
    repondu = 'a répondu' if u2 == 1 else 'ont répondu'
    oui = 'a dit oui' if u3 == 1 else 'ont dit oui'
    total = texte_points(points)
    return (
        f'{nom} — {cycle}. {u1} personnes touchées, {u2} {repondu},'
        f' {u3} {oui}, {total} points. {euros} € encaissés.'
    )


# Les niveaux de modèle d'une invocation.
NIVEAUX = {
    'fast': 'Rapide — un réflexe (classer, extraire). Le moins cher.',
    'mid': 'Moyen — assez malin pour rédiger ou comparer.',
    'smart': 'Intelligent — plans, arbitrages. Le plus cher.',
}
