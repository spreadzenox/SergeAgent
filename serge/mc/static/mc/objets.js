// Routeur de fiches objet : page parent ou tiroir feuille.
import {TYPES_OBJET, allerObjet, depuis} from './libelles.js';

const TIROIRS = new Set([
  'work_item',
  'event',
  'touch',
  'inbound_event',
  'listen_doc',
  'llm_usage',
]);

function renderCadre(cadre) {
  const bloc = el('div', 'cadre-fiche');
  bloc.append(el('h3', '', cadre.titre || ''));
  if (cadre.texte) {
    bloc.append(el('p', 'texte-cadre', cadre.texte));
  }
  if ((cadre.champs || []).length) {
    const dl = el('dl');
    for (const champ of cadre.champs) {
      dl.append(el('dt', '', champ.k), el('dd', '', champ.v));
    }
    bloc.append(dl);
  }
  if ((cadre.liens || []).length) {
    const ul = el('ul', 'liste-materiel');
    for (const lien of cadre.liens) {
      const li = el('li');
      const btn = el('button', 'clic-ligne', lien.titre);
      btn.type = 'button';
      btn.addEventListener('click', () => allerObjet(lien.type, lien.id));
      li.append(btn);
      ul.append(li);
    }
    bloc.append(ul);
  }
  if (cadre.todo) {
    const note = el('p', 'todo-mc', cadre.todo);
    bloc.append(note);
  }
  return bloc;
}

function cellule(colonne, valeur) {
  if ((colonne === 'Depuis' || colonne === 'Pause') && valeur && valeur !== '—') {
    return depuis(valeur) || valeur;
  }
  return valeur;
}

function tableau(data) {
  const wrap = el('div', 'table-scroll');
  const table = el('table', 'matrice');
  const tete = el('tr');
  for (const titre of data.colonnes || []) {
    tete.append(el('th', '', titre));
  }
  const head = el('thead');
  head.append(tete);
  table.append(head);
  const corps = el('tbody');
  for (const ligne of data.lignes || []) {
    const tr = el('tr');
    tr.tabIndex = 0;
    const etat = (ligne.cellules || [])[2] || '';
    if (etat === 'Prochain') {
      tr.className = 'rang-prochain';
    }
    (ligne.cellules || []).forEach((valeur, i) => {
      const nom = (data.colonnes || [])[i] || '';
      tr.append(el('td', '', cellule(nom, valeur)));
    });
    if (ligne.type && ligne.id) {
      tr.addEventListener('click', () => allerObjet(ligne.type, ligne.id));
    } else {
      tr.style.cursor = 'default';
    }
    corps.append(tr);
  }
  table.append(corps);
  wrap.append(table);
  return wrap;
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

export function renderFiche(data) {
  const wrap = el('div', 'fiche-objet');
  const badge = el('p', 'badge-type', TYPES_OBJET[data.type] || data.type || '');
  wrap.append(badge);
  if (data.pourquoi) {
    wrap.append(el('p', 'pourquoi', data.pourquoi));
  }
  if ((data.champs || []).length) {
    const dl = el('dl');
    for (const champ of data.champs || []) {
      dl.append(el('dt', '', champ.k), el('dd', '', champ.v));
    }
    wrap.append(dl);
  }
  for (const cadre of data.cadres || []) {
    wrap.append(renderCadre(cadre));
  }
  if (data.tableau && (data.tableau.colonnes || []).length) {
    const bloc = el('div', 'cadre-fiche');
    if (data.tableau.titre) {
      bloc.append(el('h3', '', data.tableau.titre));
    }
    bloc.append(tableau(data.tableau));
    wrap.append(bloc);
  } else if ((data.enfants || []).length) {
    wrap.append(el('h3', '', 'Suite de l’arbre'));
    const ul = el('ul');
    for (const enfant of data.enfants) {
      const li = el('li');
      const btn = el('button', 'clic-ligne', enfant.titre);
      btn.type = 'button';
      btn.addEventListener('click', () => allerObjet(enfant.type, enfant.id));
      li.append(btn);
      ul.append(li);
    }
    wrap.append(ul);
  }
  if (data.preuve) {
    const details = el('details');
    details.append(el('summary', '', 'Preuve — jusqu’au dernier caractère'));
    details.append(el('pre', 'preuve', data.preuve));
    wrap.append(details);
  }
  const exportBtn = el('button', 'btn-export', 'Exporter le JSON');
  exportBtn.type = 'button';
  exportBtn.addEventListener('click', () => {
    const blob = new Blob([JSON.stringify(data, null, 2)], {
      type: 'application/json',
    });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${data.type || 'objet'}-${data.id || 'fiche'}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  });
  wrap.append(exportBtn);
  return wrap;
}

export async function chargerObjet(type, id) {
  const res = await fetch(
    `/owner/api/objet?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`,
    {cache: 'no-store'},
  );
  if (!res.ok) {
    return null;
  }
  return res.json();
}

export async function monterObjet(main, type, id) {
  main.replaceChildren();
  const data = await chargerObjet(type, id);
  const fil = el('p', 'fil-ariane');
  const back = el('a', '', '← En direct');
  back.href = '#/live';
  const typeFr = TYPES_OBJET[type] || type;
  const nom = (data && data.titre) || id;
  fil.append(back, document.createTextNode(` · ${typeFr} · ${nom}`));
  main.append(fil);
  if (!data) {
    main.append(el('p', '', 'Objet introuvable — il n’est plus dans le canon.'));
    return () => {};
  }
  main.append(el('h2', '', data.titre || id));
  main.append(renderFiche(data));
  return () => {};
}

export function estTiroir(type) {
  return TIROIRS.has(type);
}
