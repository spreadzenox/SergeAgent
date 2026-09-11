// Page P3 Décisions : liste tickets + filtres dynamiques (carte en 7f).
import {fillList, li, rel} from '../components.js';

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
    if (filtres.recherche && !item.titre.toLowerCase().includes(filtres.recherche)) {
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
    opt.textContent = type;
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
    ligne.append(bouton);
    liste.append(ligne);
  }
  section.dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-tickets');
  main.replaceChildren(tpl.content.cloneNode(true));
  const rendus = {
    tickets: renderListe,
  };
  const unsubs = Object.keys(rendus).map((section) =>
    store.subscribe(section, (payload, sg) => {
      rendus[section](main, payload, sg, store);
    }),
  );
  for (const filtre of main.querySelectorAll('[data-filtre]')) {
    filtre.addEventListener(filtre.tagName === 'INPUT' ? 'input' : 'change', () => {
      const env = store.get('tickets');
      if (env) {
        renderListe(main, env.payload, env.sig, store);
      }
    });
  }
  for (const [section, env] of store.all()) {
    if (rendus[section]) {
      rendus[section](main, env.payload, env.sig, store);
    }
  }
  return () => {
    unsubs.forEach((unsub) => unsub());
  };
}
