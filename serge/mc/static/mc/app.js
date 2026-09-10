// MC lot 1b : boot → store → patch + stream temps réel (ou snapshot).
import {createStore} from './store.js';
import {connectStream} from './sse.js';
import {patchSection} from './patch.js';

const store = createStore();
const stats = {applied: 0, skipped: 0, mode: 'boot'};
window.__MC = {stats};

function apply(section, sig, payload) {
  const result = store.apply(section, sig, payload);
  if (result === 'updated') {
    patchSection(document, section, sig, payload);
    stats.applied += 1;
  } else {
    stats.skipped += 1;
  }
}

const bootTag = document.getElementById('serge-boot');
if (bootTag) {
  const boot = JSON.parse(bootTag.textContent);
  for (const [section, env] of Object.entries(boot.sections || {})) {
    apply(section, env.sig, env.payload);
  }
}

// Lot 1b : page unique p0 (le routeur multi-pages arrive au lot 2).
connectStream({
  page: 'p0',
  onEvent: (env) => apply(env.section, env.sig, env.payload),
  onStatus: (mode) => {
    stats.mode = mode;
  },
});

const target = document.getElementById('health');
try {
  const response = await fetch('/healthz', {cache: 'no-store'});
  const data = await response.json();
  target.textContent =
    data.status === 'ok' ? 'Serveur : en ligne' : 'Serveur : ?';
} catch {
  target.textContent = 'Serveur : injoignable';
}
