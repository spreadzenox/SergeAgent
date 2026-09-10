// Page P0 En direct : hero + urgents + file + feed + jauges.
// Libellés FR en dur (centralisation i18n.js au lot 8).
import {createGauge, updateGauge, openDrawer, toast} from '../components.js';
import {patchSection} from '../patch.js';

const KINDS_FR = {
  cycle: 'Cycle',
  guard: 'Garde',
  created: 'Créé',
  sent: 'Envoyé',
  'email.sent': 'Email envoyé',
  'work.completed': 'Tâche terminée',
  'work.failed': 'Tâche échouée',
};

const WORKERS_FR = {
  'email.send': 'Envoi email',
  'email.poll': 'Collecte email',
  'voice.send': 'Appel voix',
  'voice.score': 'Évaluation appel',
  'inbound.classify': 'Classification',
  'inbound.reply_priority': 'Réponse prioritaire',
  'inbound.judge_other': 'Arbitrage autre',
  'listen.collect': 'Collecte écoute',
  'listen.cluster': 'Regroupement écoute',
  'memory.consolidate': 'Consolidation mémoire',
  'memory.apply': 'Application mémoire',
};

const ETATS_FR = {
  READY: 'Prêt',
  RUNNING: 'En cours',
  DONE: 'Terminé',
  FAILED: 'Échoué',
};

// TODO lot 8 : migrer vers i18n.js (dates relatives + libellés).
function rel(ts) {
  const diff = Date.now() - Date.parse(ts);
  if (Number.isNaN(diff)) {
    return '';
  }
  const abs = Math.abs(diff);
  const min = Math.floor(abs / 60000);
  const words =
    min < 1
      ? "à l'instant"
      : min < 60
        ? `${min} min`
        : Math.floor(min / 60) < 24
          ? `${Math.floor(min / 60)} h`
          : `${Math.floor(min / 1440)} j`;
  if (words === "à l'instant") {
    return words;
  }
  return diff < 0 ? `dans ${words}` : `il y a ${words}`;
}

function li(text, title = '') {
  const node = document.createElement('li');
  node.textContent = text;
  if (title) {
    node.title = title;
  }
  return node;
}

function fillList(list, items, empty, render) {
  list.replaceChildren();
  if (items.length === 0) {
    list.append(li(empty));
    return;
  }
  for (const item of items) {
    list.append(render(item));
  }
}

const TYPES_FR = {GUICHET: 'Guichet', VETO_AMONT: 'Veto amont', ALERT: 'Alerte'};

function renderHero(main, payload, sig) {
  patchSection(main, 'hero', sig, payload);
  const running = payload.running;
  const headline = main.querySelector('#live-headline');
  if (running) {
    const since = rel(running.since);
    headline.textContent =
      `En cours : ${WORKERS_FR[running.kind] || running.kind}`
      + ` (${running.venture_id || 'sans venture'})`
      + (since ? ` — depuis ${since}.` : '.');
  } else if (payload.ready > 0) {
    headline.textContent = `${payload.ready} prêts, en attente de traitement.`;
  } else {
    headline.textContent = 'Rien en cours — système calme.';
  }
}

function renderUrgents(main, payload, sig) {
  const list = main.querySelector('[data-section="urgents"] [data-list]');
  fillList(list, payload.items, 'Aucun urgent. Tout est calme.', (item) => {
    const type = TYPES_FR[item.type] || item.type;
    const when = item.expiry_at ? ` — ${rel(item.expiry_at)}` : '';
    return li(`${item.titre} (${type}${when})`, item.id);
  });
  main.querySelector('[data-section="urgents"]').dataset.sig = sig;
}

function renderFile(main, payload, sig) {
  patchSection(main, 'file', sig, payload);
  const list = main.querySelector('[data-section="file"] [data-list]');
  fillList(list, payload.running, 'File vide.', (item) => {
    const node = li(
      `${WORKERS_FR[item.kind] || item.kind} (${item.venture_id || 'sans venture'})`,
      item.id,
    );
    node.classList.add('cliquable');
    node.dataset.traceId = item.id;
    node.addEventListener('click', () => showTrace(item.id));
    return node;
  });
  const next = main.querySelector('#file-next');
  if (payload.next) {
    next.textContent = `Prochain : ${WORKERS_FR[payload.next.kind] || payload.next.kind}.`;
  } else {
    next.textContent =
      payload.running.length === 0 && payload.ready_count === 0
        ? ''
        : 'Rien de plus en attente.';
  }
}

function buildTrace(trace) {
  const wrap = document.createElement('div');
  const item = trace.item;
  const title = document.createElement('p');
  title.textContent =
    `${WORKERS_FR[item.kind] || item.kind} — ${ETATS_FR[item.statut] || item.statut}`;
  wrap.append(title);
  if (trace.note) {
    const note = document.createElement('p');
    note.textContent = `Note : ${trace.note}`;
    wrap.append(note);
  }
  if (trace.ticket) {
    const ticket = document.createElement('p');
    ticket.textContent = `Ticket : ${trace.ticket.titre} (${trace.ticket.etat}).`;
    wrap.append(ticket);
  }
  if (trace.contact) {
    const contact = document.createElement('p');
    const who = trace.contact.display || trace.contact.email;
    contact.textContent = `Contact : ${who}.`;
    wrap.append(contact);
  }
  const sub = document.createElement('h3');
  sub.textContent = 'Événements';
  wrap.append(sub);
  const list = document.createElement('ul');
  if (trace.evenements.length === 0) {
    list.append(li('Aucun événement lié.'));
  }
  for (const event of trace.evenements) {
    list.append(
      li(`${rel(event.ts)} · ${KINDS_FR[event.type] || event.type}`),
    );
  }
  wrap.append(list);
  return wrap;
}

async function showTrace(id) {
  try {
    const res = await fetch(
      `/owner/api/trace?item=${encodeURIComponent(id)}`,
      {cache: 'no-store'},
    );
    if (!res.ok) {
      toast(document.body, 'Trace introuvable.', 'erreur');
      return;
    }
    const trace = await res.json();
    openDrawer(document.body, 'Détail d’exécution', buildTrace(trace));
  } catch {
    toast(document.body, 'Trace injoignable.', 'erreur');
  }
}

function renderFeed(main, payload, sig) {
  const list = main.querySelector('[data-section="feed"] [data-list]');
  fillList(list, payload.items, 'Aucune activité pour le moment.', (item) => {
    const kind = KINDS_FR[item.kind] || item.kind;
    const what = item.titre ? ` — ${item.titre}` : '';
    return li(`${rel(item.ts)} · ${kind}${what}`);
  });
  main.querySelector('[data-section="feed"]').dataset.sig = sig;
}

function renderJauges(main, payload, sig, gauges) {
  const llm = payload.llm;
  updateGauge(gauges.llm.node, llm.ratio || 0, llm.ratio > 0.8 ? 'alerte' : '');
  const euros = llm.eur_estimes.toLocaleString('fr-FR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  gauges.llm.label.textContent =
    `${llm.tokens_jour} jetons (~${euros} € / ${llm.plafond_eur} €)`;
  const email = payload.email;
  updateGauge(gauges.email.node, email.ratio || 0, email.ratio > 0.8 ? 'alerte' : '');
  gauges.email.label.textContent =
    `${email.envoyes} / ${email.quota} envoyés`;
  main.querySelector('[data-section="jauges"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-live');
  main.replaceChildren(tpl.content.cloneNode(true));
  const gauges = {};
  for (const name of ['llm', 'email']) {
    const slot = main.querySelector(`[data-gauge="${name}"]`);
    const label = document.createElement('p');
    const node = createGauge();
    slot.replaceChildren(label, node);
    gauges[name] = {label, node};
  }
  const renderers = {
    hero: (payload, sg) => renderHero(main, payload, sg),
    urgents: (payload, sg) => renderUrgents(main, payload, sg),
    file: (payload, sg) => renderFile(main, payload, sg),
    feed: (payload, sg) => renderFeed(main, payload, sg),
    jauges: (payload, sg) => renderJauges(main, payload, sg, gauges),
  };
  const unsubs = Object.keys(renderers).map((section) =>
    store.subscribe(section, (payload, sg) => renderers[section](payload, sg)),
  );
  for (const [section, env] of store.all()) {
    if (renderers[section]) {
      renderers[section](env.payload, env.sig);
    }
  }
  return () => {
    unsubs.forEach((unsub) => unsub());
  };
}
