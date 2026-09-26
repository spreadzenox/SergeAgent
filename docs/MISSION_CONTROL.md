# Mission Control

Mission Control est la console web de Julien. On y voit ce que fait Serge
en temps réel, et on y règle tout ce qui peut l'être. Elle lit et écrit la
même base que Serge (`state/serge.db`) : rien n'y est inventé.

Discord sert de second canal, surtout pour trancher les tickets (voir la
fin de ce document).

---

## Accès

- Adresse : `https://<domaine de Serge>/owner`, servie par Caddy sur le VPS.
  Localement : `http://127.0.0.1:8790/owner` (service
  `serge-public-dashboard`).
- Connexion avec le jeton owner (`owner-dashboard.token` dans les secrets
  de l'instance). Il donne un cookie valable 12 heures. Les sessions sont
  stockées hachées dans `mc_sessions`. 10 essais de connexion par minute
  au maximum.
- La page `/` est publique : elle montre seulement si Serge tourne, sans
  aucune donnée personnelle ni secret.
- `Ctrl+K` (ou `Cmd+K`) ouvre une palette pour aller vite à une page ou à
  un ticket.

La page se met à jour toute seule : le serveur envoie les changements au
navigateur au fil de l'eau.

---

## Les pages

| Page | Adresse | Ce qu'on y voit | Ce qu'on y fait |
|---|---|---|---|
| **En direct** | `#/live` | La chaîne des 8 étapes et leurs débits, les tickets urgents, la file des tâches, l'activité récente, les budgets du jour. | Couper ou relancer Serge, une étape ou un type de tâche. |
| **Écoute** | `#/ecoute` | Le dernier cycle de l'étape 1, les invocations et ce qu'elles peuvent lire, les business candidats. | Écrire un texte de guidage et lancer un cycle. |
| **Système** | `#/system` | Les îlots (sous-systèmes), l'ordonnanceur, les campagnes, la population de prospects, l'e-mail. | Lecture. Accessible par `Ctrl+K`. |
| **Cerveau** | `#/mind` | Les invocations LLM : pensées, décisions récentes, tableau de toutes les invocations avec leur usage, signaux entrants. | Ouvrir la fiche d'une invocation, l'éteindre ou la rallumer, modifier son prompt. |
| **Décisions** | `#/tickets` | Les tickets à trancher, ce qui a changé, le rythme des décisions, le résumé quotidien. | Répondre à un ticket (mêmes boutons que sur Discord), discuter. |
| **Mémoire** | `#/memory` | Épisodes archivés, procédures, pièges, leçons, dernière consolidation, demandes de nouvelles capacités. | Chercher dans la mémoire, garder, modifier ou jeter une leçon. |
| **Policy** | `#/policy` | Toutes les règles : quotas, heures, budgets, taille des essais, réglages de l'écoute. | Modifier une règle et l'enregistrer. Chaque version est gardée. |
| **Économie** | `#/economy` | De l'envoi au paiement : touches, réponses, paiements, abonnements, coût des invocations LLM. | Lecture. |
| **Voix** | `#/voice` | L'état du pont téléphonique, le journal des appels, leur qualité. | Écouter un enregistrement. Pour couper les appels : page En direct. |
| **Health** | `#/health` | Taille du code, services systemd, versions, piste d'audit. | Lecture. |
| **Identité** | `#/identite` | Qui est Serge sur cette instance : nom, e-mail, SIRET, IBAN… La source est le fichier d'instance, pas la base. | Lecture. La fonction d'écriture existe (`ecrire_identite`) mais aucun bouton ne l'appelle. |

### Les fiches

Presque tout est cliquable et ouvre une fiche : `#/objet/<type>/<id>`.
Exemples : `#/objet/etape/pre_prospection`, `#/objet/llm/classify_reply`,
`#/objet/outil/memory_search`, `#/objet/canal/email`,
`#/objet/ecoute/pages` (les pages vraiment lues).

Le texte d'une fiche vient des colonnes de la base (exemple : `doc_md`),
pas du code JavaScript.

---

## Couper quelque chose

Tout passe par la même route, `POST /owner/api/coupe`, et est enregistré en
base. Trois niveaux :

1. **Serge entier** : le gros bouton rouge en haut de En direct. Plus
   aucune tâche ne démarre (`runtime_flags`, `scheduler.heartbeat`).
2. **Une étape** : `pipeline_steps.enabled`. Les tâches de l'étape ne
   démarrent plus.
3. **Un type de tâche** (aujourd'hui un « kind », exemple : `voice.send`) :
   coupé dans toutes les étapes.

Pour couper les appels, on coupe `voice.send`. L'ancien fichier
`KILL_SWITCH` a été supprimé.

**Décidé** : les « kinds » disparaissent. Le troisième niveau devient
« une invocation ».

---

## Les routes de l'API

Toutes demandent le jeton owner.

| Route | Rôle |
|---|---|
| `GET /owner/api/state?page=…` | L'état d'une page. |
| `GET /owner/api/stream` | Les mises à jour en temps réel. |
| `GET /owner/api/objet?type=…&id=…` | Une fiche. |
| `GET /owner/api/trace` | Le fil d'une tâche. |
| `GET /owner/api/ticket/carte` | La carte d'un ticket. |
| `GET /owner/api/memory/items`, `/owner/api/memory/search` | Lire et chercher la mémoire. |
| `GET /owner/api/voice/audio` | Un enregistrement d'appel (lien signé). |
| `POST /owner/api/coupe` | Couper ou relancer (Serge, étape, kind). |
| `POST /owner/api/kill`, `/owner/api/unkill` | Éteindre ou rallumer une invocation LLM. |
| `POST /owner/api/llm-point` | Modifier une invocation LLM : prompt, mode de sortie, information externe. |
| `POST /owner/api/etape` | Allumer ou éteindre une étape. |
| `POST /owner/api/ticket/acte`, `/ticket/item`, `/ticket/discuter` | Répondre à un ticket. |
| `POST /owner/api/memory/lesson` | Garder, modifier ou jeter une leçon. |
| `POST /owner/api/policy/edit`, `/policy/testing`, `/policy/propose` | Modifier la policy. |
| `POST /owner/api/listen/start` | Lancer un cycle de l'étape 1. |

---

## Discord

Le bot (`serge/discord/`) recopie les tickets dans un forum Discord privé,
avec un canal pour les urgences et un résumé quotidien. Les boutons ont le
même effet que dans Mission Control. Julien peut aussi écrire à Serge :
trois invocations LLM traitent ses messages : « Rendre le contexte FR »,
« Lire l'intention owner » et « Juger une conséquence ».

Installation : [`installation/DISCORD_SETUP.md`](installation/DISCORD_SETUP.md).
