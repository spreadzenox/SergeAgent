// Page P6 Économie : entonnoir evidence-strict, transactions & MRR, coûts cognitifs, audit.
import {fillList, li, rel} from '../components.js';
import {allerObjet} from '../libelles.js';

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

function renderEntonnoir(main, payload, sig) {
  const tot = payload.totaux || {};
  const pTot = main.querySelector('#eco-totaux');
  pTot.textContent =
    `Total : ${tot.u1 || 0} envoyés (U1) → ${tot.u2 || 0} engagés (U2) → ${tot.u3 || 0} positifs (U3) | Encaissé : ${tot.paid_eur || 0} €`;
  const chips = main.querySelector('[data-tuiles="entonnoir"]');
  if (chips) {
    chips.replaceChildren(
      tuile(tot.u1 || 0, 'Touchées (U1)'),
      tuile(tot.u2 || 0, 'Ont répondu (U2)'),
      tuile(tot.u3 || 0, 'Ont dit oui (U3)'),
      tuile(`${tot.paid_eur || 0} €`, 'Encaissé'),
    );
  }

  const ul = main.querySelector('[data-section="entonnoir"] [data-list="ventures"]');
  fillList(ul, payload.ventures || [], 'Aucune venture enregistrée.', (v) => {
    const node = li('');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'clic-ligne';
    btn.textContent =
      `${v.name || v.id} [${v.lifecycle}] : ${v.u1} U1 → ${v.u2} U2 → ${v.u3} U3 | ${v.paid_eur} €`;
    btn.addEventListener('click', () => allerObjet('venture', v.id));
    node.append(btn);
    return node;
  });
  main.querySelector('[data-section="entonnoir"]').dataset.sig = sig;
}

function renderTransactions(main, payload, sig) {
  const pMrr = main.querySelector('#eco-mrr');
  pMrr.textContent = `MRR récurrent mensuel : ${payload.mrr_eur || 0} €`;

  const ulTx = main.querySelector('[data-section="transactions_subscriptions"] [data-list="transactions"]');
  fillList(ulTx, payload.transactions || [], 'Aucune transaction enregistrée.', (tx) => {
    const node = li('');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'clic-ligne';
    btn.textContent =
      `${tx.kind} ${tx.amount_eur} ${tx.currency} [${tx.status}] (${rel(tx.created_at)})`;
    if (tx.id) {
      btn.addEventListener('click', () => allerObjet('facture', tx.id));
    }
    node.append(btn);
    return node;
  });

  const ulSub = main.querySelector('[data-section="transactions_subscriptions"] [data-list="subscriptions"]');
  fillList(ulSub, payload.subscriptions || [], 'Aucun abonnement récurrent.', (sub) =>
    li(`${sub.provider} ${sub.amount_eur} €/${sub.period} [${sub.status}] (renouvelle ${rel(sub.renews_at)})`)
  );
  main.querySelector('[data-section="transactions_subscriptions"]').dataset.sig = sig;
}

function renderCouts(main, payload, sig) {
  const pCouts = main.querySelector('#eco-couts-detail');
  pCouts.textContent = `Consommation : ${payload.total_tokens || 0} jetons (~${payload.total_cost_eur || 0} € dépensés) | Revenu encaissé : ${payload.total_revenue_eur || 0} €`;

  const pRatio = main.querySelector('#eco-ratio-tokens');
  const ratioTxt = payload.tokens_par_euro !== null ? `${payload.tokens_par_euro} jetons / €` : 'N/A (aucun revenu encaissé)';
  pRatio.textContent = `Coût cognitif par euro gagné (E6) : ${ratioTxt}`;

  main.querySelector('[data-section="couts_cognitifs"]').dataset.sig = sig;
}

function renderAudit(main, payload, sig) {
  const ulRep = main.querySelector('[data-section="audit_reponses"] [data-list="reponses"]');
  fillList(ulRep, payload.reponses || [], 'Aucune réponse enregistrée.', (r) =>
    li(`${r.channel} → ${r.contact} [${r.status}] coût: ${r.cost_eur} € (${rel(r.created_at)})`)
  );

  const ulDette = main.querySelector('[data-section="audit_reponses"] [data-list="dette_builder"]');
  fillList(ulDette, payload.dette_builder || [], 'Aucun artifact builder en attente.', (d) =>
    li(`Artifact ${d.kind} v${d.version} (${rel(d.created_at)})`)
  );
  main.querySelector('[data-section="audit_reponses"]').dataset.sig = sig;
}

export function mount(main, store) {
  const tpl = document.getElementById('page-economy');
  main.replaceChildren(tpl.content.cloneNode(true));

  const rendus = {
    entonnoir: renderEntonnoir,
    transactions_subscriptions: renderTransactions,
    couts_cognitifs: renderCouts,
    audit_reponses: renderAudit,
  };

  const unsubs = Object.keys(rendus).map((section) =>
    store.subscribe(section, (payload, sg) => {
      rendus[section](main, payload, sg);
    })
  );

  for (const [section, env] of store.all()) {
    if (rendus[section]) {
      rendus[section](main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
