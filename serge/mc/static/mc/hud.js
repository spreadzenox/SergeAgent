// HUD canvas : boucle rAF unique, valeurs cibles (jamais piloté par tick).
const ETATS = {
  calme: {couleur: '#58a6ff', pulsation: 0.4},
  travail: {couleur: '#35e0ff', pulsation: 1.0},
  urgent: {couleur: '#ff9a3c', pulsation: 2.2},
  erreur: {couleur: '#ff7b72', pulsation: 2.2},
};

export function etatSysteme({urgents, running, echecRecent}) {
  if (echecRecent) {
    return 'erreur';
  }
  if (urgents > 0) {
    return 'urgent';
  }
  if (running) {
    return 'travail';
  }
  return 'calme';
}

export function noyauParams(etat, t) {
  const base = ETATS[etat] || ETATS.calme;
  const phase = (t / 1000) * base.pulsation * Math.PI * 2;
  return {
    couleur: base.couleur,
    rayon: 0.5 + 0.08 * Math.sin(phase),
    anneau: ((t / 1000) * base.pulsation) % 1,
  };
}

function mouvementReduit() {
  return (
    typeof matchMedia === 'function' &&
    matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

let boucles = 0;

export function hudActives() {
  return boucles;
}

function boucle(dessiner) {
  const statique = mouvementReduit();
  let actif = true;
  boucles += 1;
  function frame(t) {
    if (!actif) {
      return;
    }
    dessiner(t);
    if (!statique) {
      requestAnimationFrame(frame);
    }
  }
  requestAnimationFrame(frame);
  return {
    stop() {
      if (actif) {
        actif = false;
        boucles -= 1;
      }
    },
  };
}

export function startNoyau(canvas, getEtat) {
  const ctx = canvas.getContext('2d');
  function dessin(t) {
    const box = canvas.width;
    const centre = box / 2;
    const params = noyauParams(getEtat(), t);
    ctx.clearRect(0, 0, box, box);
    ctx.beginPath();
    ctx.arc(
      centre,
      centre,
      centre * 0.55 * (0.5 + params.rayon),
      0,
      Math.PI * 2,
    );
    ctx.fillStyle = params.couleur;
    ctx.globalAlpha = 0.85;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.beginPath();
    ctx.arc(centre, centre, centre * 0.8, 0, Math.PI * 2);
    ctx.strokeStyle = params.couleur;
    ctx.globalAlpha = 0.35;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  return boucle(dessin);
}

const COULEURS_SANTE = {
  ok: '#3fb950',
  degrade: '#ff9a3c',
  erreur: '#ff7b72',
  inconnu: '#8b949e',
};

export function dispositionIlots(n, largeur, hauteur) {
  const cols = 4;
  const lignes = Math.ceil(n / cols);
  const pos = [];
  for (let i = 0; i < n; i += 1) {
    pos.push({
      x: ((i % cols + 0.5) / cols) * largeur,
      y: ((Math.floor(i / cols) + 0.5) / lignes) * hauteur,
    });
  }
  return pos;
}

export function startIlots(canvas, getEtat) {
  const ctx = canvas.getContext('2d');
  function dessin(t) {
    const {items, choisi} = getEtat();
    const {width, height} = canvas;
    const pos = dispositionIlots(items.length, width, height);
    ctx.clearRect(0, 0, width, height);
    ctx.textAlign = 'center';
    ctx.font = '11px system-ui, sans-serif';
    items.forEach((ilot, i) => {
      const rayon = 26 + (ilot.activite || 0) * 14;
      const pulse = 1 + 0.06 * Math.sin(t / 350 + i * 0.7);
      const couleur = COULEURS_SANTE[ilot.sante] || COULEURS_SANTE.inconnu;
      ctx.beginPath();
      ctx.arc(pos[i].x, pos[i].y, (rayon + 10) * pulse, 0, Math.PI * 2);
      ctx.fillStyle = couleur;
      ctx.globalAlpha = 0.16;
      ctx.fill();
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(pos[i].x, pos[i].y, rayon, 0, Math.PI * 2);
      ctx.fillStyle = '#0d1117';
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = couleur;
      ctx.stroke();
      if (ilot.id === choisi) {
        ctx.beginPath();
        ctx.arc(pos[i].x, pos[i].y, rayon + 4, 0, Math.PI * 2);
        ctx.strokeStyle = '#e6edf3';
        ctx.stroke();
      }
      ctx.fillStyle = '#e6edf3';
      ctx.fillText(ilot.label, pos[i].x, pos[i].y + rayon + 14);
    });
  }
  return boucle(dessin);
}

export function densite24h(items, nowMs) {
  const series = new Array(24).fill(0);
  for (const item of items) {
    const t = Date.parse(item.ts);
    if (Number.isNaN(t)) {
      continue;
    }
    const ageH = Math.floor((nowMs - t) / 3600000);
    if (ageH >= 0 && ageH < 24) {
      series[23 - ageH] += 1;
    }
  }
  return series;
}

export function dessineWaveform(canvas, series) {
  const ctx = canvas.getContext('2d');
  const {width, height} = canvas;
  ctx.clearRect(0, 0, width, height);
  const max = Math.max(1, ...series);
  const step = width / Math.max(1, series.length - 1);
  ctx.beginPath();
  series.forEach((value, index) => {
    const x = index * step;
    const y = height - (value / max) * height;
    if (index === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.strokeStyle = '#35e0ff';
  ctx.lineWidth = 1.5;
  ctx.stroke();
}

const tweens = new WeakMap();

export function tweenNumber(el, from, to, {format, duration = 400} = {}) {
  const fmt = format || ((v) => String(Math.round(v)));
  const prec = tweens.get(el);
  if (prec) {
    cancelAnimationFrame(prec);
  }
  const debut = performance.now();
  function tick(t) {
    const ratio = Math.min(1, (t - debut) / duration);
    el.textContent = fmt(from + (to - from) * ratio);
    if (ratio < 1) {
      tweens.set(el, requestAnimationFrame(tick));
    } else {
      tweens.delete(el);
    }
  }
  tweens.set(el, requestAnimationFrame(tick));
}
