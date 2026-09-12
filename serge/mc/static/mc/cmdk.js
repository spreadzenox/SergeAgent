// Palette de commande globale Ctrl+K (cmdk.js, §5).
import {confirmModal, promptModal, toast} from './components.js';

const COMMANDES_FIXES = [
  {id: 'nav-live', titre: 'Aller à En direct', type: 'page', hash: '#/live'},
  {id: 'nav-mind', titre: 'Aller à Cerveau', type: 'page', hash: '#/mind'},
  {id: 'nav-tickets', titre: 'Aller à Décisions', type: 'page', hash: '#/tickets'},
  {id: 'nav-memory', titre: 'Aller à Mémoire', type: 'page', hash: '#/memory'},
  {id: 'nav-policy', titre: 'Aller à Policy', type: 'page', hash: '#/policy'},
  {id: 'nav-economy', titre: 'Aller à Économie', type: 'page', hash: '#/economy'},
  {id: 'nav-voice', titre: 'Aller à Voix', type: 'page', hash: '#/voice'},
  {id: 'nav-health', titre: 'Aller à Health', type: 'page', hash: '#/health'},
  {
    id: 'act-kill-voice',
    titre: 'Action : Basculer Kill Switch Voix',
    type: 'action',
    run: async () => {
      location.hash = '#/voice';
      const btn = document.querySelector('[data-action="toggle-kill-voice"]');
      if (btn) {
        btn.click();
      }
    },
  },
  {
    id: 'act-propose-policy',
    titre: 'Action : Proposer en POLICY',
    type: 'action',
    run: async () => {
      location.hash = '#/policy';
      const btn = document.querySelector('[data-action="proposer-policy"]');
      if (btn) {
        btn.click();
      }
    },
  },
];

export function initCmdk(store) {
  let modale = null;
  let input = null;
  let liste = null;
  let ouvert = false;

  function construireListe(q) {
    liste.replaceChildren();
    const filtre = q.trim().toLowerCase();
    const commandes = [...COMMANDES_FIXES];

    // Extraction dynamique des tickets ouverts
    const ticketsEnv = store ? store.get('tickets') : null;
    if (ticketsEnv && Array.isArray(ticketsEnv.payload?.items)) {
      for (const t of ticketsEnv.payload.items) {
        commandes.push({
          id: `ticket-${t.id}`,
          titre: `Ticket : ${t.type} — ${t.titre}`,
          type: 'ticket',
          run: () => {
            location.hash = '#/tickets';
            setTimeout(() => {
              const el = document.querySelector(`.lien-ticket[data-ticket="${t.id}"]`);
              if (el) {
                el.click();
              }
            }, 100);
          },
        });
      }
    }

    const matches = commandes.filter((c) =>
      !filtre || c.titre.toLowerCase().includes(filtre)
    );

    if (matches.length === 0) {
      const vide = document.createElement('li');
      vide.textContent = 'Aucune commande trouvée.';
      vide.className = 'cmdk-vide';
      liste.append(vide);
      return;
    }

    matches.slice(0, 10).forEach((c, idx) => {
      const item = document.createElement('li');
      item.className = 'cmdk-item';
      if (idx === 0) {
        item.classList.add('selectionne');
      }
      item.textContent = c.titre;
      item.addEventListener('click', () => {
        executer(c);
      });
      liste.append(item);
    });
  }

  function executer(c) {
    fermer();
    if (c.hash) {
      location.hash = c.hash;
    } else if (c.run) {
      c.run();
    }
  }

  function ouvrir() {
    if (ouvert) {
      return;
    }
    ouvert = true;

    const fond = document.createElement('div');
    fond.className = 'fond-modale cmdk-fond';

    const boite = document.createElement('div');
    boite.className = 'cmdk-boite';

    input = document.createElement('input');
    input.type = 'text';
    input.className = 'cmdk-input';
    input.placeholder = 'Tape une commande ou navigue… (Échap pour fermer)';
    input.setAttribute('aria-label', 'Palette de commande');

    liste = document.createElement('ul');
    liste.className = 'cmdk-liste';

    input.addEventListener('input', () => {
      construireListe(input.value);
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        fermer();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        const sel = liste.querySelector('.cmdk-item.selectionne');
        if (sel && sel.nextElementSibling && sel.nextElementSibling.classList.contains('cmdk-item')) {
          sel.classList.remove('selectionne');
          sel.nextElementSibling.classList.add('selectionne');
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const sel = liste.querySelector('.cmdk-item.selectionne');
        if (sel && sel.previousElementSibling && sel.previousElementSibling.classList.contains('cmdk-item')) {
          sel.classList.remove('selectionne');
          sel.previousElementSibling.classList.add('selectionne');
        }
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const sel = liste.querySelector('.cmdk-item.selectionne');
        if (sel) {
          sel.click();
        }
      }
    });

    fond.addEventListener('click', (e) => {
      if (e.target === fond) {
        fermer();
      }
    });

    boite.append(input, liste);
    fond.append(boite);
    document.body.append(fond);
    modale = fond;

    construireListe('');
    input.focus();
  }

  function fermer() {
    if (!ouvert) {
      return;
    }
    ouvert = false;
    if (modale) {
      modale.remove();
      modale = null;
    }
  }

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (ouvert) {
        fermer();
      } else {
        ouvrir();
      }
    }
  });

  return {ouvrir, fermer};
}
