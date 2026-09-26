# La base de données

Serge range tout dans une base SQLite : `$SERGE_SYSTEM_ROOT/state/serge.db`.
C'est la **seule source de vérité**. Mission Control la lit et y écrit ;
le code et les fichiers de `config/` ne servent qu'à la remplir.

Le déploiement crée une base vide à la première installation. Il ne la
recrée jamais ensuite.

---

## Ce qui se passe à l'ouverture

`open_db` ouvre la base (mode WAL, droits `0600`), puis `init_schema`
(`serge/db/boot.py`) fait trois choses dans l'ordre :

1. **Les migrations** (`serge/db/migrate.py`). Chaque changement de
   structure est une fonction `apply_v0NN` (fichiers `serge/db/v0NN.py`).
   Serge applique celles qui manquent, dans l'ordre. Version actuelle :
   **20**.
   - Une base neuve saute directement à la version 7 (le socle,
     `serge/db/schema.py`), puis applique 8, 9, … 20.
   - Une base **plus récente** que le code refuse de démarrer
     (`MigrateError`). Revenir à un ancien commit ne défait pas une
     migration.
2. **Le remplissage du catalogue** : étapes, tools, invocations LLM et
   techniques, canaux, liens.
3. **Le calcul des empreintes** du code de chaque objet
   (`serge/objet_sha.py`).

### La règle « insérer sans écraser »

- Un objet **nouveau** dans le code (exemple : une nouvelle invocation)
  est **ajouté** à la base.
- Un objet **existant** n'est **jamais modifié** par le code pour ce que
  Julien peut régler dans Mission Control : prompt, allumé ou éteint,
  niveau de modèle, tools.
- Serge met à jour à chaque démarrage les informations qu'il calcule
  lui-même : empreinte des fichiers, chemin du code.
- Un objet **retiré** du code est retiré de la base. L'historique
  (exemple : `llm_usage`) reste.

Exemple : Julien modifie le prompt de « Explorer les besoins A » dans
Mission Control. Un développeur modifie ensuite le prompt de départ dans le
code. Au déploiement, l'instance de Julien garde son prompt ; une nouvelle
instance reçoit celui du code.

---

## Les tables

Rangées selon les trois familles de [`MEMOIRE.md`](MEMOIRE.md), plus le
catalogue et la mécanique.

### L'état (ce qui est vrai maintenant)

| Table | Contenu |
|---|---|
| `ventures` | Les business. Colonne `lifecycle` : le statut. |
| `campaigns` | Les campagnes de test : business, canal, taille, fenêtre, seuils. |
| `contacts` | Les prospects et clients. Leurs adresses sont aujourd'hui dans une colonne JSON, `contact_reference_by_canal` (une adresse par canal). |
| `accounts_standing` | Les comptes web que Serge a créés : lieu, identifiant, mot de passe en clair, dossier de session, santé du compte. |
| `consents`, `blocklist` | Consentements et personnes à ne plus contacter. |
| `transactions` | Les paiements. |
| `subscriptions` | Les abonnements Stripe. |
| `artifacts` | Les livrables (pas encore utilisée). |
| `listen_docs` | Les pages lues par l'écoute. |
| `listen_cycles`, `listen_cycle_docs` | Les cycles de l'étape 1 et les pages figées pour chacun. |
| `business_candidates`, `business_candidate_sources`, `poc_selections` | Les business trouvés par l'étape 1, leurs pages de preuve, les sélections. |
| `tickets`, `ticket_items` | Les décisions à prendre par Julien. |
| `policy_snapshots` | Les versions successives de la policy. La dernière fait foi. |
| `runtime_flags` | Les interrupteurs : heartbeat, kinds coupés. |

### Le journal (ce qui s'est passé, jamais modifié)

| Table | Contenu |
|---|---|
| `events` | Le journal général : qui, quoi, quand, avec un contenu JSON. |
| `touches` | Chaque envoi à un prospect. |
| `inbound_events` | Chaque réaction reçue, traduite en signal. |
| `ticket_events` | L'historique de chaque ticket. |
| `llm_usage` | Chaque appel au LLM : invocation, modèle, tokens, durée, résultat. |
| `episode_archives` | Les archives d'événements anciens. |

### La connaissance

| Table | Contenu |
|---|---|
| `lessons` | Les leçons, avec leur fiabilité et leurs sources. |
| `playbooks` | Les procédures qui marchent. |
| `pitfalls` | Les pièges à éviter. |
| `summaries` | Des résumés versionnés (la version précédente est gardée). |

### Le catalogue

| Table | Contenu |
|---|---|
| `pipeline_steps` | Les 8 étapes : titre, texte d'explication, interrupteur. |
| `etape_liens` | Les liens entre étapes. Colonne `debit` : le nom d'une table dont Mission Control compte les lignes. |
| `llm_points` | Les invocations LLM : niveau de modèle, prompt, mode de sortie, allumée ou non. |
| `llm_point_tools` | Quels tools chaque invocation peut appeler. |
| `tech_invocations` | Les invocations techniques (sans LLM). |
| `tools` | Les tools. `montre_partout = 1` : offert à toutes les invocations. |
| `canaux`, `brique_canaux` | Les canaux et les invocations qui écrivent par eux. |
| `db_readers`, `llm_point_readers`, `db_reader_fixed_params`, `db_reader_fixed_joins` | Les capsules de lecture de la base (à supprimer, voir ci-dessous). |
| `tool_db_*` | Pour chaque tool de lecture de la base : tables, colonnes, filtres, jointures et paramètres autorisés. Le modèle n'écrit jamais de SQL. |

### La mécanique

| Table | Contenu |
|---|---|
| `work_items` | La file des tâches du runner. |
| `mc_sessions` | Les sessions de Mission Control (jeton haché, jamais en clair). |
| `schema_version` | La version de la base. |

### Hors de cette base

- `state/voice/voice.db` : le journal des appels.
- La boîte SMS entrante.
- L'index de recherche `memory_fts`, créé à la première recherche.

---

## Décidé : ce qui va changer

Voir [`TODO.md`](../TODO.md) pour l'ordre des chantiers.

- `business_candidates`, `business_candidate_sources` et `poc_selections`
  sont fondues dans `ventures`, avec de nouveaux statuts (`POC_SELECTED`,
  `PARKED`, `MAINTENANCE`, `CLOSED`…). La table de liens business ↔ page
  reste.
- `contacts` : une ligne par personne, et une nouvelle table avec **une
  ligne par adresse** (canal, valeur, active ou non). Regroupement
  automatique seulement sur un e-mail ou un téléphone identique. La
  colonne JSON disparaît.
- Nouvelles tables : `deliveries` (ce qui reste à livrer), `product_requests`
  (les demandes des clients), `listen_feeds` (les flux suivis), et une
  table de barème de points par canal et par signal.
- `subscriptions` : chaque abonnement est rattaché à son vrai business.
- Les capsules (`db_readers` et tables associées) disparaissent : leurs
  réglages vont sur `llm_point_tools`.
- `work_items.kind` et les interrupteurs par kind disparaissent : une tâche
  pointe vers une invocation.
- `etape_liens` est remplacée par des liens entre invocations, qui
  transportent des données.

---

## Ajouter une migration

1. Créer `serge/db/v0NN.py` avec une fonction `apply_v0NN(connection)`.
   Elle doit pouvoir tourner sur une base qui a déjà une partie du
   changement (utiliser `IF NOT EXISTS`, vérifier les colonnes).
2. L'ajouter à `MIGRATIONS` dans `serge/db/migrate.py`, et monter
   `SCHEMA_VERSION` dans `serge/db/schema.py`.
3. Ajouter un test dans `tests/test_migrate.py`.
4. Mettre à jour ce document.
