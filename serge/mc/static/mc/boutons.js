// Les boutons déclarés en base (déclencheurs « bouton ») : un bloc par
// bouton, avec ses champs, ses conditions et la question posée avant de le
// lancer. Utilisé par la page Écoute (boutons de l’étape 1) et la page
// Système (boutons sans étape, comme « Lancer un essai »).
import {confirmModal, toast, draftField, rememberDrafts} from './components.js';

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

export function afficherBoutons(conteneur, boutons, vide) {
  const cle = JSON.stringify(boutons);
  const restore = rememberDrafts(conteneur);
  if (conteneur.dataset.cle === cle) {
    return;  // ne pas effacer ce qui est en train d’être tapé
  }
  conteneur.dataset.cle = cle;
  if (!boutons.length) {
    conteneur.replaceChildren(el('p', '', vide));
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
    btn.dataset.boutonBase = '1';
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

// Branche les clics sur les boutons d’un conteneur ; ``apres`` est appelé
// quand la tâche est placée dans la file.
export function brancherBoutons(conteneur, apres) {
  conteneur.addEventListener('click', (ev) => {
    const btn = ev.target.closest('[data-bouton-base]');
    if (btn) {
      lancer(btn, apres);
    }
  });
}

async function lancer(btn, apres) {
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
    const response = await fetch('/owner/api/bouton', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({trigger_id: btn.dataset.trigger, form}),
    });
    const data = await response.json().catch(() => ({}));
    toast(document.body, response.ok ? 'Tâche placée dans la file.' : (data.erreur || 'Refusé.'), response.ok ? 'succes' : 'erreur');
    if (response.ok) {
      btn.closest('.grille-champs').querySelectorAll('[data-draft]').forEach((f) => delete f.dataset.dirty);
      await apres();
    }
  } catch {
    toast(document.body, 'Action injoignable. Réessaie : ta saisie est conservée.', 'erreur');
  } finally {
    btn.disabled = false;
  }
}
