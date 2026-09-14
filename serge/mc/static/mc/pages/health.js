// Page P8 Santé : charte E6, services systemd, versions drift, audit trail.
import {fillList, li, rel} from '../components.js';

function tuile(n, libelle) {
  const box = document.createElement('div');
  box.className = 'tuile';
  const strong = document.createElement('strong');
  strong.textContent = String(n);
  const span = document.createElement('span');
  span.textContent = libelle;
  box.append(strong, span);
  return box;
}

function renderCharte(main, payload, sig) {
  const pLoc = main.querySelector('#health-loc');
  const plusGros = payload.plus_gros_fichier || {};
  const nomCourt = (plusGros.nom || '').split('/').pop() || '—';
  pLoc.textContent =
    `${payload.loc_total || 0} lignes dans kit/ et serge/ (Python). `
    + `Le plus gros fichier est ${nomCourt} (${plusGros.lignes || 0} lignes, plafond charte 500).`;
  const chips = main.querySelector('[data-tuiles="sante"]');
  if (chips) {
    const ratio = payload.tokens_par_euro !== null
      ? String(payload.tokens_par_euro)
      : '—';
    chips.replaceChildren(
      tuile(payload.loc_total || 0, 'Lignes de code (kit + serge)'),
      tuile(ratio, 'Jetons par euro encaissé'),
      tuile(payload.requested_pending || 0, 'Demandes en attente'),
      tuile(plusGros.lignes || 0, `Plus gros fichier : ${nomCourt}`),
    );
  }

  const pRatio = main.querySelector('#health-ratio-cognitif');
  pRatio.textContent = payload.tokens_par_euro !== null
    ? `${payload.tokens_par_euro} jetons LLM par euro encaissé.`
    : 'Pas encore d’euro encaissé : le ratio jetons / € apparaîtra au premier paiement.';

  const pReq = main.querySelector('#health-requested');
  pReq.textContent = `Demandes d’évolution en attente : ${payload.requested_pending || 0}`;

  main.querySelector('[data-section="charte_metriques"]').dataset.sig = sig;
}

function renderUnits(main, payload, sig) {
  const ul = main.querySelector('[data-section="units_systemd"] [data-list="units"]');
  fillList(ul, payload.units || [], 'Aucun service renseigné.', (u) => {
    const liEl = li(`${u.titre || u.unit} — ${u.libelle || u.status}`);
    if (u.ok) {
      liEl.style.color = 'var(--vert)';
    } else if (u.status === 'inactive') {
      liEl.style.color = 'var(--texte-doux)';
    } else {
      liEl.style.color = 'var(--orange)';
    }
    return liEl;
  });
  main.querySelector('[data-section="units_systemd"]').dataset.sig = sig;
}

function renderVersions(main, payload, sig) {
  const pVer = main.querySelector('#health-versions');
  const schTxt = payload.schema_ok ? `schéma v${payload.schema_version} (conforme)` : `schéma v${payload.schema_version} (ATTENDU: v${payload.schema_attendu})`;
  pVer.textContent = `Mission Control : v${payload.mc_version} | Base SQLite : ${schTxt} | CLI gog : ${payload.gog_version}`;
  if (!payload.schema_ok) {
    pVer.style.color = 'var(--rouge)';
  }
  main.querySelector('[data-section="versions_drift"]').dataset.sig = sig;
}

function renderAudit(main, payload, sig) {
  const ul = main.querySelector('[data-section="audit_trail"] [data-list="actes"]');
  fillList(ul, payload.actes || [], 'Aucun acte d’audit enregistré.', (a) => {
    const details = a.details
      ? Object.entries(a.details)
        .map(([k, v]) => `${k} ${v}`)
        .join(' · ')
      : '';
    return li(`${rel(a.ts)} · ${a.acteur} — ${a.acte}${details ? ` : ${details}` : ''}`);
  });
  main.querySelector('[data-section="audit_trail"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-health');
  main.replaceChildren(tpl.content.cloneNode(true));

  const unsubs = [
    store.subscribe('charte_metriques', (p, s) => renderCharte(main, p, s)),
    store.subscribe('units_systemd', (p, s) => renderUnits(main, p, s)),
    store.subscribe('versions_drift', (p, s) => renderVersions(main, p, s)),
    store.subscribe('audit_trail', (p, s) => renderAudit(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'charte_metriques') {
      renderCharte(main, env.payload, env.sig);
    } else if (section === 'units_systemd') {
      renderUnits(main, env.payload, env.sig);
    } else if (section === 'versions_drift') {
      renderVersions(main, env.payload, env.sig);
    } else if (section === 'audit_trail') {
      renderAudit(main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
