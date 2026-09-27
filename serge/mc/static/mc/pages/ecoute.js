// Page Écoute : cycle manuel, paramètres DB et permissions des trois agents.
import {toast} from '../components.js';
import {fetchState} from '../sse.js';

async function poster(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return {ok: response.ok, data: await response.json()};
}

function afficher(main, payload, sig) {
  const settings = payload.settings || {};
  const cycle = payload.cycle;
  main.querySelector('[data-ecoute="besoins"]').textContent =
    `Besoins par découverte : ${settings.discovery_needs_target || '—'}`;
  main.querySelector('[data-ecoute="business"]').textContent =
    `Business pour le prochain POC : ${settings.poc_business_target || '—'}`;
  main.querySelector('[data-ecoute="guide"]').value = cycle ? (cycle.guide || '') : '';
  main.querySelector('[data-ecoute="cycle"]').textContent = cycle
    ? `Cycle ${cycle.id} : ${cycle.status} (${cycle.needs_target} besoins, ${cycle.business_target} POC)`
    : 'Aucun cycle.';
  const agents = main.querySelector('[data-ecoute="agents"]');
  agents.replaceChildren(...(payload.agents || []).map((agent) => {
    const item = document.createElement('li');
    const readers = (agent.readers || []).filter((reader) => reader.enabled).map((reader) => reader.id).join(', ');
    item.textContent = `${agent.id} : ${readers || 'aucun lecteur'}`;
    return item;
  }));
  const candidates = main.querySelector('[data-ecoute="candidates"]');
  candidates.replaceChildren(...(payload.candidates || []).map((candidate) => {
    const item = document.createElement('li');
    item.textContent = `${candidate.title} — ${candidate.status}`;
    return item;
  }));
  main.querySelector('[data-section="ecoute"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-ecoute');
  main.replaceChildren(tpl.content.cloneNode(true));
  main.querySelector('[data-ecoute-action="lancer"]').addEventListener('click', async () => {
    const guide = main.querySelector('[data-ecoute="guide"]').value;
    const result = await poster('/owner/api/listen/start', {guide});
    toast(document.body, result.ok ? 'Cycle placé dans la file.' : (result.data.erreur || 'Refusé.'), result.ok ? 'succes' : 'erreur');
    if (result.ok) {
      await rafraichir(store);
    }
  });
  const unsubscribe = store.subscribe('ecoute', (payload, sig) => afficher(main, payload, sig));
  for (const [section, env] of store.all()) {
    if (section === 'ecoute') {
      afficher(main, env.payload, env.sig);
    }
  }
  return unsubscribe;
}

async function rafraichir(store) {
  try {
    const data = await fetchState('p10');
    for (const [section, env] of Object.entries(data.sections || {})) {
      store.apply(section, env.sig, env.payload);
    }
  } catch {
    // Le flux SSE reprend l'état au prochain tick.
  }
}