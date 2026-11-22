// Une case de la carte : la carte d’une invocation, et autour d’elle ce
// qui la lance, les tables qu’elle lit (au-dessus) et celles où elle écrit
// (en dessous). Les hauteurs des rangées sont celles de carte_plan.py.
import {rel} from '../libelles.js';

const SVG = 'http://www.w3.org/2000/svg';
// Au plus tant de tables montrées par rangée ; le reste est dans « +n ».
const TABLES_MAX = 2;

export const STATUTS = {
  done: 'terminée',
  failed: 'en échec',
  running: 'en cours',
  blocked: 'attend Julien',
  cancelled: 'annulée',
  jamais: 'jamais lancée',
};
const SIGNES = {bouton: '◉', horloge: '◷', ligne: '⚡'};

function el(tag, classe, texte) {
  const node = document.createElement(tag);
  if (classe) node.className = classe;
  if (texte) node.textContent = texte;
  return node;
}

// La petite icône « base de données » : un cylindre.
export function icone() {
  const dessin = document.createElementNS(SVG, 'svg');
  dessin.setAttribute('class', 'carte-icone');
  dessin.setAttribute('viewBox', '0 0 16 16');
  dessin.setAttribute('aria-hidden', 'true');
  for (const d of [
    'M2 4v8c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V4',
    'M2 4c0-1.4 2.7-2.5 6-2.5s6 1.1 6 2.5-2.7 2.5-6 2.5S2 5.4 2 4z',
    'M2 8c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5',
  ]) {
    const trait = document.createElementNS(SVG, 'path');
    trait.setAttribute('d', d);
    dessin.append(trait);
  }
  return dessin;
}

// Ce que dit la dernière exécution d’une invocation, en court.
export function phraseEtat(etat) {
  if (!etat) return STATUTS.jamais;
  const quand = etat.finie || etat.commencee;
  return `${STATUTS[etat.statut] || etat.statut}${quand ? ` ${rel(quand)}` : ''}`;
}

function rangeeDeTables(tables, sens, surTable) {
  const rangee = el('div', `carte-tables ${sens}`);
  for (const t of tables.slice(0, TABLES_MAX)) {
    const puce = el('button', 'carte-table');
    puce.type = 'button';
    puce.dataset.table = t.table;
    puce.title = `${sens === 'lit' ? 'Elle lit' : 'Elle écrit dans'} ${t.titre || t.table} (${t.table})`;
    puce.append(icone(), el('span', '', t.table));
    puce.addEventListener('click', (ev) => {
      ev.stopPropagation();
      surTable(t.table);
    });
    rangee.append(puce);
  }
  if (tables.length > TABLES_MAX) {
    const reste = tables.slice(TABLES_MAX);
    const plus = el('button', 'carte-table plus', `+${reste.length}`);
    plus.type = 'button';
    plus.title = reste.map((t) => t.table).join(', ');
    plus.addEventListener('click', (ev) => {
      ev.stopPropagation();
      surTable(reste[0].table);
    });
    rangee.append(plus);
  }
  return rangee;
}

// Dessine une case. `actes` : {case(), table(nom)}.
export function dessinerCase(c, etat, actes) {
  const boite = el('div', 'carte-case');
  boite.dataset.id = c.id;
  if (c.fantome) boite.classList.add('fantome');
  if (c.mission_seule) boite.classList.add('mission-seule');
  if (!c.allumee) boite.classList.add('eteinte');
  boite.style.left = `${c.x}px`;
  boite.style.top = `${c.y}px`;
  boite.style.width = `${c.w}px`;
  boite.style.height = `${c.h}px`;
  if (c.lance.length) {
    const rangee = el('div', 'carte-lance');
    for (const d of c.lance.slice(0, 2)) {
      const puce = el('span', `carte-puce ${d.sorte}`, `${SIGNES[d.sorte] || ''} ${d.texte}`);
      puce.title = `Lancée par : ${d.texte}${d.allume ? '' : ' (éteint)'}`;
      if (!d.allume) puce.classList.add('eteint');
      rangee.append(puce);
    }
    if (c.lance.length > 2) rangee.append(el('span', 'carte-puce', `+${c.lance.length - 2}`));
    boite.append(rangee);
  }
  if (c.lit.length) boite.append(rangeeDeTables(c.lit, 'lit', actes.table));
  const carte = el('button', 'carte-carte');
  carte.type = 'button';
  carte.dataset.sorte = c.sorte;
  const tete = el('span', 'carte-tete');
  const pastille = el('i', 'carte-etat');
  tete.append(pastille, el('span', 'carte-titre', c.titre));
  const meta = el('span', 'carte-meta');
  const sorte = c.sorte === 'llm' ? `LLM${c.niveau ? ` · ${c.niveau}` : ''}` : 'sans LLM';
  meta.append(el('span', '', c.fantome ? 'pipeline principal' : sorte));
  if (c.mission_seule) meta.append(el('span', 'carte-badge', 'en mission'));
  if (!c.allumee) meta.append(el('span', 'carte-badge alerte', 'éteinte'));
  if (c.hors_de_serge || c.outils.some((o) => o.hors_de_serge)) {
    const dehors = el('span', 'carte-badge', 'agit dehors');
    dehors.title = 'Elle agit hors de Serge : un message envoyé, un service appelé.';
    meta.append(dehors);
  }
  if (c.outils.length) meta.append(el('span', 'carte-outils', `${c.outils.length} outil${c.outils.length > 1 ? 's' : ''}`));
  carte.append(tete, meta, el('span', 'carte-derniere'));
  carte.title = c.titre;
  carte.addEventListener('click', (ev) => {
    ev.stopPropagation();
    actes.case();
  });
  boite.append(carte);
  if (c.ecrit.length) boite.append(rangeeDeTables(c.ecrit, 'ecrit', actes.table));
  poserEtat(boite, etat);
  return boite;
}

function poserEtat(boite, etat) {
  const statut = etat ? etat.statut : 'jamais';
  boite.querySelector('.carte-carte').dataset.statut = statut;
  boite.querySelector('.carte-etat').dataset.statut = statut;
  const phrase = boite.querySelector('.carte-derniere');
  phrase.textContent = phraseEtat(etat);
  phrase.title = etat && etat.erreur ? etat.erreur : '';
}

// La dernière exécution change souvent : on ne récrit que les pastilles.
export function majEtat(plan, etats) {
  plan.querySelectorAll('.carte-case').forEach((boite) => {
    poserEtat(boite, etats[boite.dataset.id]);
  });
}
