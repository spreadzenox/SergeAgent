// Page P7 Voix : CDR, audio signée (E7), qualité F4c, pont.
import {fillList, li, rel} from '../components.js';

function libelleIssue(c) {
  if (c.decision === 'denied') {
    return c.reason || 'refusé avant l’appel';
  }
  const issues = {
    completed: 'terminé',
    pending: 'en cours ou jamais refermé',
    originate_failed: 'n’a pas abouti (ligne / trunk)',
    failed: 'échec',
    cancelled: 'annulé',
    no_answer: 'sans réponse',
    busy: 'occupé',
    congestion: 'réseau saturé',
  };
  return issues[c.outcome] || c.outcome || 'inconnu';
}

function renderBridge(main, payload, sig) {
  const info = main.querySelector('#voice-bridge-info');
  const etat = payload.bridge && payload.bridge.status
    ? payload.bridge.status
    : 'ok';
  info.textContent = `Pont : ${etat}. Pour arrêter les appels, coupe « Appel sortant » ou Serge en bas / en haut de En direct.`;
  main.querySelector('[data-section="bridge_statut"]').dataset.sig = sig;
}

function renderCdr(main, payload, sig) {
  const pTot = main.querySelector('#voice-cdr-total');
  pTot.textContent = `${payload.total || 0} appel(s) au journal.`;

  const ul = main.querySelector('[data-section="cdr_appels"] [data-list="calls"]');
  fillList(ul, payload.calls || [], 'Aucun appel enregistré.', (c) => {
    const sens = c.direction === 'out' || c.direction === 'outbound'
      ? 'sortant'
      : c.direction === 'in' || c.direction === 'inbound'
        ? 'entrant'
        : c.direction;
    const duree = Number(c.duration_s) || 0;
    const issue = libelleIssue(c);
    const temps = duree > 0
      ? `${duree}s`
      : 'pas de conversation (jamais connecté)';
    const liEl = li(`${sens} → ${c.to} — ${issue} (${temps}, ${rel(c.created_at)})`);
    if (c.transcript) {
      const pre = document.createElement('pre');
      pre.className = 'transcript-appel';
      pre.textContent = c.transcript;
      liEl.append(pre);
    }
    if (c.has_recording && c.audio_url) {
      const a = document.createElement('a');
      a.href = c.audio_url;
      a.textContent = 'Écouter';
      a.target = '_blank';
      a.style.marginLeft = '0.5rem';
      liEl.append(a);
    }
    return liEl;
  });
  main.querySelector('[data-section="cdr_appels"]').dataset.sig = sig;
}

function renderQualite(main, payload, sig) {
  const pMoy = main.querySelector('#voice-qualite-moyenne');
  const note = payload.note_moyenne !== null ? `${payload.note_moyenne} / 5` : 'Aucune note';
  pMoy.textContent = `Score moyen récent : ${note} (${payload.total_notes || 0} notés)`;

  const ul = main.querySelector('[data-section="qualite_voix"] [data-list="scores"]');
  fillList(ul, payload.scores || [], 'Aucun score d’appel récent.', (s) =>
    li(`Appel [${s.cdr || '—'}] : Note ${s.note || '—'} / 5 (flags: ${(s.flags || []).join(', ') || 'aucun'})`)
  );
  main.querySelector('[data-section="qualite_voix"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-voice');
  main.replaceChildren(tpl.content.cloneNode(true));

  const unsubs = [
    store.subscribe('bridge_statut', (p, s) => renderBridge(main, p, s)),
    store.subscribe('cdr_appels', (p, s) => renderCdr(main, p, s)),
    store.subscribe('qualite_voix', (p, s) => renderQualite(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'bridge_statut') {
      renderBridge(main, env.payload, env.sig);
    } else if (section === 'cdr_appels') {
      renderCdr(main, env.payload, env.sig);
    } else if (section === 'qualite_voix') {
      renderQualite(main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
