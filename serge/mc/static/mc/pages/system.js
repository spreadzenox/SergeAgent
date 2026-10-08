// Page P1 Système : canvas îlots + panneau drill-down + liste accessible.
import {afficherBoutons, brancherBoutons} from '../boutons.js';
import {fillList, li, rel} from '../components.js';
import {dispositionIlots, startIlots} from '../hud.js';
import {patchSection} from '../patch.js';

const SANTE_FR = {
  ok: 'En forme',
  degrade: 'Dégradé',
  erreur: 'En erreur',
  inconnu: 'Inconnu',
};

const ETATS_CAMPAGNE = {
  DRAFT: 'Brouillon',
  READY: 'Prête',
  RUNNING: 'En cours',
  PAUSED: 'En pause',
  FINISHED: 'Terminée',
  CANCELLED: 'Annulée',
};

function ilotsDuStore(store) {
  const env = store.get('ilots');
  return env && env.payload ? env.payload.items || [] : [];
}

function detailsScheduler(store) {
  const env = store.get('scheduler');
  if (!env || !env.payload) {
    return '';
  }
  const file = env.payload;
  if (!file.next) {
    const vide = file.ready === 0 && file.running === 0;
    if (vide) {
      return 'File vide.';
    }
    return file.attente || 'File coincée (voir En direct).';
  }
  return (
    `Prochain : ${file.next.kind}`
    + ` (${file.ready} prêts, ${file.running} en cours).`
  );
}

function renderScheduler(main, payload, sig) {
  patchSection(main, 'scheduler', sig, payload);
  const next = main.querySelector('#sys-next');
  if (!payload.next) {
    next.textContent =
      payload.ready === 0
        ? 'File vide, rien en attente.'
        : payload.attente || 'File coincée : revoir les ventures.';
  } else {
    const venture = payload.next.venture_id || 'sans venture';
    next.textContent = `Prochain : ${payload.next.kind} (${venture}).`;
  }
}

function renderCampagnes(main, payload, sig) {
  const section = main.querySelector('[data-section="campagnes"]');
  fillList(
    section.querySelector('[data-list="items"]'),
    payload.items,
    'Aucune campagne pour le moment.',
    (item) =>
      li(
        `${item.id} — ${ETATS_CAMPAGNE[item.state] || item.state}`
        + ` (${item.channel}, ${item.envoyes}/${item.touches} envoyés)`,
      ),
  );
  fillList(
    section.querySelector('[data-list="cooldowns"]'),
    payload.cooldowns,
    'Aucun compte en cooldown.',
    (item) =>
      li(`${item.venue} ${item.handle} — ${rel(item.jusqu_a)}.`),
  );
  section.dataset.sig = sig;
}

function trie(obj) {
  return Object.entries(obj).sort((a, b) => b[1] - a[1]);
}

function renderPopulation(main, payload, sig) {
  const section = main.querySelector('[data-section="population"]');
  fillList(
    section.querySelector('[data-list="contacts"]'),
    trie(payload.contacts),
    'Aucun contact.',
    ([etat, n]) => li(`${etat} : ${n}`),
  );
  fillList(
    section.querySelector('[data-list="ventures"]'),
    trie(payload.ventures),
    'Aucune venture.',
    ([cycle, n]) => li(`${cycle} : ${n}`),
  );
  section.dataset.sig = sig;
}

function renderEmail(main, payload, sig) {
  const section = main.querySelector('[data-section="email"]');
  fillList(
    section.querySelector('[data-list="statuts"]'),
    trie(payload.par_statut),
    'Aucun volume.',
    ([statut, n]) => li(`${statut} : ${n}`),
  );
  main.querySelector('#sys-email-acti').textContent =
    payload.derniere_activite
      ? `Dernière activité : ${rel(payload.derniere_activite)}.`
      : 'Aucune activité.';
  section.dataset.sig = sig;
}

const ETATS_CANAL = {branche: 'branché', prevu: 'pas branché sur ce serveur'};
const CANAUX = {email: 'e-mail', voice: 'appel'};
const SORTES = {first: 'premier message', reply: 'réponse', followup: 'relance'};
const STATUTS = {
  to_write: 'à rédiger',
  pending: 'à envoyer',
  sending: 'en cours d’envoi',
  sent: 'parti',
  failed: 'en échec',
  cancelled: 'annulé',
  attached: 'rattaché',
  unattached: 'non rattaché',
  ignored: 'ignoré',
};

function renderEssais(main, payload, sig) {
  const section = main.querySelector('[data-section="essais"]');
  fillList(
    section.querySelector('[data-list="canaux"]'),
    payload.canaux || [],
    'Aucun canal.',
    (c) => li(`${c.titre} : ${ETATS_CANAL[c.etat] || c.etat}${c.releve ? ` (relevé ${rel(c.releve)})` : ''}`),
  );
  afficherBoutons(
    section.querySelector('[data-essais="boutons"]'),
    payload.boutons || [],
    'Aucun bouton d’essai en base.',
  );
  const essai = payload.essai;
  section.querySelector('[data-essais="contact"]').textContent = essai
    ? `${essai.contact} — étape : ${essai.etape}.`
    : 'Aucun essai pour l’instant.';
  fillList(
    section.querySelector('[data-list="fil"]'),
    essai ? essai.fil : [],
    'Rien n’est encore parti ni arrivé.',
    (e) => li(`${rel(e.heure)} · ${e.sens} · ${CANAUX[e.canal] || e.canal} · ${SORTES[e.sorte] || e.sorte} · ${STATUTS[e.statut] || e.statut}${e.detail ? ` — ${e.detail}` : ''}`),
  );
  section.dataset.sig = sig;
}

function renderNonRattaches(main, payload, sig) {
  const section = main.querySelector('[data-section="non_rattaches"]');
  fillList(
    section.querySelector('[data-list="messages"]'),
    payload.items || [],
    'Aucun message non rattaché.',
    (m) => li(`${rel(m.heure)} · ${m.canal} · ${m.expediteur} · ${m.objet} — ${m.extrait}`),
  );
  section.dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-system');
  main.replaceChildren(tpl.content.cloneNode(true));
  // La tâche placée, le flux de Mission Control montre la suite.
  brancherBoutons(main.querySelector('[data-essais="boutons"]'), async () => {});
  let choisi = 'scheduler';
  const canvas = main.querySelector('[data-hud="ilots"]');
  const etat = () => ({items: ilotsDuStore(store), choisi});
  const boucleIlots = startIlots(canvas, etat);

  function ilotChoisi() {
    const items = ilotsDuStore(store);
    return items.find((ilot) => ilot.id === choisi) || items[0] || null;
  }

  function majPanneau() {
    const ilot = ilotChoisi();
    if (!ilot) {
      return;
    }
    main.querySelector('[data-ilot="label"]').textContent = ilot.label;
    const sante = main.querySelector('[data-ilot="sante"]');
    sante.textContent = SANTE_FR[ilot.sante] || ilot.sante;
    sante.dataset.niveau = ilot.sante;
    main.querySelector('[data-ilot="resume"]').textContent = ilot.resume;
    const noeudDetails = main.querySelector('[data-ilot="details"]');
    noeudDetails.textContent =
      ilot.id === 'scheduler' ? detailsScheduler(store) : '';
  }

  function majListe() {
    const section = main.querySelector('[data-section="ilots"]');
    const env = store.get('ilots');
    if (env) {
      section.dataset.sig = env.sig;
    }
    const liste = main.querySelector('[data-ilots="liste"]');
    liste.replaceChildren();
    for (const ilot of ilotsDuStore(store)) {
      const item = document.createElement('li');
      const bouton = document.createElement('button');
      bouton.type = 'button';
      bouton.className = 'ilot-btn';
      bouton.dataset.ilot = ilot.id;
      bouton.dataset.niveau = ilot.sante;
      if (ilot.id === choisi) {
        bouton.classList.add('actif');
      }
      bouton.textContent =
        `${ilot.label} — ${SANTE_FR[ilot.sante] || ilot.sante}`;
      bouton.addEventListener('click', () => {
        choisi = ilot.id;
        majListe();
        majPanneau();
      });
      item.append(bouton);
      liste.append(item);
    }
  }

  function choisirAuClic(event) {
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * (canvas.width / rect.width);
    const y = (event.clientY - rect.top) * (canvas.height / rect.height);
    const items = ilotsDuStore(store);
    const pos = dispositionIlots(items.length, canvas.width, canvas.height);
    items.forEach((ilot, i) => {
      const rayon = 26 + (ilot.activite || 0) * 14 + 10;
      const dx = x - pos[i].x;
      const dy = y - pos[i].y;
      if (dx * dx + dy * dy <= rayon * rayon) {
        choisi = ilot.id;
        majListe();
        majPanneau();
      }
    });
  }
  canvas.addEventListener('click', choisirAuClic);

  const rendus = {
    scheduler: renderScheduler,
    campagnes: renderCampagnes,
    population: renderPopulation,
    email: renderEmail,
    non_rattaches: renderNonRattaches,
    essais: renderEssais,
  };
  const unsubs = [
    store.subscribe('ilots', () => {
      majListe();
      majPanneau();
    }),
    store.subscribe('scheduler', (payload, sg) => {
      majPanneau();
      renderScheduler(main, payload, sg);
    }),
    store.subscribe('campagnes', (payload, sg) => {
      renderCampagnes(main, payload, sg);
    }),
    store.subscribe('population', (payload, sg) => {
      renderPopulation(main, payload, sg);
    }),
    store.subscribe('email', (payload, sg) => {
      renderEmail(main, payload, sg);
    }),
    store.subscribe('non_rattaches', (payload, sg) => {
      renderNonRattaches(main, payload, sg);
    }),
    store.subscribe('essais', (payload, sg) => {
      renderEssais(main, payload, sg);
    }),
  ];
  majListe();
  majPanneau();
  for (const [section, env] of store.all()) {
    if (rendus[section]) {
      rendus[section](main, env.payload, env.sig);
    }
  }
  return () => {
    unsubs.forEach((unsub) => unsub());
    canvas.removeEventListener('click', choisirAuClic);
    boucleIlots.stop();
  };
}
