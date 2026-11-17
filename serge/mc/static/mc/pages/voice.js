// Page P7 Voix : CDR, audio signée (E7), pont, journaux du serveur.
import {
  afficherJournaux,
  confirmModal,
  fillList,
  li,
  rel,
  toast,
} from '../components.js';

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
  direEnCours(main, payload.bridge && payload.bridge.ledger ? payload.bridge.ledger.pending : null);
  main.querySelector('[data-section="bridge_statut"]').dataset.sig = sig;
}

// Un appel « en cours » au journal bloque tout nouvel appel vers ce numéro.
function direEnCours(main, combien) {
  const nombre = Number.isInteger(combien) ? `${combien}` : 'inconnu';
  main.querySelector('#voice-en-cours').textContent =
    `Appels « en cours » au journal : ${nombre}. Tant qu’un appel y reste « en cours », aucun autre ne part vers ce numéro ; au bout d’une heure, Serge le ferme de lui-même.`;
}

// « Débloquer les appels » : ferme au journal les appels restés « en cours ».
function brancherDeblocage(main) {
  const bouton = main.querySelector('[data-voice="debloquer"]');
  bouton.addEventListener('click', async () => {
    const oui = await confirmModal(document.body, {
      title: 'Débloquer les appels ?',
      message: 'Les appels restés « en cours » au journal sont fermés (issue : échec). À faire quand un appel est reporté parce qu’un autre serait « déjà en cours » vers ce numéro, alors que personne n’est en ligne. Un appel vraiment en cours n’est pas raccroché.',
      confirm: 'Débloquer les appels',
    });
    if (!oui) return;
    bouton.disabled = true;
    try {
      const res = await fetch('/owner/api/voice/debloquer', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}',
      });
      const data = await res.json();
      if (!res.ok) {
        toast(document.body, `Échec : ${data.erreur || 'refusé'}.`, 'erreur');
        return;
      }
      direEnCours(main, 0);
      toast(document.body, `${data.fermes} appel(s) fermé(s).`, 'succes');
    } catch {
      toast(document.body, 'Action injoignable. Réessaie.', 'erreur');
    } finally {
      bouton.disabled = false;
    }
  });
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

function renderJournaux(main, payload, sig) {
  afficherJournaux(main.querySelector('[data-journaux="blocs"]'), payload.blocs);
  main.querySelector('[data-section="journal_voix"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-voice');
  main.replaceChildren(tpl.content.cloneNode(true));
  brancherDeblocage(main);

  const unsubs = [
    store.subscribe('bridge_statut', (p, s) => renderBridge(main, p, s)),
    store.subscribe('cdr_appels', (p, s) => renderCdr(main, p, s)),
    store.subscribe('journal_voix', (p, s) => renderJournaux(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'bridge_statut') {
      renderBridge(main, env.payload, env.sig);
    } else if (section === 'cdr_appels') {
      renderCdr(main, env.payload, env.sig);
    } else if (section === 'journal_voix') {
      renderJournaux(main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
