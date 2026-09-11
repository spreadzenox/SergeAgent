// Page P4 Mémoire : 5 couches C1-C5, recherche FTS, consolidation, requested.
import {fillList, li, rel} from '../components.js';

let coucheActive = 'c1';

const p = (t) => {
  const el = document.createElement('p');
  el.textContent = t;
  return el;
};
const bloc = (t) => {
  const el = document.createElement('div');
  el.className = 'diff-bloc';
  el.textContent = t;
  return el;
};

const RENDUS_COUCHES = {
  c1: (vue, c) => {
    vue.append(
      p(
        `${c.total_archives || 0} archive(s), ${c.total_episodes || 0} épisode(s) archivé(s).`,
      ),
    );
    const ul = document.createElement('ul');
    fillList(ul, c.archives || [], 'Aucune archive.', (a) =>
      li(
        `${a.period} · ${a.count} épisodes [${a.sha256}] (${rel(a.created_at)})`,
      ),
    );
    vue.append(ul);
  },
  c2: (vue, c) => {
    vue.append(p(`${c.total || 0} playbook(s) enregistré(s).`));
    const ul = document.createElement('ul');
    fillList(ul, c.items || [], 'Aucun playbook.', (pb) => {
      const etp = Array.isArray(pb.etapes) ? pb.etapes.join(' → ') : '';
      return li(
        `${pb.nom} [${pb.scope}] — ${pb.conditions} (étapes: ${etp})`,
      );
    });
    vue.append(ul);
  },
  c3: (vue, c) => {
    vue.append(p(`${c.total || 0} piège(s) répertorié(s).`));
    const ul = document.createElement('ul');
    fillList(ul, c.items || [], 'Aucun piège.', (pf) =>
      li(`${pf.piege} [coût : ${pf.cout || '—'}] (${rel(pf.created_at)})`),
    );
    vue.append(ul);
  },
  c4: (vue, c) => {
    vue.append(p(`${c.total || 0} leçon(s) répertoriée(s).`));
    const ul = document.createElement('ul');
    fillList(ul, c.items || [], 'Aucune leçon.', (l) =>
      li(`${l.lecon} [confiance: ${Math.round(l.confiance * 100)} %]`),
    );
    vue.append(ul);
  },
  c5: (vue, c) => {
    vue.append(
      p(`SERGE.md version ${c.version || 1} (${rel(c.updated_at)}).`),
    );
    vue.append(bloc(c.content || 'SERGE.md vide.'));
    if (c.previous) {
      const h3 = document.createElement('h3');
      h3.textContent = 'Version précédente';
      vue.append(h3, bloc(c.previous));
    }
  },
};

function renderCoucheVue(main, payload) {
  const vue = main.querySelector('[data-couche-vue="contenu"]');
  vue.replaceChildren();
  const rendu = RENDUS_COUCHES[coucheActive];
  if (rendu) {
    rendu(vue, payload[coucheActive] || {});
  }
}

function renderConsolidation(main, payload, sig) {
  const status = main.querySelector('#cons-status');
  const derniere = payload.last_run
    ? rel(payload.last_run)
    : 'jamais exécutée';
  status.textContent =
    `Dernière exécution : ${derniere}.`
    + ` État : ${payload.due ? 'Échéance atteinte (due)' : 'À jour'}.`;
  const liste = main.querySelector(
    '[data-section="consolidation"] [data-list="events"]',
  );
  fillList(
    liste,
    payload.events || [],
    'Aucun événement de consolidation.',
    (ev) => li(`${rel(ev.ts)} · ${ev.acteur} — ${ev.type}`),
  );
  main.querySelector('[data-section="consolidation"]').dataset.sig = sig;
}

function renderRequested(main, payload, sig) {
  const liste = main.querySelector(
    '[data-section="requested"] [data-list="items"]',
  );
  fillList(
    liste,
    payload.items || [],
    'Aucune demande d’évolution.',
    (req) =>
      li(
        `${req.titre} [${req.point_llm}] — ${req.demande} (${rel(req.created_at)})`,
      ),
  );
  main.querySelector('[data-section="requested"]').dataset.sig = sig;
}

function initSearch(main) {
  const input = main.querySelector('[data-input="recherche"]');
  const conteneur = main.querySelector('[data-recherche="resultats"]');
  const btnChercher = main.querySelector('[data-action="lancer-recherche"]');

  async function executer() {
    const q = input.value.trim();
    conteneur.replaceChildren();
    if (!q) {
      return;
    }
    try {
      const res = await fetch(
        `/owner/api/memory/search?q=${encodeURIComponent(q)}`,
        {cache: 'no-store'},
      );
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      const liste = document.createElement('ul');
      fillList(liste, data.results || [], 'Aucun résultat.', (r) =>
        li(`${r.type} [${r.id}] : ${r.extrait || r.id}`),
      );
      conteneur.append(liste);
    } catch {
      // recherche échouée
    }
  }

  btnChercher.addEventListener('click', executer);
  input.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      executer();
    }
  });
}

export function mount(main, store) {
  const tpl = document.getElementById('page-memory');
  main.replaceChildren(tpl.content.cloneNode(true));

  main.querySelectorAll('.memory-tabs button').forEach((b) => {
    b.addEventListener('click', () => {
      main
        .querySelectorAll('.memory-tabs button')
        .forEach((o) => o.classList.remove('actif'));
      b.classList.add('actif');
      coucheActive = b.dataset.couche;
      const env = store.get('couches');
      if (env) {
        renderCoucheVue(main, env.payload);
      }
    });
  });

  initSearch(main);

  const unsubs = [
    store.subscribe('couches', (payload, sg) => {
      renderCoucheVue(main, payload);
      main.querySelector('[data-section="couches"]').dataset.sig = sg;
    }),
    store.subscribe('consolidation', (p, s) =>
      renderConsolidation(main, p, s),
    ),
    store.subscribe('requested', (p, s) => renderRequested(main, p, s)),
  ];

  for (const [section, env] of store.all()) {
    if (section === 'couches') {
      renderCoucheVue(main, env.payload);
      main.querySelector('[data-section="couches"]').dataset.sig =
        env.sig;
    } else if (section === 'consolidation') {
      renderConsolidation(main, env.payload, env.sig);
    } else if (section === 'requested') {
      renderRequested(main, env.payload, env.sig);
    }
  }

  return () => {
    unsubs.forEach((u) => u());
  };
}
