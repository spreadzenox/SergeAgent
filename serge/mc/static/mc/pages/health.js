// Page P8 Santé : charte E6, services systemd, versions drift, audit trail.
import {fillList, li, rel} from '../components.js';

function renderCharte(main, payload, sig) {
  const pLoc = main.querySelector('#health-loc');
  const plusGros = payload.plus_gros_fichier || {};
  pLoc.textContent = `LOC total (kit + serge) : ${payload.loc_total || 0} lignes | Plus gros fichier : ${plusGros.nom || '—'} (${plusGros.lignes || 0} l.)`;

  const pRatio = main.querySelector('#health-ratio-cognitif');
  const ratioTxt = payload.tokens_par_euro !== null ? `${payload.tokens_par_euro} jetons / €` : 'N/A';
  pRatio.textContent = `Coût cognitif global (tokens / € de revenu) : ${ratioTxt}`;

  const pReq = main.querySelector('#health-requested');
  pReq.textContent = `Demandes d’évolution requested en attente : ${payload.requested_pending || 0}`;

  main.querySelector('[data-section="charte_metriques"]').dataset.sig = sig;
}

function renderUnits(main, payload, sig) {
  const ul = main.querySelector('[data-section="units_systemd"] [data-list="units"]');
  fillList(ul, payload.units || [], 'Aucune unit renseignée.', (u) => {
    const liEl = li(`${u.unit} : ${u.status}`);
    if (u.status === 'active') {
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
    const details = a.details ? JSON.stringify(a.details) : '';
    return li(`${rel(a.ts)} · [${a.acteur}] ${a.acte} : ${details}`);
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
