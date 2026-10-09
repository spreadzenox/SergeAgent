// Page Décisions : les administrateurs Discord et les types de tickets
// (décisions Q85 et Q86). Chaque ticket part en message privé à chaque
// administrateur ; la première réponse le tranche pour tous.
import {confirmModal, fillList, li, toast} from '../components.js';
import {libelleActe, poster, rafraichir} from './tickets_actes.js';

// « 2880 » → « 2 j » ; vide : jamais.
function duree(minutes) {
  if (minutes === null || minutes === undefined) {
    return 'jamais';
  }
  if (minutes % 1440 === 0) {
    return `${minutes / 1440} j`;
  }
  if (minutes % 60 === 0) {
    return `${minutes / 60} h`;
  }
  return `${minutes} min`;
}

async function agir(main, store, chemin, charge, succes) {
  try {
    const {ok, data} = await poster(chemin, charge);
    toast(document.body, ok ? succes : (data.erreur || 'Refusé.'), ok ? 'succes' : 'erreur');
    if (ok) {
      await rafraichir(main, store);
    }
    return ok;
  } catch {
    toast(document.body, 'Action injoignable.', 'erreur');
    return false;
  }
}

export function renderAdmins(main, payload, sig, store) {
  const section = main.querySelector('[data-section="admins_discord"]');
  fillList(
    section.querySelector('[data-list="admins"]'),
    payload.admins || [],
    'Aucun administrateur : aucun ticket ne part sur Discord.',
    (admin) => {
      const node = li(`${admin.name || 'Sans nom'} — ${admin.user_id}`);
      const retirer = document.createElement('button');
      retirer.type = 'button';
      retirer.className = 'btn-doux';
      retirer.textContent = 'Retirer';
      retirer.addEventListener('click', async () => {
        const oui = await confirmModal(document.body, {
          title: 'Retirer cet administrateur ?',
          message: `${admin.name || admin.user_id} ne recevra plus les tickets.`,
          confirm: 'Retirer',
          danger: true,
        });
        if (oui) {
          await agir(
            main,
            store,
            '/owner/api/discord/admin',
            {acte: 'retirer', user_id: admin.user_id},
            'Administrateur retiré.',
          );
        }
      });
      node.append(' ', retirer);
      return node;
    },
  );
  section.dataset.sig = sig;
}

export function brancherAjoutAdmin(main, store) {
  const form = main.querySelector('[data-admins="ajout"]');
  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const ok = await agir(
      main,
      store,
      '/owner/api/discord/admin',
      {
        acte: 'ajouter',
        user_id: form.elements.user_id.value.trim(),
        name: form.elements.name.value.trim(),
      },
      'Administrateur ajouté : il recevra les prochains tickets.',
    );
    if (ok) {
      form.reset();
    }
  });
}

function blocType(main, store, type, possibles) {
  const bloc = document.createElement('article');
  bloc.className = 'cadre-regle';
  bloc.dataset.typeTicket = type.id;
  const titre = document.createElement('h3');
  titre.textContent = `${type.emoji} ${type.id}`.trim();
  const role = document.createElement('p');
  role.className = 'pourquoi-regle';
  role.textContent = type.role;
  const delai = document.createElement('label');
  delai.textContent = `Délai avant expiration, en minutes (vide : jamais ; aujourd’hui ${duree(type.expiry_minutes)}) `;
  const champDelai = document.createElement('input');
  champDelai.type = 'number';
  champDelai.min = '1';
  champDelai.max = '43200';
  champDelai.name = 'expiry_minutes';
  champDelai.value = type.expiry_minutes ?? '';
  delai.append(champDelai);
  const defaut = document.createElement('label');
  defaut.textContent = 'Décision annoncée à l’expiration ';
  const champDefaut = document.createElement('input');
  champDefaut.type = 'text';
  champDefaut.name = 'default_detail';
  champDefaut.value = type.default_detail;
  defaut.append(champDefaut);
  const boutons = document.createElement('fieldset');
  const legende = document.createElement('legend');
  legende.textContent = 'Boutons';
  boutons.append(legende);
  for (const acte of possibles) {
    const case_ = document.createElement('label');
    const coche = document.createElement('input');
    coche.type = 'checkbox';
    coche.value = acte;
    coche.checked = type.buttons.includes(acte);
    case_.append(coche, ` ${libelleActe(acte)}`);
    boutons.append(case_);
  }
  const enregistrer = document.createElement('button');
  enregistrer.type = 'button';
  enregistrer.textContent = 'Enregistrer';
  enregistrer.addEventListener('click', () => {
    const minutes = champDelai.value.trim();
    agir(
      main,
      store,
      '/owner/api/ticket/type',
      {
        id: type.id,
        expiry_minutes: minutes === '' ? null : Number(minutes),
        default_detail: champDefaut.value,
        buttons: [...boutons.querySelectorAll('input:checked')].map((c) => c.value),
      },
      `Type ${type.id} enregistré.`,
    );
  });
  bloc.append(titre, role, delai, defaut, boutons, enregistrer);
  return bloc;
}

export function renderTypes(main, payload, sig, store) {
  const section = main.querySelector('[data-section="types_tickets"]');
  const liste = section.querySelector('[data-types="liste"]');
  liste.replaceChildren(
    ...(payload.types || []).map((type) =>
      blocType(main, store, type, payload.boutons_possibles || []),
    ),
  );
  section.dataset.sig = sig;
}
