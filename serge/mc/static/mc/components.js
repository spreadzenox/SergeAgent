// Composants HUD : toast, drawer, modale, sparkline, jauge.
// DOM via createElement uniquement (règle A4).
// Libellés FR en dur (centralisation i18n.js au lot 8).
export function toast(container, message, kind = 'info') {
  const node = document.createElement('p');
  node.className = `toast toast-${kind}`;
  node.setAttribute('role', 'status');
  node.textContent = message;
  container.appendChild(node);
  setTimeout(() => node.remove(), 4000);
  return node;
}

export function openDrawer(root, title, body) {
  const node = document.createElement('aside');
  node.className = 'drawer';
  node.setAttribute('role', 'dialog');
  node.setAttribute('aria-label', title);
  const heading = document.createElement('h2');
  heading.textContent = title;
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.textContent = 'Fermer';
  const close = () => node.remove();
  closeBtn.addEventListener('click', close);
  node.append(heading, body, closeBtn);
  root.appendChild(node);
  requestAnimationFrame(() => node.classList.add('ouvert'));
  return close;
}

export function confirmModal(
  root,
  {title, message, confirm = 'Confirmer', cancel = 'Annuler', danger = false},
) {
  return new Promise((resolve) => {
    const fond = document.createElement('div');
    fond.className = 'fond-modale';
    const node = document.createElement('div');
    node.className = 'modale';
    node.setAttribute('role', 'alertdialog');
    const heading = document.createElement('h2');
    heading.textContent = title;
    const text = document.createElement('p');
    text.textContent = message;
    const actions = document.createElement('div');
    actions.className = 'actions';
    const okBtn = document.createElement('button');
    okBtn.type = 'button';
    okBtn.textContent = confirm;
    if (danger) {
      okBtn.classList.add('danger');
    }
    const koBtn = document.createElement('button');
    koBtn.type = 'button';
    koBtn.textContent = cancel;
    const done = (value) => {
      document.removeEventListener('keydown', onKey);
      fond.remove();
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') {
        done(false);
      }
    };
    okBtn.addEventListener('click', () => done(true));
    koBtn.addEventListener('click', () => done(false));
    fond.addEventListener('click', (event) => {
      if (event.target === fond) {
        done(false);
      }
    });
    document.addEventListener('keydown', onKey);
    actions.append(okBtn, koBtn);
    node.append(heading, text, actions);
    fond.append(node);
    root.appendChild(fond);
    okBtn.focus();
  });
}

export function sparkline(values, {width = 120, height = 32} = {}) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'sparkline');
  svg.setAttribute('width', String(width));
  svg.setAttribute('height', String(height));
  if (values.length >= 2) {
    const min = Math.min(...values);
    const span = Math.max(...values) - min || 1;
    const points = values
      .map((value, index) => {
        const x = (index / (values.length - 1)) * width;
        const y = height - ((value - min) / span) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(' ');
    const line = document.createElementNS(
      'http://www.w3.org/2000/svg',
      'polyline',
    );
    line.setAttribute('points', points);
    line.setAttribute('fill', 'none');
    line.setAttribute('stroke', 'currentColor');
    line.setAttribute('stroke-width', '1.5');
    svg.append(line);
  }
  return svg;
}

export function createGauge() {
  const node = document.createElement('div');
  node.className = 'jauge';
  node.setAttribute('role', 'progressbar');
  node.append(document.createElement('span'));
  return node;
}

export function updateGauge(node, ratio, level = '') {
  const fill = node.querySelector('span');
  const clamped = Math.max(0, Math.min(1, ratio));
  fill.style.width = `${Math.round(clamped * 100)}%`;
  node.classList.toggle('alerte', level === 'alerte');
  node.classList.toggle('danger', level === 'danger');
  node.setAttribute('aria-valuenow', String(Math.round(clamped * 100)));
}

export function li(text, title = '') {
  const node = document.createElement('li');
  node.textContent = text;
  if (title) {
    node.title = title;
  }
  return node;
}

export function fillList(list, items, empty, render) {
  list.replaceChildren();
  if (items.length === 0) {
    list.append(li(empty));
    return;
  }
  for (const item of items) {
    list.append(render(item));
  }
}

// TODO lot 8 : migrer vers i18n.js (dates relatives + libellés).
export function rel(ts) {
  const diff = Date.now() - Date.parse(ts);
  if (Number.isNaN(diff)) {
    return '';
  }
  const abs = Math.abs(diff);
  const min = Math.floor(abs / 60000);
  const words =
    min < 1
      ? "à l'instant"
      : min < 60
        ? `${min} min`
        : Math.floor(min / 60) < 24
          ? `${Math.floor(min / 60)} h`
          : `${Math.floor(min / 1440)} j`;
  if (words === "à l'instant") {
    return words;
  }
  return diff < 0 ? `dans ${words}` : `il y a ${words}`;
}

export function promptModal(
  root,
  {title, message, fields, confirm = 'Valider', cancel = 'Annuler'},
) {
  return new Promise((resolve) => {
    const fond = document.createElement('div');
    fond.className = 'fond-modale';
    const node = document.createElement('div');
    node.className = 'modale';
    node.setAttribute('role', 'alertdialog');
    const heading = document.createElement('h2');
    heading.textContent = title;
    const text = document.createElement('p');
    text.textContent = message;
    const inputs = {};
    const etiquettes = [];
    for (const field of fields) {
      const label = document.createElement('label');
      label.textContent = field.label;
      const input = document.createElement('input');
      input.name = field.nom;
      input.value = field.defaut || '';
      label.append(input);
      etiquettes.push(label);
      inputs[field.nom] = {input, requis: field.requis || false};
    }
    const actions = document.createElement('div');
    actions.className = 'actions';
    const okBtn = document.createElement('button');
    okBtn.type = 'button';
    okBtn.textContent = confirm;
    okBtn.classList.add('danger');
    const koBtn = document.createElement('button');
    koBtn.type = 'button';
    koBtn.textContent = cancel;
    const done = (value) => {
      document.removeEventListener('keydown', onKey);
      fond.remove();
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') {
        done(null);
      }
    };
    okBtn.addEventListener('click', () => {
      const valeurs = {};
      for (const [nom, {input, requis}] of Object.entries(inputs)) {
        if (requis && !input.value.trim()) {
          input.focus();
          return;
        }
        valeurs[nom] = input.value;
      }
      done(valeurs);
    });
    koBtn.addEventListener('click', () => done(null));
    fond.addEventListener('click', (event) => {
      if (event.target === fond) {
        done(null);
      }
    });
    document.addEventListener('keydown', onKey);
    actions.append(okBtn, koBtn);
    node.append(heading, text, ...etiquettes, actions);
    fond.append(node);
    root.appendChild(fond);
    node.querySelector('input').focus();
  });
}
