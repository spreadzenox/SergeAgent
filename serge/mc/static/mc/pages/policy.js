// Page Policy : les réglages généraux (par famille), ceux des invocations et
// les quotas des tables. Chacun s'enregistre seul, et peut reprendre sa
// valeur précédente. Tout vient de la base : titres, aides, bornes, choix.
import {draftField, rememberDrafts, toast} from '../components.js';
import {champPolicy, el, formatValeur} from '../policy_form.js';
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

function dateCourte(iso) {
  return iso ? String(iso).slice(0, 16).replace('T', ' ') : '';
}

// « Remettre 50 € » : la valeur précédente, remplacée par qui, quand.
function boutonPrecedent(charge, texte, precedent) {
  const btn = el('button', 'btn-doux', `Remettre ${texte}`);
  btn.type = 'button';
  btn.dataset.precedent = JSON.stringify(charge);
  btn.title = `Valeur précédente, remplacée par ${precedent.par || '?'} le ${dateCourte(precedent.le)}`;
  return btn;
}

function champReglage(r, verrou) {
  const field = champPolicy(r.id, r, r.valeur);
  field.querySelectorAll('input,select,textarea').forEach((f, i) => draftField(f, `${r.id}.${i}`));
  const actes = el('div', 'actes-champ');
  const enregistrer = el('button', '', 'Enregistrer');
  enregistrer.type = 'button';
  enregistrer.dataset.enregistrer = r.id;
  actes.append(enregistrer);
  if (r.precedent) {
    actes.append(boutonPrecedent(
      {cible: 'policy', id: r.id},
      formatValeur(r, r.precedent.valeur),
      r.precedent,
    ));
  }
  field.append(actes);
  if (verrou) {
    field.querySelectorAll('input,select,textarea,button').forEach((n) => {
      n.disabled = true;
    });
  }
  return field;
}

function renderPolitiqueActive(main, payload, sig) {
  const host = main.querySelector('[data-policy="atelier"]');
  if (!host) {
    return;
  }
  const restore = rememberDrafts(host);
  host.replaceChildren();
  const sections = payload.sections || [];
  const sommaire = el('nav', 'sommaire-policy');
  sommaire.setAttribute('aria-label', 'Familles de réglages');
  const corps = el('div', 'corps-policy');
  let actif = host.dataset.sec || (sections[0] && sections[0].id) || '';
  if (!sections.some((s) => s.id === actif)) {
    actif = (sections[0] && sections[0].id) || '';
  }

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

  for (const sec of sections) {
    const btn = el('button', 'onglet-policy', sec.titre);
    btn.type = 'button';
    btn.dataset.sec = sec.id;
    btn.addEventListener('click', () => montrer(sec.id));
    sommaire.append(btn);
    const art = el('article', 'cadre-regle');
    art.dataset.sec = sec.id;
    art.append(el('h3', '', sec.titre));
    if (sec.pourquoi) {
      art.append(el('p', 'pourquoi-regle', sec.pourquoi));
    }
    if (sec.verrou) {
      const verrou = el('p', 'verrou-regle', `Verrouillé : ${sec.verrou}`);
      verrou.dataset.verrou = sec.id;
      art.append(verrou);
    }
    const grille = el('div', 'grille-champs');
    for (const r of sec.reglages) {
      grille.append(champReglage(r, sec.verrou));
    }
    art.append(grille);
    corps.append(art);
  }
  host.append(sommaire, corps);
  montrer(actif);
  restore();
  main.querySelector('[data-section="politique_active"]').dataset.sig = sig;
}

// Une ligne par réglage d'invocation ou quota : son sens, sa valeur, un
// bouton Enregistrer, et « Remettre » s'il a une valeur précédente.
function ligneReglage(texte, valeur, charge, bornes, precedent) {
  const ligne = el('div', 'ligne-reglage');
  // Repère stable : « <invocation>.<réglage> » ou « quota.<quota> ».
  ligne.dataset.reglage = charge.cible === 'quota'
    ? `quota.${charge.id}`
    : `${charge.invocation_id}.${charge.name}`;
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
  draftField(input, ligne.dataset.reglage);
  label.append(input);
  const btn = el('button', '', 'Enregistrer');
  btn.type = 'button';
  btn.dataset.reglage = JSON.stringify(charge);
  ligne.append(label, btn);
  if (precedent) {
    ligne.append(boutonPrecedent(charge, String(precedent.valeur), precedent));
  }
  return ligne;
}

function renderReglages(main, payload, sig) {
  const hote = main.querySelector('[data-reglages="liste"]');
  const restore = rememberDrafts(hote);
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
      }, bornes, r.precedent));
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
        q.precedent,
      ));
    }
  }
  if (!blocs.length) {
    blocs.push(el('p', '', 'Aucun réglage marqué « policy » en base.'));
  }
  hote.replaceChildren(...blocs);
  restore();
  main.querySelector('[data-section="reglages"]').dataset.sig = sig;
}

// Enregistrer un réglage, ou remettre sa valeur précédente.
async function agir(btn, chemin, charge, champs, store) {
  btn.disabled = true;
  try {
    const {ok, data} = await poster(chemin, charge);
    toast(
      document.body,
      ok ? 'Réglage enregistré.' : (data.erreur || 'Refusé.'),
      ok ? 'succes' : 'erreur',
    );
    if (ok) {
      champs.forEach((f) => delete f.dataset.dirty);
      await rafraichir(store);
    }
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  } finally {
    btn.disabled = false;
  }
}

function surClic(ev, store) {
  const btn = ev.target.closest('button[data-enregistrer], button[data-reglage], button[data-precedent]');
  if (!btn) {
    return;
  }
  if (btn.dataset.precedent) {
    agir(btn, '/owner/api/reglage/precedent', JSON.parse(btn.dataset.precedent), [], store);
    return;
  }
  if (btn.dataset.enregistrer) {
    const champ = btn.closest('.champ-policy');
    const charge = {cible: 'policy', id: btn.dataset.enregistrer, value: champ._lire()};
    agir(btn, '/owner/api/reglage', charge, [...champ.querySelectorAll('[data-draft]')], store);
    return;
  }
  const input = btn.parentElement.querySelector('input');
  const charge = {...JSON.parse(btn.dataset.reglage), value: input.value};
  agir(btn, '/owner/api/reglage', charge, [input], store);
}

export function mount(main, store) {
  const tpl = document.getElementById('page-policy');
  main.replaceChildren(tpl.content.cloneNode(true));
  for (const hote of main.querySelectorAll('[data-policy="atelier"], [data-reglages="liste"]')) {
    hote.addEventListener('click', (ev) => surClic(ev, store));
  }

  const unsubs = [
    store.subscribe('politique_active', (p, s) => renderPolitiqueActive(main, p, s)),
    store.subscribe('reglages', (p, s) => renderReglages(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'politique_active') {
      renderPolitiqueActive(main, env.payload, env.sig);
    } else if (section === 'reglages') {
      renderReglages(main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
