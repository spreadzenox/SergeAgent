// Les réglages en base, communs aux pages Policy et Pipeline : les familles
// de réglages généraux, les textes envoyés au modèle, et les boutons
// « Enregistrer » et « Remettre » (la valeur précédente). Tout vient de la
// base : titres, aides, bornes et choix.
import {draftField, rememberDrafts, toast} from './components.js';
import {champPolicy, el, formatValeur} from './policy_form.js';

async function poster(chemin, charge) {
  const res = await fetch(chemin, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(charge),
  });
  return {ok: res.ok, data: await res.json()};
}

function dateCourte(iso) {
  return iso ? String(iso).slice(0, 16).replace('T', ' ') : '';
}

// « Remettre 50 € » : la valeur précédente, remplacée par qui, quand.
export function boutonPrecedent(charge, texte, precedent) {
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

// Les familles de réglages : leurs noms à gauche, les réglages à droite.
export function afficherFamilles(host, sections) {
  const restore = rememberDrafts(host);
  host.replaceChildren();
  const sommaire = el('nav', 'sommaire-policy');
  sommaire.setAttribute('aria-label', 'Familles de réglages');
  const corps = el('div', 'corps-policy');
  let actif = host.dataset.sec || '';
  if (!sections.some((s) => s.id === actif)) {
    actif = (sections[0] && sections[0].id) || '';
  }

  function montrer(id) {
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
}

// Les textes envoyés au modèle : un par bloc, avec son aide.
export function afficherTextes(host, textes) {
  const restore = rememberDrafts(host);
  const blocs = textes.map((t) => {
    const bloc = el('div', 'champ-policy');
    bloc.dataset.texte = t.id;
    bloc.append(el('p', 'titre-champ', t.titre));
    if (t.aide) {
      bloc.append(el('p', 'aide-champ', t.aide));
    }
    const zone = draftField(el('textarea', 'texte-policy'), `texte.${t.id}`);
    zone.maxLength = 4000;
    zone.rows = t.id === 'presentation' ? 6 : 3;
    zone.value = t.valeur;
    zone.setAttribute('aria-label', t.titre);
    const actes = el('div', 'actes-champ');
    const enregistrer = el('button', '', 'Enregistrer');
    enregistrer.type = 'button';
    enregistrer.dataset.enregistrerTexte = t.id;
    actes.append(enregistrer);
    if (t.precedent) {
      actes.append(boutonPrecedent(
        {cible: 'texte', id: t.id},
        'le texte précédent',
        t.precedent,
      ));
    }
    bloc.append(zone, actes);
    return bloc;
  });
  host.replaceChildren(...blocs);
  restore();
}

// Enregistrer un réglage, ou remettre sa valeur précédente.
async function agir(btn, chemin, charge, champs, rafraichir) {
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
      await rafraichir();
    }
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  } finally {
    btn.disabled = false;
  }
}

// Les boutons des réglages d'un conteneur : un réglage général, un texte,
// un réglage d'invocation ou un quota, et « Remettre ».
export function brancherReglages(host, rafraichir) {
  host.addEventListener('click', (ev) => {
    const btn = ev.target.closest(
      'button[data-enregistrer], button[data-enregistrer-texte], button[data-reglage], button[data-precedent]',
    );
    if (!btn) {
      return;
    }
    if (btn.dataset.precedent) {
      agir(btn, '/owner/api/reglage/precedent', JSON.parse(btn.dataset.precedent), [], rafraichir);
      return;
    }
    if (btn.dataset.enregistrer) {
      const champ = btn.closest('.champ-policy');
      const charge = {cible: 'policy', id: btn.dataset.enregistrer, value: champ._lire()};
      agir(btn, '/owner/api/reglage', charge, [...champ.querySelectorAll('[data-draft]')], rafraichir);
      return;
    }
    if (btn.dataset.enregistrerTexte) {
      const zone = btn.closest('[data-texte]').querySelector('textarea');
      const charge = {cible: 'texte', id: btn.dataset.enregistrerTexte, value: zone.value};
      agir(btn, '/owner/api/reglage', charge, [zone], rafraichir);
      return;
    }
    const input = btn.parentElement.querySelector('input');
    const charge = {...JSON.parse(btn.dataset.reglage), value: input.value};
    agir(btn, '/owner/api/reglage', charge, [input], rafraichir);
  });
}
