// Page Pipeline : la vue d'ensemble du pipeline, lue en base.
import {toast, draftField, rememberDrafts} from '../components.js';
import {fetchState} from '../sse.js';
import {allerObjet} from '../libelles.js';
import {afficherFamilles, afficherTextes, brancherReglages} from '../reglages.js';

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

// Un tableau ; une ligne avec {type, id} ouvre la fiche de l'objet.
function tableau(colonnes, lignes) {
  const wrap = el('div', 'table-scroll');
  const table = el('table', 'matrice');
  const tete = el('tr');
  for (const titre of colonnes) {
    tete.append(el('th', '', titre));
  }
  const head = el('thead');
  head.append(tete);
  const corps = el('tbody');
  for (const ligne of lignes) {
    const tr = el('tr');
    for (const valeur of ligne.cellules) {
      tr.append(el('td', '', String(valeur)));
    }
    if (ligne.type) {
      tr.tabIndex = 0;
      const open = () => allerObjet(ligne.type, ligne.id);
      tr.setAttribute('role', 'link');
      tr.addEventListener('click', open);
      tr.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); open(); }
      });
    } else {
      tr.style.cursor = 'default';
    }
    corps.append(tr);
  }
  table.append(head, corps);
  wrap.append(table);
  return wrap;
}

const oui = (valeur) => (valeur ? 'oui' : 'non');

// Ne pas effacer ce que Julien est en train de taper.
function changer(conteneur, cle) {
  if (conteneur.dataset.cle === cle) {
    return false;
  }
  conteneur.dataset.cle = cle;
  return true;
}

async function enregistrer(btn, path, body, store, after) {
  const fields = [...btn.closest('.grille-champs').querySelectorAll('input,textarea')];
  if (fields.some((f) => !f.checkValidity())) {
    fields.find((f) => !f.checkValidity()).reportValidity();
    toast(document.body, 'Vérifie les champs requis et leurs bornes.', 'erreur');
    return;
  }
  btn.disabled = true;
  try {
    const result = await poster(path, body);
    toast(
      document.body,
      result.ok ? 'Enregistré.' : result.data.erreur || 'Refusé.',
      result.ok ? 'succes' : 'erreur',
    );
    if (result.ok && result.data.warning) {
      toast(document.body, result.data.warning, 'info');
    }
    if (result.ok) {
      fields.forEach((f) => delete f.dataset.dirty);
      await rafraichir(store);
      if (after) {
        after();
      }
    }
  } catch {
    toast(document.body, 'Action injoignable. Réessaie : ta saisie est conservée.', 'erreur');
  } finally {
    btn.disabled = false;
  }
}

// Les modèles d'OpenRouter, leurs notes et les recommandations : lus à
// chaque ouverture de la page.
let catalog = null;
const MAX_SUGGESTIONS = 12;

const perMillion = (x) => `${x.toFixed(2).replace('.', ',')} $/M`;
// Les prix des modèles bon marché ont besoin de décimales (0,003 $/M).
const price = (x) => (x >= 1 ? x.toFixed(2) : x.toFixed(3)).replace('.', ',');

function contextSize(n) {
  return n >= 1e6 ? `${(n / 1e6).toFixed(1).replace('.0', '')}M` : `${Math.round(n / 1000)}k`;
}

// Les vrais tarifs du modèle, et son prix au mélange de Serge (sans cache).
function rates(m) {
  const parts = [`entrée ${price(m.input)}`];
  if (m.cache_read != null) {
    parts.push(`cache lu ${price(m.cache_read)}`);
  }
  if (m.cache_write != null) {
    parts.push(`cache écrit ${price(m.cache_write)}`);
  }
  parts.push(`sortie ${price(m.output)} $/M (≈ ${price(m.price)})`);
  return parts.join(' · ');
}

function summary(m) {
  const parts = [m.id, rates(m), contextSize(m.context)];
  if (m.id.endsWith(':batch')) {
    parts.push('batch : réponse différée');
  }
  if (m.tools === true) {
    parts.push('outils');
  } else if (m.tools === false) {
    parts.push('sans outils');
  }
  if (m.score != null) {
    parts.push(`note ${m.score}`);
  }
  return parts.join(' · ');
}

const usable = (m) => m.tools !== false && !m.id.endsWith(':batch');

// Les modèles qui contiennent tous les mots tapés ; ceux que Serge peut
// appeler (outils, pas en batch) d'abord, puis les moins chers.
function matches(text) {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  if (!catalog || !words.length) {
    return [];
  }
  return catalog.models
    .filter((m) => words.every((word) => `${m.id} ${m.name}`.toLowerCase().includes(word)))
    .sort((a, b) => usable(b) - usable(a) || a.price - b.price)
    .slice(0, MAX_SUGGESTIONS);
}

function suggest(field, list, info) {
  // Un identifiant exact n'a plus besoin de liste.
  const found = matches(field.value);
  const exact = found.length === 1 && found[0].id === field.value.trim();
  const shown = exact ? [] : found;
  list.replaceChildren(...shown.map((m) => {
    const item = el('li');
    const choice = el('button', 'proposition', summary(m));
    choice.type = 'button';
    choice.title = m.name;
    choice.addEventListener('click', () => {
      field.value = m.id;
      suggest(field, list, info);
    });
    item.append(choice);
    return item;
  }));
  list.hidden = !shown.length;
  const known = catalog && catalog.models.find((m) => m.id === field.value.trim());
  info.textContent = known ? summary(known) : '';
}

function renderCatalog(main) {
  const status = main.querySelector('[data-pipeline="catalogue"]');
  if (!status || !catalog) {
    return;
  }
  const parts = [];
  if (catalog.models.length) {
    const when = catalog.loaded_at.replace('T', ' ').replace('+00:00', ' UTC');
    parts.push(`${catalog.models.length} modèles d’OpenRouter (lus le ${when}).`);
    if (catalog.error) {
      parts.push(`OpenRouter ne répond plus (${catalog.error}) : c’est le dernier catalogue lu.`);
    }
  } else {
    parts.push(`OpenRouter est injoignable (${catalog.error || 'pas de réponse'}) : saisie libre, sans vérification.`);
  }
  parts.push(
    catalog.scored
      ? `${catalog.scored} modèles notés sur ${catalog.models.length} (${catalog.scores_source}).`
      : 'Aucune note d’intelligence : pas de recommandation.',
  );
  const mix = catalog.mix;
  const read = `${Math.round(mix.input_share * 100)} % de jetons lus`;
  parts.push(
    mix.measured
      ? `Mélange de Serge : ${read}, mesuré sur ${(mix.tokens / 1e6).toFixed(1).replace('.', ',')} M de jetons (30 jours).`
      : `Mélange supposé : ${read} (pas assez d’appels enregistrés pour le mesurer).`,
  );
  status.textContent = parts.join(' ');
  for (const field of main.querySelectorAll('[data-tier]')) {
    const tier = field.dataset.tier;
    const reco = main.querySelector(`[data-reco="${tier}"]`);
    const r = catalog.recommendations[tier];
    reco.replaceChildren();
    if (r && r.id) {
      const use = el('button', '', 'Utiliser');
      use.type = 'button';
      use.addEventListener('click', () => {
        field.value = r.id;
        field.dispatchEvent(new Event('input'));
        field.focus();
      });
      reco.append(`Recommandé (plafond ${perMillion(r.max_price)}) : ${r.id}. ${r.reason} `, use);
    } else if (r) {
      reco.append(`Pas de recommandation (plafond ${perMillion(r.max_price)}) : ${r.reason}`);
    }
    field.dispatchEvent(new Event('input'));
  }
}

async function loadCatalog(main) {
  const status = main.querySelector('[data-pipeline="catalogue"]');
  try {
    const response = await fetch('/owner/api/pipeline/modeles');
    if (!response.ok) {
      throw new Error(String(response.status));
    }
    catalog = await response.json();
    renderCatalog(main);
  } catch {
    if (status && !catalog) {
      status.textContent = 'Liste des modèles indisponible : saisie libre.';
    }
  }
}

// Un champ numérique d'un niveau ; ``name`` est le nom de son data-attribut.
function numberField(label, name, tier, value, options) {
  const wrap = el('label', 'champ-large', `${label} `);
  const field = el('input');
  field.type = 'number';
  field.value = String(value);
  field.dataset[name] = tier;
  field.required = true;
  draftField(field, `${tier}.${name}`);
  Object.assign(field, options);
  wrap.append(field);
  return {wrap, field};
}

// Vrai quand les champs ont été recréés (il faut alors les regarnir).
function afficherModeles(conteneur, modeles, store, after) {
  if (!changer(conteneur, JSON.stringify(modeles))) {
    return false;
  }
  const restore = rememberDrafts(conteneur);
  conteneur.replaceChildren(...modeles.map((m) => {
    const bloc = el('div', 'grille-champs');
    const label = el('label', 'champ-large', `${m.libelle} `);
    const field = el('input');
    field.value = m.model;
    field.placeholder = m.effectif;
    field.maxLength = 200;
    field.dataset.tier = m.tier;
    draftField(field, `${m.tier}.model`);
    field.autocomplete = 'off';
    label.append(field);
    const maxPrice = numberField('Prix maximum ($ le million de jetons)', 'maxPrice', m.tier, m.max_price, {min: 0, max: 1000, step: 0.05});
    const tolerance = numberField('Tolérance sur la meilleure note (%)', 'tolerance', m.tier, m.tolerance, {min: 1, max: 100, step: 1});
    const btn = el('button', 'btn-fort', 'Enregistrer');
    btn.type = 'button';
    btn.dataset.pipelineAction = 'modele';
    btn.addEventListener('click', () => enregistrer(
      btn,
      '/owner/api/pipeline/modele',
      {
        tier: m.tier,
        model: field.value.trim(),
        max_price: maxPrice.field.valueAsNumber,
        tolerance: tolerance.field.valueAsNumber,
      },
      store,
      after,
    ));
    const barre = el('div', 'barre-policy');
    barre.append(btn);
    bloc.append(label, maxPrice.wrap, tolerance.wrap, barre);
    const info = el('p', 'legende-policy');
    const list = el('ul', 'propositions');
    list.hidden = true;
    const reco = el('p', 'legende-policy');
    reco.dataset.reco = m.tier;
    field.addEventListener('input', () => suggest(field, list, info));
    const all = el('div', 'modele-niveau');
    all.append(bloc, info, list, reco);
    return all;
  }));
  restore();
  return true;
}

function afficher(main, payload, sig, store) {
  const zone = (nom) => main.querySelector(`[data-pipeline="${nom}"]`);
  const after = () => loadCatalog(main);
  if (afficherModeles(zone('modeles'), payload.modeles || [], store, after)) {
    renderCatalog(main);
  }
  const reglages = payload.reglages || [];
  if (changer(zone('reglages'), JSON.stringify(reglages))) {
    afficherFamilles(zone('reglages'), reglages);
  }
  const textes = payload.textes || [];
  if (changer(zone('textes'), JSON.stringify(textes))) {
    afficherTextes(zone('textes'), textes);
  }
  zone('liens').replaceChildren(tableau(
    ['Lien', 'De → vers', 'Quand', 'Passage', 'En attente', 'Passés', 'Allumé'],
    (payload.liens || []).map((l) => ({
      type: 'lien',
      id: l.id,
      cellules: [l.titre, l.chemin, l.quand, l.passage, l.attente, l.passes, oui(l.allume)],
    })),
  ));
  zone('declencheurs').replaceChildren(tableau(
    ['Déclencheur', 'Lance', 'Quand', 'Allumé'],
    (payload.declencheurs || []).map((d) => ({
      type: 'llm',
      id: d.invocation,
      cellules: [d.titre, d.invocation_titre, d.quand, oui(d.allume)],
    })),
  ));
  zone('outils').replaceChildren(tableau(
    ['Outil', 'Capacité', 'Donné à'],
    (payload.outils || []).map((o) => ({
      type: 'outil',
      id: o.id,
      cellules: [o.titre, o.capacite, o.utilise_par],
    })),
  ));
  zone('capacites').replaceChildren(tableau(
    ['Capacité', 'Id', 'Présente dans le code', 'Outils', 'Code'],
    (payload.capacites || []).map((c) => ({
      cellules: [c.titre, c.id, oui(c.disponible), c.outils, c.code],
    })),
  ));
  zone('tables').replaceChildren(tableau(
    ['Table', 'Titre', 'Version courte', 'Colonnes lisibles', 'Plus récentes par'],
    (payload.tables || []).map((t) => ({
      type: 'table',
      id: t.table,
      cellules: [t.table, t.titre, t.courte, t.lisibles, t.ordre],
    })),
  ));
  main.querySelector('[data-section="pipeline"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-pipeline');
  main.replaceChildren(tpl.content.cloneNode(true));
  for (const nom of ['reglages', 'textes']) {
    brancherReglages(main.querySelector(`[data-pipeline="${nom}"]`), () => rafraichir(store));
  }
  loadCatalog(main);
  const unsubscribe = store.subscribe(
    'pipeline',
    (payload, sig) => afficher(main, payload, sig, store),
  );
  for (const [section, env] of store.all()) {
    if (section === 'pipeline') {
      afficher(main, env.payload, env.sig, store);
    }
  }
  return unsubscribe;
}

async function rafraichir(store) {
  try {
    const data = await fetchState('p11');
    for (const [section, env] of Object.entries(data.sections || {})) {
      store.apply(section, env.sig, env.payload);
    }
  } catch {
    // Le flux SSE reprend l'état au prochain tick.
  }
}
