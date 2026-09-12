// Catalogue Policy (données déclaratives, exception P1) : titres, aides, widget.

export const SECTIONS = {
  budget: {
    titre: 'Argent',
    pourquoi: 'Combien Serge a le droit de dépenser. Au-delà, il s’arrête.',
  },
  quotas: {
    titre: 'Plafonds par canal',
    pourquoi: 'Combien de messages, appels ou invitations par jour — pour ne pas spammer.',
  },
  windows: {
    titre: 'Horaires',
    pourquoi: 'Quand on a le droit de parler aux gens, et quand on se tait.',
  },
  calling_zones: {
    titre: 'Pays et appels',
    pourquoi: 'Les règles changent selon le pays (légal + fuseau).',
  },
  cooldowns: {
    titre: 'Temps de pause',
    pourquoi: 'Combien de jours on attend avant de relancer, pour ne pas harceler.',
  },
  voice: {
    titre: 'Téléphone',
    pourquoi: 'Durée, qualité, conservation des appels.',
  },
  observation: {
    titre: 'Lecture des réponses',
    pourquoi: 'À partir de quand on croit un jugement sur un message reçu.',
  },
  builder: {
    titre: 'Construction',
    pourquoi: 'Bornes quand Serge fabrique un livrable (fichiers, passages).',
  },
  prospection: {
    titre: 'Qui on garde',
    pourquoi: 'Le barème qui dit « dans la cible » ou « on passe ».',
  },
  collect: {
    titre: 'Encaissement',
    pourquoi: 'Prix, devis, relances de paiement, petits remboursements.',
  },
  memory: {
    titre: 'Mémoire',
    pourquoi: 'Quand on range, ce qu’on garde, ce qu’on oublie.',
  },
  tickets: {
    titre: 'Tes questions',
    pourquoi: 'À quelle heure le résumé du jour, et quand un type de question peut passer tout seul.',
  },
  consent: {
    titre: 'Accord des gens',
    pourquoi: 'Sur quels canaux il faut un oui explicite avant d’écrire ou d’appeler.',
  },
  listen: {
    titre: 'Écoute du web',
    pourquoi: 'Quand un paquet de demandes est assez fort pour valoir un essai.',
  },
};

// [titre, aide, widget, min|choix, max, pas]
export const CHAMPS = {
  'budget.monthly_eur': [
    'Plafond du mois',
    'Tout compris. Au-delà, plus rien ne part.',
    'eur',
    0,
    500,
    1,
  ],
  'budget.llm_daily_eur': [
    'Jugements, par jour',
    'Le plafond € des réflexions (celui des budgets du jour).',
    'eur',
    0,
    50,
    0.5,
  ],
  'budget.llm_eur_per_1k_tokens': [
    'Prix estimé de 1 000 jetons',
    'Sert à convertir les jetons en euros dans les jauges. Ne change pas la facture réelle.',
    'eur',
    0,
    0.05,
    0.001,
  ],
  'budget.test_provision_monthly_eur': [
    'Réserve pour les micro-essais',
    'Petite enveloppe à part, pour tester sans manger le mois.',
    'eur',
    0,
    20,
    0.5,
  ],
  'budget.browserbase_monthly_cap_eur': [
    'Navigateur, par mois',
    'Plafond si un jour on ouvre le web pour de vrai.',
    'eur',
    0,
    50,
    1,
  ],
  'budget.allocator_reserve_ratio': [
    'Part qu’on garde en réserve',
    'On ne mise pas tout. 20 % = un cinquième de côté.',
    'pct',
    0,
    1,
    0.05,
  ],
  'budget.allocator_max_unproven_ratio': [
    'Part max sur du non prouvé',
    'Au-delà, on arrête d’investir dans une idée encore fragile.',
    'pct',
    0,
    1,
    0.05,
  ],
  'budget.allocator_max_single_channel_ratio': [
    'Part max sur un seul canal',
    'Pour ne pas tout miser sur l’e-mail, ou tout sur l’appel.',
    'pct',
    0,
    1,
    0.05,
  ],
  'budget.allocator_reversal_points': [
    'Revirement : à partir de combien de points',
    'Si l’effort bascule trop fort, Serge doit justifier.',
    'curseur',
    1,
    40,
    1,
  ],
  'budget.allocator_bandit_gap_points': [
    'Écart trop grand avec le calcul',
    'Au-delà, une explication plus longue est exigée.',
    'curseur',
    1,
    40,
    1,
  ],
  'budget.allocator_trigger_spent_ratio': [
    'Seuil « on a trop dépensé »',
    'Arrivé là, on revoit où va l’argent.',
    'pct',
    0,
    1,
    0.05,
  ],
  'budget.allocator_bandit_cost_per_eur': [
    'Pénalité coût (points par euro)',
    'Plus c’est cher, plus le calcul décourage de continuer.',
    'curseur',
    0,
    40,
    1,
  ],
  'quotas.email_per_mailbox_per_day': [
    'E-mails par boîte, par jour',
    'Le 2 / 40 des budgets du jour.',
    'curseur',
    0,
    200,
    1,
  ],
  'quotas.voice_max_calls_per_day': [
    'Appels par jour',
    'Plafond d’appels sortants.',
    'curseur',
    0,
    200,
    1,
  ],
  'quotas.sms_per_sender_per_min': [
    'SMS par expéditeur, par minute',
    'Anti-rafale. Pas un plafond journalier.',
    'curseur',
    1,
    30,
    1,
  ],
  'quotas.sms_global_per_min': [
    'SMS au total, par minute',
    'Toutes les lignes confondues.',
    'curseur',
    1,
    120,
    1,
  ],
  'quotas.memory_search_per_cycle_per_point': [
    'Fois qu’un jugement peut fouiller la mémoire',
    'Par cycle, par jugement. Au-delà il s’arrête.',
    'curseur',
    0,
    10,
    1,
  ],
  'quotas.llm_recalls_json': [
    'Rappels si la réponse est mal formée',
    'Combien de fois on redemande un JSON propre.',
    'curseur',
    0,
    5,
    1,
  ],
  'quotas.linkedin_connect_per_day': [
    'Invitations LinkedIn par jour',
    'Le compteur des budgets du jour.',
    'curseur',
    0,
    80,
    1,
  ],
  'quotas.linkedin_inmail_per_month': [
    'Messages LinkedIn payants, par mois',
    'Les InMails, pas les invitations.',
    'curseur',
    0,
    200,
    1,
  ],
  'windows.timezone': [
    'Fuseau',
    'Toutes les heures ci-dessous sont lues dans ce fuseau.',
    'liste',
    ['Europe/Paris', 'Europe/Brussels', 'Europe/London', 'UTC'],
  ],
  'windows.intent_sla_hours': [
    'Délai max pour une intention d’achat',
    'Au-delà, c’est en retard — quelqu’un a dit « oui » et on n’a pas suivi.',
    'curseur',
    1,
    48,
    1,
  ],
  'windows.intent_biz_hours': [
    'Heures où on peut relancer une intention',
    'En dehors, on attend.',
    'fenetres',
  ],
  'windows.quiet_hours': [
    'Heures silencieuses',
    'Pas de notif, sauf un guichet qui expire très vite.',
    'fenetres',
  ],
  'calling_zones.default': [
    'Pays par défaut',
    'Si on ne sait pas où est la personne.',
    'liste',
    ['FR', 'BE', 'CH'],
  ],
  'calling_zones.FR.timezone': [
    'Fuseau (France)',
    'Les plages d’appel FR sont lues ici.',
    'liste',
    ['Europe/Paris', 'Europe/Brussels'],
  ],
  'calling_zones.FR.voice_windows': [
    'Plages d’appel (France)',
    'On n’appelle pas en dehors. Midi est souvent coupé.',
    'fenetres',
  ],
  'calling_zones.FR.voice_days': [
    'Jours où on peut appeler',
    'En France, plutôt les jours ouvrés.',
    'jours',
  ],
  'calling_zones.FR.prospecting_days': [
    'Jours où on peut prospecter',
    'Premier contact, pas seulement les relances.',
    'jours',
  ],
  'calling_zones.FR.contact_per_30d': [
    'Prises de contact max / 30 jours / personne',
    'Règle légale FR. Monter ça = ticket + motif.',
    'curseur',
    1,
    8,
    1,
  ],
  'calling_zones.FR.appointment_margin_min': [
    'Marge avant un rendez-vous (min)',
    'On n’appelle pas à 2 minutes du créneau.',
    'curseur',
    0,
    60,
    5,
  ],
  'calling_zones.FR.holidays': [
    'Calendrier des fériés',
    'Les jours fériés de ce pays sont exclus.',
    'liste',
    ['FR', 'BE', 'CH', 'DE'],
  ],
  'cooldowns.inbound_silence_days': [
    'Silence avant de relancer quelqu’un venu tout seul',
    'S’il a écrit puis plus rien.',
    'curseur',
    1,
    30,
    1,
  ],
  'cooldowns.thread_days_per_venue': [
    'Jours min entre deux fils au même endroit',
    'Évite de spammer un forum ou un groupe.',
    'curseur',
    1,
    30,
    1,
  ],
  'cooldowns.guichet_repropose_backoff_days': [
    'Attentes avant de te reposer la même question',
    'Exemple : 1 jour, puis 3, puis 7.',
    'nombres',
  ],
  'cooldowns.guichet_repropose_max': [
    'Fois max qu’on te repose la question',
    'Après, on arrête.',
    'curseur',
    1,
    8,
    1,
  ],
  'voice.npv_per_venture': [
    'Un numéro par venture',
    'Chaque idée de business a sa ligne, pas un numéro unique pour tout.',
    'ouinon',
  ],
  'voice.record_retention_hot_days': [
    'Garder l’audio sous la main (jours)',
    'Ensuite ça passe en archive, ou ça disparaît.',
    'curseur',
    7,
    365,
    1,
  ],
  'voice.record_retention_archive_years': [
    'Archive audio (années)',
    'Après, purge.',
    'curseur',
    0,
    5,
    1,
  ],
  'voice.quality_window': [
    'Fenêtre pour juger la qualité (derniers appels)',
    'On regarde les N derniers, pas toute l’histoire.',
    'curseur',
    3,
    30,
    1,
  ],
  'voice.quality_min_score': [
    'Note en dessous de laquelle c’est mauvais',
    'Sur 5. Deux mauvais d’affilée → on pause.',
    'curseur',
    1,
    5,
    1,
  ],
  'voice.quality_max_bad': [
    'Mauvais appels max dans la fenêtre',
    'Au-delà, on coupe les appels.',
    'curseur',
    1,
    8,
    1,
  ],
  'voice.max_turns': [
    'Répliques max dans un appel',
    'Pour ne pas tourner en rond.',
    'curseur',
    4,
    30,
    1,
  ],
  'voice.max_duration_min': [
    'Durée max d’un appel (min)',
    'Au-delà on raccroche proprement.',
    'curseur',
    2,
    30,
    1,
  ],
  'voice.script_max_seconds': [
    'Script d’ouverture, durée max (s)',
    'Le pitch du début, pas tout l’appel.',
    'curseur',
    20,
    180,
    5,
  ],
  'observation.classify_confidence_min': [
    'Confiance min pour classer une réponse',
    'En dessous, un humain tranche.',
    'pct',
    0,
    1,
    0.05,
  ],
  'observation.meeting_confidence_min': [
    'Confiance min pour extraire un rendez-vous',
    'On ne bloque pas un agenda sur un « peut-être mardi ».',
    'pct',
    0,
    1,
    0.05,
  ],
  'observation.other_batch_max_items': [
    'Messages « autre » relus d’un coup',
    'Pour ne pas noyer le jugement qui relit le bruit.',
    'curseur',
    5,
    80,
    1,
  ],
  'observation.other_alert_pending': [
    'Alerte si trop de « autre » en attente',
    'Au-delà, ticket pour toi.',
    'curseur',
    5,
    200,
    5,
  ],
  'observation.tech_fail_pattern_per_week': [
    'Pannes techniques / semaine avant alerte',
    'Toujours le même échec = on te le dit.',
    'curseur',
    1,
    20,
    1,
  ],
  'builder.fix_max_items': [
    'Correctifs max d’un livrable',
    'On ne polit pas indéfiniment.',
    'curseur',
    1,
    20,
    1,
  ],
  'builder.passes_max': [
    'Passages max sur une construction',
    'Après, on s’arrête.',
    'curseur',
    1,
    10,
    1,
  ],
  'builder.gate3_spotcheck_n': [
    'Fichiers tirés au sort pour relecture',
    'Contrôle ponctuel, pas tout relire.',
    'curseur',
    1,
    20,
    1,
  ],
  'builder.artifact_max_files': [
    'Fichiers max dans un livrable',
    'Au-delà, trop gros.',
    'curseur',
    1,
    80,
    1,
  ],
  'builder.artifact_max_chars': [
    'Caractères max d’un livrable',
    'Garde-fou taille.',
    'nombre',
    1000,
    500000,
    1000,
  ],
  'prospection.qualify_confidence_min': [
    'Confiance min pour garder quelqu’un',
    'En dessous : hors cible.',
    'pct',
    0,
    1,
    0.05,
  ],
  'prospection.lead_score_gray': [
    'Zone grise du score (à départager)',
    'Entre les deux bornes, un jugement tranche.',
    'paire',
    0,
    100,
    1,
  ],
  'prospection.score_w_intent': [
    'Poids : intention d’achat',
    'Points ajoutés si la personne veut clairement.',
    'curseur',
    -40,
    80,
    1,
  ],
  'prospection.score_w_reply': [
    'Poids : une réponse',
    'Elle a répondu, même sans acheter.',
    'curseur',
    -20,
    40,
    1,
  ],
  'prospection.score_w_engaged': [
    'Poids : un échange',
    'Plus qu’un simple « reçu ».',
    'curseur',
    -20,
    40,
    1,
  ],
  'prospection.score_w_meeting': [
    'Poids : un rendez-vous',
    'Très fort signal.',
    'curseur',
    0,
    80,
    1,
  ],
  'prospection.score_w_negative': [
    'Poids : un non',
    'En négatif : ça descend le score.',
    'curseur',
    -80,
    0,
    1,
  ],
  'collect.refund_auto_max_eur': [
    'Remboursement auto, plafond €',
    'Au-dessus, toi tu décides.',
    'eur',
    0,
    50,
    0.5,
  ],
  'collect.draft_price_min_eur': [
    'Prix proposé, plancher €',
    'Le jugement prix ne descend pas sous ça.',
    'eur',
    0,
    1000,
    1,
  ],
  'collect.draft_price_max_eur': [
    'Prix proposé, plafond €',
    'Il n’invente pas un tarif hors bornes.',
    'nombre',
    1,
    1000000,
    1,
  ],
  'collect.dunning_days': [
    'Jours de relance de paiement',
    'Exemple : J+7 puis J+14.',
    'nombres',
  ],
  'collect.quote_required_above_eur': [
    'Devis obligatoire au-dessus de (€)',
    'En dessous, un prix simple suffit.',
    'eur',
    0,
    2000,
    10,
  ],
  'collect.recanary_months': [
    'Mois avant de retester une idée arrêtée',
    'On ne relance pas le lendemain.',
    'curseur',
    1,
    12,
    1,
  ],
  'memory.consolidation_days': [
    'Jours entre deux rangements de mémoire',
    'Trop souvent = bruit. Trop rarement = oubli.',
    'curseur',
    1,
    14,
    1,
  ],
  'memory.consolidate_max_items': [
    'Éléments max par rangement',
    'Pour ne pas tout avaler d’un coup.',
    'curseur',
    1,
    40,
    1,
  ],
  'memory.lesson_infirm_deprecate': [
    'Fois qu’une leçon se trompe avant qu’on la retire',
    'Trois erreurs, on ne s’y fie plus.',
    'curseur',
    1,
    10,
    1,
  ],
  'memory.episode_archive_days': [
    'Jours avant d’archiver un épisode',
    'Le détail brut quitte le quotidien.',
    'curseur',
    7,
    180,
    1,
  ],
  'memory.other_promote_per_week': [
    'Messages « autre » promus / semaine',
    'Ceux qu’on relit pour ne pas jeter un vrai oui.',
    'curseur',
    0,
    40,
    1,
  ],
  'memory.judge_oscillation_days': [
    'Jours pour détecter un jugement qui se contredit',
    'S’il change d’avis trop vite, on le voit.',
    'curseur',
    1,
    14,
    1,
  ],
  'memory.serge_md_max_lines': [
    'Lignes max de tes envies écrites',
    'SERGE.md trop long = moins lisible.',
    'curseur',
    20,
    400,
    10,
  ],
  'tickets.digest_hour': [
    'Heure du résumé du jour',
    'Dans le fuseau des horaires.',
    'heure',
    0,
    23,
    1,
  ],
  'tickets.trust_min_approvals': [
    'Oui minimum avant de proposer l’auto',
    'Pas d’automatique sur 3 tickets.',
    'curseur',
    5,
    100,
    1,
  ],
  'tickets.trust_min_rate': [
    'Taux de oui pour proposer l’auto',
    '95 % = presque toujours d’accord.',
    'pct',
    0.5,
    1,
    0.01,
  ],
  'consent.opt_in_channels': [
    'Canaux où il faut un oui explicite',
    'Les autres : on peut écrire, la personne se retire.',
    'canaux',
  ],
  'listen.hot_min_volume': [
    'Volume min pour une demande « chaude »',
    'On en voit beaucoup, ou presque pas.',
    'pct',
    0,
    1,
    0.05,
  ],
  'listen.hot_min_willingness': [
    'Envie min pour une demande « chaude »',
    'Les gens ont l’air prêts à payer, ou juste à râler.',
    'pct',
    0,
    1,
    0.05,
  ],
  'listen.cluster_jaccard_min': [
    'Ressemblance min pour mettre deux textes ensemble',
    'Trop bas : tout se mélange. Trop haut : rien ne se groupe.',
    'pct',
    0,
    1,
    0.05,
  ],
};

export const JOURS = [
  ['mon', 'lun'],
  ['mar', 'mar'],
  ['wed', 'mer'],
  ['thu', 'jeu'],
  ['fri', 'ven'],
  ['sat', 'sam'],
  ['sun', 'dim'],
];

export const CANAUX = [
  ['voice', 'Voix'],
  ['sms', 'SMS'],
  ['whatsapp', 'WhatsApp'],
  ['email', 'E-mail'],
];

export function specDe(chemin, val) {
  const brut = CHAMPS[chemin];
  if (brut) {
    const [titre, aide, widget, a, b, c] = brut;
    const spec = {titre, aide, widget};
    if (widget === 'liste' && Array.isArray(a)) {
      spec.choix = a;
    } else {
      if (a != null) {
        spec.min = a;
      }
      if (b != null) {
        spec.max = b;
      }
      if (c != null) {
        spec.pas = c;
      }
    }
    return spec;
  }
  const feuille = chemin.split('.').pop().replace(/_/g, ' ');
  if (typeof val === 'boolean') {
    return {titre: feuille, aide: '', widget: 'ouinon'};
  }
  if (typeof val === 'number') {
    const widget = val >= 0 && val <= 1 ? 'pct' : 'nombre';
    return {titre: feuille, aide: '', widget};
  }
  if (Array.isArray(val) && val.every((x) => typeof x === 'string')) {
    const ids = new Set(JOURS.map((j) => j[0]));
    if (val.every((x) => ids.has(x))) {
      return {titre: feuille, aide: '', widget: 'jours'};
    }
    return {titre: feuille, aide: '', widget: 'canaux'};
  }
  if (
    Array.isArray(val)
    && val.every((x) => Array.isArray(x) && x.length === 4)
  ) {
    return {titre: feuille, aide: '', widget: 'fenetres'};
  }
  if (Array.isArray(val) && val.every((x) => typeof x === 'number')) {
    return {titre: feuille, aide: '', widget: val.length === 2 ? 'paire' : 'nombres'};
  }
  return {titre: feuille, aide: '', widget: 'texte'};
}
