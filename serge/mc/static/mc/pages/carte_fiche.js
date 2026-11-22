// Le détail d’une case, d’une table ou d’un lien de la carte : le panneau
// de droite. `actes` : {aller(id), table(nom, id), ouvrir(type, id), fermer()}.
import {dateLocale, depuis} from '../libelles.js';
import {chargerObjet} from '../objets.js';
import {icone, phraseEtat} from './carte_case.js';

const SOURCES = {
  field: 'la réponse',
  fixed: 'fixe',
  task: 'la tâche',
  setting: 'un réglage',
  now: 'l’heure',
  parent_row: 'la ligne du dessus',
};

function el(tag, classe, texte) {
  const node = document.createElement(tag);
  if (classe) node.className = classe;
  if (texte) node.textContent = texte;
  return node;
}

function bouton(texte, action, classe) {
  const b = el('button', classe || 'clic-ligne', texte);
  b.type = 'button';
  b.addEventListener('click', action);
  return b;
}

function entete(type, titre, actes) {
  const tete = el('header', 'carte-fiche-tete');
  const fermer = bouton('×', actes.fermer, 'carte-fermer');
  fermer.setAttribute('aria-label', 'Fermer le détail');
  tete.append(el('p', 'badge-type', type), fermer, el('h3', '', titre));
  return tete;
}

function partie(titre, ...enfants) {
  const bloc = el('section', 'carte-partie');
  bloc.append(el('h4', '', titre), ...enfants);
  return bloc;
}

function liste(items, vide) {
  if (!items.length) return el('p', 'carte-vide', vide || 'Rien.');
  const ul = el('ul');
  for (const item of items) {
    const li = el('li');
    li.append(...[].concat(item));
    ul.append(li);
  }
  return ul;
}

function lienTable(t, id, actes) {
  const b = bouton('', () => actes.table(t.table, id), 'carte-table');
  b.append(icone(), el('span', '', t.table));
  b.title = t.titre || t.table;
  return b;
}

// Comment une table est lue : par un outil (son nom), ou « pour comparer ».
function comment(par) {
  return par.map((p) => (p === 'pour comparer' || p === 'sa lecture' ? p : `par « ${p} »`)).join(', ');
}

// Une règle d’écriture, en clair : « ajoute une ligne, si verdict = bon ».
function regle(r) {
  const verbes = {insert: 'ajoute une ligne', update: 'modifie la ligne', upsert: 'ajoute ou modifie', delete: 'supprime'};
  let texte = verbes[r.operation] || r.operation;
  if (r.pour_chaque) texte += ` pour chaque « ${r.pour_chaque} »`;
  if (r.condition) texte += `, si ${r.condition}`;
  const bloc = el('div', 'carte-regle');
  bloc.append(el('p', '', texte));
  if (r.colonnes.length) {
    const dl = el('dl');
    for (const c of r.colonnes) {
      const d = c.valeur ? `${SOURCES[c.source] || c.source} : ${c.valeur}` : SOURCES[c.source] || c.source;
      dl.append(el('dt', '', c.colonne), el('dd', '', d));
    }
    bloc.append(dl);
  }
  return bloc;
}

function voisins(c, data, sens, actes) {
  const liens = data.liens.filter((l) => (sens === 'avant' ? l.vers : l.de) === c.id);
  return liste(
    liens.map((l) => {
      const autre = data.noeuds.find((n) => n.id === (sens === 'avant' ? l.de : l.vers));
      const detail = [l.sorte === 'mission' ? 'mission' : '', l.condition ? `si ${l.condition}` : '', l.couloir === 'trial' ? 'essai' : '', l.sorte === 'lien' && !l.auto ? 'attend un clic' : '']
        .filter(Boolean)
        .join(', ');
      return [bouton(autre ? autre.titre : sens === 'avant' ? l.de : l.vers, () => actes.aller(autre.id)), detail ? ` (${detail})` : ''];
    }),
    sens === 'avant' ? 'Aucun lien n’y mène.' : 'Elle ne lance rien d’autre.',
  );
}

// Ce que la dernière tâche a rendu : lu sur sa fiche, au premier besoin.
function rendu(tache) {
  const bloc = el('div', 'carte-rendu', 'Lecture de ce qu’elle a rendu…');
  chargerObjet('task', tache).then((fiche) => {
    const cadres = ((fiche && fiche.cadres) || []).filter((c) => (c.champs || []).length && !c.journal);
    if (!cadres.length) {
      bloc.textContent = 'Elle n’a pas rendu de réponse (une invocation sans LLM, ou une tâche sans résultat).';
      return;
    }
    const dl = el('dl');
    for (const champ of cadres[0].champs.slice(0, 6)) {
      const texte = String(champ.v);
      dl.append(el('dt', '', champ.k), el('dd', '', texte.length > 400 ? `${texte.slice(0, 400)}…` : texte));
    }
    bloc.replaceChildren(dl);
  });
  return bloc;
}

export function ficheCase(c, data, etat, actes) {
  const boite = el('div', 'carte-fiche-corps');
  const sorte = c.sorte === 'llm' ? `Invocation LLM${c.niveau ? ` · niveau ${c.niveau}` : ''}` : `Invocation sans LLM${c.capacite_titre ? ` · ${c.capacite_titre}` : ''}`;
  boite.append(entete(sorte, c.titre, actes));
  if (c.role) boite.append(el('p', 'carte-role', c.role));
  const actions = el('p', 'carte-actions');
  actions.append(bouton('Ouvrir la fiche de l’invocation', () => actes.ouvrir('llm', c.id), 'btn-fort'));
  boite.append(actions);
  const derniere = el('div');
  derniere.append(el('p', `carte-statut ${etat ? etat.statut : 'jamais'}`, phraseEtat(etat)));
  if (etat) {
    const dl = el('dl');
    if (etat.commencee) dl.append(el('dt', '', 'Commencée'), el('dd', '', dateLocale(etat.commencee)));
    if (etat.finie) dl.append(el('dt', '', 'Finie'), el('dd', '', dateLocale(etat.finie)));
    if (etat.statut === 'running' && etat.commencee) dl.append(el('dt', '', 'Tourne'), el('dd', '', depuis(etat.commencee)));
    if (etat.erreur) dl.append(el('dt', '', 'Erreur'), el('dd', 'carte-erreur', etat.erreur));
    derniere.append(dl, rendu(etat.tache), bouton('Ouvrir cette tâche', () => actes.ouvrir('task', etat.tache)));
  }
  boite.append(partie('Sa dernière exécution', derniere));
  boite.append(
    partie('Ce qui la lance', liste(c.lance.map((d) => `${d.texte}${d.allume ? '' : ' (éteint)'}`), 'Aucun déclencheur : un lien, une mission ou le code la lance.')),
    partie('Avant elle', voisins(c, data, 'avant', actes)),
    partie('Après elle', voisins(c, data, 'apres', actes)),
    partie('Elle lit', liste(c.lit.map((t) => [lienTable(t, c.id, actes), ` ${t.titre ? `${t.titre} — ` : ''}${comment(t.par)}`]), 'Aucune table.')),
    partie('Elle écrit', liste(c.ecrit.map((t) => [lienTable(t, c.id, actes), ` ${t.titre || ''}`, ...t.regles.map(regle)]), 'Aucune règle d’écriture en base.')),
  );
  const parCapacite = new Map();
  for (const o of c.outils) {
    if (!parCapacite.has(o.capacite)) parCapacite.set(o.capacite, []);
    parCapacite.get(o.capacite).push(o);
  }
  const outils = el('div');
  for (const [capacite, groupe] of parCapacite) {
    outils.append(el('p', 'carte-capacite', capacite));
    outils.append(
      liste(
        groupe.map((o) => {
          const suite = [o.mode, o.service ? `service : ${o.service}` : '', o.tables.length ? `tables : ${o.tables.join(', ')}` : ''].filter(Boolean).join(' · ');
          const ligne = [bouton(o.titre, () => actes.ouvrir('outil', o.id)), ` (${suite})`];
          if (o.mission) ligne.push(' → ', bouton(o.mission, () => actes.aller(o.mission)));
          return ligne;
        }),
      ),
    );
  }
  boite.append(partie(`Ses outils (${c.outils.length})`, c.outils.length ? outils : el('p', 'carte-vide', 'Aucun outil.')));
  return boite;
}

export function ficheTable(table, c, data, actes) {
  const boite = el('div', 'carte-fiche-corps');
  const titre = data.noeuds.flatMap((n) => [...n.lit, ...n.ecrit]).find((t) => t.table === table);
  boite.append(entete('Table', table, actes));
  if (titre && titre.titre) boite.append(el('p', 'carte-role', titre.titre));
  const actions = el('p', 'carte-actions');
  actions.append(bouton('Ouvrir la table', () => actes.ouvrir('table', table), 'btn-fort'));
  boite.append(actions);
  if (c) {
    const ecrit = c.ecrit.find((t) => t.table === table);
    const lit = c.lit.find((t) => t.table === table);
    if (ecrit) boite.append(partie(`Ce que « ${c.titre} » y écrit`, ...ecrit.regles.map(regle)));
    if (lit) boite.append(partie(`Comment « ${c.titre} » la lit`, el('p', '', comment(lit.par))));
  }
  const qui = (cle) => data.noeuds.filter((n) => !n.fantome && n[cle].some((t) => t.table === table)).map((n) => bouton(n.titre, () => actes.aller(n.id)));
  const lancees = data.noeuds.filter((n) => n.lance.some((d) => d.table === table)).map((n) => bouton(n.titre, () => actes.aller(n.id)));
  boite.append(
    partie('Qui y écrit, dans cet onglet', liste(qui('ecrit'), 'Personne, par une règle d’écriture.')),
    partie('Qui la lit', liste(qui('lit'), 'Personne.')),
    partie('Qui est lancé quand une ligne y est écrite', liste(lancees, 'Personne.')),
  );
  return boite;
}

export function ficheLien(l, data, actes) {
  const boite = el('div', 'carte-fiche-corps');
  const nom = (id) => (data.noeuds.find((n) => n.id === id) || {titre: id}).titre;
  boite.append(entete(l.sorte === 'mission' ? 'Mission confiée' : 'Lien', l.titre, actes));
  const dl = el('dl');
  const ligne = (k, v) => dl.append(el('dt', '', k), v instanceof Node ? v : el('dd', '', v));
  const dd = (id) => {
    const d = el('dd');
    d.append(bouton(nom(id), () => actes.aller(id)));
    return d;
  };
  ligne('De', dd(l.de));
  ligne('Vers', dd(l.vers));
  if (l.sorte === 'lien') {
    ligne('Condition', l.condition || 'aucune : il passe toujours');
    ligne('Passe', l.par_ligne ? 'une tâche par ligne écrite' : 'une tâche quand l’invocation finit');
    ligne('Délai', l.delai ? `réglage ${l.delai}` : 'aucun');
    ligne('Couloir', {trial: 'seulement pendant un essai total', real: 'seulement hors essai'}[l.couloir] || 'les deux');
    ligne('Passage', l.auto ? 'automatique' : 'attend un clic « Passer à la suite »');
    ligne('État', l.allume ? 'allumé' : 'éteint');
  } else {
    ligne('Comment', 'L’invocation de gauche confie ce travail à celle de droite, qui lui rend sa réponse ; les liens de celle de droite ne jouent pas.');
  }
  boite.append(dl);
  if (l.sorte === 'lien') {
    const actions = el('p', 'carte-actions');
    actions.append(bouton('Ouvrir la fiche du lien', () => actes.ouvrir('lien', l.id), 'btn-fort'));
    boite.append(actions);
  }
  return boite;
}

