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

export function startNoyau(canvas, getEtat) {
  const ctx = canvas.getContext('2d');
  const statique = mouvementReduit();
  let actif = true;
  boucles += 1;
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
  function frame(t) {
    if (!actif) {
      return;
    }
    dessin(t);
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
