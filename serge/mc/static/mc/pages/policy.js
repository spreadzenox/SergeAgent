// Page P5 Politique : éditeur sections, snapshots, testing à froid, trust candidates.
import {
  confirmModal,
  fillList,
  li,
  promptModal,
  rel,
  toast,
} from '../components.js';
import {fetchState} from '../sse.js';

async function poster(chemin, charge) {
  const res = await fetch(chemin, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(charge),
  });
  return {ok: res.ok, data: await res.json()};
}

async function rafraichir(store) {
  try {
    const data = await fetchState('p5');
    for (const [section, env] of Object.entries(data.sections || {})) {
      store.apply(section, env.sig, env.payload);
    }
  } catch {
    // reprise au tick suivant
  }
}

async function proposerModif(store) {
  const v = await promptModal(document.body, {
    title: 'Proposer en POLICY (M12)',
    message: 'Création d’un ticket POLICY DRAFT pour revue.',
    fields: [
      {nom: 'titre', label: 'Titre : ', defaut: 'Ajustement seuils', requis: true},
      {nom: 'diff', label: 'Diff prévu : ', defaut: 'budget.llm_daily_eur: 5 -> 10', requis: true},
      {nom: 'justif', label: 'Justification : ', defaut: 'Hausse volume'},
    ],
    confirm: 'Créer ticket',
  });
  if (!v) {
    return;
  }
  try {
    const {ok, data} = await poster('/owner/api/policy/propose', {
      titre: v.titre,
      diff: v.diff,
      justification: v.justif,
      decision_id: `mc-${Date.now()}-prop`,
    });
    if (!ok) {
      toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
      return;
    }
    toast(document.body, `Ticket POLICY ${data.ticket_id} créé.`, 'succes');
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  }
}

async function rollbackSnap(store, snapId) {
  const ok = await confirmModal(document.body, {
    title: `Restaurer snapshot #${snapId} ?`,
    message: 'La configuration correspondante sera rechargée en nouveau snapshot.',
    confirm: 'Restaurer',
  });
  if (!ok) {
    return;
  }
  try {
    const {ok: resOk, data} = await poster('/owner/api/policy/rollback', {
      snapshot_id: snapId,
      decision_id: `mc-${Date.now()}-roll-${snapId}`,
    });
    if (!resOk) {
      toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
      return;
    }
    toast(document.body, `Snapshot #${snapId} restauré.`, 'succes');
    await rafraichir(store);
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  }
}

function renderPolitiqueActive(main, payload, sig, store) {
  const conteneur = main.querySelector('[data-policy="sections"]');
  conteneur.replaceChildren();
  const pol = payload.policy || {};

  for (const [secNom, secVal] of Object.entries(pol)) {
    if (secNom === 'schema_version') {
      continue;
    }
    const h3 = document.createElement('h3');
    h3.textContent = secNom;
    const pre = document.createElement('div');
    pre.className = 'diff-bloc';
    pre.textContent = JSON.stringify(secVal, null, 2);
    conteneur.append(h3, pre);
  }
  main.querySelector('[data-section="politique_active"]').dataset.sig = sig;
}

function renderTesting(main, payload, sig) {
  const pStat = main.querySelector('#testing-lock-status');
  const btnEnregistrer = main.querySelector('[data-btn="enregistrer-testing"]');
  const locked = payload.is_locked;
  if (locked) {
    pStat.textContent = `Verrouillé : ${payload.running_campaigns} campagne(s) en cours d’exécution.`;
    pStat.style.color = 'var(--orange)';
    btnEnregistrer.disabled = true;
  } else {
    pStat.textContent = 'Déverrouillé : aucune campagne active (testing modifiable à froid).';
    pStat.style.color = 'var(--vert)';
    btnEnregistrer.disabled = false;
  }

  const cfg = payload.config || {};
  const inSmoke = main.querySelector('[data-testing="n_smoke_min"]');
  const inFull = main.querySelector('[data-testing="n_full_target"]');
  if (inSmoke && !inSmoke.matches(':focus')) {
    inSmoke.value = cfg.n_smoke_min || 30;
  }
  if (inFull && !inFull.matches(':focus')) {
    inFull.value = cfg.n_full_target || 200;
  }
  main.querySelector('[data-section="testing_froid"]').dataset.sig = sig;
}

function renderSnapshots(main, payload, sig, store) {
  const ul = main.querySelector('[data-section="policy_snapshots"] [data-list="snapshots"]');
  fillList(ul, payload.snapshots || [], 'Aucun snapshot enregistré.', (snap) => {
    const liEl = li(`#${snap.id} [${snap.content_hash}] par ${snap.applied_by} (${rel(snap.active_from)}) `);
    const bRoll = document.createElement('button');
    bRoll.type = 'button';
    bRoll.textContent = 'Rollback';
    bRoll.addEventListener('click', () => rollbackSnap(store, snap.id));
    liEl.append(bRoll);
    return liEl;
  });
  main.querySelector('[data-section="policy_snapshots"]').dataset.sig = sig;
}

function renderTrust(main, payload, sig) {
  const ul = main.querySelector('[data-section="trust_candidates"] [data-list="candidates"]');
  fillList(ul, payload.candidates || [], 'Aucun type de ticket candidat.', (cand) => {
    const statut = cand.eligible ? 'ÉLIGIBLE AUTO' : 'Non éligible';
    const ratePct = Math.round(cand.rate * 100);
    const thPct = Math.round(cand.threshold_rate * 100);
    return li(
      `${cand.type} — ${statut} (${cand.approved}/${cand.total} approuvés, `
      + `${ratePct} % vs seuil ${thPct} %, min ${cand.threshold_min})`
    );
  });
  main.querySelector('[data-section="trust_candidates"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-policy');
  main.replaceChildren(tpl.content.cloneNode(true));

  main.querySelector('[data-action="proposer-policy"]').addEventListener('click', () => {
    proposerModif(store);
  });

  main.querySelector('[data-btn="enregistrer-testing"]').addEventListener('click', async (ev) => {
    ev.preventDefault();
    const n_smoke_min = parseInt(main.querySelector('[data-testing="n_smoke_min"]').value, 10);
    const n_full_target = parseInt(main.querySelector('[data-testing="n_full_target"]').value, 10);
    try {
      const {ok, data} = await poster('/owner/api/policy/testing', {
        testing: {n_smoke_min, n_full_target},
        decision_id: `mc-${Date.now()}-test`,
      });
      if (!ok) {
        toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
        return;
      }
      toast(document.body, 'Testing mis à jour.', 'succes');
      await rafraichir(store);
    } catch {
      toast(document.body, 'Action injoignable.', 'erreur');
    }
  });

  const unsubs = [
    store.subscribe('politique_active', (p, s) => renderPolitiqueActive(main, p, s, store)),
    store.subscribe('testing_froid', (p, s) => renderTesting(main, p, s)),
    store.subscribe('policy_snapshots', (p, s) => renderSnapshots(main, p, s, store)),
    store.subscribe('trust_candidates', (p, s) => renderTrust(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'politique_active') {
      renderPolitiqueActive(main, env.payload, env.sig, store);
    } else if (section === 'testing_froid') {
      renderTesting(main, env.payload, env.sig);
    } else if (section === 'policy_snapshots') {
      renderSnapshots(main, env.payload, env.sig, store);
    } else if (section === 'trust_candidates') {
      renderTrust(main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
