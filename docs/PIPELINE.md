# Le pipeline de Serge

Ce document explique comment Serge fonctionne, de bout en bout. Il est
écrit pour quelqu'un qui arrive sans rien connaître du projet, humain ou
LLM.

Chaque section distingue deux choses :

- **Aujourd'hui** : ce que le code fait vraiment.
- **Décidé** : ce que Julien a validé et qui reste à construire. La liste
  des chantiers est dans [`TODO.md`](../TODO.md).

Les décisions détaillées, question par question, sont dans
[`DECISIONS_REVUE.md`](DECISIONS_REVUE.md).

---

## Serge en une phrase

Serge est un programme qui cherche des besoins sur le web, teste des idées
de business auprès de vrais prospects, garde la meilleure, la construit, la
vend et encaisse. Julien valide les décisions importantes.

Serge tourne sur un serveur (le VPS de Julien). Chaque push sur la branche
`main` le redéploie automatiquement.

---

## La chaîne des 8 étapes

Tout Serge est organisé autour de cette chaîne. Un business avance d'étape
en étape.

| # | Étape | Identifiant | Ce qui s'y passe | Ce qui en sort |
|---|---|---|---|---|
| 1 | Pré-prospection | `pre_prospection` | Serge lit le web et des flux, repère des besoins, en tire des idées de business et choisit celles à tester. | Des business choisis pour un test (POC). |
| 2 | Conception du POC | `conception_poc` | Serge écrit le plan du test, le fait critiquer, Julien le valide, puis Serge construit un petit livrable d'essai. | Un plan validé et un livrable en ligne. |
| 3 | Prospection légère | `prospection_light` | Serge trouve une quarantaine de prospects, leur écrit ou les appelle, relance, répond. | Les réactions des prospects, notées en points. |
| 4 | Choix du business principal | `choix_venture` | Quand les 3 tests légers sont finis, Serge propose le meilleur, Julien valide. | Un business principal. Les autres sont mis de côté. |
| 5 | Construction | `build_venture` | Serge construit le vrai produit, le met en ligne sur un domaine dédié et branche le paiement. | Un produit vendable. |
| 6 | Prospection lourde | `prospection_lourde` | Serge prospecte à plus grande échelle, vend, livre, améliore le produit avec les retours clients. | Des clients et de l'argent. |
| 7 | Mémoire | `collect_feedback` | Serge tire des leçons de ce qui s'est passé. Julien garde ou jette chaque leçon. | Des leçons, des procédures, des pièges à éviter. |
| 8 | Caisse | `caisse` | Serge encaisse via Stripe, relance les impayés, rembourse. | Des paiements. |

Chaque étape a sa page : [`docs/etapes/`](etapes/).

**Couper une étape.** Chaque étape a un interrupteur dans Mission Control
(page En direct). Une étape coupée ne lance plus rien.

---

## La vie d'un business

Un business est une seule ligne dans la table `ventures`. Seul son statut
change au fil de sa vie.

**Aujourd'hui**, deux autres tables stockent aussi des business pendant
l'étape 1 : `business_candidates` et `poc_selections`. Les statuts de
`ventures` sont `CANDIDATE`, `SMOKE_READY`, `SMOKE_RUNNING`, `SMOKE_DONE`,
`FULL_READY`, `FULL_RUNNING`, `SCALE`, `PIVOT`, `EXTEND`, `KILLED`,
`INVALID_RETRY`.

**Décidé** : une seule table, `ventures`. Les deux autres disparaissent. Le
parcours devient :

```text
CANDIDATE        trouvé par l'étape 1
   ↓
POC_SELECTED     choisi pour être testé (prend une place de test léger)
   ↓
SMOKE_READY → SMOKE_RUNNING → SMOKE_DONE     test léger (étapes 2 et 3)
   ↓
choisi comme business principal (étape 4)  ──→  sinon PARKED
   ↓
construction (étape 5), puis prospection lourde (étape 6)
   ↓
MAINTENANCE      plus de nouveaux prospects, mais on livre, on répond,
   ↓             on corrige et on encaisse
CLOSED           plus rien à faire : fermé et archivé
```

Les noms exacts des statuts entre le choix et `MAINTENANCE` seront fixés
lors du chantier sur les données.

- `PARKED` : un business testé mais non choisi. Il libère sa place. Il peut
  être repris si le business principal s'arrête, tant que son test a moins
  de 60 jours.
- `KILLED` : arrêté alors qu'il n'avait aucun client.
- Chaque changement de statut est écrit dans le journal : qui, quand,
  pourquoi.

### Les places

Serge ne teste pas tout en même temps.

- **3 places en prospection légère.** Un business prend une place dès qu'il
  est choisi à l'étape 1 et la garde pendant les étapes 2 et 3. Premier
  arrivé, premier servi.
- **1 place en prospection lourde** : c'est le business principal.
- **Pas de file d'attente.** Quand les places sont prises, rien de nouveau
  n'entre. L'étape 1 ne cherche de nouveaux business que s'il reste une
  place libre en prospection légère.
- **Choix du principal** : seulement quand les 3 tests légers sont finis.
  Le passage en `MAINTENANCE` libère la place de prospection lourde.

Ces deux nombres (3 et 1) sont des réglages de la policy.

**Aujourd'hui** : le code impose « une seule venture active à la fois »
(`serge/funnels/lifecycle.py`) et rien d'autre. Les places sont à
construire.

---

## Les objets du catalogue

Serge est décrit comme un catalogue d'objets. Chaque objet a sa ligne en
base et sa fiche dans Mission Control.

| Objet | Table | Exemple |
|---|---|---|
| Étape | `pipeline_steps` | « Pré-prospection » |
| Invocation LLM | `llm_points` | « Explorer les besoins A » : un appel au LLM avec son prompt |
| Invocation technique | `tech_invocations` | « Ramasser des pages » : un traitement sans LLM |
| Tool | `tools` | « Chercher dans la mémoire » : une capacité qu'une invocation LLM peut appeler |
| Lien | `etape_liens` | « Pré-prospection → Conception du POC » |
| Canal | `canaux` | « E-mail » : un moyen d'écrire à un tiers |

**Au démarrage**, Serge calcule l'empreinte des fichiers de code de chaque
objet. Quand un fichier change, l'objet reçoit une nouvelle empreinte et
une nouvelle date. Mission Control peut ainsi montrer « code modifié le … ».

### La base fait foi

La base SQLite (`state/serge.db`) est la seule source de vérité. Le code et
les fichiers YAML (`config/`) ne servent qu'à remplir la base.

- **Nouvelle instance** : la base est remplie avec les valeurs du code.
- **Instance qui tourne** : une nouvelle version du code ajoute les objets
  nouveaux, mais **ne modifie jamais** un réglage existant. Exemple : si
  Julien a changé le prompt d'une invocation dans Mission Control, un
  déploiement ne l'écrase pas.
- **Objet retiré du code** : il est retiré de la base au démarrage.

### Décidé : trois changements de structure

1. **Plus de « kind ».** Aujourd'hui, le runner exécute des tâches typées
   par un « kind » (exemple : `listen.business_cycle`), et un kind lance
   plusieurs invocations d'un coup. Décidé : la tâche pointe directement
   vers une invocation. Une tâche = une invocation = un nœud du graphe.
2. **Des liens entre invocations.** Aujourd'hui, les liens relient
   seulement des étapes et ne transportent rien : ils servent à afficher un
   compteur. L'enchaînement des invocations est écrit dans le code des
   workers. Décidé : un lien relie deux invocations et transporte des
   données. Exemple : « chaque business choisi par l'étape 1 lance une
   conception de POC, avec l'identifiant du business en paramètre ». Un
   résultat n'est transmis qu'une fois. On déclenche le passage avec un
   bouton dans Mission Control, ou automatiquement si l'interrupteur
   « passage automatique » est allumé.
3. **Plus de « capsules ».** Aujourd'hui, la table `db_readers` décrit des
   capsules : un tool de lecture de la base avec des paramètres figés.
   Décidé : ces réglages vont sur le lien entre une invocation et un tool
   (`llm_point_tools`). Ce lien dit si le tool est **donné d'office**
   (Serge lit avant l'appel et met le résultat dans le prompt) ou
   **appelable** (le modèle décide), et quels paramètres sont figés.

---

## Qui décide quoi

Serge agit seul par défaut. Julien valide dans un ticket Discord, où l'on
peut discuter, les décisions suivantes :

| Décision | Étape | Sans réponse |
|---|---|---|
| Le plan d'un POC | 2 | s'applique après 48 h |
| Le choix du business principal | 4 | s'applique après 48 h |
| Le prix définitif et le plan du produit | 5 | — |
| Pivoter ou arrêter le business principal | 6 | — |
| Une nouvelle fonctionnalité importante ou un changement de prix | 6 | — |
| Un nouveau connecteur écrit par Serge | Web | — |
| Chaque message et publication LinkedIn | 3 et 6 | — |
| Un remboursement au-dessus du seuil | 8 | — |
| Les leçons proposées par la consolidation | 7 | acceptées après 48 h |

**La seule limite de Serge est la légalité.** Pas de tromperie : Serge
assume d'être un agent IA.

---

## Mesurer un test : la grille de points

Chaque canal (e-mail, appel, pub, réseau social, page web) traduit ce qui
se passe en **signaux** communs : vu, a réagi, a répondu, veut acheter,
refuse, se désinscrit, erreur technique, inclassable.

**Aujourd'hui** : ces signaux existent (`serge/observe/signals.py`), et des
compteurs U1 à U5 sont calculés dessus (`serge/funnels/metrics.py`).

**Décidé** : chaque signal rapporte des points de 0 à 10, selon un barème
par canal, modifiable dans Mission Control. Exemple pour l'e-mail : ouvert
0,5, clic 1, réponse 4, veut acheter 10, refus 1. On compare deux business
avec deux chiffres : **le total de points** et **les points par euro
dépensé**. Le détail de chaque signal reste dans le journal.

---

## Priorités et délais

**Décidé** :

- Chaque invocation a une priorité, réglable dans Mission Control. Le
  runner prend toujours la tâche prête la plus prioritaire.
  - 100 : traiter une réponse de prospect, désinscription.
  - 80 : relever les boîtes mail et les canaux entrants.
  - 50 : envois et relances.
  - 30 : construction.
  - 10 : écoute, veille, consolidation.
- Serge relève sa boîte mail toutes les 5 minutes. **Aujourd'hui**, c'est
  en place (réglage `windows.email_poll_minutes`).
- Serge répond à un prospect entre 5 et 20 minutes après son message
  pendant les heures ouvrées, et le lendemain matin sinon.

---

## Où lire la suite

- Les étapes une par une : [`docs/etapes/`](etapes/)
- La mémoire : [`MEMOIRE.md`](MEMOIRE.md)
- La base de données : [`DB.md`](DB.md)
- La console : [`MISSION_CONTROL.md`](MISSION_CONTROL.md)
- Les règles pour écrire du code : [`CHARTE.md`](CHARTE.md)
- L'installation : [`installation/`](installation/)
