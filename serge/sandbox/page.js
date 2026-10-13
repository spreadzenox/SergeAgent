// La page telle que la lit un lecteur d'écran, une ligne par élément.
// Chaque élément sur lequel on peut agir reçoit un repère (data-serge-ref,
// « e7 ») que l'invocation cite pour cliquer ou taper. Les repères sont
// refaits à chaque lecture. Lancé par serge/sandbox/navigateur.py.
(options) => {
  const maxLines = options.maxLines;
  const maxChars = 200;
  for (const old of document.querySelectorAll('[data-serge-ref]')) {
    old.removeAttribute('data-serge-ref');
  }
  const lines = [];
  let count = 0;
  const clean = (text) => (text || '').replace(/\s+/g, ' ').trim().slice(0, maxChars);
  const visible = (el) => {
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || style.display === 'none') {
      return false;
    }
    const box = el.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  };
  const label = (el) => {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
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
    count += 1;
    el.setAttribute('data-serge-ref', `e${count}`);
    return `[e${count}]`;
  };
  const own = (el) => clean(
    [...el.childNodes].filter((c) => c.nodeType === 3).map((c) => c.textContent).join(' '),
  );
  const TEXTE = new Set([
    'p', 'li', 'td', 'th', 'dd', 'dt', 'span', 'div', 'pre', 'blockquote',
    'figcaption', 'strong', 'em', 'small', 'b', 'i', 'code', 'section',
    'article', 'main', 'header', 'footer', 'label', 'caption', 'output',
  ]);
  const walk = (el) => {
    if (lines.length >= maxLines || el.nodeType !== 1) {
      return;
    }
    const tag = el.tagName.toLowerCase();
    if (['script', 'style', 'noscript', 'template', 'svg', 'head'].includes(tag)) {
      return;
    }
    if (!visible(el)) {
      return;
    }
    const role = el.getAttribute('role');
    if (/^h[1-6]$/.test(tag)) {
      lines.push(`${'#'.repeat(Number(tag[1]))} ${clean(el.innerText)}`);
      return;
    }
    if (tag === 'a' && el.getAttribute('href')) {
      lines.push(`${ref(el)} lien « ${clean(el.innerText) || label(el)} » → ${el.getAttribute('href')}`);
      return;
    }
    const kind = (el.getAttribute('type') || 'text').toLowerCase();
    if (tag === 'button' || role === 'button'
        || (tag === 'input' && ['submit', 'button', 'reset'].includes(kind))) {
      const grise = el.disabled ? ' (grisé)' : '';
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
    if (tag === 'img') {
      const alt = clean(el.getAttribute('alt'));
      if (alt) {
        lines.push(`image « ${alt} »`);
      }
      return;
    }
    if (TEXTE.has(tag)) {
      const texte = own(el);
      if (texte) {
        lines.push(tag === 'li' ? `- ${texte}` : texte);
      }
    }
    for (const child of el.children) {
      walk(child);
    }
  };
  if (document.body) {
    walk(document.body);
  }
  return {
    title: document.title,
    url: location.href,
    lines,
    truncated: lines.length >= maxLines,
  };
}
