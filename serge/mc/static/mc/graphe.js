// Carte Serge : nœuds HTML, arêtes canvas, scrubber, suivre l’euro, typewriter.
import {icone} from './icones.js';
import {TYPES_OBJET, allerObjet, verbe} from './libelles.js';

const EPINE_X = {
  ecoute: 0.08,
  hypothese: 0.22,
  test: 0.38,
  qualif: 0.52,
  conversation: 0.66,
  intent: 0.80,
  caisse: 0.93,
  memoire: 0.18,
  policy: 0.42,
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

function place(el, x, y) {
  el.style.left = `${x * 100}%`;
  el.style.top = `${y * 100}%`;
}

function ouvrirCible(item, lignage) {
  const objet = item.objet;
  if (objet && TYPES_OBJET[objet.type] && objet.id) {
    allerObjet(objet.type, objet.id);
    return;
  }
  if (item.cible && item.cible.type && item.cible.id) {
    allerObjet(item.cible.type, item.cible.id);
    return;
  }
  if (item.id === 'stripe') {
    const facture = (lignage || []).find((x) => x && x.type === 'facture');
    if (facture) {
      allerObjet(facture.type, facture.id);
    }
  }
}

function boutonNoeud(item, classe, x, y, lignage) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = `noeud ${classe}`;
  btn.dataset.id = item.id;
  if (item.tier) {
    btn.dataset.tier = item.tier;
  }
  if (item.chaud) {
    btn.dataset.chaud = '1';
  }
  const ic = icone(classe === 'llm' ? 'llm' : item.id, classe === 'llm' ? 12 : 16);
  const titre = item.titre || item.id.replace(/_/g, ' ');
  btn.title = titre;
  if (classe !== 'llm' || item.chaud) {
    const span = document.createElement('span');
    span.textContent = titre;
    btn.append(ic, span);
  } else {
    btn.append(ic);
    btn.classList.add('point');
  }
  place(btn, x, y);
  btn.addEventListener('click', () => ouvrirCible(item, lignage));
  return btn;
}

function tip(host, texte, x, y) {
  const node = document.createElement('div');
  node.className = 'tip-noeud';
  node.textContent = texte;
  place(node, x, y + 0.08);
  host.append(node);
  return node;
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

export function dessineAretes(canvas, flux, t, euroIds) {
  const ctx = canvas.getContext('2d');
  const {width, height} = canvas;
  ctx.clearRect(0, 0, width, height);
  const midY = height * 0.52;
  flux.forEach((f, i) => {
    const x0 = (EPINE_X[f.de] || 0.1) * width;
    const x1 = (EPINE_X[f.vers] || 0.9) * width;
    const chaud = euroIds && (euroIds.has(f.de) || euroIds.has(f.vers));
    const couleur = chaud ? '#f0c45a' : '#35e0ff';
    ligne(ctx, x0, midY, x1, midY, couleur, chaud ? 3 : 1.6, 0.25 + Math.min(0.55, (f.debit || 0) / 20));
    const phase = ((t / 800 + i * 0.2) % 1);
    const px = x0 + (x1 - x0) * phase;
    ctx.beginPath();
    ctx.arc(px, midY, chaud ? 4 : 2.5, 0, Math.PI * 2);
    ctx.fillStyle = couleur;
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
    const chaud = euroIds && (euroIds.has(id) || euroIds.has(cible));
    ligne(ctx, x0, y0, x1, y1, chaud ? '#f0c45a' : '#58a6ff', 1, chaud ? 0.45 : 0.12);
    const phase = ((t / 1400 + i * 0.13) % 1);
    ctx.beginPath();
    ctx.arc(x0 + (x1 - x0) * phase, y0 + (y1 - y0) * phase, 1.8, 0, Math.PI * 2);
    ctx.fillStyle = chaud ? '#f0c45a' : '#58a6ff';
    ctx.globalAlpha = 0.7;
    ctx.fill();
    ctx.globalAlpha = 1;
  });
}

export function monterGraphe(main, getPayload, stoppers) {
  const canvas = main.querySelector('[data-hud="carte"]');
  const host = main.querySelector('[data-graphe="noeuds"]');
  const tw = main.querySelector('[data-typewriter]');
  const scrub = main.querySelector('[data-scrubber]');
  const btnEuro = main.querySelector('[data-euro]');
  let euroOn = false;
  let tipNode = null;

  function payload() {
    const data = getPayload();
    return data || {epine: [], orbites: [], llm: [], flux: [], blocages: [], io: null};
  }

  function idsEuro(p) {
    const ids = new Set();
    if (!euroOn) {
      return ids;
    }
    ['intent', 'caisse', 'stripe'].forEach((id) => ids.add(id));
    (p.epine || []).forEach((n) => {
      if (n.argent) {
        ids.add(n.id);
      }
    });
    return ids;
  }

  function renderNoeuds() {
    const p = payload();
    host.replaceChildren();
    const bloques = new Set((p.blocages || []).map((b) => b.noeud));
    const euros = idsEuro(p);
    (p.epine || []).forEach((n) => {
      const btn = boutonNoeud(n, '', EPINE_X[n.id] || 0.5, 0.52, p.lignage);
      if (bloques.has(n.id)) {
        btn.dataset.bloque = '1';
      }
      if (euros.has(n.id)) {
        btn.dataset.euro = '1';
      }
      btn.addEventListener('mouseenter', () => {
        if (tipNode) {
          tipNode.remove();
        }
        tipNode = tip(
          host,
          `${n.pourquoi || ''} ${n.argent || ''}`,
          EPINE_X[n.id] || 0.5,
          0.52,
        );
      });
      btn.addEventListener('mouseleave', () => {
        if (tipNode) {
          tipNode.remove();
          tipNode = null;
        }
      });
      host.append(btn);
    });
    (p.orbites || []).forEach((n) => {
      const xy = ORBITE_POS[n.id] || [0.5, 0.2];
      const btn = boutonNoeud(n, 'orbite', xy[0], xy[1], p.lignage);
      if (euros.has(n.id)) {
        btn.dataset.euro = '1';
      }
      if (n.id === 'mail') {
        btn.addEventListener('click', () => {
          location.hash = '#/live';
        });
      }
      if (n.id === 'memoire') {
        btn.addEventListener('click', () => {
          location.hash = '#/memory';
        });
      }
      if (n.id === 'policy') {
        btn.addEventListener('click', () => {
          location.hash = '#/policy';
        });
      }
      if (n.id === 'voix') {
        btn.addEventListener('click', () => {
          location.hash = '#/voice';
        });
      }
      if (n.id === 'discord') {
        btn.addEventListener('click', () => {
          location.hash = '#/tickets';
        });
      }
      if (n.id === 'scheduler') {
        btn.addEventListener('click', () => {
          location.hash = '#/health';
        });
      }
      host.append(btn);
    });
    const parEtape = {};
    (p.llm || []).forEach((n) => {
      const et = n.etape || 'test';
      parEtape[et] = parEtape[et] || [];
      parEtape[et].push(n);
    });
    Object.entries(parEtape).forEach(([et, liste]) => {
      liste.forEach((n, i) => {
        const pas = host.clientWidth < 720 ? 0.016 : 0.02;
        const x = (EPINE_X[et] || 0.5) + (i - (liste.length - 1) / 2) * pas;
        const y = n.chaud ? 0.33 : 0.38;
        const btn = boutonNoeud(n, 'llm', x, y, p.lignage);
        btn.addEventListener('mouseenter', () => {
          if (tipNode) {
            tipNode.remove();
          }
          tipNode = tip(host, n.chaud ? 'Travaille maintenant.' : 'En attente.', x, y);
        });
        btn.addEventListener('mouseleave', () => {
          if (tipNode) {
            tipNode.remove();
            tipNode = null;
          }
        });
        host.append(btn);
      });
    });
  }

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
    dessineAretes(canvas, p.flux || [], t, idsEuro(p));
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
    dessineAretes(canvas, payload().flux || [], 0, new Set());
  } else {
    frame = requestAnimationFrame(loop);
  }

  if (btnEuro) {
    btnEuro.addEventListener('click', () => {
      euroOn = !euroOn;
      btnEuro.textContent = euroOn ? 'Masquer la lignée' : 'Suivre l’euro';
      renderNoeuds();
    });
  }
  if (scrub) {
    scrub.addEventListener('input', () => {
      const p = payload();
      const items = p.timeline || [];
      const idx = Math.floor(((Number(scrub.value) || 100) / 100) * Math.max(0, items.length - 1));
      const ev = items[items.length - 1 - idx];
      if (ev && tw) {
        tw.textContent = verbe(ev.kind);
      }
    });
  }

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
  });
  return renderNoeuds;
}

export {verbe};
