// Coupe-circuits En direct : Serge, étapes, kinds.
import {toast} from '../components.js';
import {patchSection} from '../patch.js';
import {fetchState} from '../sse.js';

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

function bouton(classe, texte, cible, ident, marche) {
  const btn = el('button', classe, texte);
  btn.type = 'button';
  btn.dataset.coupeCible = cible;
  if (ident) {
    btn.dataset.coupeId = ident;
  }
  btn.dataset.coupe = marche ? '0' : '1';
  btn.setAttribute('aria-pressed', marche ? 'false' : 'true');
  return btn;
}

function remplirRang(host, items, cible) {
  host.replaceChildren();
  for (const item of items) {
    const titre = item.titre || item.id;
    const marche = item.marche !== false;
    const texte = marche ? `Couper ${titre}` : `Remettre ${titre}`;
    host.append(bouton('btn-kill', texte, cible, item.id, marche));
  }
}

export function renderCoupes(main, payload, sig) {
  patchSection(main, 'coupes', sig, payload);
  const sec = main.querySelector('[data-section="coupes"]');
  if (!sec) {
    return;
  }
  sec.dataset.sergeCoupe = payload.serge === false ? '1' : '0';
  const slotSerge = sec.querySelector('[data-coupes="serge"]');
  if (slotSerge) {
    const marche = payload.serge !== false;
    const texte = marche
      ? 'Arrêter Serge'
      : 'Remettre Serge en marche';
    slotSerge.replaceChildren(
      bouton('btn-kill-serge', texte, 'serge', '', marche),
    );
  }
  const slotEtapes = main.querySelector('[data-coupes="etapes"]');
  if (slotEtapes) {
    remplirRang(slotEtapes, payload.etapes || [], 'etape');
  }
  const slotKinds = main.querySelector('[data-coupes="kinds"]');
  if (slotKinds) {
    remplirRang(slotKinds, payload.kinds || [], 'kind');
  }
}

async function poster(chemin, charge) {
  const res = await fetch(chemin, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(charge),
  });
  return {ok: res.ok, data: await res.json()};
}

export function brancherCoupes(main, store) {
  main.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-coupe-cible]');
    if (!btn || !main.contains(btn)) {
      return;
    }
    if (btn.disabled) {
      return;
    }
    btn.disabled = true;
    const cible = btn.dataset.coupeCible;
    const ident = btn.dataset.coupeId || '';
    const marche = btn.dataset.coupe === '1';
    try {
      const {ok, data} = await poster('/owner/api/coupe', {
        cible,
        id: ident,
        marche,
        decision_id: `mc-${Date.now()}-${cible}-${ident || 'serge'}`,
      });
      if (!ok) {
        toast(document.body, data.erreur || 'Action refusée.', 'erreur');
        return;
      }
      const etat = await fetchState('p0');
      for (const nom of ['coupes', 'graphe']) {
        const env = etat.sections && etat.sections[nom];
        if (env) {
          store.apply(nom, env.sig, env.payload);
        }
      }
    } catch {
      toast(document.body, 'Action injoignable.', 'erreur');
    } finally {
      btn.disabled = false;
    }
  });
}
