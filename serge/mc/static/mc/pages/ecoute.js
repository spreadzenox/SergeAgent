// Page Écoute : les boutons de l’étape 1 (déclencheurs en base), cycle, candidats.
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

// Un bloc par déclencheur « bouton » : ses champs, puis son bouton.
function afficherBoutons(conteneur, boutons) {
  const cle = JSON.stringify(boutons.map((b) => [b.id, b.titre, b.champs]));
  if (conteneur.dataset.cle === cle) {
    return;  // ne pas effacer ce qui est en train d’être tapé
  }
  conteneur.dataset.cle = cle;
  if (!boutons.length) {
    conteneur.replaceChildren(el(
      'p',
      '',
      'Aucun bouton en base pour cette étape : il sera ajouté au pipeline de départ.',
    ));
    return;
  }
  conteneur.replaceChildren(...boutons.map((bouton) => {
    const bloc = el('div', 'grille-champs');
    for (const champ of bouton.champs || []) {
      const label = el('label', 'champ-large', `${champ} `);
      const zone = el('textarea');
      zone.maxLength = 4000;
      zone.dataset.champ = champ;
      label.append(zone);
      bloc.append(label);
    }
    const barre = el('div', 'barre-policy');
    const btn = el('button', 'btn-fort', bouton.titre);
    btn.type = 'button';
    btn.dataset.ecouteAction = 'lancer';
    btn.dataset.trigger = bouton.id;
    barre.append(btn);
    bloc.append(barre, el('p', '', `Lance « ${bouton.invocation_titre} ».`));
    return bloc;
  }));
}

function afficher(main, payload, sig) {
  const cycle = payload.cycle;
  afficherBoutons(
    main.querySelector('[data-ecoute="boutons"]'),
    payload.boutons || [],
  );
  main.querySelector('[data-ecoute="cycle"]').textContent = cycle
    ? `Cycle ${cycle.id} : ${cycle.status} (${cycle.needs_target} besoins, ${cycle.business_target} POC)`
    : 'Aucun cycle.';
  const invocations = main.querySelector('[data-ecoute="invocations"]');
  invocations.replaceChildren(...(payload.invocations || []).map((inv) => {
    const item = document.createElement('li');
    item.textContent = inv.titre;
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
  main.querySelector('[data-ecoute="boutons"]').addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-ecoute-action="lancer"]');
    if (!btn) {
      return;
    }
    const form = {};
    for (const zone of btn.closest('.grille-champs').querySelectorAll('[data-champ]')) {
      form[zone.dataset.champ] = zone.value;
    }
    btn.disabled = true;
    try {
      const result = await poster('/owner/api/bouton', {trigger_id: btn.dataset.trigger, form});
      toast(document.body, result.ok ? 'Tâche placée dans la file.' : (result.data.erreur || 'Refusé.'), result.ok ? 'succes' : 'erreur');
      if (result.ok) {
        await rafraichir(store);
      }
    } finally {
      btn.disabled = false;
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