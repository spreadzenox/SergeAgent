// MC lot 2b : boot → store → routeur hash → patch + stream par page.
import {createStore} from './store.js';
import {connectStream} from './sse.js';
import {patchSection} from './patch.js';
import {initCmdk} from './cmdk.js';

const ROUTES = {
  live: 'p0',
  system: 'p1',
  mind: 'p2',
  tickets: 'p3',
  memory: 'p4',
  policy: 'p5',
  economy: 'p6',
  voice: 'p7',
  health: 'p8',
  identite: 'p9',
  ecoute: 'p10',
  pipeline: 'p11',
};
const store = createStore();
const stats = {applied: 0, skipped: 0, mode: 'boot', page: 'p0'};
window.__MC = {stats};

function current() {
  const raw = (location.hash || '').replace(/^#\//, '');
  if (raw.startsWith('objet/')) {
    return 'objet';
  }
  return ROUTES[raw] || 'p0';
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
  if (!raw.startsWith('objet/') && !ROUTES[raw]) {
    location.hash = '#/live';
  }
  stats.page = page;
  document.querySelectorAll('.barre-laterale a').forEach((link) => {
    link.classList.toggle('actif', link.dataset.page === page);
  });
  const main = document.getElementById('page');
  if (stream) {
    stream.close();
    stream = null;
  }
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
    const cleanup = await monterObjet(main, parts[1], decodeURIComponent(parts[2] || ''), () => mine === generation);
    if (mine !== generation) return;
    unmount = cleanup;
  } else if (page === 'p0') {
    const {mount} = await import('./pages/live.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p1') {
    const {mount} = await import('./pages/system.js');
    if (mine !== generation) return;
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
  } else if (page === 'p9') {
    const {mount} = await import('./pages/identite.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p10') {
    const {mount} = await import('./pages/ecoute.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
  } else if (page === 'p11') {
    const {mount} = await import('./pages/pipeline.js');
    if (mine !== generation) {
      return;
    }
    unmount = mount(main, store);
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
    onEvent: (env) => {
      if (mine === generation) apply(env.section, env.sig, env.payload);
    },
    onStatus: (mode) => {
      if (mine !== generation) return;
      stats.mode = mode;
      const target = document.getElementById('health');
      target.dataset.etat = ['live','poll','snapshot'].includes(mode) ? 'ok' : 'ko';
      target.title = {live: 'Connecté', poll: 'Connecté par actualisation', snapshot: 'Instantané', auth: 'Session expirée — reconnecte-toi', paused: 'Actualisation suspendue'}[mode] || 'Connexion interrompue';
      target.textContent = target.dataset.etat === 'ok' ? '' : target.title;
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
