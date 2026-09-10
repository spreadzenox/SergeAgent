// Page P1 Système : canvas îlots + panneau drill-down + liste accessible.
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

function detailsScheduler(store) {
  const env = store.get('scheduler');
  if (!env || !env.payload) {
    return '';
  }
  const file = env.payload;
  if (!file.next) {
    const vide = file.ready === 0 && file.running === 0;
    return vide ? 'File vide.' : 'File coincée (voir En direct).';
  }
  return (
    `Prochain : ${file.next.kind}`
    + ` (${file.ready} prêts, ${file.running} en cours).`
  );
}

export function mount(main, store) {
  const tpl = document.getElementById('page-system');
  main.replaceChildren(tpl.content.cloneNode(true));
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

  const unsubs = [
    store.subscribe('ilots', () => {
      majListe();
      majPanneau();
    }),
    store.subscribe('scheduler', majPanneau),
  ];
  majListe();
  majPanneau();
  return () => {
    unsubs.forEach((unsub) => unsub());
    canvas.removeEventListener('click', choisirAuClic);
    boucleIlots.stop();
  };
}
