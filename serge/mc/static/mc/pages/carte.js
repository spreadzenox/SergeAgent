// Page Carte : tout le pipeline à plat, tel qu’il est en base.
// Le serveur pose les cases (serge/mc/carte_plan.py) ; ici on les dessine,
// on se déplace dessus, et on ouvre le détail d’une case, d’une table ou
// d’un lien. La carte se redessine quand le pipeline change en base ;
// l’état de la dernière exécution arrive à part, bien plus souvent.
import {allerObjet} from '../libelles.js';
import {ficheCase, ficheLien, ficheTable} from './carte_fiche.js';
import {STATUTS, dessinerCase, icone, majEtat} from './carte_case.js';

const SVG = 'http://www.w3.org/2000/svg';
const ONGLETS = {principal: 'Pipeline principal', essais: 'Essais et boutons'};
const ZOOM_MIN = 0.12;
const ZOOM_MAX = 1.6;

function el(tag, classe, texte) {
  const node = document.createElement(tag);
  if (classe) node.className = classe;
  if (texte) node.textContent = texte;
  return node;
}

function svg(tag, attrs) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) node.setAttribute(k, v);
  return node;
}

// Le milieu du bord droit (sortie) ou gauche (entrée) de la carte d’une case.
function ancre(c, sortie) {
  return {x: c.x + (sortie ? c.w : 0), y: c.y + c.carte_y + 34};
}

// Le tracé d’un trait : une courbe de gauche à droite ; un lien qui revient
// en arrière, ou qui descend dans la même colonne, passe par-dessous.
function trace(de, vers) {
  const a = ancre(de, true);
  const b = ancre(vers, false);
  if (b.x > a.x + 20) {
    const m = (b.x - a.x) / 2;
    return `M${a.x} ${a.y} C${a.x + m} ${a.y} ${b.x - m} ${b.y} ${b.x} ${b.y}`;
  }
  const bas = Math.max(de.y + de.h, vers.y + vers.h) + 26;
  return `M${a.x} ${a.y} C${a.x + 70} ${a.y} ${a.x + 70} ${bas} ${a.x - 20} ${bas}`
    + ` L${b.x + 20} ${bas} C${b.x - 70} ${bas} ${b.x - 70} ${b.y} ${b.x} ${b.y}`;
}

function classesDuTrait(lien) {
  const classes = ['carte-trait', lien.sorte];
  if (lien.couloir === 'trial') classes.push('essai');
  if (lien.sorte === 'lien' && !lien.auto) classes.push('manuel');
  if (lien.sorte === 'lien' && !lien.allume) classes.push('eteint');
  return classes.join(' ');
}

export function mount(main, store) {
  const tpl = document.getElementById('page-carte');
  main.replaceChildren(tpl.content.cloneNode(true));
  const q = (nom) => main.querySelector(`[data-carte="${nom}"]`);
  const vue = q('vue');
  const plan = q('plan');
  const fiche = q('fiche');
  let carte = null;
  let etat = {};
  let onglet = 'principal';
  let choix = null;
  // La vue de chaque onglet : où on est, et à quelle échelle.
  const vues = {};
  const v = () => vues[onglet] || (vues[onglet] = {x: 12, y: 12, k: 0.8});

  function appliquerVue() {
    const {x, y, k} = v();
    plan.style.transform = `translate(${x}px, ${y}px) scale(${k})`;
    q('echelle').textContent = `${Math.round(k * 100)} %`;
  }

  function zoomer(facteur, cx, cy) {
    const vu = v();
    const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, vu.k * facteur));
    // Le point sous le curseur ne bouge pas.
    vu.x = cx - ((cx - vu.x) * k) / vu.k;
    vu.y = cy - ((cy - vu.y) * k) / vu.k;
    vu.k = k;
    appliquerVue();
  }

  function toutVoir() {
    const data = carte && carte[onglet];
    if (!data) return;
    const boite = vue.getBoundingClientRect();
    const k = Math.min(
      ZOOM_MAX,
      Math.max(ZOOM_MIN, Math.min(boite.width / data.largeur, boite.height / data.hauteur)),
    );
    vues[onglet] = {x: (boite.width - data.largeur * k) / 2, y: 8, k};
    appliquerVue();
  }

  function centrerSur(c) {
    const boite = vue.getBoundingClientRect();
    const vu = v();
    vu.k = Math.max(vu.k, 0.7);
    vu.x = boite.width / 2 - (c.x + c.w / 2) * vu.k;
    vu.y = boite.height / 2 - (c.y + c.h / 2) * vu.k;
    appliquerVue();
  }

  const cases = () => (carte && carte[onglet] ? carte[onglet].noeuds : []);
  const laCase = (id) => cases().find((c) => c.id === id);

  // Ce qui est choisi ressort, le reste s’efface un peu.
  function eclairer() {
    plan.classList.toggle('carte-attenue', Boolean(choix));
    plan.querySelectorAll('.choisie, .voisine, .vif').forEach((n) => {
      n.classList.remove('choisie', 'voisine', 'vif');
    });
    if (!choix) return;
    const data = carte[onglet];
    const allume = (id, classe) => {
      const n = plan.querySelector(`.carte-case[data-id="${CSS.escape(id)}"]`);
      if (n) n.classList.add(classe);
    };
    if (choix.sorte === 'table') {
      plan.querySelectorAll(`.carte-table[data-table="${CSS.escape(choix.table)}"]`).forEach((n) => {
        n.classList.add('vif');
        n.closest('.carte-case').classList.add('voisine');
      });
      if (choix.id) allume(choix.id, 'choisie');
      return;
    }
    const liens = data.liens.filter((l) =>
      choix.sorte === 'lien' ? l.id === choix.id : l.de === choix.id || l.vers === choix.id,
    );
    for (const lien of liens) {
      plan.querySelectorAll(`[data-lien="${CSS.escape(lien.id)}"]`).forEach((n) => n.classList.add('vif'));
      allume(lien.de, 'voisine');
      allume(lien.vers, 'voisine');
    }
    if (choix.sorte === 'case') allume(choix.id, 'choisie');
  }

  function montrerFiche() {
    fiche.hidden = !choix;
    if (!choix) return;
    const data = carte[onglet];
    const outils = {
      aller: (id) => choisir({sorte: 'case', id}, true),
      table: (table, id) => choisir({sorte: 'table', table, id}),
      ouvrir: allerObjet,
      fermer: () => choisir(null),
    };
    let contenu = null;
    if (choix.sorte === 'case' && laCase(choix.id)) {
      contenu = ficheCase(laCase(choix.id), data, etat[choix.id], outils);
    } else if (choix.sorte === 'table') {
      contenu = ficheTable(choix.table, choix.id && laCase(choix.id), data, outils);
    } else if (choix.sorte === 'lien') {
      const lien = data.liens.find((l) => l.id === choix.id);
      contenu = lien && ficheLien(lien, data, outils);
    }
    if (!contenu) {
      choix = null;
      fiche.hidden = true;
      return;
    }
    fiche.replaceChildren(contenu);
  }

  function choisir(nouveau, centrer) {
    choix = nouveau;
    montrerFiche();
    eclairer();
    if (centrer && choix && choix.sorte === 'case' && laCase(choix.id)) {
      centrerSur(laCase(choix.id));
    }
  }

  function dessiner() {
    const data = carte && carte[onglet];
    plan.replaceChildren();
    main.querySelectorAll('[data-onglet]').forEach((b) => {
      const actif = b.dataset.onglet === onglet;
      b.setAttribute('aria-selected', actif ? 'true' : 'false');
      const n = carte && carte[b.dataset.onglet] ? carte[b.dataset.onglet].noeuds.length : 0;
      b.textContent = `${ONGLETS[b.dataset.onglet]} · ${n}`;
    });
    q('vide').hidden = Boolean(data && data.noeuds.length);
    if (!data) return;
    plan.style.width = `${data.largeur}px`;
    plan.style.height = `${data.hauteur}px`;
    for (const bande of data.bandes) {
      const boite = el('div', 'carte-bande');
      boite.style.left = `${bande.x}px`;
      boite.style.top = `${bande.y}px`;
      boite.style.width = `${bande.w}px`;
      boite.style.height = `${bande.h}px`;
      const tete = el('div', 'carte-bande-tete');
      tete.append(el('h3', '', bande.titre));
      if (bande.sous_titre) tete.append(el('p', '', bande.sous_titre));
      boite.append(tete);
      plan.append(boite);
    }
    const traits = svg('svg', {
      class: 'carte-traits',
      width: data.largeur,
      height: data.hauteur,
      viewBox: `0 0 ${data.largeur} ${data.hauteur}`,
    });
    const defs = svg('defs');
    for (const nom of ['lien', 'mission', 'essai']) {
      const fleche = svg('marker', {
        id: `fleche-${nom}`, class: `carte-fleche ${nom}`, viewBox: '0 0 10 10',
        refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse',
      });
      fleche.append(svg('path', {d: 'M0 0 L10 5 L0 10 z'}));
      defs.append(fleche);
    }
    traits.append(defs);
    const parId = new Map(data.noeuds.map((c) => [c.id, c]));
    for (const lien of data.liens) {
      const de = parId.get(lien.de);
      const vers = parId.get(lien.vers);
      if (!de || !vers) continue;
      const d = trace(de, vers);
      const nom = lien.couloir === 'trial' ? 'essai' : lien.sorte;
      const dessin = svg('path', {
        d, class: classesDuTrait(lien), 'data-lien': lien.id, 'marker-end': `url(#fleche-${nom})`,
      });
      // Un trait fin se vise mal : une zone large et invisible prend le clic.
      const prise = svg('path', {d, class: 'carte-prise', 'data-lien': lien.id});
      const bulle = svg('title');
      bulle.textContent = lien.titre + (lien.condition ? ` (si ${lien.condition})` : '');
      prise.append(bulle);
      prise.addEventListener('click', () => choisir({sorte: 'lien', id: lien.id}));
      traits.append(dessin, prise);
    }
    plan.append(traits);
    for (const c of data.noeuds) {
      plan.append(
        dessinerCase(c, etat[c.id], {
          case: () => choisir({sorte: 'case', id: c.id}),
          table: (table) => choisir({sorte: 'table', table, id: c.id}),
        }),
      );
    }
    appliquerVue();
    montrerFiche();
    eclairer();
  }

  function changerOnglet(nom) {
    onglet = nom;
    choix = null;
    dessiner();
  }

  // Se déplacer : on tire le fond ; la molette zoome sous le curseur.
  let tire = null;
  vue.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0 || ev.target.closest('button, a, input, .carte-prise')) return;
    tire = {x: ev.clientX, y: ev.clientY, vx: v().x, vy: v().y, bouge: false};
    vue.setPointerCapture(ev.pointerId);
    vue.classList.add('carte-tire');
  });
  vue.addEventListener('pointermove', (ev) => {
    if (!tire) return;
    const dx = ev.clientX - tire.x;
    const dy = ev.clientY - tire.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) tire.bouge = true;
    v().x = tire.vx + dx;
    v().y = tire.vy + dy;
    appliquerVue();
  });
  const lacher = (ev) => {
    if (!tire) return;
    // Un clic sur le fond, sans tirer, referme le détail.
    if (!tire.bouge && ev.type === 'pointerup') choisir(null);
    tire = null;
    vue.classList.remove('carte-tire');
  };
  vue.addEventListener('pointerup', lacher);
  vue.addEventListener('pointercancel', lacher);
  vue.addEventListener(
    'wheel',
    (ev) => {
      ev.preventDefault();
      const boite = vue.getBoundingClientRect();
      zoomer(ev.deltaY < 0 ? 1.15 : 1 / 1.15, ev.clientX - boite.left, ev.clientY - boite.top);
    },
    {passive: false},
  );
  vue.addEventListener('keydown', (ev) => {
    const pas = {ArrowLeft: [60, 0], ArrowRight: [-60, 0], ArrowUp: [0, 60], ArrowDown: [0, -60]}[ev.key];
    const boite = vue.getBoundingClientRect();
    if (pas) {
      v().x += pas[0];
      v().y += pas[1];
      appliquerVue();
    } else if (ev.key === '+' || ev.key === '=') {
      zoomer(1.2, boite.width / 2, boite.height / 2);
    } else if (ev.key === '-') {
      zoomer(1 / 1.2, boite.width / 2, boite.height / 2);
    } else if (ev.key === 'Escape') {
      choisir(null);
    } else {
      return;
    }
    ev.preventDefault();
  });
  const milieu = () => {
    const boite = vue.getBoundingClientRect();
    return [boite.width / 2, boite.height / 2];
  };
  q('plus').addEventListener('click', () => zoomer(1.25, ...milieu()));
  q('moins').addEventListener('click', () => zoomer(1 / 1.25, ...milieu()));
  q('tout').addEventListener('click', toutVoir);
  main.querySelectorAll('[data-onglet]').forEach((b) => {
    b.addEventListener('click', () => changerOnglet(b.dataset.onglet));
  });

  // Chercher : une invocation par son titre, ou une table par son nom.
  const chercher = q('chercher');
  const trouver = () => {
    const mot = chercher.value.trim().toLowerCase();
    plan.querySelectorAll('.trouvee').forEach((n) => n.classList.remove('trouvee'));
    q('trouvees').textContent = '';
    if (!mot) return [];
    const trouvees = cases().filter(
      (c) =>
        `${c.titre} ${c.id}`.toLowerCase().includes(mot)
        || [...c.lit, ...c.ecrit].some((t) => `${t.table} ${t.titre}`.toLowerCase().includes(mot)),
    );
    for (const c of trouvees) {
      const n = plan.querySelector(`.carte-case[data-id="${CSS.escape(c.id)}"]`);
      if (n) n.classList.add('trouvee');
    }
    q('trouvees').textContent = `${trouvees.length} trouvée(s)`;
    return trouvees;
  };
  let rang = 0;
  chercher.addEventListener('input', () => {
    rang = 0;
    const trouvees = trouver();
    if (trouvees.length) centrerSur(trouvees[0]);
  });
  chercher.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter') return;
    const trouvees = trouver();
    if (!trouvees.length) return;
    rang = (rang + 1) % trouvees.length;
    centrerSur(trouvees[rang]);
  });

  const legende = q('legende');
  for (const [statut, texte] of Object.entries(STATUTS)) {
    const item = el('span', 'carte-legende-item');
    const pastille = el('i', 'carte-etat');
    pastille.dataset.statut = statut;
    item.append(pastille, texte);
    legende.append(item);
  }
  const base = el('span', 'carte-legende-item');
  base.append(icone(), 'une table : au-dessus de la carte elle est lue, en dessous elle est écrite');
  legende.append(base);

  const surCarte = (payload) => {
    carte = payload;
    dessiner();
    trouver();
  };
  const surEtat = (payload) => {
    etat = (payload && payload.invocations) || {};
    majEtat(plan, etat);
    if (choix && choix.sorte === 'case') montrerFiche();
  };
  const fins = [store.subscribe('carte', surCarte), store.subscribe('carte_etat', surEtat)];
  for (const [section, env] of store.all()) {
    if (section === 'carte_etat') surEtat(env.payload);
  }
  for (const [section, env] of store.all()) {
    if (section === 'carte') surCarte(env.payload);
  }
  // « il y a 3 min » vieillit tout seul : on le récrit de temps en temps.
  const horloge = setInterval(() => majEtat(plan, etat), 30000);
  return () => {
    fins.forEach((fin) => fin());
    clearInterval(horloge);
  };
}
