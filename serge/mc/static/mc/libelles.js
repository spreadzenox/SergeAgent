// Dictionnaire FR — miroir de serge/mc/libelles.py (kinds, dates, phrases).
export const KINDS = {
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
};

export const EVENTS = {
  cycle: 'Cycle',
  guard: 'Garde-fou',
  created: 'Créé',
  sent: 'Envoyé',
  'email.sent': 'E-mail envoyé',
  'email.delivered': 'E-mail livré',
  'email.queued': 'E-mail en file',
  'sms.sent': 'SMS envoyé',
  'work.enqueued': 'Tâche mise en file',
  'work.claimed': 'Tâche prise en charge',
  'work.completed': 'Tâche terminée',
  'work.failed': 'Tâche échouée',
  mc_act: 'Acte owner',
  'llm.io': 'Réflexion d’un agent',
  'transition.approved': 'Approuvé',
  'transition.rejected': 'Rejeté',
};

export const ETATS_WORK = {
  READY: 'Prêt',
  RUNNING: 'En cours',
  DONE: 'Terminé',
  FAILED: 'Échoué',
};

export const TYPES_TICKET = {
  GUICHET: 'Guichet',
  VETO_AMONT: 'Veto amont',
  ALERT: 'Alerte',
  HYPOTHESIS: 'Idée de business',
  MEMORY: 'Mémoire',
  POLICY: 'Policy',
  FYI: 'Pour info',
  QNA: 'Question',
  PUBLICATION: 'Publication',
  R1_OVERRIDE: 'Dépassement R1',
  REQUESTED: 'Demande d’évolution',
  OWNER_ORDER: 'Ordre owner',
};

export const LIFECYCLE = {
  CANDIDATE: 'Candidat',
  SMOKE_READY: 'Smoke prêt',
  SMOKE_RUNNING: 'Smoke en cours',
  SMOKE_DONE: 'Smoke terminé',
  FULL_READY: 'Full prêt',
  FULL_RUNNING: 'Full en cours',
  SCALE: 'Passage à l’échelle',
  PIVOT: 'Pivot',
  EXTEND: 'Extension',
  KILLED: 'Arrêté',
  INVALID_RETRY: 'À refaire',
};

export const FUNNEL = {
  NEW: 'Nouveau',
  QUALIFIED: 'Qualifié',
  CONTACTING: 'En prise de contact',
  ENGAGED: 'Engagé',
  INTENT: 'Intention d’achat',
  MEETING: 'Rendez-vous',
  CUSTOMER: 'Client',
  REJECTED: 'Écarté',
  UNREACHABLE: 'Injoignable',
  OPTED_OUT: 'Désinscrit',
  BLOCKED: 'Bloqué',
  INVALID: 'Fiche invalide',
};

export const LLM_TITRES = {
  draft_hypothesis_smoke: 'Écrire l’idée de business',
  draft_hypothesis_full: 'Écrire l’idée (après essai)',
  plan_scale: 'Comment grandir',
  options_pivot: 'Trois autres idées',
  resume_test: 'Raconter l’essai',
  qualify_prospect: 'Cette personne est-elle dans la cible ?',
  fill_slots: 'Remplir les créneaux',
  write_followup: 'Écrire une relance',
  voice_script: 'Écrire un script d’appel',
  voice_dialog: 'Dialoguer à l’oral',
  summarize_thread: 'Résumer un fil',
  score_lead_departage: 'Départager deux pistes',
  build_artifact: 'Construire un livrable',
  review_build: 'Relire un livrable',
  summarize_build_debt: 'Résumer la dette builder',
  classify_reply: 'Classer une réponse',
  extract_meeting: 'Extraire un rendez-vous',
  reply_intent: 'Répondre à une intention',
  review_other: 'Relire un message autre',
  score_call: 'Noter un appel',
  draft_price: 'Proposer un prix',
  judge_allocator: 'Arbitrer l’allocation',
  consolidate: 'Consolider la mémoire',
  edit_serge_md: 'Éditer SERGE.md',
  render_context_fr: 'Rendre le contexte FR',
  classify_owner_intent: 'Lire l’intention owner',
  judge_consequence: 'Juger une conséquence',
  cluster_demand: 'Regrouper la demande',
  install_guide: 'Guider l’installation',
};

export const ETATS_CAMPAGNE = {
  RUNNING: 'En cours',
  PAUSED: 'En pause',
  DONE: 'Terminé',
  DRAFT: 'Brouillon',
};

export const ETATS_TICKET = {
  DRAFT: 'Brouillon',
  OPEN: 'Ouvert',
  DISCUSSING: 'En discussion',
  APPROVED: 'Approuvé',
  REJECTED: 'Rejeté',
  EXPIRED: 'Expiré',
  EDITED: 'Édité',
};

export const TYPES_OBJET = {
  venture: 'Venture',
  campagne: 'Campagne',
  prospect: 'Prospect',
  client: 'Client',
  facture: 'Facture',
  abonnement: 'Abonnement',
  llm: 'Jugement',
  compte: 'Compte web',
  plateforme: 'Endroit du web',
  ticket: 'Question pour toi',
  lesson: 'Leçon',
  playbook: 'Recette',
  work_item: 'Petit travail',
  touch: 'Prise de contact',
  inbound_event: 'Réponse reçue',
  listen_doc: 'Page lue',
  event: 'Fait enregistré',
  file: 'File',
  sqlite: 'SQLite',
  table: 'Table',
  llm_usage: 'Passage',
  contexte: 'Lecture autorisée',
  ecoute: 'Pages lues',
  outil: 'Outil',
  notion: 'Pour comprendre',
};

export function verbe(kind) {
  return KINDS[kind] || EVENTS[kind] || String(kind || '').replace(/\./g, ' · ');
}

export function titreLlm(nom) {
  return LLM_TITRES[nom] || String(nom || '').replace(/_/g, ' ');
}

function duree(abs) {
  const min = Math.floor(abs / 60000);
  if (min < 1) {
    return '';
  }
  if (min < 60) {
    return `${min} min`;
  }
  const h = Math.floor(min / 60);
  if (h < 24) {
    return `${h} h`;
  }
  return `${Math.floor(min / 1440)} j`;
}

export function rel(ts) {
  const diff = Date.now() - Date.parse(ts);
  if (Number.isNaN(diff)) {
    return '';
  }
  const words = duree(Math.abs(diff));
  if (!words) {
    return 'à l’instant';
  }
  return diff < 0 ? `dans ${words}` : `il y a ${words}`;
}

export function depuis(ts) {
  const diff = Date.now() - Date.parse(ts);
  if (Number.isNaN(diff)) {
    return '';
  }
  const words = duree(Math.abs(diff));
  if (!words) {
    return 'à l’instant';
  }
  return diff < 0 ? `dans ${words}` : `depuis ${words}`;
}

export function demarre(ts) {
  const r = rel(ts);
  if (!r || r === 'à l’instant') {
    return 'démarré à l’instant';
  }
  if (r.startsWith('il y a ')) {
    return `démarré ${r}`;
  }
  return r;
}

export function allerObjet(type, id) {
  if (!type || !id) {
    return;
  }
  location.hash = `#/objet/${type}/${encodeURIComponent(id)}`;
}
