// Carte Serge : nœuds HTML, arêtes canvas, panneau d’étape.
import {icone} from './icones.js';
import {TYPES_OBJET, allerObjet} from './libelles.js';

const EPINE_X = {
  ecoute: 0.08,
  hypothese: 0.22,
  test: 0.38,
  qualif: 0.52,
  conversation: 0.66,
  intent: 0.80,
  caisse: 0.93,
};

const ORBITE_POS = {
  sqlite: [0.12, 0.18],
  scheduler: [0.30, 0.16],
  mail: [0.50, 0.14],
  discord: [0.68, 0.16],
  voix: [0.86, 0.20],
  memoire: [0.14, 0.86],
  policy: [0.40, 0.88],
  stripe: [0.88, 0.84],
};

const ORBITE_LIEN = {
  sqlite: 'ecoute',
  scheduler: 'hypothese',
  mail: 'conversation',
  discord: 'conversation',
  voix: 'conversation',
  memoire: 'ecoute',
  policy: 'qualif',
  stripe: 'caisse',
};

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

function place(node, x, y) {
  node.style.left = `${x * 100}%`;
  node.style.top = `${y * 100}%`;
}

function ouvrirCible(item) {
  const objet = item.objet;
  if (objet && TYPES_OBJET[objet.type] && objet.id) {
    allerObjet(objet.type, objet.id);
  }
}

function boutonNoeud(item, classe, x, y) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `noeud ${classe}`;
  btn.dataset.id = item.id;
  const ic = icone(item.id, 16);
  const titre = item.titre || item.id.replace(/_/g, ' ');
  const span = document.createElement('span');
  span.textContent = titre;
  btn.append(ic, span);
  place(btn, x, y);
  btn.addEventListener('click', () => ouvrirCible(item));
  return btn;
}

function ligneJugement(j) {
  const li = el('li');
  const btn = el('button', 'clic-ligne');
  btn.type = 'button';
  if (j.chaud) {
    btn.dataset.chaud = '1';
  }
  const rang = j.ordre && j.rang ? `${j.rang}. ` : '';
  btn.append(el('strong', '', `${rang}${j.titre || j.id}`));
  if (j.detail) {
    btn.append(el('span', 'detail-jugement', j.detail));
  }
  btn.addEventListener('click', () => allerObjet('llm', j.id));
  li.append(btn);
  return li;
}

function remplirPanneau(box, etape, verrouille, onUnlock) {
  box.replaceChildren();
  box.hidden = false;
  box.dataset.etape = etape.id;
  if (verrouille) {
    box.dataset.lock = '1';
  } else {
    delete box.dataset.lock;
  }
  box.append(el('p', 'titre-panneau', etape.titre || etape.id));
  const desc = `${etape.pourquoi || ''} ${etape.argent || ''}`.trim();
  if (desc) {
    box.append(el('p', 'texte-panneau', desc));
  }
  const jugs = etape.jugements || [];
  const ordres = jugs.filter((j) => j.ordre);
  const restes = jugs.filter((j) => !j.ordre);
  if (ordres.length) {
    box.append(el('h3', '', 'Jugements, dans l’ordre'));
    const ol = el('ol', 'liste-jugements');
    ordres.forEach((j) => ol.append(ligneJugement(j)));
    box.append(ol);
  }
  if (restes.length) {
    box.append(el('h3', '', 'Autres jugements (pas d’ordre fixe)'));
    const ul = el('ul', 'liste-jugements');
    restes.forEach((j) => ul.append(ligneJugement(j)));
    box.append(ul);
  }
  if (!jugs.length) {
    box.append(
      el('p', 'texte-panneau', 'Aucun jugement ici — surtout des règles et de l’encaissement.'),
    );
  }
  const actions = el('div', 'actions-panneau');
  const plus = el('button', 'clic-ligne', 'Plus de détails sur cette étape');
  plus.type = 'button';
  plus.addEventListener('click', () => allerObjet('etape', etape.id));
  actions.append(plus);
  if (verrouille) {
    const fermer = el('button', 'clic-ligne', 'Refermer');
    fermer.type = 'button';
    fermer.addEventListener('click', onUnlock);
    actions.append(fermer);
  }
  box.append(actions);
}

function ligne(ctx, x0, y0, x1, y1, couleur, largeur, alpha) {
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.strokeStyle = couleur;
  ctx.globalAlpha = alpha;
  ctx.lineWidth = largeur;
  ctx.stroke();
  ctx.globalAlpha = 1;
}

export function dessineAretes(canvas, flux, t) {
  const ctx = canvas.getContext('2d');
  const {width, height} = canvas;
  ctx.clearRect(0, 0, width, height);
  const midY = height * 0.52;
  flux.forEach((f, i) => {
    const x0 = (EPINE_X[f.de] || 0.1) * width;
    const x1 = (EPINE_X[f.vers] || 0.9) * width;
    ligne(ctx, x0, midY, x1, midY, '#35e0ff', 1.6, 0.25 + Math.min(0.55, (f.debit || 0) / 20));
    const phase = (t / 800 + i * 0.2) % 1;
    const px = x0 + (x1 - x0) * phase;
    ctx.beginPath();
    ctx.arc(px, midY, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = '#35e0ff';
    ctx.globalAlpha = 0.9;
    ctx.fill();
    ctx.globalAlpha = 1;
  });
  Object.entries(ORBITE_POS).forEach(([id, xy], i) => {
    const cible = ORBITE_LIEN[id];
    const x0 = xy[0] * width;
    const y0 = xy[1] * height;
    const x1 = (EPINE_X[cible] || 0.5) * width;
    const y1 = midY;
    ligne(ctx, x0, y0, x1, y1, '#58a6ff', 1, 0.12);
    const phase = (t / 1400 + i * 0.13) % 1;
    ctx.beginPath();
    ctx.arc(x0 + (x1 - x0) * phase, y0 + (y1 - y0) * phase, 1.8, 0, Math.PI * 2);
    ctx.fillStyle = '#58a6ff';
    ctx.globalAlpha = 0.7;
    ctx.fill();
    ctx.globalAlpha = 1;
  });
}

export function monterGraphe(main, getPayload, stoppers) {
  const canvas = main.querySelector('[data-hud="carte"]');
  const host = main.querySelector('[data-graphe="noeuds"]');
  const tw = main.querySelector('[data-typewriter]');
  let lockId = '';
  let hideTimer = 0;
  let panneau = main.querySelector('[data-panneau-etape]');
  if (!panneau) {
    panneau = el('div', 'panneau-etape');
    panneau.hidden = true;
    panneau.setAttribute('data-panneau-etape', '');
    canvas.parentElement.after(panneau);
  }

  function payload() {
    const data = getPayload();
    return data || {epine: [], orbites: [], llm: [], flux: [], blocages: [], io: null};
  }

  function unlock() {
    lockId = '';
    panneau.hidden = true;
    delete panneau.dataset.lock;
    host.querySelectorAll('.noeud.actif').forEach((n) => n.classList.remove('actif'));
  }

  function montrer(etape, verrouille) {
    remplirPanneau(panneau, etape, verrouille, unlock);
  }

  function renderNoeuds() {
    const p = payload();
    host.replaceChildren();
    const bloques = new Set((p.blocages || []).map((b) => b.noeud));
    (p.epine || []).forEach((n) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'noeud';
      btn.dataset.id = n.id;
      const ic = icone(n.id, 16);
      const span = document.createElement('span');
      span.textContent = n.titre || n.id;
      btn.append(ic, span);
      const nJ = (n.jugements || []).length;
      if (nJ) {
        const badge = el('span', 'compte-llm', String(nJ));
        btn.append(badge);
        const mot = nJ === 1 ? 'jugement' : 'jugements';
        btn.setAttribute('aria-label', `${n.titre || n.id} — ${nJ} ${mot}`);
      }
      if ((n.jugements || []).some((j) => j.chaud)) {
        btn.dataset.chaud = '1';
      }
      if (bloques.has(n.id)) {
        btn.dataset.bloque = '1';
      }
      if (lockId === n.id) {
        btn.classList.add('actif');
      }
      place(btn, EPINE_X[n.id] || 0.5, 0.52);
      btn.addEventListener('mouseenter', () => {
        window.clearTimeout(hideTimer);
        if (!lockId) {
          montrer(n, false);
        }
      });
      btn.addEventListener('mouseleave', () => {
        if (lockId) {
          return;
        }
        hideTimer = window.setTimeout(() => {
          if (!lockId && !panneau.matches(':hover')) {
            panneau.hidden = true;
          }
        }, 220);
      });
      btn.addEventListener('click', (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        lockId = n.id;
        host.querySelectorAll('.noeud.actif').forEach((x) => x.classList.remove('actif'));
        btn.classList.add('actif');
        montrer(n, true);
      });
      host.append(btn);
    });
    (p.orbites || []).forEach((n) => {
      const xy = ORBITE_POS[n.id] || [0.5, 0.2];
      const btn = boutonNoeud(n, 'orbite', xy[0], xy[1]);
      const hash = {
        mail: '#/live',
        memoire: '#/memory',
        policy: '#/policy',
        voix: '#/voice',
        discord: '#/tickets',
        scheduler: '#/health',
        stripe: '#/economy',
      };
      if (hash[n.id]) {
        btn.addEventListener('click', () => {
          location.hash = hash[n.id];
        });
      }
      host.append(btn);
    });
  }

  panneau.addEventListener('mouseenter', () => window.clearTimeout(hideTimer));
  panneau.addEventListener('mouseleave', () => {
    if (!lockId) {
      panneau.hidden = true;
    }
  });

  function syncCanvas() {
    const box = canvas.parentElement.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    const w = Math.max(480, Math.round(box.width * ratio));
    const h = Math.max(220, Math.round(box.height * ratio));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
  }

  let frame = 0;
  let stop = false;
  function loop(t) {
    if (stop) {
      return;
    }
    syncCanvas();
    const p = payload();
    dessineAretes(canvas, p.flux || [], t);
    if (tw && p.io && p.io.sortie) {
      const full = String(p.io.sortie);
      const n = Math.min(full.length, 8 + Math.floor(t / 40));
      if (tw.textContent.length < n) {
        tw.textContent = full.slice(0, n);
      }
    }
    frame = requestAnimationFrame(loop);
  }
  if (typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches) {
    dessineAretes(canvas, payload().flux || [], 0);
  } else {
    frame = requestAnimationFrame(loop);
  }

  const onDoc = (ev) => {
    if (!lockId) {
      return;
    }
    if (panneau.contains(ev.target) || host.contains(ev.target)) {
      return;
    }
    unlock();
  };
  document.addEventListener('click', onDoc);

  renderNoeuds();
  const onResize = () => {
    syncCanvas();
    renderNoeuds();
  };
  window.addEventListener('resize', onResize);
  stoppers.push(() => {
    stop = true;
    cancelAnimationFrame(frame);
    window.removeEventListener('resize', onResize);
    document.removeEventListener('click', onDoc);
  });
  return renderNoeuds;
}
