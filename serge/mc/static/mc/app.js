// MC lot 2b : boot → store → routeur hash → patch + stream par page.
import {createStore} from './store.js';
import {connectStream} from './sse.js';
import {patchSection} from './patch.js';
import {initCmdk} from './cmdk.js';

const ROUTES = {
  live: 'p0',
  mind: 'p2',
  tickets: 'p3',
  memory: 'p4',
  policy: 'p5',
  economy: 'p6',
  voice: 'p7',
  health: 'p8',
};
const LABELS = {
  p2: 'Cerveau',
  p3: 'Décisions',
  p4: 'Mémoire',
  p5: 'Policy',
  p6: 'Économie',
  p7: 'Voix',
  p8: 'Health',
};

const store = createStore();
const stats = {applied: 0, skipped: 0, mode: 'boot', page: 'p0'};
window.__MC = {stats};

function current() {
  const raw = (location.hash || '').replace(/^#\//, '');
  if (raw === 'system') {
    location.hash = '#/live';
    return 'p0';
  }
  if (raw.startsWith('objet/')) {
    return 'objet';
  }
  return ROUTES[raw] || 'p0';
}

function template(id) {
  return document.getElementById(id).content.cloneNode(true);
}

function apply(section, sig, payload) {
  const result = store.apply(section, sig, payload);
  if (result === 'updated') {
    patchSection(document, section, sig, payload);
    stats.applied += 1;
  } else {
    stats.skipped += 1;
  }
}

let stream = null;
let unmount = null;
let generation = 0;

async function render() {
  const mine = ++generation;
  const page = current();
  const raw = (location.hash || '').replace(/^#\//, '');
  if (raw === 'system') {
    location.hash = '#/live';
    return;
  }
  if (!raw.startsWith('objet/') && !ROUTES[raw]) {
    location.hash = '#/live';
  }
  stats.page = page;
  document.querySelectorAll('.barre-laterale a').forEach((link) => {
    link.classList.toggle('actif', link.dataset.page === page);
  });
  const main = document.getElementById('page');
  if (unmount) {
    unmount();
    unmount = null;
  }
  if (page === 'objet') {
    const {monterObjet} = await import('./objets.js');
    if (mine !== generation) {
      return;
    }
    const parts = raw.split('/');
    unmount = await monterObjet(main, parts[1], decodeURIComponent(parts[2] || ''));
  } else if (page === 'p0') {
    const {mount} = await import('./pages/live.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p2') {
    const {mount} = await import('./pages/mind.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p3') {
    const {mount} = await import('./pages/tickets.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p4') {
    const {mount} = await import('./pages/memory.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p5') {
    const {mount} = await import('./pages/policy.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p6') {
    const {mount} = await import('./pages/economy.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p7') {
    const {mount} = await import('./pages/voice.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p8') {
    const {mount} = await import('./pages/health.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else {
    const node = template('page-bientot');
    node.querySelector('h2').textContent = LABELS[page];
    main.replaceChildren(node);
  }
  if (stream) {
    stream.close();
    stream = null;
  }
  if (page === 'objet') {
    stats.mode = 'objet';
    return;
  }
  stream = connectStream({
    page,
    onEvent: (env) => apply(env.section, env.sig, env.payload),
    onStatus: (mode) => {
      stats.mode = mode;
    },
  });
}

window.addEventListener('hashchange', render);

const bootTag = document.getElementById('serge-boot');
if (bootTag) {
  const boot = JSON.parse(bootTag.textContent);
  for (const [section, env] of Object.entries(boot.sections || {})) {
    apply(section, env.sig, env.payload);
  }
}
render();
initCmdk(store);

const target = document.getElementById('health');
try {
  const response = await fetch('/healthz', {cache: 'no-store'});
  const data = await response.json();
  target.dataset.etat = data.status === 'ok' ? 'ok' : 'ko';
  target.title = data.status === 'ok' ? 'Connecté' : 'Coupe';
  target.textContent = '';
} catch {
  target.dataset.etat = 'ko';
  target.title = 'Injoignable';
  target.textContent = '';
}
