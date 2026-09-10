// MC lot 2b : boot → store → routeur hash → patch + stream par page.
import {createStore} from './store.js';
import {connectStream} from './sse.js';
import {patchSection} from './patch.js';

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
};
const LABELS = {
  p1: 'Système',
  p2: 'Cerveau',
  p3: 'Décisions',
  p4: 'Mémoire',
  p5: 'Politique',
  p6: 'Économie',
  p7: 'Voix',
  p8: 'Santé',
};

const store = createStore();
const stats = {applied: 0, skipped: 0, mode: 'boot', page: 'p0'};
window.__MC = {stats};

function current() {
  const name = (location.hash || '').replace(/^#\//, '');
  return ROUTES[name] || 'p0';
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

function render() {
  const page = current();
  if (!ROUTES[(location.hash || '').replace(/^#\//, '')]) {
    location.hash = '#/live';
  }
  stats.page = page;
  document.querySelectorAll('.barre-laterale a').forEach((link) => {
    link.classList.toggle('actif', link.dataset.page === page);
  });
  const main = document.getElementById('page');
  if (page === 'p0') {
    main.replaceChildren(template('page-live'));
  } else {
    const node = template('page-bientot');
    node.querySelector('h2').textContent = LABELS[page];
    main.replaceChildren(node);
  }
  for (const [section, env] of store.all()) {
    patchSection(document, section, env.sig, env.payload);
  }
  if (stream) {
    stream.close();
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

const target = document.getElementById('health');
try {
  const response = await fetch('/healthz', {cache: 'no-store'});
  const data = await response.json();
  target.textContent =
    data.status === 'ok' ? 'Serveur : en ligne' : 'Serveur : ?';
} catch {
  target.textContent = 'Serveur : injoignable';
}
