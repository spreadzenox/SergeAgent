// Pictogrammes SVG (createElementNS — jamais innerHTML).
const NS = 'http://www.w3.org/2000/svg';

function svg(taille) {
  const node = document.createElementNS(NS, 'svg');
  node.setAttribute('viewBox', '0 0 24 24');
  node.setAttribute('width', String(taille));
  node.setAttribute('height', String(taille));
  node.setAttribute('aria-hidden', 'true');
  node.classList.add('icone');
  return node;
}

function trait(d, stroke = 'currentColor') {
  const p = document.createElementNS(NS, 'path');
  p.setAttribute('d', d);
  p.setAttribute('fill', 'none');
  p.setAttribute('stroke', stroke);
  p.setAttribute('stroke-width', '1.6');
  p.setAttribute('stroke-linecap', 'round');
  p.setAttribute('stroke-linejoin', 'round');
  return p;
}

function plein(d, fill = 'currentColor') {
  const p = document.createElementNS(NS, 'path');
  p.setAttribute('d', d);
  p.setAttribute('fill', fill);
  return p;
}

const DESSINS = {
  ecoute: 'M4 12a8 8 0 0 1 16 0M7 12a5 5 0 0 1 10 0M10 12a2 2 0 0 1 4 0M12 16v4',
  hypothese: 'M12 3l2 6h6l-5 4 2 6-5-4-5 4 2-6-5-4h6z',
  test: 'M4 6h16M4 12h16M4 18h10',
  qualif: 'M5 12l4 4 10-10',
  conversation: 'M4 6h16v9H8l-4 4V6z',
  intent: 'M12 3v18M5 10l7-7 7 7',
  caisse: 'M3 8h18v11H3zM8 8V6a4 4 0 0 1 8 0v2',
  sqlite: 'M5 4h14v16H5zM5 9h14M9 9v11',
  scheduler: 'M12 6v6l4 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z',
  mail: 'M3 7l9 6 9-6M3 7h18v10H3z',
  discord: 'M7 8c2-2 8-2 10 0M8 16l-1 3m9-3 1 3M8 12h.01M16 12h.01',
  voix: 'M12 4v8m-4 2a4 4 0 0 0 8 0M8 20h8',
  memoire: 'M6 4h12v16H6zM9 8h6M9 12h6M9 16h3',
  policy: 'M12 3l8 4v6c0 5-3.5 7-8 8-4.5-1-8-3-8-8V7z',
  stripe: 'M6 8h12M6 12h12M6 16h8',
  llm: 'M12 3a4 4 0 0 1 4 4c2 0 3 2 3 4s-1 4-3 4a4 4 0 0 1-8 0c-2 0-3-2-3-4s1-4 3-4a4 4 0 0 1 4-4z',
};

export function icone(nom, taille = 18) {
  const node = svg(taille);
  const d = DESSINS[nom] || DESSINS.llm;
  node.append(trait(d));
  if (nom === 'hypothese') {
    node.append(plein('M12 10l.8 2.2H15l-1.8 1.4.7 2.2L12 14.6 10.1 16l.7-2.2L9 12.2h2.2z', 'currentColor'));
  }
  return node;
}
