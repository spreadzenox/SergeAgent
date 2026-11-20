// Page Identité : miroir de identite_serge(), pas une table. Le formulaire
// écrit dans le fichier d’instance ce que Serge donne à un site pour s’y
// inscrire.
import {fillList, li, toast} from '../components.js';

function renderIdentite(main, payload, sig) {
  const fiche = payload.fiche || {};
  const section = main.querySelector('[data-section="identite"]');
  fillList(section.querySelector('[data-list="champs"]'), fiche.champs || [], 'Pas d’instance chargée.', (c) =>
    li(`${c.k} : ${c.v}`),
  );
  // Un champ en cours de saisie n’est pas écrasé par un rafraîchissement.
  const form = section.querySelector('[data-identite="inscription"]');
  if (!form.contains(document.activeElement)) {
    for (const champ of form.querySelectorAll('input')) {
      champ.value = (fiche.basique || {})[champ.name] || '';
    }
  }
  section.dataset.sig = sig;
}

function brancher(main) {
  const form = main.querySelector('[data-identite="inscription"]');
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const response = await fetch('/owner/api/identite', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        document.activeElement.blur();
        renderIdentite(main, {fiche: data.fiche}, '');
      }
      toast(
        document.body,
        response.ok ? 'Identité enregistrée.' : (data.erreur || 'Refusé.'),
        response.ok ? 'succes' : 'erreur',
      );
    } catch {
      toast(document.body, 'Action injoignable. Réessaie.', 'erreur');
    }
  });
}

export function mount(main, store) {
  main.replaceChildren(document.getElementById('page-identite').content.cloneNode(true));
  brancher(main);
  return store.subscribe('identite', (p, s) => renderIdentite(main, p, s));
}
