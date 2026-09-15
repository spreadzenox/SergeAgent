// Page Identité : miroir de identite_serge(), pas une table.
import {fillList, li} from '../components.js';

function renderIdentite(main, payload, sig) {
  const fiche = payload.fiche || {};
  const ul = main.querySelector('[data-section="identite"] [data-list="champs"]');
  fillList(ul, fiche.champs || [], 'Pas d’instance chargée.', (c) =>
    li(`${c.k} : ${c.v}`),
  );
  main.querySelector('[data-section="identite"]').dataset.sig = sig;
}

export function mount(main, store) {
  main.replaceChildren(document.getElementById('page-identite').content.cloneNode(true));
  return store.subscribe('identite', (p, s) => renderIdentite(main, p, s));
}
