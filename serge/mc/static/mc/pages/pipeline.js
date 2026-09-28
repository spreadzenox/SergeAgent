// Page Pipeline : la vue d'ensemble du pipeline, lue en base.
import {toast} from '../components.js';
import {fetchState} from '../sse.js';
import {allerObjet} from '../libelles.js';

async function poster(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return {ok: response.ok, data: await response.json().catch(() => ({}))};
}

function el(tag, classe, texte) {
  const node = document.createElement(tag);
  if (classe) {
    node.className = classe;
  }
  if (texte) {
    node.textContent = texte;
  }
  return node;
}

// Un tableau ; une ligne avec {type, id} ouvre la fiche de l'objet.
function tableau(colonnes, lignes) {
  const wrap = el('div', 'table-scroll');
  const table = el('table', 'matrice');
  const tete = el('tr');
  for (const titre of colonnes) {
    tete.append(el('th', '', titre));
  }
  const head = el('thead');
  head.append(tete);
  const corps = el('tbody');
  for (const ligne of lignes) {
    const tr = el('tr');
    for (const valeur of ligne.cellules) {
      tr.append(el('td', '', String(valeur)));
    }
    if (ligne.type) {
      tr.tabIndex = 0;
      tr.addEventListener('click', () => allerObjet(ligne.type, ligne.id));
    } else {
      tr.style.cursor = 'default';
    }
    corps.append(tr);
  }
  table.append(head, corps);
  wrap.append(table);
  return wrap;
}

const oui = (valeur) => (valeur ? 'oui' : 'non');

// Ne pas effacer ce que Julien est en train de taper.
function changer(conteneur, cle) {
  if (conteneur.dataset.cle === cle) {
    return false;
  }
  conteneur.dataset.cle = cle;
  return true;
}

async function enregistrer(btn, path, body, store) {
  btn.disabled = true;
  try {
    const result = await poster(path, body);
    toast(
      document.body,
      result.ok ? 'Enregistré.' : result.data.erreur || 'Refusé.',
      result.ok ? 'succes' : 'erreur',
    );
    if (result.ok) {
      await rafraichir(store);
    }
  } finally {
    btn.disabled = false;
  }
}

function afficherModeles(conteneur, modeles, store) {
  if (!changer(conteneur, JSON.stringify(modeles))) {
    return;
  }
  conteneur.replaceChildren(...modeles.map((m) => {
    const bloc = el('div', 'grille-champs');
    const label = el('label', 'champ-large', `${m.libelle} `);
    const champ = el('input');
    champ.value = m.model;
    champ.placeholder = m.effectif;
    champ.maxLength = 200;
    champ.dataset.tier = m.tier;
    label.append(champ);
    const btn = el('button', 'btn-fort', 'Enregistrer');
    btn.type = 'button';
    btn.dataset.pipelineAction = 'modele';
    btn.addEventListener('click', () => enregistrer(
      btn,
      '/owner/api/pipeline/modele',
      {tier: m.tier, model: champ.value.trim()},
      store,
    ));
    const barre = el('div', 'barre-policy');
    barre.append(btn);
    bloc.append(label, barre);
    return bloc;
  }));
}

function afficherPresentation(conteneur, texte, store) {
  if (!changer(conteneur, texte)) {
    return;
  }
  const zone = el('textarea');
  zone.maxLength = 4000;
  zone.rows = 6;
  zone.value = texte;
  zone.dataset.pipeline = 'texte';
  const btn = el('button', 'btn-fort', 'Enregistrer le texte');
  btn.type = 'button';
  btn.addEventListener('click', () => enregistrer(
    btn,
    '/owner/api/pipeline/texte',
    {body: zone.value},
    store,
  ));
  const label = el('label', 'champ-large');
  label.append(zone);
  const barre = el('div', 'barre-policy');
  barre.append(btn);
  const bloc = el('div', 'grille-champs');
  bloc.append(label, barre);
  conteneur.replaceChildren(bloc);
}

function afficher(main, payload, sig, store) {
  const zone = (nom) => main.querySelector(`[data-pipeline="${nom}"]`);
  afficherModeles(zone('modeles'), payload.modeles || [], store);
  afficherPresentation(zone('presentation'), payload.presentation || '', store);
  zone('liens').replaceChildren(tableau(
    ['Lien', 'De → vers', 'Quand', 'Passage', 'En attente', 'Passés', 'Allumé'],
    (payload.liens || []).map((l) => ({
      type: 'lien',
      id: l.id,
      cellules: [l.titre, l.chemin, l.quand, l.passage, l.attente, l.passes, oui(l.allume)],
    })),
  ));
  zone('declencheurs').replaceChildren(tableau(
    ['Déclencheur', 'Lance', 'Quand', 'Allumé'],
    (payload.declencheurs || []).map((d) => ({
      type: 'llm',
      id: d.invocation,
      cellules: [d.titre, d.invocation_titre, d.quand, oui(d.allume)],
    })),
  ));
  zone('outils').replaceChildren(tableau(
    ['Outil', 'Capacité', 'Donné à'],
    (payload.outils || []).map((o) => ({
      type: 'outil',
      id: o.id,
      cellules: [o.titre, o.capacite, o.utilise_par],
    })),
  ));
  zone('capacites').replaceChildren(tableau(
    ['Capacité', 'Id', 'Présente dans le code', 'Outils', 'Code'],
    (payload.capacites || []).map((c) => ({
      cellules: [c.titre, c.id, oui(c.disponible), c.outils, c.code],
    })),
  ));
  zone('tables').replaceChildren(tableau(
    ['Table', 'Titre', 'Version courte', 'Colonnes lisibles', 'Plus récentes par'],
    (payload.tables || []).map((t) => ({
      type: 'table',
      id: t.table,
      cellules: [t.table, t.titre, t.courte, t.lisibles, t.ordre],
    })),
  ));
  main.querySelector('[data-section="pipeline"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-pipeline');
  main.replaceChildren(tpl.content.cloneNode(true));
  const unsubscribe = store.subscribe(
    'pipeline',
    (payload, sig) => afficher(main, payload, sig, store),
  );
  for (const [section, env] of store.all()) {
    if (section === 'pipeline') {
      afficher(main, env.payload, env.sig, store);
    }
  }
  return unsubscribe;
}

async function rafraichir(store) {
  try {
    const data = await fetchState('p11');
    for (const [section, env] of Object.entries(data.sections || {})) {
      store.apply(section, env.sig, env.payload);
    }
  } catch {
    // Le flux SSE reprend l'état au prochain tick.
  }
}
