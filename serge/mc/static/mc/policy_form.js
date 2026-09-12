// Contrôles Policy : curseur, oui/non, jours, plages, listes.

import {CANAUX, JOURS, SECTIONS, specDe} from './policy_champs.js';

export function el(tag, classe, texte) {
  const node = document.createElement(tag);
  if (classe) {
    node.className = classe;
  }
  if (texte) {
    node.textContent = texte;
  }
  return node;
}

function aplatir(obj, prefix, acc) {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    acc.push([prefix, obj]);
    return;
  }
  for (const [k, v] of Object.entries(obj)) {
    const next = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      aplatir(v, next, acc);
    } else {
      acc.push([next, v]);
    }
  }
}

export function poser(cible, chemin, val) {
  const parts = chemin.split('.');
  let cur = cible;
  for (let i = 0; i < parts.length - 1; i += 1) {
    if (!(parts[i] in cur) || typeof cur[parts[i]] !== 'object') {
      cur[parts[i]] = {};
    }
    cur = cur[parts[i]];
  }
  cur[parts[parts.length - 1]] = val;
}

function cadre(chemin, spec) {
  const wrap = el('div', 'champ-policy');
  wrap.dataset.chemin = chemin;
  wrap.dataset.widget = spec.widget;
  const lab = el('p', 'titre-champ', spec.titre);
  wrap.append(lab);
  if (spec.aide) {
    wrap.append(el('p', 'aide-champ', spec.aide));
  }
  return wrap;
}

function pad2(n) {
  return String(n).padStart(2, '0');
}

function versHeure(h, m) {
  return `${pad2(Number(h) || 0)}:${pad2(Number(m) || 0)}`;
}

function depuisHeure(s) {
  const [h, m] = String(s || '00:00').split(':');
  return [Number(h) || 0, Number(m) || 0];
}

function curseur(spec, val, fmt) {
  const box = el('div', 'range-policy');
  const range = el('input');
  range.type = 'range';
  range.min = String(spec.min ?? 0);
  range.max = String(spec.max ?? 100);
  range.step = String(spec.pas ?? 1);
  const num = el('input');
  num.type = 'number';
  num.min = range.min;
  num.max = range.max;
  num.step = range.step;
  const v = val == null || Number.isNaN(Number(val)) ? Number(range.min) : Number(val);
  range.value = String(v);
  num.value = String(v);
  const out = el('span', 'valeur-champ', fmt(v));
  const sync = (src) => {
    const n = Number(src.value);
    range.value = String(n);
    num.value = String(n);
    out.textContent = fmt(n);
  };
  range.addEventListener('input', () => sync(range));
  num.addEventListener('input', () => sync(num));
  box.append(range, num, out);
  return {box, lire: () => Number(num.value)};
}

function fmtEur(n) {
  return `${n} €`;
}

function fmtPct(n) {
  return `${Math.round(Number(n) * 100)} %`;
}

function fmtHeure(n) {
  return `${n} h`;
}

function fmtBrut(n) {
  return String(n);
}

function champCurseur(chemin, spec, val, fmt) {
  const wrap = cadre(chemin, spec);
  const {box, lire} = curseur(spec, val, fmt);
  wrap.append(box);
  wrap._lire = lire;
  return wrap;
}

function champOuiNon(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const lab = el('label', 'switch-policy');
  const box = el('input');
  box.type = 'checkbox';
  box.checked = Boolean(val);
  lab.append(box, el('span', 'switch-piste'), el('span', 'switch-texte', val ? 'Oui' : 'Non'));
  box.addEventListener('change', () => {
    lab.querySelector('.switch-texte').textContent = box.checked ? 'Oui' : 'Non';
  });
  wrap.append(lab);
  wrap._lire = () => box.checked;
  return wrap;
}

function champListe(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const sel = el('select', 'select-policy');
  const choix = spec.choix || [];
  const cur = String(val ?? '');
  if (cur && !choix.includes(cur)) {
    choix.unshift(cur);
  }
  for (const opt of choix) {
    const o = el('option', '', String(opt));
    o.value = String(opt);
    sel.append(o);
  }
  sel.value = cur;
  wrap.append(sel);
  wrap._lire = () => sel.value;
  return wrap;
}

function champJours(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const pris = new Set(Array.isArray(val) ? val : []);
  const grille = el('div', 'jours-policy');
  const cases = [];
  for (const [id, lib] of JOURS) {
    const lab = el('label', 'puce-choix');
    const box = el('input');
    box.type = 'checkbox';
    box.checked = pris.has(id);
    box.dataset.jour = id;
    lab.append(box, el('span', '', lib));
    grille.append(lab);
    cases.push(box);
  }
  wrap.append(grille);
  wrap._lire = () => cases.filter((c) => c.checked).map((c) => c.dataset.jour);
  return wrap;
}

function champCanaux(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const pris = new Set(Array.isArray(val) ? val : []);
  const grille = el('div', 'jours-policy');
  const cases = [];
  for (const [id, lib] of CANAUX) {
    const lab = el('label', 'puce-choix');
    const box = el('input');
    box.type = 'checkbox';
    box.checked = pris.has(id);
    box.dataset.canal = id;
    lab.append(box, el('span', '', lib));
    grille.append(lab);
    cases.push(box);
  }
  wrap.append(grille);
  wrap._lire = () => cases.filter((c) => c.checked).map((c) => c.dataset.canal);
  return wrap;
}

function ligneFenetre(plage, onRetirer) {
  const row = el('div', 'fenetre-ligne');
  const a = el('input');
  a.type = 'time';
  const b = el('input');
  b.type = 'time';
  const [h1, m1, h2, m2] = Array.isArray(plage) ? plage : [8, 0, 18, 0];
  a.value = versHeure(h1, m1);
  b.value = versHeure(h2, m2);
  const retirer = el('button', 'btn-doux', 'Retirer');
  retirer.type = 'button';
  retirer.addEventListener('click', () => onRetirer(row));
  row.append(a, el('span', 'fleche-plage', '→'), b, retirer);
  row._lire = () => [...depuisHeure(a.value), ...depuisHeure(b.value)];
  return row;
}

function champFenetres(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const liste = el('div', 'liste-fenetres');
  const rows = [];
  const oter = (row) => {
    row.remove();
    const i = rows.indexOf(row);
    if (i >= 0) {
      rows.splice(i, 1);
    }
  };
  const ajouter = (plage) => {
    const row = ligneFenetre(plage, oter);
    rows.push(row);
    liste.append(row);
  };
  const depart = Array.isArray(val) && val.length ? val : [[8, 0, 18, 0]];
  depart.forEach((p) => ajouter(p));
  const plus = el('button', 'btn-doux', 'Ajouter une plage');
  plus.type = 'button';
  plus.addEventListener('click', () => ajouter([9, 0, 12, 0]));
  wrap.append(liste, plus);
  wrap._lire = () => rows.filter((r) => r.isConnected).map((r) => r._lire());
  return wrap;
}

function champNombres(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const input = el('input', 'texte-policy');
  input.type = 'text';
  input.value = Array.isArray(val) ? val.join(', ') : '';
  wrap.append(input);
  wrap._lire = () => input.value.split(/[,\s]+/).filter(Boolean).map(Number).filter((n) => !Number.isNaN(n));
  return wrap;
}

function champPaire(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const [a, b] = Array.isArray(val) ? val : [spec.min ?? 0, spec.max ?? 100];
  const bas = curseur(spec, a, fmtBrut);
  const haut = curseur(spec, b, fmtBrut);
  wrap.append(el('p', 'mini-lib', 'Bas'), bas.box, el('p', 'mini-lib', 'Haut'), haut.box);
  wrap._lire = () => [bas.lire(), haut.lire()];
  return wrap;
}

function champNombre(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const input = el('input', 'texte-policy');
  input.type = 'number';
  if (spec.min != null) {
    input.min = String(spec.min);
  }
  if (spec.max != null) {
    input.max = String(spec.max);
  }
  if (spec.pas != null) {
    input.step = String(spec.pas);
  }
  input.value = String(val ?? 0);
  wrap.append(input);
  wrap._lire = () => Number(input.value);
  return wrap;
}

function champTexte(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const input = el('input', 'texte-policy');
  input.type = 'text';
  input.value = typeof val === 'string' ? val : JSON.stringify(val);
  wrap.append(input);
  wrap._lire = () => input.value;
  return wrap;
}

const FABRIQUES = {
  eur: (c, s, v) => champCurseur(c, s, v, fmtEur),
  pct: (c, s, v) => champCurseur(c, s, v, fmtPct),
  curseur: (c, s, v) => champCurseur(c, s, v, fmtBrut),
  heure: (c, s, v) => champCurseur(c, s, v, fmtHeure),
  nombre: champNombre,
  ouinon: champOuiNon,
  liste: champListe,
  jours: champJours,
  canaux: champCanaux,
  fenetres: champFenetres,
  nombres: champNombres,
  paire: champPaire,
  texte: champTexte,
};

export function champPolicy(chemin, val) {
  const spec = specDe(chemin, val);
  const fabrique = FABRIQUES[spec.widget] || champTexte;
  return fabrique(chemin, spec, val);
}

export function feuillesPolicy(pol) {
  const plats = [];
  for (const [secNom, secVal] of Object.entries(pol)) {
    if (secNom === 'schema_version' || typeof secVal !== 'object') {
      continue;
    }
    aplatir(secVal, secNom, plats);
  }
  return plats;
}

export function grouperFeuilles(plats) {
  const groupes = new Map();
  for (const [chemin, val] of plats) {
    const sec = chemin.split('.')[0];
    if (!groupes.has(sec)) {
      groupes.set(sec, []);
    }
    groupes.get(sec).push([chemin, val]);
  }
  const ordre = Object.keys(SECTIONS);
  const cles = [...groupes.keys()].sort((a, b) => {
    const ia = ordre.indexOf(a);
    const ib = ordre.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  return cles.map((id) => ({
    id,
    titre: (SECTIONS[id] && SECTIONS[id].titre) || id,
    pourquoi: (SECTIONS[id] && SECTIONS[id].pourquoi) || '',
    champs: groupes.get(id),
  }));
}

export function lirePolicy(conteneur, base) {
  const out = structuredClone(base);
  conteneur.querySelectorAll('.champ-policy').forEach((node) => {
    if (typeof node._lire === 'function') {
      poser(out, node.dataset.chemin, node._lire());
    }
  });
  return out;
}
