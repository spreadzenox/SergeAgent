// Page Écoute : les boutons de l’étape 1 (déclencheurs en base), le dernier
// cycle, les business, les flux RSS suivis.
import {confirmModal, toast, draftField, rememberDrafts} from '../components.js';
import {fetchState} from '../sse.js';

async function poster(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  return {ok: response.ok, data: await response.json().catch(() => ({}))};
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

const ETIQUETTES = {
  besoin_nouveau: 'besoin nouveau',
  bruit: 'bruit',
  enrichit: 'enrichit un business',
  preuve: 'preuve d’un business',
};

// Un bloc par déclencheur « bouton » : ses champs, ses conditions, son bouton.
function afficherBoutons(conteneur, boutons) {
  const cle = JSON.stringify(boutons);
  const restore = rememberDrafts(conteneur);
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
    const bloc = el('div', 'grille-champs ecoute-bouton');
    for (const champ of bouton.champs || []) {
      const label = el('label', 'champ-large', `${champ === 'guide' ? 'Texte de guidage' : champ} `);
      const zone = draftField(el('textarea'), `${bouton.id}.${champ}`);
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
    btn.dataset.confirmer = bouton.confirmer || '';
    btn.disabled = Boolean(bouton.refus);
    barre.append(btn);
    bloc.append(barre, el('p', '', `Lance « ${bouton.invocation_titre} ».`));
    for (const condition of bouton.conditions || []) {
      bloc.append(el(
        'p',
        'legende-policy',
        `${condition.texte} : ${condition.occupe} sur ${condition.max}.`,
      ));
    }
    if (bouton.refus) {
      bloc.append(el('p', 'todo-mc', `Pas maintenant : ${bouton.refus}.`));
    }
    return bloc;
  }));
  restore();
}

function afficherCycle(conteneur, cycle) {
  if (!cycle) {
    conteneur.replaceChildren(el('p', '', 'Aucun cycle.'));
    return;
  }
  const dl = el('dl');
  const pages = Object.entries(cycle.pages || {})
    .map(([label, n]) => `${ETIQUETTES[label] || label} : ${n}`)
    .join(' ; ');
  for (const [k, v] of [
    ['Cycle', `${cycle.id} (${cycle.status})`],
    ['Texte de guidage', cycle.guide || '—'],
    ['Pages triées', pages || 'aucune'],
    ['Idées écrites', (cycle.fiches || []).map((f) => `${f.titre} (${f.statut})`).join(' ; ') || 'aucune'],
    ['Note du choix', cycle.note || '—'],
  ]) {
    dl.append(el('dt', '', k), el('dd', '', v));
  }
  conteneur.replaceChildren(dl);
}

function afficherFlux(conteneur, flux) {
  if (!flux.length) {
    conteneur.replaceChildren(el('p', '', 'Aucun flux suivi pour l’instant.'));
    return;
  }
  const table = el('table', 'matrice');
  const tete = el('tr');
  for (const titre of ['Flux', 'Pages ramenées', 'Utiles', 'Dernière lecture', '']) {
    tete.append(el('th', '', titre));
  }
  const head = el('thead');
  head.append(tete);
  const corps = el('tbody');
  for (const f of flux) {
    const tr = el('tr');
    tr.style.cursor = 'default';
    const btn = el('button', 'btn-export', f.actif ? 'Couper' : 'Rallumer');
    btn.type = 'button';
    btn.dataset.ecouteFlux = f.id;
    btn.dataset.actif = f.actif ? '1' : '0';
    const cellule = el('td');
    cellule.append(btn);
    tr.append(
      el('td', '', f.actif ? f.titre : `${f.titre} (coupé)`),
      el('td', '', String(f.pages)),
      el('td', '', String(f.utiles)),
      el('td', '', f.lu || 'jamais'),
      cellule,
    );
    corps.append(tr);
  }
  table.append(head, corps);
  const wrap = el('div', 'table-scroll');
  wrap.append(table);
  conteneur.replaceChildren(wrap);
}

function afficher(main, payload, sig) {
  const zone = (nom) => main.querySelector(`[data-ecoute="${nom}"]`);
  afficherBoutons(zone('boutons'), payload.boutons || []);
  afficherCycle(zone('cycle'), payload.cycle);
  zone('candidates').replaceChildren(...(payload.candidates || []).map((c) => {
    const raison = c.raison ? ` — ${c.raison}` : '';
    const item = el('li');
    const link = el('a', 'clic-ligne', `${c.title} (${c.status})${raison}`);
    link.href = `#/objet/venture/${encodeURIComponent(c.id)}`;
    item.append(link);
    return item;
  }));
  afficherFlux(zone('flux'), payload.flux || []);
  zone('invocations').replaceChildren(
    ...(payload.invocations || []).map((inv) => el('li', '', inv.titre)),
  );
  main.querySelector('[data-section="ecoute"]').dataset.sig = sig;
}

async function lancer(btn, store) {
  if (btn.disabled) return;
  btn.disabled = true;
  const titre = btn.textContent;
  try {
  if (btn.dataset.confirmer) {
    const ok = await confirmModal(document.body, {
      title: `${titre} ?`,
      message: btn.dataset.confirmer,
      confirm: titre,
    });
    if (!ok) {
      return;
    }
  }
  const form = {};
  for (const zone of btn.closest('.grille-champs').querySelectorAll('[data-champ]')) {
    form[zone.dataset.champ] = zone.value;
  }
    const result = await poster('/owner/api/bouton', {trigger_id: btn.dataset.trigger, form});
    toast(document.body, result.ok ? 'Tâche placée dans la file.' : (result.data.erreur || 'Refusé.'), result.ok ? 'succes' : 'erreur');
    if (result.ok) {
      btn.closest('.grille-champs').querySelectorAll('[data-draft]').forEach((f) => delete f.dataset.dirty);
      await rafraichir(store);
    }
  } catch {
    toast(document.body, 'Action injoignable. Réessaie : ta saisie est conservée.', 'erreur');
  } finally {
    btn.disabled = false;
  }
}

export function mount(main, store) {
  const tpl = document.getElementById('page-ecoute');
  main.replaceChildren(tpl.content.cloneNode(true));
  main.querySelector('[data-ecoute="boutons"]').addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-ecoute-action="lancer"]');
    if (btn) {
      lancer(btn, store);
    }
  });
  main.querySelector('[data-ecoute="flux"]').addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-ecoute-flux]');
    if (!btn) {
      return;
    }
    if (btn.disabled) return;
    btn.disabled = true;
    try {
    const result = await poster('/owner/api/flux', {
      feed_id: btn.dataset.ecouteFlux,
      active: btn.dataset.actif !== '1',
    });
    toast(document.body, result.ok ? 'Fait.' : (result.data.erreur || 'Refusé.'), result.ok ? 'succes' : 'erreur');
    if (result.ok) {
      await rafraichir(store);
    }
    } catch {
      toast(document.body, 'Action injoignable.', 'erreur');
    } finally { btn.disabled = false; }
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
