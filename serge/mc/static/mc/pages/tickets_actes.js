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

const OUTCOME_FR = {APPROVED: 'approuvé', REJECTED: 'rejeté', EDITED: 'édité', DISCUSSING: 'en réécriture'};

export async function poster(chemin, charge) {
  const res = await fetch(chemin, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(charge),
  });
  return {ok: res.ok, data: await res.json()};
}

export async function rafraichir(main, store) {
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

export async function agirTicket(main, store, ticketId, acte, message = {}) {
  let charge = {ticket_id: ticketId, acte};
  if (acte === 'discuter_fil') acte = 'discuter';
  charge.acte = acte;
  if (['editer','discuter','reponse_libre','ma_reponse','reecrire','a_corriger','revoir_plan','choisir_autre'].includes(acte)) {
    const estEdit = acte !== 'discuter';
    const consignes = {
      editer: ['Décris la modification.', 'Note : '],
      ma_reponse: ['Le message qui partira au contact, tel quel.', 'Réponse : '],
      reecrire: ['Tes consignes : Serge réécrit, et le brouillon revient ici.', 'Consignes : '],
      a_corriger: ['Ce qu’il faut corriger : tes consignes repartent à Serge.', 'Consignes : '],
      revoir_plan: ['Ce que le produit doit faire d’autre : le plan repart en conception, puis chez le critique.', 'Consignes : '],
      choisir_autre: ['Le nom du business voulu, tel qu’il est écrit dans le ticket.', 'Business : '],
    }[acte];
    // « Ma réponse » et « Éditer » s'ouvrent avec le message dont parle le
    // ticket : son texte, et son objet s'il en a un.
    const reprend = ['ma_reponse', 'editer'].includes(acte) && message.texte !== undefined;
    const valeurs = await promptModal(document.body, {
      title: libelleActe(acte),
      message: consignes ? consignes[0] :
        (estEdit ? 'Écris ta réponse.' : 'Écris ton message.'),
      fields: [
        ...(reprend && message.objet
          ? [{nom: 'objet', label: 'Objet : ', defaut: message.objet, requis: true}]
          : []),
        {
          nom: estEdit ? 'note' : 'message',
          label: consignes ? consignes[1] :
            (estEdit ? 'Réponse : ' : 'Message : '),
          defaut: reprend ? message.texte : '',
          requis: true,
          multiligne: reprend,
        },
      ],
      confirm: estEdit ? libelleActe(acte) : 'Envoyer',
    });
    if (!valeurs) {
      return;
    }
    charge = {
      ...charge,
      ...(estEdit ? {note: valeurs.note} : {}),
      ...(valeurs.objet ? {objet: valeurs.objet} : {}),
    };
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
      danger: ['rejeter','abandonner','ne_rien_envoyer','arreter_business','aucun'].includes(acte),
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

export function libelleActe(acte) {
  return (
    {
      approuver: 'Approuver',
      rejeter: 'Rejeter',
      editer: 'Éditer',
      discuter: 'Discuter', discuter_fil: 'Discuter',
      cest_fait: 'C’est fait', abandonner: 'Abandonner',
      reponse_libre: 'Répondre librement',
      envoyer_brouillon: 'Envoyer le brouillon', ma_reponse: 'Ma réponse',
      reecrire: 'Réécrire', ne_rien_envoyer: 'Ne rien envoyer',
      passer: 'Passer à la suite', ne_pas_passer: 'Ne pas passer',
      valider: 'Valider', a_corriger: 'À corriger', revoir_plan: 'Revoir le plan',
      arreter_business: 'Arrêter le business', faire_sans: 'Faire sans', pret: 'Je suis prêt',
      choisir_autre: 'Choisir un autre', aucun: 'Aucun',
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
    const bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.textContent = libelleActe(acte);
    if (acte === 'rejeter') {
      bouton.classList.add('danger');
    }
    bouton.addEventListener('click', async () => {
      if (bouton.disabled) return;
      bouton.disabled = true;
      try { await agirTicket(main, store, carte.ticket.id, acte, carte.message); }
      catch { toast(document.body, 'Acte injoignable.', 'erreur'); }
      finally { bouton.disabled = false; }
    });
    barre.append(bouton);
  }
  const fiche = document.createElement('button');
  fiche.type = 'button';
  fiche.textContent = 'Fiche complète';
  fiche.addEventListener('click', () => allerObjet('ticket', carte.ticket.id));
  barre.append(fiche);
  corps.append(barre);
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
