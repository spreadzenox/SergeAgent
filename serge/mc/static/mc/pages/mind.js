// Page P2 Cerveau : stream, décisions, invocations, signaux.
import {
  confirmModal,
  fillList,
  li,
  openDrawer,
  rel,
  toast,
} from '../components.js';
import {fetchState} from '../sse.js';

function etatPoint(item) {
  return item.enabled ? 'Allumée' : 'Éteinte';
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

function renderMatrice(main, payload, sig, store) {
  const conteneur = main.querySelector('[data-matrice="table"]');
  conteneur.replaceChildren();
  if (!(payload.points || []).length) {
    const vide = document.createElement('p');
    vide.textContent = 'Aucune invocation en base pour l’instant.';
    conteneur.append(vide);
  } else {
    const table = document.createElement('table');
    table.className = 'matrice';
    const tete = document.createElement('tr');
    for (const titre of [
      'Invocation',
      'Niveau',
      'File',
      'Priorité',
      'Appels 7j',
      'Jetons 7j',
      'Verdicts',
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
      const tdNom = document.createElement('td');
      const bouton = document.createElement('button');
      bouton.type = 'button';
      bouton.className = 'lien-point';
      bouton.textContent = item.titre || item.nom;
      bouton.title = item.nom;
      bouton.addEventListener('click', () => ouvrirFiche(store, item));
      tdNom.append(bouton);
      tr.append(tdNom);
      const cellules = [
        item.tier,
        item.file,
        String(item.priorite),
        String(item.appels_7j),
        item.tokens_7j.toLocaleString('fr-FR'),
        verdictsCompacts(item.verdicts),
        etatPoint(item),
      ];
      cellules.forEach((texte, i) => {
        const td = document.createElement('td');
        td.textContent = texte;
        if (i === 6 && !item.enabled) {
          td.classList.add('alerte');
        }
        tr.append(td);
      });
      corps.append(tr);
    }
    table.append(corps);
    const scroll = document.createElement('div');
    scroll.className = 'table-scroll';
    scroll.append(table);
    conteneur.append(scroll);
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

export function mount(main, store) {
  const tpl = document.getElementById('page-mind');
  main.replaceChildren(tpl.content.cloneNode(true));
  const rendus = {
    pensees: renderPensees,
    decisions: renderDecisions,
    matrice: renderMatrice,
    signaux: renderSignaux,
  };
  const unsubs = Object.keys(rendus).map((section) =>
    store.subscribe(section, (payload, sg) => {
      rendus[section](main, payload, sg, store);
    }),
  );
  for (const [section, env] of store.all()) {
    if (rendus[section]) {
      rendus[section](main, env.payload, env.sig, store);
    }
  }
  return () => {
    unsubs.forEach((unsub) => unsub());
  };
}

async function rafraichir(store) {
  try {
    const data = await fetchState('p2');
    for (const [section, env] of Object.entries(data.sections || {})) {
      store.apply(section, env.sig, env.payload);
    }
  } catch {
    // le stream reprendra au prochain tick
  }
}

async function poster(chemin, charge) {
  const res = await fetch(chemin, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(charge),
  });
  return {ok: res.ok, data: await res.json()};
}

async function basculer(store, item, rouvrir) {
  const allumer = !item.enabled;
  const confirmer = await confirmModal(document.body, {
    title: `${allumer ? 'Allumer' : 'Éteindre'} ${item.titre || item.nom} ?`,
    message: allumer
      ? 'Ses tâches en attente reprendront au prochain tour de sa file.'
      : 'Ses tâches attendront ; aucune nouvelle tâche ne sera créée.',
    confirm: allumer ? 'Allumer' : 'Éteindre',
  });
  if (!confirmer) {
    return;
  }
  try {
    const {ok, data} = await poster('/owner/api/coupe', {
      cible: 'invocation',
      id: item.nom,
      marche: allumer,
      decision_id: `mc-${Date.now()}-${item.nom}`,
    });
    if (!ok) {
      toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
      return;
    }
    toast(
      document.body,
      `${item.titre || item.nom} ${allumer ? 'allumée' : 'éteinte'}.`,
      'succes',
    );
    await rafraichir(store);
    rouvrir();
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  }
}

function ouvrirFiche(store, item) {
  const corps = document.createElement('div');
  const lignes = [
    ['État', etatPoint(item)],
    ['Niveau', item.tier],
    ['File', item.file],
    ['Priorité', String(item.priorite)],
    [
      '7 jours',
      `${item.appels_7j} appels, ${item.tokens_7j.toLocaleString('fr-FR')} jetons, ${item.latence_ms} ms`,
    ],
    ['Verdicts', verdictsCompacts(item.verdicts)],
  ];
  for (const [cle, valeur] of lignes) {
    const p = document.createElement('p');
    p.textContent = `${cle} : ${valeur}`;
    corps.append(p);
  }
  const bouton = document.createElement('button');
  bouton.type = 'button';
  bouton.textContent = item.enabled ? 'Éteindre' : 'Allumer';
  if (item.enabled) {
    bouton.classList.add('danger');
  }
  const ferme = openDrawer(document.body, item.titre || item.nom, corps);
  function rouvrir() {
    ferme();
    const env = store.get('matrice');
    const items = env && env.payload ? env.payload.points || [] : [];
    const frais = items.find((p) => p.nom === item.nom);
    if (frais) {
      ouvrirFiche(store, frais);
    }
  }
  bouton.addEventListener('click', () => {
    bouton.disabled = true;
    const fin = () => {
      bouton.disabled = false;
    };
    basculer(store, item, rouvrir).finally(fin);
  });
  const fiche = document.createElement('button');
  fiche.type = 'button';
  fiche.textContent = 'Fiche complète';
  fiche.addEventListener('click', () => {
    ferme();
    location.hash = `#/objet/llm/${encodeURIComponent(item.nom)}`;
  });
  corps.append(bouton, fiche);
}
