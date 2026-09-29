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
| **En direct** | `#/live` | La chaîne des 8 étapes, leurs invocations dans l'ordre des liens, et le nombre de résultats passés d'une étape à l'autre ; les tickets urgents, les deux files de tâches (avec la raison quand des tâches attendent, par exemple le plafond LLM du jour), l'activité récente, les budgets du jour (la dépense LLM au coût réel facturé par OpenRouter, avec la part estimée s'il y en a une). | Démarrer ou arrêter Serge ; couper une étape, une file ou une invocation. |
| **Écoute** | `#/ecoute` | L'étape 1 : ses boutons tels qu'ils sont déclarés en base (chacun avec ses champs et ses conditions, par exemple « Places de test occupées : 2 sur 3 »), le dernier cycle (pages par étiquette, idées écrites, note du choix), les business candidats et choisis avec la raison du choix, les flux RSS suivis (pages ramenées, pages utiles), les invocations de l'étape. | Remplir les champs d'un bouton et cliquer : il lance l'invocation de son déclencheur (grisé si un quota est plein ; une confirmation est demandée pour « Abandonner le cycle » et « Effacer les idées »). Couper ou rallumer un flux. |
| **Pipeline** | `#/pipeline` | Tout le pipeline tel qu'il est en base : les liens (avec ce qui attend un clic), les déclencheurs, les outils, les capacités du code, ce que les invocations voient de chaque table, le modèle derrière chaque niveau et le texte « Qui est Serge ». | Choisir le modèle de chaque niveau (vide : celui de l'installation), réécrire le texte « Qui est Serge » ; ouvrir la fiche d'un lien, d'un outil, d'une invocation ou d'une table. |
| **Système** | `#/system` | Les îlots (sous-systèmes), les files de tâches, les campagnes, la population de prospects, l'e-mail. | Lecture. Accessible par `Ctrl+K`. |
| **Cerveau** | `#/mind` | Pensées, décisions récentes, tableau de toutes les invocations en base (niveau, file, priorité, usage sur 7 jours), signaux entrants. | Ouvrir la fiche d'une invocation, l'éteindre ou la rallumer. |
| **Décisions** | `#/tickets` | Les tickets à trancher, ce qui a changé, le rythme des décisions, le résumé quotidien. | Répondre à un ticket (mêmes boutons que sur Discord), discuter. |
| **Mémoire** | `#/memory` | Épisodes archivés, procédures, pièges, leçons, dernière consolidation, demandes de nouvelles capacités. | Chercher dans la mémoire, garder, modifier ou jeter une leçon. |
| **Policy** | `#/policy` | Toutes les règles : quotas, heures, budgets, taille des essais ; et les réglages des invocations et les quotas des tables marqués « policy », rangés par étape et par invocation. | Modifier une règle et l'enregistrer. Chaque version de la policy générale est gardée ; chaque changement de réglage est noté au journal. |
| **Économie** | `#/economy` | De l'envoi au paiement : touches, réponses, paiements, abonnements, coût des invocations LLM. | Lecture. |
| **Voix** | `#/voice` | L'état du pont téléphonique, le journal des appels, leur qualité. | Écouter un enregistrement. Pour couper les appels : page En direct. |
| **Health** | `#/health` | Taille du code, services systemd, versions, piste d'audit. | Lecture. |
| **Identité** | `#/identite` | Qui est Serge sur cette instance : nom, e-mail, SIRET, IBAN… La source est le fichier d'instance, pas la base. | Lecture. La fonction d'écriture existe (`ecrire_identite`) mais aucun bouton ne l'appelle. |

### Les fiches

Presque tout est cliquable et ouvre une fiche : `#/objet/<type>/<id>`.
Exemples : `#/objet/etape/pre_prospection`, `#/objet/llm/<id>` (une
invocation), `#/objet/outil/memory_search`, `#/objet/task/<id>` (une
tâche), `#/objet/canal/email`, `#/objet/ecoute/pages` (les pages vraiment
lues).

Le texte d'une fiche vient des colonnes de la base (exemple : `doc_md`),
pas du code JavaScript. La fiche d'une invocation montre tout ce que la
base dit d'elle : son rôle, sa sorte (avec ou sans LLM), son étape, sa
file, sa priorité, son niveau de modèle, son prompt, ce qu'elle lit
d'office (ce qu'elle doit traiter), ce qu'elle voit pour comparer (la
version courte des tables, avec un bouton pour retirer, remettre ou
ajouter une table), ses leçons, ce qu'elle peut appeler, le format de sa
réponse, où sa réponse est écrite, ce qui la lance, ce qu'elle lance
ensuite, et ses derniers appels au modèle (tours d'outils, réponses, appels ratés, avec les jetons et le coût réel). La fiche d'une tâche montre ses
paramètres et ce qu'elle a reçu (par exemple « Pour comparer : Les
business — 20 lignes, 230 laissées de côté ») ; si elle a échoué, un
bouton « Relancer la tâche » la remet dans sa file ; si elle attend, un
bouton « Annuler la tâche » la retire. La fiche d'un lien
(`#/objet/lien/<id>`, ouverte depuis la fiche d'une invocation) montre ce
qui est déjà passé et ce qui attend un clic, avec un bouton « Passer à la
suite » par passage et l'interrupteur « passage automatique ».

---

## Couper quelque chose

Tout passe par la même route, `POST /owner/api/coupe`, et est enregistré en
base. Quatre niveaux, tous en bas de la page En direct (sauf le premier) :

1. **Serge entier** : le gros bouton en haut de En direct. **Serge est
   arrêté par défaut**, même sur une instance neuve et après chaque
   déploiement : il ne tourne qu'après un clic sur « Démarrer Serge »
   (avec une confirmation). Arrêté, les files ne créent ni ne prennent de
   tâche, et la voix ne décroche pas et n'appelle pas (`runtime_flags`,
   `scheduler.heartbeat` à `on`).
2. **Une étape** : `pipeline_steps.enabled`. Les tâches des invocations de
   l'étape attendent.
3. **Une file** : `queues.enabled`. Exemple : couper `works` arrête les
   travaux longs, les conversations continuent.
4. **Une invocation** : `invocations.enabled`. Ses tâches attendent, et
   aucune nouvelle tâche n'est créée pour elle. C'est aussi le bouton
   « Éteindre » de la page Cerveau.

L'ancien fichier `KILL_SWITCH` et les « kinds » ont été supprimés.

---

## Décidé : ce qui va changer

Julien et Clem ont décidé que le code n'est qu'un interpréteur de la base
(voir [`PIPELINE.md`](PIPELINE.md)). Mission Control devient donc l'endroit
où l'on voit et règle tout le pipeline, et pas seulement les prompts.

**Chaque invocation se règle entièrement depuis sa fiche.** Aujourd'hui,
sa fiche montre tout ce qui la décrit, et l'API
`POST /owner/api/invocation` modifie son prompt, son niveau de modèle, sa
file, sa priorité et son interrupteur. Demain, la fiche permettra de
modifier tout le reste (ce qu'elle reçoit, ses outils, le format de sa
réponse, où elle écrit) : c'est l'éditeur sans code, plus bas.

**Une tâche arrêtée au milieu d'une action extérieure** (un envoi, un
remboursement) apparaîtra pour qu'on vérifie avant de la relancer (lot 8).

**La fiche d'un prospect montre son fil de discussion**, tous canaux
confondus : ce que Serge a envoyé, avec le texte, et ce que la personne a
répondu. Les réponses qu'on n'a pas pu rattacher à un prospect ont leur
propre liste, pour qu'aucune ne soit ignorée.

**La fiche d'un canal porte ses délais de réponse** : délai minimum,
délai maximum, heures et jours ouvrés. Exemple : e-mail entre 5 et
20 minutes, LinkedIn entre 1 et 4 heures.

**La fiche d'un business montre sa fiche produit**, avec ses questions
fréquentes, que Julien peut compléter.

**Plus tard, un éditeur sans code.** C'est le dernier lot du TODO : une
page qui montre le pipeline comme un schéma et permet de le modifier en
direct, sans écrire de code. On y crée une invocation de toutes pièces
(rôle, modèle, prompt, ce qu'elle reçoit, ce qu'elle peut appeler, où elle
écrit et avec quelles protections), on trace un lien, on ajoute un
déclencheur. Tout ce que la page permet n'est que de l'écriture en base :
elle ne demande jamais de code nouveau.
Chaque changement est écrit au journal avec la date et l'auteur, pour
pouvoir revenir en arrière.

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
| `POST /owner/api/coupe` | Couper ou relancer (Serge, étape, file, invocation). |
| `POST /owner/api/invocation` | Modifier une invocation : prompt, niveau de modèle, file, priorité, allumée. |
| `POST /owner/api/etape` | Allumer ou éteindre une étape. |
| `POST /owner/api/ticket/acte`, `/ticket/item`, `/ticket/discuter` | Répondre à un ticket. |
| `POST /owner/api/memory/lesson` | Garder, modifier ou jeter une leçon. |
| `POST /owner/api/policy/edit`, `/policy/testing`, `/policy/propose` | Modifier la policy. |
| `POST /owner/api/reglage` | Changer un réglage d'invocation ou un quota marqué « policy » (valeur vérifiée, changement noté au journal). |
| `POST /owner/api/bouton` | Un déclencheur « bouton » : crée la tâche de son invocation, avec les champs du formulaire. Refusé, avec la raison, si l'un de ses quotas est plein. |
| `POST /owner/api/flux` | Couper ou rallumer un flux RSS suivi (page Écoute). |
| `POST /owner/api/tache/relancer` | Remettre une tâche échouée dans sa file (bouton « Relancer la tâche » de sa fiche). |
| `POST /owner/api/tache/annuler` | Annuler une tâche en attente (bouton « Annuler la tâche » de sa fiche) : ce qu'elle aurait lancé ensuite ne part pas non plus. |
| `POST /owner/api/lien/passer` | « Passer à la suite » : lance un passage qui attendait un clic, avec ses paramètres gardés (fiche du lien). |
| `POST /owner/api/lien/auto` | L'interrupteur « passage automatique » d'un lien (pour les passages suivants). |
| `POST /owner/api/pipeline/modele` | Le modèle derrière un niveau (rapide, moyen, intelligent) ; vide pour celui de l'installation (page Pipeline). |
| `POST /owner/api/pipeline/texte` | Le texte « Qui est Serge » (page Pipeline). |
| `POST /owner/api/invocation/comparer` | Retirer, remettre ou ajouter une table que l'invocation voit pour comparer (boutons de sa fiche). Seule une table décrite en base (`table_views`) peut être vue. |

---

## Discord

Le bot (`serge/discord/`) recopie les tickets dans un forum Discord privé,
avec un canal pour les urgences et un résumé quotidien. Les boutons ont le
même effet que dans Mission Control. Le ticket est recopié tel qu'il est
en base, sans résumé par un modèle. Les messages libres de Julien ne sont
plus traités depuis le lot 6 : ils reviendront par le pipeline en base
(voir « Plus tard » dans le [`TODO.md`](../TODO.md)).

Installation : [`installation/DISCORD_SETUP.md`](installation/DISCORD_SETUP.md).
