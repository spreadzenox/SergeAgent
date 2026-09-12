// Page P7 Voix : CDR, audio signée (E7), qualité F4c, bridge & kill switch M9/M11.
import {
  confirmModal,
  fillList,
  li,
  rel,
  toast,
} from '../components.js';
import {fetchState} from '../sse.js';

async function poster(chemin, charge) {
  const res = await fetch(chemin, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(charge),
  });
  return {ok: res.ok, data: await res.json()};
}

async function rafraichir(store) {
  try {
    const data = await fetchState('p7');
    for (const [section, env] of Object.entries(data.sections || {})) {
      store.apply(section, env.sig, env.payload);
    }
  } catch {
    // reprise au tick suivant
  }
}

async function toggleKillVoice(store, etatActuel) {
  const action = etatActuel ? 'Désactiver' : 'Activer';
  const ok = await confirmModal(document.body, {
    title: `${action} le Kill Switch Voix ?`,
    message: etatActuel
      ? 'Les appels sortants seront de nouveau autorisés.'
      : 'Tous les appels sortants seront immédiatement bloqués.',
    confirm: action,
    danger: !etatActuel,
  });
  if (!ok) {
    return;
  }
  try {
    const {ok: resOk, data} = await poster('/owner/api/voice/kill', {
      activer: !etatActuel,
      decision_id: `mc-${Date.now()}-voice-kill`,
    });
    if (!resOk) {
      toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
      return;
    }
    toast(
      document.body,
      'Kill Switch Voix : ' + (data.kill_switch ? 'ACTIVÉ.' : 'Désactivé.'),
      'succes',
    );
    await rafraichir(store);
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
  }
}

function renderBridge(main, payload, sig, store) {
  const info = main.querySelector('#voice-bridge-info');
  const btnKill = main.querySelector('[data-action="toggle-kill-voice"]');
  const kActif = payload.kill_switch;

  info.textContent = `Kill Switch Voix : ${kActif ? 'ACTIF (appels coupés)' : 'Inactif (appels autorisés)'} | Bridge statut : ${payload.bridge?.status || 'ok'}`;
  info.style.color = kActif ? 'var(--rouge)' : 'var(--vert)';
  btnKill.textContent = kActif ? 'Désactiver Kill Switch Voix' : 'Activer Kill Switch Voix';
  btnKill.className = kActif ? '' : 'danger';

  main
    .querySelector('[data-action="toggle-kill-voice"]')
    .addEventListener('click', () => {
      const env = store.get('bridge_statut');
      const k = env ? env.payload?.kill_switch : false;
      toggleKillVoice(store, k);
    });

  main.querySelector('[data-section="bridge_statut"]').dataset.sig = sig;
}

function renderCdr(main, payload, sig) {
  const pTot = main.querySelector('#voice-cdr-total');
  pTot.textContent = `${payload.total || 0} appel(s) enregistré(s) au ledger.`;

  const ul = main.querySelector('[data-section="cdr_appels"] [data-list="calls"]');
  fillList(ul, payload.calls || [], 'Aucun appel enregistré.', (c) => {
    const sens = c.direction === 'out' || c.direction === 'outbound'
      ? 'sortant'
      : c.direction === 'in' || c.direction === 'inbound'
        ? 'entrant'
        : c.direction;
    const liEl = li(`${sens} → ${c.to} [${c.outcome}] (${c.duration_s}s, ${rel(c.created_at)}) `);
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
    store.subscribe('bridge_statut', (p, s) => renderBridge(main, p, s, store)),
    store.subscribe('cdr_appels', (p, s) => renderCdr(main, p, s)),
    store.subscribe('qualite_voix', (p, s) => renderQualite(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'bridge_statut') {
      renderBridge(main, env.payload, env.sig, store);
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
