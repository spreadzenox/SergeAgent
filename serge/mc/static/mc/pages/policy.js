// Page Policy : règles cadrées, réglages des invocations, taille des essais, confiance.
import {
  fillList,
  li,
  promptModal,
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
      {nom: 'diff', label: 'Quoi changer : ', defaut: 'invocations / jour : 5 → 10', requis: true},
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
  if (inSmoke && !inSmoke.matches(':focus') && cfg.n_smoke_min != null) {
    inSmoke.value = cfg.n_smoke_min;
  }
  if (inFull && !inFull.matches(':focus') && cfg.n_full_target != null) {
    inFull.value = cfg.n_full_target;
  }
  main.querySelector('[data-section="testing_froid"]').dataset.sig = sig;
}

// Une ligne par réglage : son sens, sa valeur, un bouton Enregistrer.
function ligneReglage(texte, valeur, charge, bornes) {
  const ligne = el('div', 'ligne-reglage');
  const label = el('label', 'champ-large', `${texte} `);
  const input = document.createElement('input');
  input.value = valeur;
  if (bornes) {
    input.type = 'number';
    if (bornes.min !== '') {
      input.min = bornes.min;
    }
    if (bornes.max !== '') {
      input.max = bornes.max;
    }
  }
  label.append(input);
  const btn = el('button', '', 'Enregistrer');
  btn.type = 'button';
  btn.dataset.reglage = JSON.stringify(charge);
  ligne.append(label, btn);
  return ligne;
}

function renderReglages(main, payload, sig) {
  const hote = main.querySelector('[data-reglages="liste"]');
  const blocs = [];
  for (const inv of payload.invocations || []) {
    blocs.push(el('h3', '', `${inv.etape} · ${inv.titre}`));
    for (const r of inv.reglages) {
      const bornes = r.type === 'number' ? {min: r.min, max: r.max} : null;
      const texte = r.description || r.name;
      const suffixe = bornes && (r.min !== '' || r.max !== '')
        ? ` (entre ${r.min || '…'} et ${r.max || '…'})`
        : '';
      blocs.push(ligneReglage(`${texte}${suffixe}`, r.value, {
        cible: 'invocation',
        invocation_id: inv.invocation_id,
        name: r.name,
      }, bornes));
    }
  }
  if ((payload.quotas || []).length) {
    blocs.push(el('h3', '', 'Quotas des tables'));
    for (const q of payload.quotas) {
      blocs.push(ligneReglage(
        q.description || `${q.table} : ${q.column} parmi ${q.values}`,
        String(q.max),
        {cible: 'quota', id: q.id},
        {min: '0', max: ''},
      ));
    }
  }
  if (!blocs.length) {
    blocs.push(el('p', '', 'Aucun réglage marqué « policy » en base.'));
  }
  hote.replaceChildren(...blocs);
  main.querySelector('[data-section="reglages"]').dataset.sig = sig;
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
    if (!Number.isFinite(n_smoke_min) || !Number.isFinite(n_full_target)) {
      toast(document.body, 'Taille des essais : nombres requis.', 'erreur');
      return;
    }
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

  main.querySelector('[data-reglages="liste"]').addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-reglage]');
    if (!btn) {
      return;
    }
    const input = btn.parentElement.querySelector('input');
    btn.disabled = true;
    try {
      const charge = {...JSON.parse(btn.dataset.reglage), value: input.value};
      const {ok, data} = await poster('/owner/api/reglage', charge);
      toast(
        document.body,
        ok ? 'Réglage enregistré.' : (data.erreur || 'Refusé.'),
        ok ? 'succes' : 'erreur',
      );
      if (ok) {
        await rafraichir(store);
      }
    } catch {
      toast(document.body, 'Action injoignable.', 'erreur');
    } finally {
      btn.disabled = false;
    }
  });

  const unsubs = [
    store.subscribe('politique_active', (p, s) => renderPolitiqueActive(main, p, s, store)),
    store.subscribe('reglages', (p, s) => renderReglages(main, p, s)),
    store.subscribe('testing_froid', (p, s) => renderTesting(main, p, s)),
    store.subscribe('trust_candidates', (p, s) => renderTrust(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'politique_active') {
      renderPolitiqueActive(main, env.payload, env.sig, store);
    } else if (section === 'reglages') {
      renderReglages(main, env.payload, env.sig);
    } else if (section === 'testing_froid') {
      renderTesting(main, env.payload, env.sig);
    } else if (section === 'trust_candidates') {
      renderTrust(main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
