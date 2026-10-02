// Catalogue Policy : titre, aide et widget de chaque réglage de la policy.

export const SECTIONS = {
  budget: {
    titre: 'Argent',
    pourquoi: 'Combien Serge a le droit de dépenser. Au-delà, il s’arrête.',
  },
  quotas: {
    titre: 'Plafonds par canal',
    pourquoi: 'Combien de messages, appels ou invitations, pour ne pas spammer, et combien de fois on redemande une réponse au modèle.',
  },
  windows: {
    titre: 'Horaires',
    pourquoi: 'Quand on a le droit de parler aux gens, et quand on se tait.',
  },
  calling_zones: {
    titre: 'Pays et appels',
    pourquoi: 'Les règles légales changent selon le pays.',
  },
  standing: {
    titre: 'Santé des comptes',
    pourquoi: 'Capital qui baisse à l’usage et remonte au repos. En dessous du plancher, l’acte est refusé.',
  },
  voice: {
    titre: 'Téléphone',
    pourquoi: 'Durée, qualité, conservation des appels.',
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
    pourquoi: 'À quelle heure le résumé du jour.',
  },
  consent: {
    titre: 'Accord des gens',
    pourquoi: 'Sur quels canaux il faut un oui explicite avant d’écrire ou d’appeler.',
  },
};

// [titre, aide, widget, min|choix, max, pas]
export const CHAMPS = {
  'budget.monthly_eur': [
    'Plafond du mois',
    'Ce que Serge nous coûte en IA ce mois-ci (coût réel des modèles). Au-delà, plus aucune tâche n’appelle de modèle jusqu’au mois suivant. Les achats de Serge pour ses business n’y comptent pas.',
    'eur',
    0,
    500,
    1,
  ],
  'budget.llm_daily_eur': [
    'Modèles, par jour',
    'Ce que les appels aux modèles coûtent aujourd’hui (coût réel). Au-delà, plus aucune tâche n’appelle de modèle jusqu’au lendemain.',
    'eur',
    0,
    50,
    0.5,
  ],
  'budget.eur_per_usd': [
    'Un dollar en euros',
    'OpenRouter facture en dollars : ce taux convertit le coût réel des appels pour les plafonds du jour et du mois.',
    'eur',
    0.5,
    1.5,
    0.01,
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
    'SMS reçus par expéditeur, par minute',
    'Anti-rafale sur les SMS reçus. Au-delà, le SMS est refusé.',
    'curseur',
    1,
    30,
    1,
  ],
  'quotas.sms_global_per_min': [
    'SMS reçus au total, par minute',
    'Toutes les lignes confondues. Au-delà, le SMS est refusé.',
    'curseur',
    1,
    120,
    1,
  ],
  'quotas.llm_outil_resultat_max_caracteres': [
    'Taille maximale d’un résultat d’outil',
    'En caractères. Au-delà, le résultat est coupé avant d’être renvoyé au modèle : il repart à chaque tour, et coûte à chaque fois.',
    'curseur',
    1000,
    100000,
    1000,
  ],
  'quotas.llm_recalls_json': [
    'Nouveaux essais si la réponse est mal formée',
    'Combien de fois on redemande au modèle une réponse au bon format, sans outil.',
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
  'windows.timezone': [
    'Fuseau',
    'Toutes les heures ci-dessous sont lues dans ce fuseau.',
    'liste',
    ['Europe/Paris', 'Europe/Brussels', 'Europe/London', 'UTC'],
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
  'calling_zones.FR.contact_per_30d': [
    'Prises de contact max / 30 jours / personne',
    'Règle légale FR. Monter ça = ticket + motif.',
    'curseur',
    1,
    8,
    1,
  ],
  'standing.cout_usage': [
    'Coût d’un acte',
    'On retire ça du capital après chaque usage. Jamais une hausse ici.',
    'pct',
    0,
    1,
    0.01,
  ],
  'standing.gain_par_heure': [
    'Gain par heure de repos',
    'Quand le compte ne sert pas, le capital remonte de ce pas.',
    'pct',
    0,
    1,
    0.01,
  ],
  'standing.idle_apres_heures': [
    'Heures avant que ça remonte',
    'Rien ne remonte tant que ce délai n’est pas passé.',
    'curseur',
    0,
    48,
    1,
  ],
  'standing.capital_min': [
    'Plancher pour agir',
    'En dessous, l’acte est refusé. Insister ne change rien.',
    'pct',
    0,
    1,
    0.05,
  ],
  'standing.capital_max': [
    'Plafond du capital',
    'Le repos ne dépasse jamais ça.',
    'pct',
    0,
    1,
    0.05,
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
  'collect.refund_auto_max_eur': [
    'Remboursement auto, plafond €',
    'Au-dessus, toi tu décides.',
    'eur',
    0,
    50,
    0.5,
  ],
  'collect.dunning_days': [
    'Jours de relance de paiement',
    'Exemple : J+7 puis J+14.',
    'nombres',
  ],
  'memory.episode_archive_days': [
    'Jours avant d’archiver un épisode',
    'Le détail brut quitte le quotidien.',
    'curseur',
    7,
    180,
    1,
  ],
  'tickets.digest_hour': [
    'Heure du résumé du jour',
    'Dans le fuseau des horaires.',
    'heure',
    0,
    23,
    1,
  ],
  'consent.opt_in_channels': [
    'Canaux où il faut un oui explicite',
    'Les autres : on peut écrire, la personne se retire.',
    'canaux',
  ],
};

export const JOURS = [
  ['mon', 'lun'],
  ['tue', 'mar'],
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
