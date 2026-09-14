#!/usr/bin/env python3
"""Libellés FR Mission Control : kinds, events, enums, phrases pédagogiques."""

from __future__ import annotations

KINDS = {
    'email.send': 'Envoi d’e-mail',
    'email.poll': 'Collecte de la boîte',
    'voice.send': 'Appel sortant',
    'voice.score': 'Notation d’un appel',
    'inbound.classify': 'Classification d’une réponse',
    'inbound.reply_priority': 'Réponse prioritaire',
    'inbound.judge_other': 'Arbitrage des messages autres',
    'listen.collect': 'Ramasser des pages',
    'listen.cluster': 'Regrouper les demandes',
    'memory.consolidate': 'Consolidation de la mémoire',
    'memory.apply': 'Application d’une leçon',
}

EVENTS = {
    'cycle': 'Cycle',
    'guard': 'Garde-fou',
    'created': 'Créé',
    'sent': 'Envoyé',
    'email.sent': 'E-mail envoyé',
    'email.delivered': 'E-mail livré',
    'email.queued': 'E-mail en file',
    'sms.sent': 'SMS envoyé',
    'work.enqueued': 'Tâche mise en file',
    'work.claimed': 'Tâche prise en charge',
    'work.completed': 'Tâche terminée',
    'work.failed': 'Tâche échouée',
    'mc_act': 'Acte owner',
    'llm.io': 'Réflexion d’un agent',
    'transition.approved': 'Approuvé',
    'transition.rejected': 'Rejeté',
}

ETATS_WORK = {
    'READY': 'Prêt',
    'RUNNING': 'En cours',
    'DONE': 'Terminé',
    'FAILED': 'Échoué',
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

NOEUDS = {
    'pre_prospection': {
        'titre': 'Pré-prospection',
        'pourquoi': 'Écoute des réseaux, clustering : sentir une demande réelle.',
        'argent': 'Sans demande observée, pas de pré-venture à concevoir.',
    },
    'conception_poc': {
        'titre': 'Conception d’un PoC',
        'pourquoi': 'Pré-venture, produit, specs, prérequis, puis builder si besoin.',
        'argent': 'Le PoC sert à faire valoir que le produit existe.',
    },
    'prospection_light': {
        'titre': 'Prospection light',
        'pourquoi': 'Smoke test multicanal (N configurable) avec le PoC s’il existe.',
        'argent': 'On mesure le message, pas encore l’encaissement.',
    },
    'choix_venture': {
        'titre': 'Choix de venture',
        'pourquoi': 'Parmi les N pré-ventures, garder la plus prometteuse.',
        'argent': 'Un seul actif aujourd’hui ; MC pourra en ouvrir d’autres.',
    },
    'build_venture': {
        'titre': 'Build / rebuild',
        'pourquoi': 'Livrable, delivery, onboarding — la venture devient active.',
        'argent': 'Sans livrable, la prospection lourde vend du vent.',
    },
    'prospection_lourde': {
        'titre': 'Prospection lourde',
        'pourquoi': 'Échanges, démo, devis signé, client actif.',
        'argent': 'C’est ici qu’une touche devient un contrat.',
    },
    'collect_feedback': {
        'titre': 'Collect feedback',
        'pourquoi': 'Mails, voix, réseaux, leçons — améliorer le livrable ou Serge.',
        'argent': 'Les leçons évitent de payer deux fois la même erreur.',
    },
    'caisse': {
        'titre': 'Caisse',
        'pourquoi': 'Stripe encaisse. Scale, pivot ou arrêt selon les seuils.',
        'argent': 'L’euro entre ici. Tout le reste sert ce nœud.',
    },
}

ORBITES = {
    'sqlite': {
        'titre': 'SQLite',
        'pourquoi': 'Une seule vérité. Tout le reste est un miroir.',
    },
    'scheduler': {
        'titre': 'Ordonnanceur',
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

LLM_ETAPE = {
    'cluster_demand': 'pre_prospection',
    'draft_hypothesis_smoke': 'conception_poc',
    'draft_hypothesis_full': 'choix_venture',
    'resume_test': 'choix_venture',
    'plan_scale': 'prospection_lourde',
    'options_pivot': 'choix_venture',
    'qualify_prospect': 'prospection_light',
    'fill_slots': 'prospection_light',
    'score_lead_departage': 'prospection_light',
    'write_followup': 'prospection_lourde',
    'voice_script': 'prospection_lourde',
    'voice_dialog': 'prospection_lourde',
    'summarize_thread': 'prospection_lourde',
    'classify_reply': 'prospection_lourde',
    'extract_meeting': 'prospection_lourde',
    'reply_intent': 'prospection_lourde',
    'review_other': 'prospection_lourde',
    'score_call': 'prospection_lourde',
    'draft_price': 'prospection_lourde',
    'judge_allocator': 'prospection_lourde',
    'consolidate': 'collect_feedback',
    'edit_serge_md': 'collect_feedback',
    'build_artifact': 'build_venture',
    'review_build': 'build_venture',
    'summarize_build_debt': 'build_venture',
    'render_context_fr': 'prospection_lourde',
    'classify_owner_intent': 'policy',
    'judge_consequence': 'policy',
    'install_guide': 'policy',
}

SECTIONS_POLICY = {
    'budget': 'Budget',
    'quotas': 'Quotas',
    'windows': 'Fenêtres horaires',
    'calling_zones': 'Zones d’appel',
    'cooldowns': 'Temps de pause',
    'voice': 'Voix',
    'observation': 'Observation',
    'builder': 'Builder',
    'prospection': 'Prospection',
    'collect': 'Encaissement',
    'memory': 'Mémoire',
    'tickets': 'Tickets',
    'consent': 'Consentement',
    'listen': 'Écoute',
}


LLM_TITRES = {
    'draft_hypothesis_smoke': 'Écrire l’idée de business',
    'draft_hypothesis_full': 'Écrire l’idée (après essai)',
    'plan_scale': 'Comment grandir',
    'options_pivot': 'Trois autres idées',
    'resume_test': 'Raconter l’essai',
    'qualify_prospect': 'Cette personne est-elle dans la cible ?',
    'fill_slots': 'Remplir les créneaux',
    'write_followup': 'Écrire une relance',
    'voice_script': 'Écrire un script d’appel',
    'voice_dialog': 'Dialoguer à l’oral',
    'summarize_thread': 'Résumer un fil',
    'score_lead_departage': 'Départager deux pistes',
    'build_artifact': 'Construire un livrable',
    'review_build': 'Relire un livrable',
    'summarize_build_debt': 'Résumer la dette builder',
    'classify_reply': 'Classer une réponse',
    'extract_meeting': 'Extraire un rendez-vous',
    'reply_intent': 'Répondre à une intention',
    'review_other': 'Relire un message autre',
    'score_call': 'Noter un appel',
    'draft_price': 'Proposer un prix',
    'judge_allocator': 'Arbitrer l’allocation',
    'consolidate': 'Consolider la mémoire',
    'edit_serge_md': 'Éditer SERGE.md',
    'render_context_fr': 'Rendre le contexte FR',
    'classify_owner_intent': 'Lire l’intention owner',
    'judge_consequence': 'Juger une conséquence',
    'cluster_demand': 'Regrouper la demande',
    'install_guide': 'Guider l’installation',
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
    """Libellé humain d’un kind worker ou event (jamais le brut)."""
    return KINDS.get(kind) or EVENTS.get(kind) or kind.replace('.', ' · ')


def titre_llm(nom: str) -> str:
    """Nom humain d’un point LLM (jamais le snake_case seul)."""
    return LLM_TITRES.get(nom) or nom.replace('_', ' ')


def phrase_noyau(urgents: int, running: dict | None, paid: float) -> str:
    """Une phrase à la première personne pour le noyau."""
    if urgents:
        return f'J’attends ta décision — {urgents} urgent(s) me bloquent.'
    if running:
        return f'Je travaille : {verbe(str(running.get("kind", ""))).lower()}.'
    if paid > 0:
        euros = f'{paid:.0f}'.replace('.', ',')
        return f'J’ai encaissé {euros} € sur le test en cours.'
    return 'Je scrute. Rien d’urgent — le prochain travail viendra tout seul.'


def phrase_recit(
    nom: str, lifecycle: str, u1: int, u2: int, u3: int, paid: float
) -> str:
    """Phrase métier pour un étranger : touche → réponse → euro."""
    cycle = LIFECYCLE.get(lifecycle, lifecycle)
    euros = f'{paid:.0f}'.replace('.', ',')
    repondu = 'a répondu' if u2 == 1 else 'ont répondu'
    oui = 'a dit oui' if u3 == 1 else 'ont dit oui'
    return (
        f'{nom} — {cycle}. {u1} personnes touchées, {u2} {repondu},'
        f' {u3} {oui}. {euros} € encaissés.'
    )
