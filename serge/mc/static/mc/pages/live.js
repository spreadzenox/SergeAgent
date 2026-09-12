// Home : récit + graphe + urgents cliquables + activité humaine.
import {
  createGauge,
  fillList,
  li,
  openDrawer,
  toast,
  updateGauge,
} from '../components.js';
import {monterGraphe} from '../graphe.js';
import {
  densite24h,
  dessineWaveform,
  etatSysteme,
  startNoyau,
  tweenNumber,
} from '../hud.js';
import {
  LIFECYCLE,
  TYPES_TICKET,
  allerObjet,
  depuis,
  rel,
  verbe,
} from '../libelles.js';
import {chargerObjet, renderFiche} from '../objets.js';
import {patchSection} from '../patch.js';

function renderHero(main, payload, sig, store) {
  patchSection(main, 'hero', sig, payload);
  const running = payload.running;
  const headline = main.querySelector('#live-headline');
  if (running) {
    headline.textContent =
      `En cours : ${verbe(running.kind)}`
      + ` (${nomVenture(store, running.venture_id)})`
      + (running.since ? ` — ${depuis(running.since)}.` : '.');
  } else if (payload.ready > 0) {
    headline.textContent = `${payload.ready} prêts, en attente de traitement.`;
  } else {
    headline.textContent = 'Rien en cours — système calme.';
  }
  const prochain = main.querySelector('.file-hero [data-file="prochain"]');
  if (prochain) {
    if (payload.next) {
      prochain.hidden = false;
      prochain.textContent = `Prochain : ${verbe(payload.next.kind)}`;
    } else {
      prochain.hidden = true;
      prochain.textContent = '';
    }
  }
}

function canalFr(canal) {
  if (canal === 'email') {
    return 'e-mail';
  }
  if (canal === 'voice') {
    return 'voix';
  }
  return canal || 'canal';
}

function etatCampagne(etat) {
  if (etat === 'RUNNING') {
    return 'en cours';
  }
  if (etat === 'PAUSED') {
    return 'en pause';
  }
  if (etat === 'DRAFT') {
    return 'brouillon';
  }
  return etat || '';
}

function ligneMetriques(u1, u2, u3, paid) {
  const t = u1 || 0;
  const r = u2 || 0;
  const touch = t <= 1 ? `${t} touchée` : `${t} touchées`;
  const rep = r <= 1 ? `${r} réponse` : `${r} réponses`;
  return `${touch} · ${rep} · ${u3 || 0} oui · ${paid || 0} € encaissés`;
}

function renderBusiness(main, payload, sig) {
  const sec = main.querySelector('[data-section="business"]');
  if (!sec) {
    return;
  }
  const voix = main.querySelector('#voix-noyau');
  if (voix) {
    voix.textContent = payload.voix || 'Je scrute.';
  }
  const slot = main.querySelector('[data-biz="bandeau"]');
  if (slot) {
    slot.replaceChildren();
    if (payload.venture) {
      const cadre = document.createElement('div');
      cadre.className = 'cadre-venture';
      const etiq = document.createElement('p');
      etiq.className = 'etiq-venture';
      etiq.textContent = 'Venture en cours';
      const titre = document.createElement('button');
      titre.type = 'button';
      titre.className = 'titre-venture';
      titre.textContent = payload.venture.nom;
      titre.addEventListener('click', () =>
        allerObjet('venture', payload.venture.id),
      );
      const cycle = document.createElement('p');
      cycle.className = 'cycle-venture';
      cycle.textContent = LIFECYCLE[payload.venture.lifecycle] || '';
      const met = document.createElement('p');
      met.className = 'met-venture';
      met.textContent = ligneMetriques(
        payload.u1,
        payload.u2,
        payload.u3,
        payload.paid_eur,
      );
      cadre.append(etiq, titre, cycle, met);
      if ((payload.tests || []).length) {
        const rang = document.createElement('div');
        rang.className = 'tests-venture';
        const sous = document.createElement('p');
        sous.className = 'etiq-tests';
        sous.textContent = 'Campagnes de cette venture';
        rang.append(sous);
        payload.tests.forEach((t) => {
          const b = document.createElement('button');
          b.type = 'button';
          b.className = 'puce-test';
          const n = t.u1 || 0;
          const touch = n <= 1 ? `${n} touchée` : `${n} touchées`;
          b.textContent =
            `Test ${canalFr(t.canal)} · ${etatCampagne(t.etat)} · ${touch}`;
          b.addEventListener('click', () => allerObjet('campagne', t.id));
          rang.append(b);
        });
        cadre.append(rang);
      }
      slot.append(cadre);
    }
  }
  sec.dataset.sig = sig;
}

function renderUrgents(main, payload, sig) {
  const list = main.querySelector('[data-section="urgents"] [data-list]');
  fillList(list, payload.items, 'Aucun urgent. Tout est calme.', (item) => {
    const type = TYPES_TICKET[item.type] || item.type;
    const when = item.expiry_at ? ` — ${rel(item.expiry_at)}` : '';
    const node = li('', item.id);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'lien-urgent';
    btn.textContent = `${item.titre} (${type}${when})`;
    btn.addEventListener('click', () => allerObjet('ticket', item.id));
    node.append(btn);
    return node;
  });
  main.querySelector('[data-section="urgents"]').dataset.sig = sig;
}

function nomVenture(store, id) {
  if (!id) {
    return 'sans venture';
  }
  const env = store.get('business');
  const v = env && env.payload ? env.payload.venture : null;
  if (v && v.id === id) {
    return v.nom;
  }
  return id;
}

function renderFile(main, payload, sig, store) {
  patchSection(main, 'file', sig, payload);
  const list = main.querySelector('[data-section="file"] [data-list]');
  fillList(list, payload.running, 'File vide.', (item) => {
    const node = li('', item.id);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'clic-ligne';
    btn.textContent = `${verbe(item.kind)} (${nomVenture(store, item.venture_id)})`;
    btn.addEventListener('click', () => allerObjet('work_item', item.id));
    node.append(btn);
    return node;
  });
  const next = main.querySelector('#file-next');
  if (payload.next) {
    next.hidden = false;
    next.textContent = `Prochain : ${verbe(payload.next.kind)}`;
  } else {
    next.hidden = true;
    next.textContent = '';
  }
}

async function ouvrirFeuille(type, id) {
  const data = await chargerObjet(type, id);
  if (!data) {
    toast(document.body, 'Détail introuvable.', 'erreur');
    return;
  }
  openDrawer(document.body, data.titre || id, renderFiche(data));
}

function renderFeed(main, payload, sig) {
  const list = main.querySelector('[data-section="feed"] [data-list]');
  fillList(list, payload.items, 'Aucune activité pour le moment.', (item) => {
    const node = li('');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'clic-ligne';
    const extra = item.extra || {};
    let cible = null;
    if (extra.ticket_id) {
      cible = ['ticket', extra.ticket_id];
    } else if (extra.touch_id) {
      cible = ['touch', extra.touch_id];
    } else if (extra.event_id) {
      cible = ['event', extra.event_id];
    } else if (extra.id && String(item.kind || '').startsWith('work.')) {
      cible = ['work_item', extra.id];
    }
    btn.textContent = `${rel(item.ts)} · ${verbe(item.kind)}${item.titre ? ` — ${item.titre}` : ''}`;
    if (cible) {
      btn.addEventListener('click', () => allerObjet(cible[0], cible[1]));
    } else {
      btn.addEventListener('click', () => ouvrirFeuille('event', extra.event_id || item.ts));
    }
    node.append(btn);
    return node;
  });
  main.querySelector('[data-section="feed"]').dataset.sig = sig;
  const wave = main.querySelector('[data-hud="wave"]');
  if (wave) {
    dessineWaveform(wave, densite24h(payload.items || [], Date.now()));
  }
}

function tweenNombre(node, cible, format) {
  const prev = parseFloat(node.dataset.v || '0');
  node.dataset.v = String(cible);
  if (prev === cible) {
    node.textContent = format(cible);
    return;
  }
  tweenNumber(node, prev, cible, {format, duration: 400});
}

function renderJauges(main, payload, sig, gauges) {
  const llm = payload.llm;
  updateGauge(gauges.llm.node, llm.ratio || 0, llm.ratio > 0.8 ? 'alerte' : '');
  const euros = llm.eur_estimes.toLocaleString('fr-FR', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  tweenNombre(
    gauges.llm.label,
    llm.tokens_jour,
    (v) => `${Math.round(v)} jetons (~${euros} € / ${llm.plafond_eur} €)`,
  );
  const email = payload.email;
  updateGauge(gauges.email.node, email.ratio || 0, email.ratio > 0.8 ? 'alerte' : '');
  tweenNombre(
    gauges.email.label,
    email.envoyes,
    (v) => `${Math.round(v)} / ${email.quota} envoyés`,
  );
  main.querySelector('[data-section="jauges"]').dataset.sig = sig;
}

function etatDepuisStore(store) {
  const hero = store.get('hero');
  const urgents = store.get('urgents');
  const feed = store.get('feed');
  const items = feed && feed.payload ? feed.payload.items || [] : [];
  const urgentsItems =
    urgents && urgents.payload ? urgents.payload.items || [] : [];
  return {
    urgents: urgentsItems.length,
    running: hero && hero.payload ? hero.payload.running : null,
    echecRecent: items.length > 0 && items[0].kind === 'work.failed',
  };
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
  main.addEventListener('click', (ev) => {
    const cible = ev.target.closest('[data-file]');
    if (!cible || !main.contains(cible)) {
      return;
    }
    if (cible.dataset.file === 'ouvrir') {
      allerObjet('file', 'canon');
      return;
    }
    if (cible.dataset.file === 'prochain') {
      const hero = store.get('hero');
      const file = store.get('file');
      const nxt =
        (hero && hero.payload && hero.payload.next)
        || (file && file.payload && file.payload.next);
      if (nxt) {
        allerObjet('work_item', nxt.id);
      }
    }
  });
  const noyau = startNoyau(main.querySelector('[data-hud="noyau"]'), () =>
    etatDepuisStore(store),
  );
  const stoppers = [];
  const rafGraphe = monterGraphe(
    main,
    () => {
      const g = store.get('graphe');
      const b = store.get('business');
      const base = g && g.payload ? g.payload : {};
      return {
        ...base,
        lignage: b && b.payload ? b.payload.lignage : [],
      };
    },
    stoppers,
  );
  const renderers = {
    hero: (payload, sg) => renderHero(main, payload, sg, store),
    business: (payload, sg) => renderBusiness(main, payload, sg),
    graphe: (payload, sg) => {
      const sec = main.querySelector('[data-section="graphe"]');
      if (sec) {
        sec.dataset.sig = sg;
      }
      if (payload.io && main.querySelector('[data-typewriter]')) {
        const tw = main.querySelector('[data-typewriter]');
        if (!tw.textContent) {
          tw.textContent = payload.io.sortie ? '' : (payload.io.prompt || '');
        }
      }
      rafGraphe();
    },
    urgents: (payload, sg) => renderUrgents(main, payload, sg),
    file: (payload, sg) => renderFile(main, payload, sg, store),
    feed: (payload, sg) => renderFeed(main, payload, sg),
    jauges: (payload, sg) => renderJauges(main, payload, sg, gauges),
  };
  const majEtat = () => {
    const tete = main.querySelector('.recit') || main.querySelector('.hero');
    if (tete) {
      tete.dataset.etat = etatSysteme(etatDepuisStore(store));
    }
  };
  const unsubs = Object.keys(renderers).map((section) =>
    store.subscribe(section, (payload, sg) => {
      renderers[section](payload, sg);
      majEtat();
    }),
  );
  for (const [section, env] of store.all()) {
    if (renderers[section]) {
      renderers[section](env.payload, env.sig);
    }
  }
  majEtat();
  return () => {
    unsubs.forEach((unsub) => unsub());
    noyau.stop();
    stoppers.forEach((fn) => fn());
  };
}
