// Dictionnaire FR — miroir de serge/mc/libelles.py (événements, dates, phrases).
export const EVENTS = {
  cycle: 'Cycle',
  guard: 'Garde-fou',
  created: 'Créé',
  sent: 'Envoyé',
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
  mc_act: 'Acte owner',
  'transition.approved': 'Approuvé',
  'transition.rejected': 'Rejeté',
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
  POC_SELECTED: 'Choisi pour un test',
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
  llm: 'Invocation',
  compte: 'Compte web',
  plateforme: 'Endroit du web',
  ticket: 'Question pour toi',
  lesson: 'Leçon',
  playbook: 'Recette',
  task: 'Tâche',
  lien: 'Lien',
  touch: 'Prise de contact',
  inbound_event: 'Réponse reçue',
  listen_doc: 'Page lue',
  event: 'Fait enregistré',
  file: 'File',
  sqlite: 'SQLite',
  table: 'Table',
  llm_usage: 'Passage',
  ecoute: 'Pages lues',
  outil: 'Outil',
  etape: 'Étape',
  canal: 'Canal',
}

export function verbe(kind) {
  return EVENTS[kind] || String(kind || '').replace(/\./g, ' · ');
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
