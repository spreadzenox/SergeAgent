// La page telle que la lit un lecteur d'écran, une ligne par élément.
// Chaque élément sur lequel on peut agir reçoit un repère (data-serge-ref,
// « e7 ») que l'invocation cite pour cliquer ou taper : un lien, un bouton,
// un champ, mais aussi tout ce qui se clique sans être un vrai bouton (un
// bloc avec un clic, un onglet, une entrée de menu). Un tel élément a son
// repère où qu'il soit : dans un titre, un paragraphe, un composant web
// (shadow DOM). Un cadre intégré (iframe) a le sien ; son contenu est lu à
// part, avec des repères qui commencent par celui du cadre (« e7.e2 »).
// Un élément garde son repère d'une lecture à l'autre, tant qu'il est dans
// la page : un repère lu plus tôt ne désigne jamais un autre élément.
// Lancé par serge/sandbox/lecture.py.
(options) => {
  const maxLines = options.maxLines;
  const prefix = options.prefix || '';
  const maxChars = 200;
  const lines = [];
  // Le dernier numéro donné dans ce document, et les repères déjà vus dans
  // cette lecture (une page peut recopier un élément, repère compris).
  let count = window.__sergeDernierRepere || 0;
  const vus = new Set();
  const clean = (text) => (text || '').replace(/\s+/g, ' ').trim().slice(0, maxChars);
  // « non » : rien à lire ; « enfants » : l'élément n'a pas de boîte à lui
  // (display: contents, ou une racine de fenêtre modale haute de 0), mais
  // ses enfants peuvent se voir.
  const visible = (el) => {
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') {
      return 'non';
    }
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0 ? 'oui' : 'enfants';
  };
  const label = (el) => {
    if (el.id) {
      const lab = el.getRootNode().querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab) {
        return clean(lab.innerText);
      }
    }
    const parent = el.closest('label');
    if (parent) {
      return clean(parent.innerText);
    }
    return clean(
      el.getAttribute('aria-label') || el.getAttribute('placeholder')
      || el.getAttribute('title') || el.getAttribute('name') || '',
    );
  };
  const ref = (el) => {
    let repere = el.getAttribute('data-serge-ref') || '';
    if (!repere.startsWith(`${prefix}e`) || repere.slice(prefix.length).includes('.')
        || vus.has(repere)) {
      count += 1;
      repere = `${prefix}e${count}`;
      el.setAttribute('data-serge-ref', repere);
    }
    vus.add(repere);
    return `[${repere}]`;
  };
  const own = (el) => clean(
    [...el.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join(' '),
  );
  const ACTIONNABLE = 'a[href], button, input, select, textarea, summary, iframe,'
    + ' [role="button"], [role="link"], [role="tab"], [role="menuitem"], [onclick]';
  // Le texte d'un titre, sans celui des boutons et des liens qu'il contient
  // (ils ont leur propre ligne, juste après).
  const sansActions = (el) => {
    const parts = [];
    const visit = (node) => {
      for (const c of node.childNodes) {
        if (c.nodeType === 3) {
          parts.push(c.textContent);
        } else if (c.nodeType === 1 && !c.matches(ACTIONNABLE) && visible(c) !== 'non') {
          visit(c);
        }
      }
    };
    visit(el);
    return clean(parts.join(' '));
  };
  const ROLES = {
    link: 'lien', tab: 'onglet', menuitem: 'entrée de menu',
    menuitemcheckbox: 'entrée de menu', menuitemradio: 'entrée de menu',
    option: 'option', treeitem: 'entrée', switch: 'interrupteur',
    checkbox: 'case', radio: 'case à choix unique',
  };
  const pointer = (el) => getComputedStyle(el).cursor === 'pointer';
  // Ce qui se clique sans être un vrai bouton ni un vrai lien : son nom, ou ''.
  const cliquable = (el, tag, role) => {
    if (ROLES[role]) {
      return ROLES[role];
    }
    if (tag === 'summary') {
      return 'bouton';
    }
    if (el.hasAttribute('onclick') || typeof el.onclick === 'function') {
      return 'élément cliquable';
    }
    if (el.getAttribute('draggable') === 'true') {
      return 'élément à glisser';
    }
    // Le curseur « main » dit qu'un clic fait quelque chose ; on garde
    // l'élément le plus haut qui le porte, pas chacun de ses enfants.
    if (tag !== 'label' && pointer(el) && !(el.parentElement && pointer(el.parentElement))) {
      return 'élément cliquable';
    }
    return '';
  };
  const enfants = (el, muet) => {
    if (el.shadowRoot) {
      for (const child of el.shadowRoot.children) {
        walk(child, muet);
      }
    }
    for (const child of el.children) {
      walk(child, muet);
    }
  };
  // « muet » : le texte est déjà dit (par un titre, par un élément
  // cliquable) ; on ne garde que ce sur quoi on peut agir.
  const walk = (el, muet) => {
    if (lines.length >= maxLines || el.nodeType !== 1) {
      return;
    }
    const tag = el.tagName.toLowerCase();
    if (['script', 'style', 'noscript', 'template', 'svg', 'head'].includes(tag)) {
      return;
    }
    const vu = visible(el);
    if (vu === 'non') {
      return;
    }
    if (vu === 'enfants') {
      enfants(el, muet);
      return;
    }
    const role = el.getAttribute('role');
    if (/^h[1-6]$/.test(tag)) {
      if (!muet) {
        lines.push(`${'#'.repeat(Number(tag[1]))} ${sansActions(el) || clean(el.innerText)}`);
      }
      enfants(el, true);
      return;
    }
    if (tag === 'a' && el.getAttribute('href')) {
      lines.push(`${ref(el)} lien « ${clean(el.innerText) || label(el)} » → ${el.getAttribute('href')}`);
      return;
    }
    const kind = (el.getAttribute('type') || 'text').toLowerCase();
    if (tag === 'button' || role === 'button'
        || (tag === 'input' && ['submit', 'button', 'reset'].includes(kind))) {
      const grise = el.disabled || el.getAttribute('aria-disabled') === 'true' ? ' (grisé)' : '';
      lines.push(`${ref(el)} bouton « ${clean(el.innerText || el.value) || label(el)} »${grise}`);
      return;
    }
    if (tag === 'input') {
      if (kind === 'hidden') {
        return;
      }
      if (kind === 'checkbox' || kind === 'radio') {
        const etat = el.checked ? 'cochée' : 'vide';
        lines.push(`${ref(el)} case ${kind === 'radio' ? 'à choix unique ' : ''}« ${label(el)} » (${etat})`);
        return;
      }
      if (kind === 'file') {
        const noms = [...el.files].map((f) => f.name).join(', ');
        lines.push(`${ref(el)} champ fichier « ${label(el)} »${noms ? ` = ${clean(noms)}` : ' (vide)'}`);
        return;
      }
      const valeur = kind === 'password' ? (el.value ? '••••' : '') : clean(el.value);
      lines.push(`${ref(el)} champ ${kind} « ${label(el)} »${valeur ? ` = ${valeur}` : ' (vide)'}`);
      return;
    }
    if (tag === 'textarea') {
      const valeur = clean(el.value);
      lines.push(`${ref(el)} zone de texte « ${label(el)} »${valeur ? ` = ${valeur}` : ' (vide)'}`);
      return;
    }
    if (tag === 'select') {
      const choix = [...el.options].slice(0, 20).map((o) => clean(o.text)).join(' | ');
      const pris = clean(el.selectedOptions[0] ? el.selectedOptions[0].text : '');
      lines.push(`${ref(el)} liste « ${label(el)} » = ${pris} (choix : ${choix})`);
      return;
    }
    if (tag === 'iframe' || tag === 'frame') {
      lines.push(`${ref(el)} cadre « ${label(el) || clean(el.getAttribute('src'))} »`);
      return;
    }
    if (el.isContentEditable && !(el.parentElement && el.parentElement.isContentEditable)) {
      const valeur = clean(el.innerText);
      lines.push(`${ref(el)} zone de texte « ${label(el)} »${valeur ? ` = ${valeur}` : ' (vide)'}`);
      return;
    }
    if (tag === 'canvas') {
      const box = el.getBoundingClientRect();
      lines.push(
        `zone de dessin, de (${Math.round(box.left)}, ${Math.round(box.top)}) à`
        + ` (${Math.round(box.right)}, ${Math.round(box.bottom)}) : à voir sur une capture,`
        + ' on y agit par x, y',
      );
      return;
    }
    if (tag === 'img') {
      const alt = clean(el.getAttribute('alt'));
      if (alt && !muet) {
        lines.push(`image « ${alt} »`);
      }
      return;
    }
    const nom = cliquable(el, tag, role);
    if (nom) {
      // Un grand bloc cliquable (une carte, toute une section) : on dit son
      // début, et son contenu se lit normalement à la suite.
      const texte = clean(el.innerText);
      const long = (el.innerText || '').trim().length > maxChars;
      lines.push(`${ref(el)} ${nom} « ${long ? `${texte.slice(0, 60)}…` : texte || label(el)} »`);
      enfants(el, muet || !long);
      return;
    }
    if (!muet) {
      const texte = own(el);
      if (texte) {
        lines.push(tag === 'li' ? `- ${texte}` : texte);
      }
    }
    enfants(el, muet);
  };
  if (document.body) {
    walk(document.body, false);
  }
  window.__sergeDernierRepere = count;
  return {
    title: document.title,
    url: location.href,
    lines,
    truncated: lines.length >= maxLines,
  };
}
