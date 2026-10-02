// Page Policy : les familles de réglages généraux (les limites de Serge face
// au monde), puis les réglages des invocations et les quotas des tables.
// Chacun s'enregistre seul, et peut reprendre sa valeur précédente.
import {draftField, rememberDrafts} from '../components.js';
import {el} from '../policy_form.js';
import {afficherFamilles, boutonPrecedent, brancherReglages} from '../reglages.js';
import {fetchState} from '../sse.js';

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

function renderPolitiqueActive(main, payload, sig) {
  const host = main.querySelector('[data-policy="atelier"]');
  if (!host) {
    return;
  }
  afficherFamilles(host, payload.sections || []);
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

export function mount(main, store) {
  const tpl = document.getElementById('page-policy');
  main.replaceChildren(tpl.content.cloneNode(true));
  for (const hote of main.querySelectorAll('[data-policy="atelier"], [data-reglages="liste"]')) {
    brancherReglages(hote, () => rafraichir(store));
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
