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
| **En direct** | `#/live` | La chaîne des 8 étapes, leurs invocations dans l'ordre des liens, et le nombre de résultats passés d'une étape à l'autre ; les tickets urgents, les deux files de tâches (avec la raison quand des tâches attendent, par exemple le plafond du jour ou du mois atteint), l'activité récente, les budgets : le coût des modèles du jour et ce que Serge coûte ce mois-ci, face à leurs plafonds (le coût réel facturé par OpenRouter ; les jetons des appels dont le coût n'est pas connu sont signalés à part, jamais estimés), et les envois du jour face à leurs quotas. | Démarrer ou arrêter Serge ; couper une étape, une file ou une invocation. |
| **Écoute** | `#/ecoute` | L'étape 1 : ses boutons tels qu'ils sont déclarés en base (chacun avec ses champs et ses conditions, par exemple « Places de test occupées : 2 sur 3 »), le dernier cycle (pages par étiquette, idées écrites, note du choix), les business candidats et choisis avec la raison du choix, les flux RSS suivis (pages ramenées, pages utiles), les invocations de l'étape. | Remplir les champs d'un bouton et cliquer : il lance l'invocation de son déclencheur (grisé si un quota est plein ; une confirmation est demandée pour « Abandonner le cycle » et « Effacer les idées »). Couper ou rallumer un flux. |
| **Pipeline** | `#/pipeline` | Tout le pipeline tel qu'il est en base : les liens (avec ce qui attend un clic), les déclencheurs, les outils, les capacités du code, ce que les invocations voient de chaque table, le modèle derrière chaque niveau et le texte « Qui est Serge ». | Choisir le modèle de chaque niveau parmi ceux d'OpenRouter, avec leurs prix et une recommandation (vide : celui de l'installation), réécrire le texte « Qui est Serge » ; ouvrir la fiche d'un lien, d'un outil, d'une invocation ou d'une table. |
| **Système** | `#/system` | Les îlots (sous-systèmes), les files de tâches, les campagnes, la population de prospects, l'e-mail. | Lecture. Accessible par `Ctrl+K`. |
| **Cerveau** | `#/mind` | Pensées, décisions récentes, tableau de toutes les invocations en base (niveau, file, priorité, usage sur 7 jours), signaux entrants. | Ouvrir la fiche d'une invocation, l'éteindre ou la rallumer. |
| **Décisions** | `#/tickets` | Les tickets à trancher, ce qui a changé, le rythme des décisions, le résumé quotidien. | Répondre à un ticket (boutons du registre, y compris QCM et réponse libre), discuter plusieurs fois et lire les messages. Les tickets actifs sont tous présents ; les 50 derniers clos complètent la liste. |
| **Mémoire** | `#/memory` | Épisodes archivés, procédures, pièges, leçons, dernière consolidation, demandes de nouvelles capacités. | Chercher dans la mémoire ; ouvrir une leçon pour la modifier ou la jeter. Les propositions de leçons sont dans Décisions et ouvrent leur ticket pour garder, modifier ou jeter chaque proposition. |
| **Policy** | `#/policy` | Les réglages généraux (argent, plafonds par canal, horaires, pays, santé des comptes, téléphone, encaissement, mémoire, résumé du jour, accord des gens), la taille des essais, et les réglages des invocations et les quotas des tables marqués « policy », rangés par étape et par invocation. Chaque réglage affiché est lu par un programme : un test le vérifie. | Modifier une règle et l'enregistrer. Chaque version de la policy générale est gardée ; chaque changement de réglage est noté au journal. |
| **Économie** | `#/economy` | De l'envoi au paiement : touches, réponses, paiements, derniers envois et livrables, abonnements, coût des invocations LLM (le coût réel facturé par OpenRouter, avec les jetons sans coût connu à part). | Lecture. |
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

## Choisir le modèle d'un niveau

Sur la page Pipeline, chaque niveau (rapide, moyen, intelligent) a un champ
pour le modèle qu'il utilise. Il prend effet au prochain appel au modèle,
sans redémarrage ; une tâche en cours finit avec l'ancien.

**Chercher.** Quelques lettres dans le champ (« deepseek », « gpt mini »)
filtrent les modèles d'OpenRouter. Chaque proposition montre les vrais
tarifs, en dollars par million de jetons, tels qu'OpenRouter les donne
(entrée, lecture et écriture de cache quand le modèle en a, sortie) et, entre
parenthèses, le prix au mélange de jetons de Serge ; puis la taille du
contexte, la prise en charge des outils et la note d'intelligence quand elle
existe. Les modèles sans outils et les variantes `:batch` passent après les
autres. Le catalogue est lu sur OpenRouter à chaque ouverture de la page
(environ une demi-seconde) : il est toujours à jour. Si OpenRouter ne répond
pas, la page garde le dernier catalogue lu, ou laisse la saisie libre sans
vérification.

**Recommander.** Sous chaque champ, la page propose le modèle au meilleur
rapport note / prix du niveau :

1. seuls comptent les modèles qui savent appeler des outils, lisent au moins
   128 000 jetons, ne sont pas gratuits (les gratuits sont limités et
   échouent souvent), ne sont pas une variante `:batch` (le Batch API
   d'OpenRouter répond sous 24 h, alors que Serge fait des appels directs),
   sont sortis depuis moins d'un an et ne sont pas retirés ;
2. ils doivent coûter au plus le **prix maximum** du niveau (en dollars par
   million de jetons, au mélange de jetons de Serge) ;
3. parmi eux, la meilleure note donne la référence ; on garde les modèles
   qui en ont au moins la **tolérance** du niveau (en %) ;
4. on recommande celui dont le rapport note / prix est le meilleur.

Le prix maximum et la tolérance de chaque niveau se règlent sur la page, à
côté du modèle, avec le même bouton « Enregistrer » : ils vivent en base
(`llm_models`), et le changement est noté au journal avec l'ancienne valeur.
Au départ : rapide 0,30 $/M et 85 % (il cherche la valeur : un peu moins
d'intelligence pour un prix plus bas), moyen 1,50 $/M et 95 %, intelligent
8 $/M et 95 % (les deux visent presque la meilleure note sous leur maximum).
Un prix maximum à 0 veut dire « pas réglé » : rien n'est recommandé.

**Le mélange de jetons.** Le prix d'un modèle dépend de ce que Serge lui fait
lire et écrire : ses boucles d'outils relisent tout l'historique à chaque
tour, donc il lit bien plus qu'il n'écrit, et un modèle à sortie chère lui
coûte moins qu'il n'y paraît. Le mélange est mesuré dans `llm_usage` sur les
30 derniers jours (appels qui ont eu une réponse) ; la page dit la part de
jetons lus et sur combien de jetons elle est mesurée. Sous 100 000 jetons
enregistrés, elle suppose 75 % de jetons lus (trois pour un écrit) et le dit.
Le prix compte toute la lecture au tarif normal : la remise du cache n'est
pas déduite, c'est donc le prix sans remise, le plus prudent. Le coût réel de
chaque appel, lui, est celui qu'OpenRouter a facturé (`usage.cost`), cache
compris.

La note d'intelligence est l'indice d'Artificial Analysis (plus haut = mieux),
que `/models` donne avec chaque modèle : pas de clé d'API ni d'appel de plus.
OpenRouter n'en a pas pour tous les modèles (le 30 septembre 2026 : 146 sur
464, soit 31 % ; 98 des 355 modèles hors variantes et alias), et **un modèle
sans note n'est jamais recommandé**, même s'il est bon ; on peut toujours le
choisir à la main. La page dit combien de modèles sont notés. Choisir à la
main une variante `:batch` ou un modèle sans outils est accepté, avec un
avertissement. Le bouton « Utiliser » recopie la recommandation dans le champ
du modèle ; rien n'est enregistré avant « Enregistrer ».

---

## Navigation, saisies et sessions

La carte des étapes garde des cases distinctes sur ordinateur et téléphone.
Les lignes de Pipeline et des fiches s’ouvrent aussi avec Entrée ou Espace.
La palette propose toutes les pages, dont Écoute, Pipeline et Système, et
les tickets ouverts.

Les champs modifiés restent en place quand le flux actualise Pipeline,
Policy ou les conditions d’un bouton d’Écoute. Enregistrer un réglage ne
supprime pas les brouillons des autres réglages. Une erreur réseau garde
la saisie et affiche un message visible.

Les tailles des essais sont des entiers cohérents et ne peuvent changer
pendant une campagne RUNNING, par aucune des deux routes Policy. Les
réglages numériques des invocations désignent des nombres d’éléments :
ils refusent les décimales et les valeurs non finies.

« Se déconnecter » révoque la session. Le flux déjà ouvert vérifie sa
session à chaque tour (toutes les deux secondes) puis se ferme si elle
est révoquée ou expirée. L’audio exige la même session ; aucun lien public
signé ne permet de contourner cette vérification. La pastille de connexion
suit les réponses du flux ou du polling, et signale une interruption.

La page publique dit seulement si Serge est arrêté, démarré au repos ou
occupé. Elle n’affirme pas que tous les services sont opérationnels.

## Les routes de l'API

Toutes demandent le jeton owner ou une session valide. Les corps JSON sont limités à 64 Kio (413 au-delà), assez pour les champs de 4 000 caractères, y compris accentués.

| Route | Rôle |
|---|---|
| `GET /owner/api/state?page=…` | L'état d'une page. |
| `GET /owner/api/stream` | Les mises à jour en temps réel. |
| `GET /owner/api/objet?type=…&id=…` | Une fiche. |
| `GET /owner/api/trace` | Le fil d'une tâche. |
| `GET /owner/api/ticket/carte` | La carte d'un ticket. |
| `GET /owner/api/memory/items`, `/owner/api/memory/search` | Lire et chercher la mémoire. |
| `GET /owner/api/voice/audio` | Un enregistrement d’appel, réservé à une session owner valide. |
| `POST /owner/api/coupe` | Couper ou relancer (Serge, étape, file, invocation). |
| `POST /owner/api/invocation` | Modifier une invocation : prompt, niveau de modèle, file, priorité, allumée. |
| `POST /owner/api/etape` | Allumer ou éteindre une étape. |
| `POST /owner/api/ticket/acte`, `/ticket/item`, `/ticket/discuter` | Répondre à un ticket. |
| `POST /owner/api/memory/lesson` | Garder, modifier ou jeter une leçon. |
| `POST /owner/api/policy/edit`, `/policy/testing` | Modifier la policy. |
| `POST /owner/api/reglage` | Changer un réglage d'invocation ou un quota marqué « policy » (valeur vérifiée, changement noté au journal). |
| `POST /owner/api/bouton` | Un déclencheur « bouton » : crée la tâche de son invocation, avec les champs du formulaire. Refusé, avec la raison, si l'un de ses quotas est plein. |
| `POST /owner/api/flux` | Couper ou rallumer un flux RSS suivi (page Écoute). |
| `POST /owner/api/tache/relancer` | Remettre une tâche échouée dans sa file (bouton « Relancer la tâche » de sa fiche). |
| `POST /owner/api/tache/annuler` | Annuler une tâche en attente (bouton « Annuler la tâche » de sa fiche) : ce qu'elle aurait lancé ensuite ne part pas non plus. |
| `POST /owner/api/lien/passer` | « Passer à la suite » : lance un passage qui attendait un clic, avec ses paramètres gardés (fiche du lien). |
| `POST /owner/api/lien/auto` | L'interrupteur « passage automatique » d'un lien (pour les passages suivants). |
| `GET /owner/api/pipeline/modeles` | Les modèles d'OpenRouter (prix, contexte, outils, note d'intelligence), leurs recommandations par niveau et l'état du catalogue. Lu sur OpenRouter à chaque appel. |
| `POST /owner/api/pipeline/modele` | Un niveau (rapide, moyen, intelligent) : son modèle (vide pour celui de l'installation), et facultativement son prix maximum (`max_price`, $/M) et sa tolérance (`tolerance`, entier de 1 à 100 %) (page Pipeline). Un identifiant qu'OpenRouter ne connaît pas est refusé (409) ; un modèle sans outils ou une variante `:batch` est accepté avec un avertissement ; si OpenRouter ne répond pas, la saisie n'est pas bloquée. L'événement `pipeline.model` garde l'ancien modèle. |
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
