// Contrôles Policy : curseur, liste, choix multiples, plages, nombres.
// Chaque réglage arrive décrit par la base (spec) : titre, aide, sorte
// (widget), bornes (min, max, pas) et choix. Aucun catalogue ici.

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

function champListe(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const sel = el('select', 'select-policy');
  const choix = [...(spec.choix || [])];
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

// Plusieurs choix parmi ceux du réglage (canaux, jours) : chaque choix est
// [valeur, libellé] ; on montre le libellé, on lit la valeur.
function champChoix(chemin, spec, val) {
  const wrap = cadre(chemin, spec);
  const pris = new Set(Array.isArray(val) ? val : []);
  const grille = el('div', 'jours-policy');
  const cases = [];
  for (const [id, lib] of spec.choix || []) {
    const lab = el('label', 'puce-choix');
    const box = el('input');
    box.type = 'checkbox';
    box.checked = pris.has(id);
    box.dataset.choix = id;
    lab.append(box, el('span', '', lib));
    grille.append(lab);
    cases.push(box);
  }
  wrap.append(grille);
  wrap._lire = () => cases.filter((c) => c.checked).map((c) => c.dataset.choix);
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

const FABRIQUES = {
  eur: (c, s, v) => champCurseur(c, s, v, fmtEur),
  pct: (c, s, v) => champCurseur(c, s, v, fmtPct),
  curseur: (c, s, v) => champCurseur(c, s, v, fmtBrut),
  heure: (c, s, v) => champCurseur(c, s, v, fmtHeure),
  nombre: champNombre,
  liste: champListe,
  jours: champChoix,
  canaux: champChoix,
  fenetres: champFenetres,
  nombres: champNombres,
};

// Le champ d'un réglage ; il lit sa valeur avec node._lire().
export function champPolicy(chemin, spec, val) {
  const fabrique = FABRIQUES[spec.widget] || champNombre;
  const node = fabrique(chemin, spec, val);
  node.querySelectorAll('input,select,textarea').forEach((field, i) => {
    field.setAttribute('aria-label', `${spec.titre}${i ? ` · ${i + 1}` : ''}`);
  });
  return node;
}

// Une valeur en clair, comme dans son champ : « 50 € », « 25 % »,
// « 23:00 → 08:00 », « Voix, SMS ».
export function formatValeur(spec, val) {
  if (spec.widget === 'eur') {
    return fmtEur(val);
  }
  if (spec.widget === 'pct') {
    return fmtPct(val);
  }
  if (spec.widget === 'heure') {
    return fmtHeure(val);
  }
  if (spec.widget === 'fenetres' && Array.isArray(val)) {
    return val.map(([h1, m1, h2, m2]) => `${versHeure(h1, m1)} → ${versHeure(h2, m2)}`).join(', ');
  }
  if (Array.isArray(val)) {
    const libelles = new Map((spec.choix || []).filter(Array.isArray));
    return val.map((v) => libelles.get(v) || String(v)).join(', ') || '(aucun)';
  }
  return String(val);
}
