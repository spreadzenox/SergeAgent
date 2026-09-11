// Page P2 Cerveau : stream, décisions, matrice, signaux, clusters.
// Fiche point + kills au lot 6e.
import {fillList, li, rel} from '../components.js';

function etatPoint(item) {
  if (item.tue_runtime) {
    return 'Tué (temporaire)';
  }
  if (!item.enabled) {
    return 'Coupé (registre)';
  }
  return 'En service';
}

function verdictsCompacts(verdicts) {
  const entrees = Object.entries(verdicts || {});
  if (entrees.length === 0) {
    return '—';
  }
  return entrees.map(([v, n]) => `${v}×${n}`).join(', ');
}

function renderPensees(main, payload, sig) {
  const section = main.querySelector('[data-section="pensees"]');
  fillList(
    section.querySelector('[data-list="items"]'),
    payload.items,
    'Aucune pensée pour le moment.',
    (item) => li(`${rel(item.ts)} · ${item.texte}`),
  );
  section.dataset.sig = sig;
}

function renderDecisions(main, payload, sig) {
  const section = main.querySelector('[data-section="decisions"]');
  fillList(
    section.querySelector('[data-list="items"]'),
    payload.items,
    'Aucune décision récente.',
    (item) =>
      li(
        `${rel(item.ts)} · ${item.point} — ${item.verdict}`
        + ` (${item.tokens} jetons, ${item.latence_ms} ms)`,
      ),
  );
  section.dataset.sig = sig;
}

function renderMatrice(main, payload, sig) {
  const conteneur = main.querySelector('[data-matrice="table"]');
  conteneur.replaceChildren();
  if (payload.erreur) {
    const averti = document.createElement('p');
    averti.textContent = 'Registre illisible — matrice indisponible.';
    conteneur.append(averti);
  } else {
    const table = document.createElement('table');
    table.className = 'matrice';
    const tete = document.createElement('tr');
    for (const titre of [
      'Point',
      'Tier',
      'Appels 7j',
      'Jetons 7j',
      'Verdicts',
      'Dérive',
      'État',
    ]) {
      const th = document.createElement('th');
      th.textContent = titre;
      tete.append(th);
    }
    const head = document.createElement('thead');
    head.append(tete);
    table.append(head);
    const corps = document.createElement('tbody');
    for (const item of payload.points) {
      const tr = document.createElement('tr');
      const cellules = [
        item.nom,
        item.tier,
        String(item.appels_7j),
        item.tokens_7j.toLocaleString('fr-FR'),
        verdictsCompacts(item.verdicts),
        item.derive ? `Dérive ${item.derive}` : '—',
        etatPoint(item),
      ];
      cellules.forEach((texte, i) => {
        const td = document.createElement('td');
        td.textContent = texte;
        if ((i === 5 && item.derive) || (i === 6 && texte !== 'En service')) {
          td.classList.add('alerte');
        }
        tr.append(td);
      });
      corps.append(tr);
    }
    table.append(corps);
    conteneur.append(table);
  }
  main.querySelector('[data-section="matrice"]').dataset.sig = sig;
}

function renderSignaux(main, payload, sig) {
  const section = main.querySelector('[data-section="signaux"]');
  fillList(
    section.querySelector('[data-list="items"]'),
    payload.items,
    'Aucun signal récent.',
    (item) =>
      li(
        `${rel(item.ts)} · ${item.channel} ${item.signal}`
        + (item.classe ? ` (${item.classe})` : ' (non classé)'),
      ),
  );
  section.dataset.sig = sig;
}

function renderClusters(main, payload, sig) {
  const section = main.querySelector('[data-section="clusters"]');
  fillList(
    section.querySelector('[data-list="items"]'),
    payload.items,
    'Aucun cluster chaud.',
    (item) => li(`${item.id} — ${item.docs} docs (${item.titres.join(', ')})`),
  );
  section.dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-mind');
  main.replaceChildren(tpl.content.cloneNode(true));
  const rendus = {
    pensees: renderPensees,
    decisions: renderDecisions,
    matrice: renderMatrice,
    signaux: renderSignaux,
    clusters: renderClusters,
  };
  const unsubs = Object.keys(rendus).map((section) =>
    store.subscribe(section, (payload, sg) => {
      rendus[section](main, payload, sg);
    }),
  );
  for (const [section, env] of store.all()) {
    if (rendus[section]) {
      rendus[section](main, env.payload, env.sig);
    }
  }
  return () => {
    unsubs.forEach((unsub) => unsub());
  };
}
