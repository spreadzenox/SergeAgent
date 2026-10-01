// Actions tickets & rendu carte (M1/M2/M3, sous-module de tickets.js).
import {
  confirmModal,
  li,
  promptModal,
  rel,
  toast,
} from '../components.js';
import {allerObjet} from '../libelles.js';
import {fetchState} from '../sse.js';

const OUTCOME_FR = {APPROVED: 'approuvé', REJECTED: 'rejeté', EDITED: 'édité', ACK: 'accusé réception'};
const ETAT_ITEM_FR = {keep: 'gardé', edit: 'à modifier', drop: 'jeté'};

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
      store?.apply(section, env.sig, env.payload);
    }
  } catch {
    // le stream reprendra au prochain tick
  }
  const ouverte = main.querySelector('[data-carte="panneau"]');
  if (ouverte && !ouverte.hidden) {
    await chargerCarte(main, store, ouverte.dataset.ticket);
  }
}

export async function agirTicket(main, store, ticketId, acte, options = []) {
  let charge = {ticket_id: ticketId, acte};
  if (acte === 'discuter_fil') acte = 'discuter';
  charge.acte = acte;
  if (['editer','discuter','reponse_libre','choix_qcm'].includes(acte)) {
    const estEdit = acte !== 'discuter';
    const valeurs = await promptModal(document.body, {
      title: libelleActe(acte),
      message: acte === 'editer' ? 'Décris la modification.' :
        (estEdit ? 'Choisis ou saisis ta réponse.' : 'Écris ton message.'),
      fields: [
        {
          nom: estEdit ? 'note' : 'message',
          label: acte === 'editer' ? 'Note : ' :
            (estEdit ? 'Réponse : ' : 'Message : '),
          defaut: '',
          requis: true,
          ...(acte === 'choix_qcm' ? {options} : {}),
        },
      ],
      confirm: estEdit ? libelleActe(acte) : 'Envoyer',
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
      title: `${libelleActe(acte)} ?`,
      message: `Ticket ${ticketId} — acte irréversible côté état.`,
      confirm: libelleActe(acte),
      danger: ['rejeter','abandonner','refuser','annuler'].includes(acte),
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
    toast(
      document.body,
      `Ticket ${OUTCOME_FR[data.outcome] || data.outcome}.`,
      'succes',
    );
    await rafraichir(main, store);
  } catch {
    toast(document.body, 'Acte injoignable.', 'erreur');
  }
}

export async function agirItem(main, store, ticketId, item, acte) {
  let charge = {item_id: item.id, acte};
  if (acte === 'modifier') {
    const valeurs = await promptModal(document.body, {
      title: 'Modifier ?',
      message: `Item actuel : ${item.label}`,
      fields: [
        {
          nom: 'valeur',
          label: 'Nouveau : ',
          defaut: item.label,
          requis: true,
        },
      ],
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
    toast(
      document.body,
      `Item ${ETAT_ITEM_FR[data.etat] || data.etat}.`,
      'succes',
    );
    await rafraichir(main, store);
  } catch {
    toast(document.body, 'Acte injoignable.', 'erreur');
  }
}

function libelleActe(acte) {
  return (
    {
      approuver: 'Approuver',
      rejeter: 'Rejeter',
      editer: 'Éditer',
      discuter: 'Discuter', discuter_fil: 'Discuter',
      approuver_version: 'Approuver la version', cest_fait: 'C’est fait',
      confirmer: 'Confirmer', ouvrir: 'Ouvrir',
      abandonner: 'Abandonner', refuser: 'Refuser', annuler: 'Annuler',
      accuse_reception: 'Accuser réception', choix_qcm: 'Choisir une réponse',
      reponse_libre: 'Répondre librement', tout_approuver: 'Tout approuver',
    }[acte] || acte
  );
}

export function renderCarte(main, store, carte) {
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
    + (carte.ticket.expiry_at
      ? ` — expire ${rel(carte.ticket.expiry_at)}`
      : '')
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
    if (acte === 'tout_approuver' && carte.items.length) continue;
    const bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.textContent = libelleActe(acte);
    if (acte === 'rejeter') {
      bouton.classList.add('danger');
    }
    bouton.addEventListener('click', async () => {
      if (bouton.disabled) return;
      bouton.disabled = true;
      try { await agirTicket(main, store, carte.ticket.id, acte, carte.options); }
      catch { toast(document.body, 'Acte injoignable.', 'erreur'); }
      finally { bouton.disabled = false; }
    });
    barre.append(bouton);
  }
  if (carte.options?.length) {
    const options = document.createElement('p');
    options.textContent = `Réponses proposées : ${carte.options.join(' ; ')}`;
    corps.append(options);
  }
  const fiche = document.createElement('button');
  fiche.type = 'button';
  fiche.textContent = 'Fiche complète';
  fiche.addEventListener('click', () => allerObjet('ticket', carte.ticket.id));
  barre.append(fiche);
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
        bouton.addEventListener('click', () =>
          agirItem(main, store, carte.ticket.id, item, acte)
        );
        ligne.append(bouton);
      }
      liste.append(ligne);
    }
    corps.append(liste);
    if (carte.boutons.includes('tout_approuver')) {
      const tous = document.createElement('button');
      tous.type = 'button';
      tous.textContent = 'Tout approuver';
      tous.addEventListener('click', async () => {
        tous.disabled = true;
        try { await agirTicket(main, store, carte.ticket.id, 'tout_approuver'); }
        finally { tous.disabled = false; }
      });
      corps.append(tous);
    }
  }
  if (carte.events.length > 0) {
    const titre = document.createElement('h3');
    titre.textContent = 'Historique';
    corps.append(titre);
    const liste = document.createElement('ul');
    for (const event of carte.events) {
      liste.append(li(`${rel(event.ts)} · ${event.acteur} — ${event.message || event.kind}`));
    }
    corps.append(liste);
  }
}

export async function chargerCarte(main, store, ticketId) {
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
