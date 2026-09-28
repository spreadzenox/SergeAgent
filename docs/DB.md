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
   **28**.
   - Une base neuve saute directement à la version 7 (le socle,
     `serge/db/schema.py`), puis applique 8, 9, … 28.
   - Une base **plus récente** que le code refuse de démarrer
     (`MigrateError`). Revenir à un ancien commit ne défait pas une
     migration.
2. **Le remplissage de départ** : les 8 étapes, les canaux, les
   capacités déclarées par le code, puis le pipeline de départ
   (`config/pipeline.yaml` : files, outils, invocations, règles
   d'écriture, liens, déclencheurs).
3. **Le calcul des empreintes** du code de chaque objet
   (`serge/objet_sha.py`).

### La règle « insérer sans écraser »

Les réglages écrits dans le code et dans `config/pipeline.yaml` ne servent
qu'à remplir la base. Un objet **nouveau**, par exemple une nouvelle
invocation, est **ajouté** à la base, en entier. Un objet **existant**
n'est **jamais modifié** : prompt, allumée ou éteinte, niveau de modèle,
outils, règles d'écriture, liens. Serge met seulement à jour, à chaque
démarrage, ce qu'il calcule lui-même : l'empreinte des fichiers et le
chemin du code.

Exemple : Julien modifie le prompt d'une invocation dans Mission Control.
Un développeur modifie ensuite le prompt de départ dans
`config/pipeline.yaml`. Au déploiement, l'instance de Julien garde son
prompt ; une nouvelle instance reçoit celui du fichier.

Rien n'est effacé au démarrage : une invocation supprimée dans Mission
Control (`deleted_at` rempli) ne revient pas. Seule une capacité retirée du
code est marquée absente (`capabilities.available` = 0), et la fiche des
outils qui s'en servaient le signale.

---

## Les tables

Rangées selon les trois familles de [`MEMOIRE.md`](MEMOIRE.md), plus le
catalogue et la mécanique.

### L'état (ce qui est vrai maintenant)

| Table | Contenu |
|---|---|
| `ventures` | Les business, de leur découverte à leur fermeture. Colonne `lifecycle` : le statut. Fiche : `name`, `description`, `observations`, `sellable_offer`. `dedup_key` sert à écarter les doublons. |
| `venture_sources` | Les pages qui prouvent le besoin derrière un business. |
| `campaigns` | Les campagnes de test : business, canal, taille, fenêtre, seuils. |
| `contacts` | Les prospects et clients : une fiche par personne dans un business. Colonne `funnel_state` : où la personne en est. |
| `contact_addresses` | Les adresses d'une personne : une ligne par adresse (`channel` = `email`, `phone` ou un réseau, `value`, `active`). Une adresse n'est jamais écrasée : une nouvelle s'ajoute à côté. |
| `accounts_standing` | Les comptes web que Serge a créés : lieu, identifiant, mot de passe en clair, dossier de session, santé du compte. |
| `consents`, `blocklist` | Consentements et personnes à ne plus contacter. |
| `transactions` | Les paiements. |
| `subscriptions` | Les abonnements Stripe, chacun rattaché à son business (lu dans le champ `metadata.venture_id` du prix ou de l'abonnement Stripe). `venture_id` vide : business inconnu, signalé au journal. |
| `artifacts` | Les livrables (pas encore utilisée). |
| `listen_docs` | Les pages lues par l'écoute. |
| `listen_cycles`, `listen_cycle_docs` | Les cycles de l'étape 1 et les pages figées pour chacun. |
| `tickets`, `ticket_items` | Les décisions à prendre par Julien. |
| `policy_snapshots` | Les versions successives de la policy. La dernière fait foi. |
| `runtime_flags` | Les interrupteurs à chaud. Aujourd'hui : Serge démarré (`scheduler.heartbeat` à `on`). Sans cette ligne, Serge est arrêté. |

### Le journal (ce qui s'est passé, jamais modifié)

| Table | Contenu |
|---|---|
| `events` | Le journal général : qui, quoi, quand, avec un contenu JSON. |
| `event_rows` | Quel événement concerne quelle ligne (une table et un numéro). C'est l'historique d'une ligne, que lit l'outil « Lire l'historique ». Rempli par chaque écriture d'invocation et par chaque événement d'un business. |
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

### Le pipeline décrit en base

Le code n'est qu'un interpréteur de ces tables (`serge/interpreter/`) : il
lit la description d'une invocation, l'exécute, écrit sa réponse selon ses
règles, puis passe la main selon les liens. Elles sont remplies au
démarrage à partir de `config/pipeline.yaml`, sans jamais écraser ce qui
est déjà en base. Chaque table est expliquée dans
[`LOT6_CONCEPTION.md`](LOT6_CONCEPTION.md).

| Table | Contenu |
|---|---|
| `pipeline_steps` | Les 8 étapes : titre, texte d'explication, rang dans la chaîne, interrupteur. |
| `capabilities`, `capability_params` | Ce que le code sait faire, déclaré par le code au démarrage. |
| `tools` | Les outils : une capacité réglée pour un usage précis (`capability_id`). `montre_partout = 1` : appelable par toutes les invocations LLM. |
| `tool_db_*` | Pour chaque outil de lecture de la base : tables, colonnes, filtres, jointures (toujours faites) et paramètres autorisés. Le modèle n'écrit jamais de SQL. |
| `invocations` | Chaque invocation, avec ou sans LLM, et tous ses réglages : rôle, étape, niveau de modèle, prompt, file, priorité, interrupteur. |
| `invocation_tools`, `invocation_tool_params` | Les outils de chaque invocation (lus d'office ou appelables) et leurs paramètres figés. |
| `table_views`, `table_view_columns` | Ce qu'une invocation peut voir de chaque table, réglé une fois par table : son titre, la colonne des lignes les plus récentes, ses colonnes lisibles et celles de sa version courte (pour un business : numéro et nom). Une colonne absente n'est jamais lue. |
| `invocation_compare_tables` | Les tables à comparer ajoutées ou retirées pour une invocation. Par défaut, elle voit la version courte des tables où elle écrit. |
| `invocation_settings` | Les réglages d'une invocation, une ligne par réglage (exemple : « nombre d'idées = 2 », entre 1 et 5). Ils servent dans le prompt (`{nombre_idees}`), le format de la réponse, l'écriture et les paramètres. `policy` = 1 : modifiable sur la page Policy de MC. |
| `invocation_output_fields` | Le format de la réponse de chaque invocation. Une liste peut avoir un nombre d'éléments minimum et maximum (un nombre ou le nom d'un réglage). |
| `writable_tables`, `writable_columns` | Ce qu'une invocation a le droit d'écrire. |
| `invocation_writes`, `invocation_write_values` | Où chaque invocation écrit sa réponse, avec au besoin « au plus N lignes par passage ». |
| `status_transitions`, `dedup_rules`, `dedup_rule_columns` | Les protections : changements de statut permis, doublons. |
| `table_quotas` | Une protection de plus : « au plus N lignes dont telle colonne vaut l'une de ces valeurs » (exemple : au plus 3 business choisis pour un POC). Modifiable sur la page Policy. |
| `links`, `link_params`, `link_passages`, `link_passage_params` | Les liens entre invocations, ce qui est déjà passé, et ce qui attend un clic « Passer à la suite » avec ses paramètres (lien réglé à la main). |
| `triggers`, `trigger_params` | Ce qui lance une invocation : une ligne écrite, une heure, un bouton. |
| `queues`, `tasks`, `task_params`, `task_inputs`, `task_seen_tables` | Les deux files (conversations, travaux), leurs tâches, et ce que chaque tâche a reçu : ses lectures d'office, les tables à comparer et ses leçons (lignes données, lignes laissées de côté). |
| `llm_models` | Le modèle derrière chaque niveau (rapide, moyen, intelligent). |
| `serge_texts` | Les textes de Serge, dont sa présentation. |
| `canaux` | Les canaux par lesquels Serge écrit à un tiers (e-mail, voix). |

### La mécanique

| Table | Contenu |
|---|---|
| `mc_sessions` | Les sessions de Mission Control (jeton haché, jamais en clair). |
| `schema_version` | La version de la base. |

### Hors de cette base

- `state/voice/voice.db` : le journal des appels.
- La boîte SMS entrante.
- L'index de recherche `memory_fts`, créé à la première recherche.

---

## Décidé : ce qui va changer

L'ordre des chantiers est dans le [`TODO.md`](../TODO.md). Voici ce qu'ils
changent dans la base.

**Le pipeline passe en base (lot 6).** C'est fait pour les tables, le
runner, l'interpréteur, les réglages des invocations et les quotas
(version 26), ce que voit chaque invocation (version 27) et le passage
d'un lien à la main (version 28). `config/pipeline.yaml`
ne décrit encore qu'un demi-cycle de démonstration de l'étape 1 ; le vrai
pipeline, étape par étape, est l'objet des lots suivants (à commencer par
le lot 7).

**De nouvelles tables pour les conversations et les clients.** Une fiche
produit par business, avec ses questions fréquentes. Une table des
livraisons (ce qui reste à livrer à chaque client) et une table des
demandes clients (bugs, insatisfactions, idées). Sur la fiche de chaque
canal (table `canaux`), les délais de réponse : minimum, maximum, heures et
jours ouvrés.

**De nouvelles tables pour l'étape 1 et la mesure des tests.** La liste des
flux RSS suivis (`listen_feeds`), et une table de barème qui donne des
points à chaque réaction, canal par canal.

**De nouveaux statuts de business** : mis de côté (`PARKED`), en
maintenance (`MAINTENANCE`) et fermé (`CLOSED`), avec le code qui les pose.

---

## Ajouter une migration

1. Créer `serge/db/v0NN.py` avec une fonction `apply_v0NN(connection)`.
   Elle doit pouvoir tourner sur une base qui a déjà une partie du
   changement (utiliser `IF NOT EXISTS`, vérifier les colonnes).
2. L'ajouter à `MIGRATIONS` dans `serge/db/migrate.py`, et monter
   `SCHEMA_VERSION` dans `serge/db/schema.py`.
3. Ajouter un test dans `tests/test_migrate.py`.
4. Mettre à jour ce document.
