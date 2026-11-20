// Page P1 Système : canvas îlots + panneau drill-down + liste accessible.
import {afficherBoutons, brancherBoutons} from '../boutons.js';
import {confirmModal, fillList, li, rel, toast} from '../components.js';
import {dispositionIlots, startIlots} from '../hud.js';

const SANTE_FR = {
  ok: 'En forme',
  degrade: 'Dégradé',
  erreur: 'En erreur',
  inconnu: 'Inconnu',
};

function ilotsDuStore(store) {
  const env = store.get('ilots');
  return env && env.payload ? env.payload.items || [] : [];
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
  afficherBoutons(
    section.querySelector('[data-essais="boutons"]'),
    payload.boutons || [],
    'Aucun bouton d’essai en base.',
  );
  const essai = payload.essai;
  const business = essai && essai.business;
  section.querySelector('[data-essais="etat"]').textContent = essai
    ? `${essai.en_cours ? 'En cours' : 'Arrêté ou fini'}, lancé ${rel(essai.lance)}, à partir de l’étape ${essai.depart}${business ? ` — ${business.nom} : ${business.statut}` : ''}.`
    : 'Aucun essai pour l’instant.';
  section.querySelector('[data-essais="arreter"]').hidden = !(essai && essai.en_cours);
  fillList(
    section.querySelector('[data-list="tickets-essai"]'),
    essai ? essai.tickets : [],
    'Aucun ticket d’essai n’attend.',
    (t) => lienVers(`#/objet/ticket/${t.id}`, t.titre),
  );
  fillList(
    section.querySelector('[data-list="taches-essai"]'),
    essai ? essai.taches : [],
    'Aucune tâche.',
    (t) => ligneTache(t, essai.en_cours),
  );
  section.querySelector('[data-essais="contact"]').textContent = essai && essai.contact
    ? `${essai.contact} — étape : ${essai.etape}.`
    : '';
  fillList(
    section.querySelector('[data-list="fil"]'),
    essai ? essai.fil : [],
    'Rien n’est encore parti ni arrivé.',
    (e) => li(`${rel(e.heure)} · ${e.sens} · ${CANAUX[e.canal] || e.canal} · ${SORTES[e.sorte] || e.sorte} · ${STATUTS[e.statut] || e.statut}${e.detail ? ` — ${e.detail}` : ''}`),
  );
  section.dataset.sig = sig;
}

function lienVers(adresse, texte) {
  const item = document.createElement('li');
  const lien = document.createElement('a');
  lien.href = adresse;
  lien.textContent = texte;
  item.append(lien);
  return item;
}

// Une tâche de l’essai : son heure, son titre (lien vers sa fiche), son
// état, et « Repartir d’ici » si elle n’attend pas et ne tourne pas.
function ligneTache(tache, enCours) {
  const item = lienVers(`#/objet/task/${tache.id}`, tache.titre);
  item.prepend(`${rel(tache.heure)} · `);
  item.append(` · ${tache.etat}${tache.erreur ? ` — ${tache.erreur}` : ''} `);
  if (enCours && !['ready', 'running'].includes(tache.statut)) {
    const bouton = document.createElement('button');
    bouton.type = 'button';
    bouton.className = 'btn-doux';
    bouton.dataset.repartir = tache.id;
    bouton.textContent = 'Repartir d’ici';
    item.append(bouton);
  }
  return item;
}

async function poster(route, charge, question) {
  const ok = await confirmModal(document.body, question);
  if (!ok) {
    return;
  }
  try {
    const response = await fetch(route, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(charge),
    });
    const data = await response.json().catch(() => ({}));
    toast(document.body, response.ok ? 'C’est fait.' : (data.erreur || 'Refusé.'), response.ok ? 'succes' : 'erreur');
  } catch {
    toast(document.body, 'Action injoignable. Réessaie.', 'erreur');
  }
}

function brancherEssai(section) {
  section.addEventListener('click', (ev) => {
    const repartir = ev.target.closest('[data-repartir]');
    if (repartir) {
      poster('/owner/api/tache/repartir', {task_id: repartir.dataset.repartir}, {
        title: 'Repartir d’ici ?',
        message: 'Une tâche neuve, copie de celle-ci, part dans sa file, et toute sa suite repart avec elle. Ce que l’ancienne avait laissé en attente (des tâches, des tickets) est annulé.',
        confirm: 'Repartir d’ici',
      });
    }
    if (ev.target.closest('[data-essais="arreter"]')) {
      poster('/owner/api/essai/arreter', {}, {
        title: 'Arrêter l’essai ?',
        message: 'Ses tâches en attente sont annulées, ses tickets fermés, et son business arrêté. Une tâche en cours finit, mais sa suite ne part pas. Ce qui est en ligne reste.',
        confirm: 'Arrêter l’essai',
        danger: true,
      });
    }
  });
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

function renderComptesWeb(main, payload, sig) {
  const section = main.querySelector('[data-section="comptes_web"]');
  section.querySelector('[data-comptes="plafond"]').textContent =
    `Au plus ${payload.plafond} actions par jour et par compte (page Policy, « Comptes web »).`;
  fillList(
    section.querySelector('[data-list="comptes-web"]'),
    payload.comptes || [],
    'Aucun compte pour l’instant.',
    (c) => {
      const item = lienVers(
        `#/objet/compte/${c.id}`,
        `${c.id} — ${c.identifiant || 'sans identifiant'} — ${c.etat}, ${c.session ? 'session gardée' : 'sans session'}, ${c.actions} action(s) aujourd’hui — ${c.site}`,
      );
      if (c.retirable) {
        const bouton = document.createElement('button');
        bouton.type = 'button';
        bouton.className = 'btn-doux';
        bouton.dataset.retirer = c.id;
        bouton.textContent = 'Retirer';
        item.append(' ', bouton);
      }
      return item;
    },
  );
  afficherBoutons(
    section.querySelector('[data-comptes="boutons"]'),
    payload.boutons || [],
    'Aucun bouton de compte en base.',
  );
  section.dataset.sig = sig;
}

// « Enregistrer un compte qui existe déjà » : le mot de passe part chiffré
// en base et ne revient jamais.
function brancherComptes(section) {
  section.addEventListener('click', (ev) => {
    const bouton = ev.target.closest('[data-retirer]');
    if (bouton) {
      const compte = bouton.dataset.retirer;
      poster('/owner/api/compte/retirer', {compte}, {
        title: `Retirer le compte « ${compte} » ?`,
        message: 'Sa ligne, son mot de passe et sa session gardés par Serge sont effacés. Le compte lui-même, s’il existe sur le site, n’est pas touché.',
        confirm: 'Retirer le compte',
        danger: true,
      });
    }
  });
  const form = section.querySelector('[data-comptes="enregistrer"]');
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    try {
      const response = await fetch('/owner/api/compte/enregistrer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        form.reset();
      }
      toast(
        document.body,
        response.ok ? `Compte « ${data.compte} » enregistré.` : (data.erreur || 'Refusé.'),
        response.ok ? 'succes' : 'erreur',
      );
    } catch {
      toast(document.body, 'Action injoignable. Réessaie.', 'erreur');
    }
  });
}

export function mount(main, store) {
  const tpl = document.getElementById('page-system');
  main.replaceChildren(tpl.content.cloneNode(true));
  // La tâche placée, le flux de Mission Control montre la suite.
  brancherBoutons(main.querySelector('[data-essais="boutons"]'), async () => {});
  brancherBoutons(main.querySelector('[data-comptes="boutons"]'), async () => {});
  brancherComptes(main.querySelector('[data-section="comptes_web"]'));
  brancherEssai(main.querySelector('[data-section="essais"]'));
  let choisi = 'taches';
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
    main.querySelector('[data-ilot="details"]').replaceChildren(
      ...(ilot.details || []).map((ligne) => li(ligne)),
    );
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
    population: renderPopulation,
    non_rattaches: renderNonRattaches,
    essais: renderEssais,
    comptes_web: renderComptesWeb,
  };
  const unsubs = [
    store.subscribe('ilots', () => {
      majListe();
      majPanneau();
    }),
    store.subscribe('population', (payload, sg) => {
      renderPopulation(main, payload, sg);
    }),
    store.subscribe('non_rattaches', (payload, sg) => {
      renderNonRattaches(main, payload, sg);
    }),
    store.subscribe('essais', (payload, sg) => {
      renderEssais(main, payload, sg);
    }),
    store.subscribe('comptes_web', (payload, sg) => {
      renderComptesWeb(main, payload, sg);
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
