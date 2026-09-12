// Page P3 Décisions : liste, filtres, carte (actes), diffs, MEMORY, E5, digest.
import {fillList, li, rel} from '../components.js';
import {TYPES_TICKET, allerObjet} from '../libelles.js';
import {chargerCarte} from './tickets_actes.js';

const OUVERTS = ['DRAFT', 'OPEN', 'DISCUSSING'];

function lisFiltres(main) {
  return {
    type: main.querySelector('[data-filtre="type"]').value,
    etat: main.querySelector('[data-filtre="etat"]').value,
    urgents: main.querySelector('[data-filtre="urgents"]').checked,
    recherche: main
      .querySelector('[data-filtre="recherche"]')
      .value.trim()
      .toLowerCase(),
    tri: main.querySelector('[data-filtre="tri"]').value,
  };
}

function appliqueFiltres(items, filtres) {
  const gardes = items.filter((item) => {
    if (filtres.type && item.type !== filtres.type) {
      return false;
    }
    if (filtres.etat === 'atraiter' && !OUVERTS.includes(item.etat)) {
      return false;
    }
    if (filtres.etat === 'termines' && OUVERTS.includes(item.etat)) {
      return false;
    }
    if (filtres.urgents && !item.urgent) {
      return false;
    }
    if (
      filtres.recherche
      && !item.titre.toLowerCase().includes(filtres.recherche)
    ) {
      return false;
    }
    return true;
  });
  if (filtres.tri === 'expiry') {
    gardes.sort((a, b) => {
      if (!a.expiry_at) {
        return 1;
      }
      if (!b.expiry_at) {
        return -1;
      }
      return a.expiry_at.localeCompare(b.expiry_at);
    });
  }
  return gardes;
}

function majOptionsTypes(main, items) {
  const select = main.querySelector('[data-filtre="type"]');
  const courant = select.value;
  const types = [...new Set(items.map((item) => item.type))].sort();
  select.replaceChildren();
  const tous = document.createElement('option');
  tous.value = '';
  tous.textContent = 'Tous types';
  select.append(tous);
  for (const type of types) {
    const opt = document.createElement('option');
    opt.value = type;
    opt.textContent = TYPES_TICKET[type] || type;
    select.append(opt);
  }
  if (types.includes(courant)) {
    select.value = courant;
  }
}

function renderListe(main, payload, sig, store) {
  const section = main.querySelector('[data-section="tickets"]');
  majOptionsTypes(main, payload.items);
  const filtres = lisFiltres(main);
  const liste = section.querySelector('[data-list="items"]');
  liste.replaceChildren();
  const gardes = appliqueFiltres(payload.items, filtres);
  if (gardes.length === 0) {
    liste.append(li('Aucun ticket pour ces filtres.'));
  }
  for (const item of gardes) {
    const ligne = document.createElement('li');
    const bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'lien-ticket';
    bouton.dataset.ticket = item.id;
    bouton.textContent =
      `${item.type} — ${item.titre} [${item.etat}]`
      + (item.urgent ? ' — URGENT' : '')
      + (item.expiry_at ? ` (${rel(item.expiry_at)})` : '');
    bouton.addEventListener('click', () =>
      chargerCarte(main, store, item.id)
    );
    ligne.append(bouton);
    liste.append(ligne);
  }
  section.dataset.sig = sig;
}

function renderDiffs(main, payload, sig) {
  const section = main.querySelector('[data-section="diffs"]');
  const conteneur = main.querySelector('[data-diffs="contenu"]');
  conteneur.replaceChildren();
  const aDesDiffs =
    payload.policy.length > 0
    || payload.versions.length > 0
    || payload.items.length > 0;
  if (!aDesDiffs) {
    const p = document.createElement('p');
    p.textContent = 'Aucun diff en attente ni révision récente.';
    conteneur.append(p);
  }
  if (payload.policy.length > 0) {
    const titre = document.createElement('h3');
    titre.textContent = 'Propositions de politique (POLICY)';
    conteneur.append(titre);
    const liste = document.createElement('ul');
    for (const p of payload.policy) {
      const ligne = document.createElement('li');
      ligne.textContent = `${p.titre} — ${p.diff} (${p.justification})`;
      liste.append(ligne);
    }
    conteneur.append(liste);
  }
  if (payload.versions.length > 0) {
    const titre = document.createElement('h3');
    titre.textContent = 'Historique des révisions (EDITED)';
    conteneur.append(titre);
    const liste = document.createElement('ul');
    for (const v of payload.versions) {
      const notes = v.versions.map((n) => `v${n.n}: ${n.note}`).join(', ');
      liste.append(li(`${v.titre} — ${notes}`));
    }
    conteneur.append(liste);
  }
  if (payload.items.length > 0) {
    const titre = document.createElement('h3');
    titre.textContent = 'Modifications d’items (MEMORY)';
    conteneur.append(titre);
    const liste = document.createElement('ul');
    for (const it of payload.items) {
      liste.append(li(`${it.avant} → ${it.apres}`));
    }
    conteneur.append(liste);
  }
  section.dataset.sig = sig;
}

function renderMetriques(main, payload, sig) {
  const section = main.querySelector('[data-section="metriques"]');
  const conteneur = main.querySelector('[data-metriques="contenu"]');
  conteneur.replaceChildren();
  const sem = payload.semaine || {};
  const app = payload.approbation || {};
  const tauxTxt =
    app.taux_global !== null
      ? `${Math.round(app.taux_global * 100)} %`
      : '—';
  const medianesTxt =
    Object.entries(payload.reponse_mediane_s || {})
      .map(([typ, sec]) => `${typ}: ${Math.round(sec / 60)} min`)
      .join(', ') || '—';
  const lignes = [
    `Semaine : ${sem.tickets || 0} tickets, ${sem.expirations || 0} expirations`,
    `Backlog en cours : ${payload.backlog || 0} ouverts`,
    `Taux d’approbation : ${tauxTxt} (rejets : ${payload.rejets || 0})`,
    `Délais médians de réponse : ${medianesTxt}`,
    `Actes automatiques : ${payload.auto_approbations || 0} auto, ${payload.bypass || 0} défaut appliqué`,
    `Guichet : ${payload.guichet?.resolus || 0} résolus, ${payload.guichet?.expires || 0} expirés`,
  ];
  for (const texte of lignes) {
    const p = document.createElement('p');
    p.textContent = texte;
    conteneur.append(p);
  }
  section.dataset.sig = sig;
}

function renderDigest(main, payload, sig) {
  const info = main.querySelector('#digest-info');
  const heure = payload.digest_hour ?? 8;
  const plages = (payload.quiet_hours || [])
    .map(([deb, fin]) => `${deb}h-${fin}h`)
    .join(', ');
  info.textContent =
    `Digest quotidien : ${heure}h (Europe/Paris).`
    + (plages ? ` Heures silencieuses : ${plages}.` : '');
  main.querySelector('[data-section="digest"]').dataset.sig = sig;
}

function initMemory(main) {
  let page = 1;
  const taille = 10;
  const liste = main.querySelector('[data-list="memory-items"]');
  const info = main.querySelector('[data-memory="info"]');
  const btnPrev = main.querySelector('[data-memory="prev"]');
  const btnNext = main.querySelector('[data-memory="next"]');

  async function charger(p) {
    try {
      const res = await fetch(
        `/owner/api/memory/items?page=${p}&size=${taille}`,
        {
          cache: 'no-store',
        },
      );
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      page = data.page;
      info.textContent = `Page ${data.page} / ${data.pages} (${data.total} leçons)`;
      btnPrev.disabled = page <= 1;
      btnNext.disabled = page >= data.pages;
      fillList(liste, data.items, 'Aucune leçon enregistrée.', (it) => {
        const node = li('');
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'clic-ligne';
        btn.textContent = `${it.label} [${it.etat}]`;
        if (it.id) {
          btn.addEventListener('click', () => allerObjet('lesson', it.id));
        }
        node.append(btn);
        return node;
      });
    } catch {
      // réessai ultérieur
    }
  }

  btnPrev.addEventListener('click', () => {
    if (page > 1) {
      charger(page - 1);
    }
  });
  btnNext.addEventListener('click', () => {
    charger(page + 1);
  });
  charger(1);
}

export function mount(main, store) {
  const tpl = document.getElementById('page-tickets');
  main.replaceChildren(tpl.content.cloneNode(true));
  const rendus = {
    tickets: renderListe,
    diffs: renderDiffs,
    metriques: renderMetriques,
    digest: renderDigest,
  };
  const unsubs = Object.keys(rendus).map((section) =>
    store.subscribe(section, (payload, sg) => {
      rendus[section](main, payload, sg, store);
    }),
  );
  for (const filtre of main.querySelectorAll('[data-filtre]')) {
    filtre.addEventListener(
      filtre.tagName === 'INPUT' ? 'input' : 'change',
      () => {
        const env = store.get('tickets');
        if (env) {
          renderListe(main, env.payload, env.sig, store);
        }
      },
    );
  }
  for (const [section, env] of store.all()) {
    if (rendus[section]) {
      rendus[section](main, env.payload, env.sig, store);
    }
  }
  initMemory(main);
  return () => {
    unsubs.forEach((unsub) => unsub());
  };
}
