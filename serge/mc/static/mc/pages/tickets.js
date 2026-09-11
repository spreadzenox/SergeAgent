// Page P3 Décisions : liste + filtres dynamiques + carte interactive (M1/M2/M3).
import {
  confirmModal,
  fillList,
  li,
  promptModal,
  rel,
  toast,
} from '../components.js';
import {fetchState} from '../sse.js';

const OUVERTS = ['DRAFT', 'OPEN', 'DISCUSSING'];
const OUTCOME_FR = {APPROVED: 'approuvé', REJECTED: 'rejeté', EDITED: 'édité'};
const ETAT_ITEM_FR = {keep: 'gardé', edit: 'à modifier', drop: 'jeté'};

function lisFiltres(main) {
  return {
    type: main.querySelector('[data-filtre="type"]').value,
    etat: main.querySelector('[data-filtre="etat"]').value,
    urgents: main.querySelector('[data-filtre="urgents"]').checked,
    recherche: main
      .querySelector('[data-filtre="recherche"]')
      .value.trim()
      .toLowerCase(),
    tri: main.querySelector('[data-filtre="tri"]').value,
  };
}

function appliqueFiltres(items, filtres) {
  const gardes = items.filter((item) => {
    if (filtres.type && item.type !== filtres.type) {
      return false;
    }
    if (filtres.etat === 'atraiter' && !OUVERTS.includes(item.etat)) {
      return false;
    }
    if (filtres.etat === 'termines' && OUVERTS.includes(item.etat)) {
      return false;
    }
    if (filtres.urgents && !item.urgent) {
      return false;
    }
    if (filtres.recherche && !item.titre.toLowerCase().includes(filtres.recherche)) {
      return false;
    }
    return true;
  });
  if (filtres.tri === 'expiry') {
    gardes.sort((a, b) => {
      if (!a.expiry_at) {
        return 1;
      }
      if (!b.expiry_at) {
        return -1;
      }
      return a.expiry_at.localeCompare(b.expiry_at);
    });
  }
  return gardes;
}

function majOptionsTypes(main, items) {
  const select = main.querySelector('[data-filtre="type"]');
  const courant = select.value;
  const types = [...new Set(items.map((item) => item.type))].sort();
  select.replaceChildren();
  const tous = document.createElement('option');
  tous.value = '';
  tous.textContent = 'Tous types';
  select.append(tous);
  for (const type of types) {
    const opt = document.createElement('option');
    opt.value = type;
    opt.textContent = type;
    select.append(opt);
  }
  if (types.includes(courant)) {
    select.value = courant;
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

async function rafraichir(main, store) {
  try {
    const data = await fetchState('p3');
    for (const [section, env] of Object.entries(data.sections || {})) {
      store.apply(section, env.sig, env.payload);
    }
  } catch {
    // le stream reprendra au prochain tick
  }
  const ouverte = main.querySelector('[data-carte="panneau"]');
  if (!ouverte.hidden) {
    await chargerCarte(main, store, ouverte.dataset.ticket);
  }
}

async function agirTicket(main, store, ticketId, acte) {
  let charge = {ticket_id: ticketId, acte};
  if (acte === 'editer' || acte === 'discuter') {
    const estEdit = acte === 'editer';
    const valeurs = await promptModal(document.body, {
      title: estEdit ? 'Éditer ?' : 'Discuter ?',
      message: estEdit ? 'Décris la modification.' : 'Écris ton message.',
      fields: [
        {
          nom: estEdit ? 'note' : 'message',
          label: estEdit ? 'Note : ' : 'Message : ',
          defaut: '',
          requis: true,
        },
      ],
      confirm: estEdit ? 'Éditer' : 'Envoyer',
    });
    if (!valeurs) {
      return;
    }
    charge = {...charge, ...(estEdit ? {note: valeurs.note} : {})};
    if (!estEdit) {
      const {ok, data} = await poster('/owner/api/ticket/discuter', {
        ticket_id: ticketId,
        message: valeurs.message,
        decision_id: `mc-${Date.now()}-${ticketId}`,
      });
      if (!ok) {
        toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
        return;
      }
      toast(document.body, 'Message envoyé.', 'succes');
      await rafraichir(main, store);
      return;
    }
  } else {
    const confirmer = await confirmModal(document.body, {
      title: `${acte === 'approuver' ? 'Approuver' : 'Rejeter'} ?`,
      message: `Ticket ${ticketId} — acte irréversible côté état.`,
      confirm: acte === 'approuver' ? 'Approuver' : 'Rejeter',
      danger: acte !== 'approuver',
    });
    if (!confirmer) {
      return;
    }
  }
  charge.decision_id = `mc-${Date.now()}-${ticketId}`;
  try {
    const {ok, data} = await poster('/owner/api/ticket/acte', charge);
    if (!ok) {
      toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
      return;
    }
    toast(document.body, `Ticket ${OUTCOME_FR[data.outcome] || data.outcome}.`, 'succes');
    await rafraichir(main, store);
  } catch {
    toast(document.body, 'Acte injoignable.', 'erreur');
  }
}

async function agirItem(main, store, ticketId, item, acte) {
  let charge = {item_id: item.id, acte};
  if (acte === 'modifier') {
    const valeurs = await promptModal(document.body, {
      title: 'Modifier ?',
      message: `Item actuel : ${item.label}`,
      fields: [{nom: 'valeur', label: 'Nouveau : ', defaut: item.label, requis: true}],
      confirm: 'Modifier',
    });
    if (!valeurs) {
      return;
    }
    charge = {...charge, valeur: valeurs.valeur};
  }
  try {
    const {ok, data} = await poster('/owner/api/ticket/item', {
      ...charge,
      decision_id: `mc-${Date.now()}-${item.id}`,
    });
    if (!ok) {
      toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
      return;
    }
    toast(document.body, `Item ${ETAT_ITEM_FR[data.etat] || data.etat}.`, 'succes');
    await rafraichir(main, store);
  } catch {
    toast(document.body, 'Acte injoignable.', 'erreur');
  }
}

async function toutApprouver(main, store, ticketId) {
  const confirmer = await confirmModal(document.body, {
    title: 'Tout approuver ?',
    message: 'Tous les items ouverts seront gardés.',
    confirm: 'Tout approuver',
  });
  if (!confirmer) {
    return;
  }
  try {
    const {ok, data} = await poster('/owner/api/ticket/item', {
      ticket_id: ticketId,
      acte: 'tout_approuver',
      decision_id: `mc-${Date.now()}-${ticketId}`,
    });
    if (!ok) {
      toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
      return;
    }
    toast(document.body, `${data.bascules} items gardés.`, 'succes');
    await rafraichir(main, store);
  } catch {
    toast(document.body, 'Acte injoignable.', 'erreur');
  }
}

function libelleActe(acte) {
  return {
    approuver: 'Approuver',
    rejeter: 'Rejeter',
    editer: 'Éditer',
    discuter: 'Discuter',
  }[acte] || acte;
}

function renderCarte(main, store, carte) {
  const panneau = main.querySelector('[data-carte="panneau"]');
  panneau.hidden = false;
  panneau.dataset.ticket = carte.ticket.id;
  main.querySelector('[data-carte="titre"]').textContent =
    `${carte.ticket.type} — ${carte.ticket.titre}`;
  const corps = main.querySelector('[data-carte="corps"]');
  corps.replaceChildren();
  const meta = document.createElement('p');
  meta.textContent =
    `État : ${carte.ticket.etat}`
    + (carte.ticket.expiry_at ? ` — expire ${rel(carte.ticket.expiry_at)}` : '')
    + (carte.ticket.defaut ? ` — défaut : ${carte.ticket.defaut}` : '');
  corps.append(meta);
  for (const champ of carte.champs) {
    const p = document.createElement('p');
    p.textContent = `${champ.titre} : ${champ.texte}`;
    corps.append(p);
  }
  const barre = document.createElement('div');
  barre.className = 'carte-actes';
  for (const acte of carte.boutons) {
    const bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.textContent = libelleActe(acte);
    if (acte === 'rejeter') {
      bouton.classList.add('danger');
    }
    bouton.addEventListener('click', () => agirTicket(main, store, carte.ticket.id, acte));
    barre.append(bouton);
  }
  corps.append(barre);
  if (carte.items.length > 0) {
    const titre = document.createElement('h3');
    titre.textContent = 'Items';
    corps.append(titre);
    const liste = document.createElement('ul');
    for (const item of carte.items) {
      const ligne = document.createElement('li');
      ligne.textContent = `${item.label} [${item.etat}] `;
      for (const acte of carte.items_actes) {
        const bouton = document.createElement('button');
        bouton.type = 'button';
        bouton.textContent = acte;
        bouton.dataset.item = item.id;
        bouton.addEventListener('click', () => agirItem(main, store, carte.ticket.id, item, acte));
        ligne.append(bouton);
      }
      liste.append(ligne);
    }
    corps.append(liste);
    const tous = document.createElement('button');
    tous.type = 'button';
    tous.textContent = 'Tout approuver';
    tous.addEventListener('click', () => toutApprouver(main, store, carte.ticket.id));
    corps.append(tous);
  }
  if (carte.events.length > 0) {
    const titre = document.createElement('h3');
    titre.textContent = 'Historique';
    corps.append(titre);
    const liste = document.createElement('ul');
    for (const event of carte.events) {
      liste.append(li(`${rel(event.ts)} · ${event.acteur} — ${event.kind}`));
    }
    corps.append(liste);
  }
}

async function chargerCarte(main, store, ticketId) {
  try {
    const res = await fetch(
      `/owner/api/ticket/carte?ticket=${encodeURIComponent(ticketId)}`,
      {cache: 'no-store'},
    );
    if (!res.ok) {
      return;
    }
    renderCarte(main, store, await res.json());
  } catch {
    // stream + retry manuel
  }
}

function renderListe(main, payload, sig, store) {
  const section = main.querySelector('[data-section="tickets"]');
  majOptionsTypes(main, payload.items);
  const filtres = lisFiltres(main);
  const liste = section.querySelector('[data-list="items"]');
  liste.replaceChildren();
  const gardes = appliqueFiltres(payload.items, filtres);
  if (gardes.length === 0) {
    liste.append(li('Aucun ticket pour ces filtres.'));
  }
  for (const item of gardes) {
    const ligne = document.createElement('li');
    const bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'lien-ticket';
    bouton.dataset.ticket = item.id;
    bouton.textContent =
      `${item.type} — ${item.titre} [${item.etat}]`
      + (item.urgent ? ' — URGENT' : '')
      + (item.expiry_at ? ` (${rel(item.expiry_at)})` : '');
    bouton.addEventListener('click', () => chargerCarte(main, store, item.id));
    ligne.append(bouton);
    liste.append(ligne);
  }
  section.dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-tickets');
  main.replaceChildren(tpl.content.cloneNode(true));
  const rendus = {
    tickets: renderListe,
  };
  const unsubs = Object.keys(rendus).map((section) =>
    store.subscribe(section, (payload, sg) => {
      rendus[section](main, payload, sg, store);
    }),
  );
  for (const filtre of main.querySelectorAll('[data-filtre]')) {
    filtre.addEventListener(filtre.tagName === 'INPUT' ? 'input' : 'change', () => {
      const env = store.get('tickets');
      if (env) {
        renderListe(main, env.payload, env.sig, store);
      }
    });
  }
  for (const [section, env] of store.all()) {
    if (rendus[section]) {
      rendus[section](main, env.payload, env.sig, store);
    }
  }
  return () => {
    unsubs.forEach((unsub) => unsub());
  };
}
