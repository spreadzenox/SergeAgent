// Page Policy : règles cadrées, historique, taille des essais, confiance.
import {
  confirmModal,
  fillList,
  li,
  promptModal,
  rel,
  toast,
} from '../components.js';
import {TYPES_TICKET} from '../libelles.js';
import {
  champPolicy,
  el,
  grouperFeuilles,
  feuillesPolicy,
  lirePolicy,
} from '../policy_form.js';
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

async function proposerModif() {
  const v = await promptModal(document.body, {
    title: 'Demander un changement',
    message: 'Ça crée une question pour toi : rien n’est appliqué tout seul.',
    fields: [
      {nom: 'titre', label: 'Titre : ', defaut: 'Ajuster un plafond', requis: true},
      {nom: 'diff', label: 'Quoi changer : ', defaut: 'jugements / jour : 5 → 10', requis: true},
      {nom: 'justif', label: 'Pourquoi : ', defaut: 'On touche plus de monde'},
    ],
    confirm: 'Créer la question',
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
      toast(document.body, `Refusé : ${data.erreur || 'pas passé'}.`, 'erreur');
      return;
    }
    toast(document.body, `Question Policy ${data.ticket_id} créée.`, 'succes');
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  }
}

async function rollbackSnap(store, snapId) {
  const ok = await confirmModal(document.body, {
    title: `Revenir à la version #${snapId} ?`,
    message: 'Les règles actuelles seront remplacées par celles de cette version.',
    confirm: 'Revenir à cette version',
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
      toast(document.body, `Refusé : ${data.erreur || 'pas passé'}.`, 'erreur');
      return;
    }
    toast(document.body, `Version #${snapId} remise en place.`, 'succes');
    await rafraichir(store);
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  }
}

function renderPolitiqueActive(main, payload, sig, store) {
  const host = main.querySelector('[data-policy="atelier"]');
  if (!host) {
    return;
  }
  host.replaceChildren();
  const pol = payload.policy || {};
  const groupes = grouperFeuilles(feuillesPolicy(pol));
  const sommaire = el('nav', 'sommaire-policy');
  sommaire.setAttribute('aria-label', 'Familles de règles');
  const corps = el('div', 'corps-policy');
  let actif = host.dataset.sec || (groupes[0] && groupes[0].id) || '';

  function montrer(id) {
    actif = id;
    host.dataset.sec = id;
    sommaire.querySelectorAll('button').forEach((b) => {
      b.classList.toggle('actif', b.dataset.sec === id);
    });
    corps.querySelectorAll('[data-sec]').forEach((art) => {
      art.hidden = art.dataset.sec !== id;
    });
  }

  for (const g of groupes) {
    const btn = el('button', 'onglet-policy', g.titre);
    btn.type = 'button';
    btn.dataset.sec = g.id;
    btn.addEventListener('click', () => montrer(g.id));
    sommaire.append(btn);
    const art = el('article', 'cadre-regle');
    art.dataset.sec = g.id;
    art.append(el('h3', '', g.titre));
    if (g.pourquoi) {
      art.append(el('p', 'pourquoi-regle', g.pourquoi));
    }
    const grille = el('div', 'grille-champs');
    for (const [chemin, val] of g.champs) {
      grille.append(champPolicy(chemin, val));
    }
    art.append(grille);
    corps.append(art);
  }

  const barre = el('div', 'barre-policy');
  const enregistrer = el('button', 'btn-fort', 'Enregistrer les réglages');
  enregistrer.type = 'button';
  enregistrer.addEventListener('click', async () => {
    const body = lirePolicy(corps, pol);
    try {
      const {ok, data} = await poster('/owner/api/policy/edit', {
        policy: body,
        decision_id: `mc-${Date.now()}-edit`,
      });
      if (!ok) {
        toast(document.body, `Refusé : ${data.erreur || 'pas passé'}.`, 'erreur');
        return;
      }
      toast(document.body, 'Règles enregistrées.', 'succes');
      await rafraichir(store);
    } catch {
      toast(document.body, 'Action injoignable.', 'erreur');
    }
  });
  barre.append(enregistrer);
  corps.append(barre);
  host.append(sommaire, corps);
  montrer(actif);
  main.querySelector('[data-section="politique_active"]').dataset.sig = sig;
}

function renderTesting(main, payload, sig) {
  const pStat = main.querySelector('#testing-lock-status');
  const btn = main.querySelector('[data-btn="enregistrer-testing"]');
  if (payload.is_locked) {
    pStat.textContent =
      `Un essai tourne (${payload.running_campaigns}) — on ne change pas la taille ici.`;
    pStat.dataset.etat = 'bloque';
    btn.disabled = true;
  } else {
    pStat.textContent = 'Aucun essai en cours — tu peux changer la taille.';
    pStat.dataset.etat = 'libre';
    btn.disabled = false;
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
  fillList(ul, payload.snapshots || [], 'Aucune version enregistrée.', (snap) => {
    const qui = snap.applied_by === 'owner' || snap.applied_by === 'owner_init'
      ? 'toi'
      : (snap.applied_by || 'Serge');
    const liEl = li(`Version #${snap.id} · posée par ${qui} · ${rel(snap.active_from)}`);
    const bRoll = el('button', 'btn-doux', 'Revenir à cette version');
    bRoll.type = 'button';
    bRoll.addEventListener('click', () => rollbackSnap(store, snap.id));
    liEl.append(bRoll);
    return liEl;
  });
  main.querySelector('[data-section="policy_snapshots"]').dataset.sig = sig;
}

function renderTrust(main, payload, sig) {
  const ul = main.querySelector('[data-section="trust_candidates"] [data-list="candidates"]');
  fillList(ul, payload.candidates || [], 'Aucun type assez régulier pour l’instant.', (cand) => {
    const nom = TYPES_TICKET[cand.type] || cand.type;
    const statut = cand.eligible
      ? 'assez régulier pour proposer l’auto'
      : 'pas encore assez régulier';
    const ratePct = Math.round(cand.rate * 100);
    const thPct = Math.round(cand.threshold_rate * 100);
    return li(
      `${nom} — ${statut} (${cand.approved}/${cand.total} oui, `
      + `${ratePct} % vs ${thPct} %, min ${cand.threshold_min})`
    );
  });
  main.querySelector('[data-section="trust_candidates"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-policy');
  main.replaceChildren(tpl.content.cloneNode(true));

  main.querySelector('[data-action="proposer-policy"]').addEventListener('click', () => {
    proposerModif();
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
        toast(document.body, `Refusé : ${data.erreur || 'pas passé'}.`, 'erreur');
        return;
      }
      toast(document.body, 'Taille des essais mise à jour.', 'succes');
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
