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
   **23**.
   - Une base neuve saute directement à la version 7 (le socle,
     `serge/db/schema.py`), puis applique 8, 9, … 23.
   - Une base **plus récente** que le code refuse de démarrer
     (`MigrateError`). Revenir à un ancien commit ne défait pas une
     migration.
2. **Le remplissage du catalogue** : étapes, tools, invocations LLM et
   techniques, canaux, liens.
3. **Le calcul des empreintes** du code de chaque objet
   (`serge/objet_sha.py`).

### La règle « insérer sans écraser »

Les réglages écrits dans le code ne servent qu'à remplir la base. Un objet
**nouveau** dans le code, par exemple une nouvelle invocation, est
**ajouté** à la base. Un objet **existant** n'est **jamais modifié** par le
code pour tout ce que Julien peut régler dans Mission Control : prompt,
allumé ou éteint, niveau de modèle, tools. Serge met seulement à jour, à
chaque démarrage, les informations qu'il calcule lui-même : l'empreinte des
fichiers et le chemin du code.

Exemple : Julien modifie le prompt de « Explorer les besoins A » dans
Mission Control. Un développeur modifie ensuite le prompt de départ dans le
code. Au déploiement, l'instance de Julien garde son prompt ; une nouvelle
instance reçoit celui du code.

Aujourd'hui, un objet **retiré** du code est aussi retiré de la base au
démarrage (l'historique, comme les appels au LLM, reste). Ça va changer :
voir la fin de ce document.

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

L'ordre des chantiers est dans le [`TODO.md`](../TODO.md). Voici ce qu'ils
changent dans la base.

**Le pipeline entier passe en base.** Julien et Clem ont décidé que le code
n'est qu'un interpréteur de la base : l'ordre des invocations et tous leurs
paramètres sont en base, et seulement en base. Il faudra donc des tables
pour décrire chaque invocation en entier (son rôle, son modèle, son prompt,
ce qu'elle reçoit dès le départ, le format de sa réponse et où elle est
écrite, sa priorité et sa file), les liens entre invocations (quel
résultat passe de l'une à l'autre, avec quels paramètres), et les
déclencheurs (quel événement ou quelle heure lance quelle invocation). Les
tables doivent rester simples à lire : une table par sorte de chose, pas
de texte JSON fourre-tout. La liste actuelle des liens entre étapes
(`etape_liens`), qui ne sert qu'à afficher un compteur, sera remplacée par
ces liens entre invocations.

**Les tâches pointent vers une invocation.** Aujourd'hui, chaque tâche de
la file est typée par un « kind » (colonne `work_items.kind`), qui lance
parfois plusieurs invocations d'un coup, et chaque kind a son propre
interrupteur. Le kind disparaît : une tâche désigne directement
l'invocation à lancer, et l'interrupteur se trouve sur l'invocation.

**Les capsules disparaissent.** Les quatre tables des capsules
(`db_readers`, `llm_point_readers`, `db_reader_fixed_params`,
`db_reader_fixed_joins`) sont supprimées. Leur réglage va sur le lien entre
une invocation et un tool (`llm_point_tools`) : ce lien dit si le tool est
lu avant l'appel et mis dans le prompt, ou si le modèle peut l'appeler
lui-même, et avec quels paramètres figés.

**Ce qui est retiré du code n'est plus effacé de la base.** Aujourd'hui,
une invocation qui n'est plus dans le code est supprimée au démarrage. Avec
la nouvelle règle, une invocation ou un lien créé ou modifié dans Mission
Control n'est jamais effacé au démarrage, et une invocation supprimée dans
Mission Control ne revient pas. Seule une brique de base retirée du code
(un tool, un traitement sans LLM) disparaît.

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
