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
   **34**.
   - Une base neuve saute directement à la version 7 (le socle,
     `serge/db/schema.py`), puis applique 8, 9, … 34.
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

Trois exceptions, toutes décrites dans `config/pipeline.yaml` :
- ce qui est **nouveau dans un objet existant** s'ajoute : un réglage
  nouveau d'une invocation, un droit d'écriture ou une colonne nouvelle
  d'une vue de table ; rien de ce qui existe n'est modifié ;
- une **valeur d'un objet existant** ne change que par la section
  `changes` : une seule fois par instance, et seulement si la valeur en
  base est encore celle d'origine (une valeur changée dans Mission Control
  est gardée). Le résultat est noté dans `pipeline_changes`. Détail :
  [`LOT7_CONCEPTION.md`](LOT7_CONCEPTION.md), partie 5 ;
- ce qui est **retiré** du fichier est listé dans la section `deleted` et
  marqué supprimé en base.

Rien d'autre n'est effacé au démarrage : une invocation supprimée dans
Mission Control (`deleted_at` rempli) ne revient pas. Seule une capacité retirée du
code est marquée absente (`capabilities.available` = 0), et la fiche des
outils qui s'en servaient le signale.

---

## Les tables

Rangées selon les trois familles de [`MEMOIRE.md`](MEMOIRE.md), plus le
catalogue et la mécanique.

### L'état (ce qui est vrai maintenant)

| Table | Contenu |
|---|---|
| `ventures` | Les business, de leur découverte à leur fermeture. Colonne `lifecycle` : le statut. Fiche : `name`, `description`, `observations`, `sellable_offer`, `family` (sa famille de business), `choice_reason` (pourquoi il a été choisi pour un test). `dedup_key` sert à écarter les doublons. |
| `venture_sources` | Les pages qui prouvent le besoin derrière un business. |
| `campaigns` | Les campagnes de test : business, canal, taille, fenêtre, seuils. |
| `contacts` | Les prospects et clients : une fiche par personne dans un business. Colonne `funnel_state` : où la personne en est. Les contacts des anciens essais ont été effacés une fois, avec leurs adresses, au branchement de l'e-mail (version 36, décision Q81). |
| `contact_addresses` | Les adresses d'une personne : une ligne par adresse (`channel` = `email`, `phone` ou un réseau, `value`, `active`). Une adresse n'est jamais écrasée : une nouvelle s'ajoute à côté. |
| `touches` | Ce que Serge envoie à un contact, une ligne par message, écrite avant l'envoi : à qui, pour quel business, par quel canal et vers quelle adresse ; la sorte (`first` premier message, `reply` réponse, `followup` relance) ; l'objet et le texte ; le statut (`to_write` relance à rédiger, `pending` à envoyer, `sending` en cours d'envoi, `sent`, `failed`, `cancelled` avec la raison dans `last_error`) ; le message reçu auquel il répond (`reply_to`) ou l'envoi qu'il relance (`followup_of`) ; la référence rendue par le canal (`external_ref`, pour l'e-mail son Message-ID) et l'heure de départ (`sent_at`). La moitié « Serge » du fil d'un contact (version 35, décision Q79). |
| `inbound_events` | Ce que Serge reçoit d'un contact, une ligne par message : canal, expéditeur, objet, texte, sa référence pour lui répondre dans le même fil (`message_ref`), sa référence chez le canal (`external_ref` : un message n'est jamais écrit deux fois), le contact et le business auxquels il est rattaché, son statut (`attached` ; `unattached` : d'un inconnu, pas traité, montré dans Mission Control ; `ignored` : une réponse automatique d'absence, qui n'arrête pas les relances) et sa réaction (`question`, `refus`…). La moitié « contact » du fil (version 35). |
| `product_sheets`, `product_faq` | La fiche produit d'un business (ce que fait le produit et pour qui, ce qu'il ne fait pas, son prix, ses délais habituels, comment on l'utilise) et ses questions fréquentes. « Traiter une réponse » les lit pour répondre (version 35). |
| `customer_requests` | Les demandes des contacts sur le produit : `bug`, `insatisfaction` ou `idée`, avec le contact et le message d'où elles viennent (version 35). |
| `accounts_standing` | Les comptes web que Serge a créés : lieu, identifiant, mot de passe en clair, dossier de session, santé du compte. |
| `consents`, `blocklist` | Consentements et personnes à ne plus contacter. |
| `transactions` | Les paiements. |
| `subscriptions` | Les abonnements Stripe, chacun rattaché à son business (lu dans le champ `metadata.venture_id` du prix ou de l'abonnement Stripe). `venture_id` vide : business inconnu, signalé au journal. |
| `artifacts` | Les livrables (pas encore utilisée). |
| `listen_docs` | Les pages gardées par l'étape 1 : adresse, titre, aperçu (jamais le texte entier), source (`web` ou `rss`), flux (`feed_id`), cycle où elle a été triée (`cycle_id`), étiquette de tri (`label` : vide, `besoin_nouveau`, `bruit`, `enrichit`, `preuve`). |
| `listen_feeds` | Les flux RSS que Serge a choisis : adresse, titre, invocation qui l'a ajouté, actif ou coupé, dernière lecture. |
| `listen_cycles` | Les cycles de l'étape 1 : texte de guidage, état (`OPEN`, `CLOSED`, `ABANDONED`), dates, et ce que « Choisir » a dit du cycle (`choice_note`). |
| `tickets`, `ticket_items` | Les décisions à prendre par Julien. |
| `policy_sections`, `policy_settings`, `policy_relations` | Les réglages généraux (la « policy », page Policy de MC), une ligne par réglage : sa valeur (en JSON), son titre, son aide, sa sorte (`eur`, `curseur`, `liste`…), ses bornes et ses choix, et sa **valeur précédente** (qui l'a remplacée, quand) pour « Remettre la valeur précédente ». Les familles de réglages, avec leur page (`page` : `policy`, ou `pipeline` pour ce qui touche au modèle, version 34) et un verrou éventuel (la taille des essais ne change pas pendant qu'un essai tourne), et les relations entre réglages (le plancher du capital ≤ son plafond). Remplis par `config/policy.yaml`, sans jamais écraser une valeur ; un réglage renommé (section `renamed`) garde sa valeur (version 33, décision Q68 ; avant, la policy était une copie complète en JSON à chaque modification). |
| `runtime_flags` | Les interrupteurs à chaud. Aujourd'hui : Serge démarré (`scheduler.heartbeat` à `on`). Sans cette ligne, Serge est arrêté. |

### Le journal (ce qui s'est passé, jamais modifié)

| Table | Contenu |
|---|---|
| `events` | Le journal général : qui, quoi, quand, avec un contenu JSON. |
| `event_rows` | Quel événement concerne quelle ligne (une table et un numéro). C'est l'historique d'une ligne, que lit l'outil « Lire l'historique ». Rempli par chaque écriture d'invocation et par chaque événement d'un business. |
| `ticket_events` | L'historique de chaque ticket. |
| `llm_usage` | Chaque appel au modèle, noté aussitôt : invocation, modèle, jetons, durée, résultat (`ok`, `format_invalide`, `outil` pour un tour d'outils, `erreur` pour un appel raté) et coût réel facturé par OpenRouter (`cost_usd`, en dollars, vide s'il n'est pas donné). Les plafonds du jour et du mois comptent ce coût réel. |
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
| `capabilities`, `capability_params` | Ce que le code sait faire, déclaré par le code au démarrage. `acts_outside` = 1 : la capacité agit hors de Serge (envoyer un message) et enregistre son état pendant la tâche, pour ne jamais agir deux fois (version 35). |
| `tools` | Les outils : une capacité réglée pour un usage précis (`capability_id`). `montre_partout = 1` : appelable par toutes les invocations LLM. |
| `tool_db_*` | Pour chaque outil de lecture de la base : tables, colonnes, filtres, jointures (toujours faites) et paramètres autorisés. Le modèle n'écrit jamais de SQL. |
| `invocations` | Chaque invocation, avec ou sans LLM, et tous ses réglages : rôle, étape, niveau de modèle, prompt, file, priorité, interrupteur. `single_pending_param` : une seule tâche en attente par valeur de ce paramètre (`contact_id` : deux messages coup sur coup ne créent qu'une réponse, version 35). |
| `invocation_tools`, `invocation_tool_params` | Les outils de chaque invocation (lus d'office ou appelables) et leurs paramètres figés ; une lecture d'office peut être donnée par paquets (`batch_size`) et un outil limité à N appels (`max_calls`). |
| `table_views`, `table_view_columns` | Ce qu'une invocation peut voir de chaque table, réglé une fois par table : son titre, la colonne des lignes les plus récentes, ses colonnes lisibles et celles de sa version courte (pour un business : numéro et nom). Une colonne absente n'est jamais lue. |
| `invocation_compare_tables` | Les tables à comparer ajoutées ou retirées pour une invocation. Par défaut, elle voit la version courte des tables où elle écrit. |
| `invocation_settings` | Les réglages d'une invocation, une ligne par réglage (exemple : « nombre d'idées = 2 », entre 1 et 5). Ils servent dans le prompt (`{nombre_idees}`), le format de la réponse, l'écriture et les paramètres. `policy` = 1 : modifiable sur la page Policy de MC, qui garde la valeur précédente (`previous_value`, `previous_at`, `previous_by`). |
| `invocation_output_fields` | Le format de la réponse de chaque invocation. Une liste peut avoir un nombre d'éléments minimum et maximum (un nombre ou le nom d'un réglage). |
| `writable_tables`, `writable_columns` | Ce qu'une invocation a le droit d'écrire : ajouter, modifier, supprimer, table par table, et les colonnes permises. |
| `invocation_writes`, `invocation_write_values` | Où chaque invocation écrit sa réponse, avec au besoin « au plus N lignes par passage » et une condition (`condition_field`, `condition_op` parmi `=`, `!=`, `non_vide`, `condition_value`). Exemple : la réponse n'est écrite que si `reply` est non vide (version 35). |
| `status_transitions`, `dedup_rules`, `dedup_rule_columns` | Les protections : changements de statut permis, doublons. |
| `task_cancel_rules` | Les tâches à annuler quand une ligne change d'état : « quand un cycle passe à `ABANDONED`, ses tâches en attente (paramètre `cycle_id`) sont annulées ». |
| `table_quotas` | Une protection de plus : « au plus N lignes dont telle colonne vaut l'une de ces valeurs » (exemple : au plus 3 business choisis pour un POC). Modifiable sur la page Policy, qui garde la valeur précédente. |
| `links`, `link_params`, `link_passages`, `link_passage_params` | Les liens entre invocations, ce qui est déjà passé, et ce qui attend un clic « Passer à la suite » avec ses paramètres (lien réglé à la main). Un lien peut avoir une condition (comme une écriture : lue dans la réponse, ou dans la ligne écrite pour un lien `per_row`) et un délai tiré entre deux réglages de la policy (`delay_min_setting`, `delay_max_setting` ; `{channel}` y est remplacé par le canal de la ligne, version 35). |
| `triggers`, `trigger_params`, `trigger_conditions` | Ce qui lance une invocation : une ligne écrite, une heure (une tâche par ligne d'une table, si le déclencheur en vise une), un bouton (avec sa question de confirmation). `trigger_conditions` : les quotas qui doivent avoir de la place. |
| `pipeline_changes` | Les modifications d'objets déjà en base passées par la section `changes` de `pipeline.yaml`, une ligne par modification, avec son résultat. |
| `queues`, `tasks`, `task_params`, `task_inputs`, `task_seen_tables` | Les files (conversations, travaux, et « Appels » : chaque appel téléphonique est une tâche de l'agent vocal, menée en direct par le pont téléphonique, lot 8), leurs tâches, et ce que chaque tâche a reçu : ses lectures d'office, les tables à comparer et ses leçons (lignes données, lignes laissées de côté). |
| `llm_models` | Chaque niveau (rapide, moyen, intelligent) : le modèle derrière lui, et pour la recommandation de la page Pipeline son prix maximum (`max_price_usd`, $ par million de jetons) et sa tolérance (`tolerance_pct`, % de la meilleure note sous ce prix). |
| `serge_texts` | Les textes de Serge, modifiables sur la page Pipeline : la présentation de Serge (« Qui est Serge »), le message quand ses outils sont épuisés, le début de la consigne de format, la redemande d'une réponse mal formée, la note d'un résultat d'outil coupé, et la phrase de fin de chaque e-mail (`footer_email` : « …répondez STOP »). Chacun a un titre, une aide, et sa valeur précédente (qui l'a remplacée, quand) pour « Remettre » (version 34). |
| `canaux` | Les canaux par lesquels Serge parle à un tiers (e-mail, voix), remplis au démarrage : `connected` = 1 si son adaptateur existe dans le code (`serge/channels/`) et que le canal est configuré sur ce serveur (l'e-mail : une boîte Gmail ou SMTP/IMAP dans le fichier d'instance ; la voix : `features.phone_voice`), la sorte d'adresse qu'il utilise (`address_channel` : `email`, `phone`), s'il se relève (`polls`) et sa dernière relève (`polled_at`, version 35). |

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
d'un lien à la main (version 28). L'étape 1 est décrite en base (lot 7,
version 29 : voir [`LOT7_CONCEPTION.md`](LOT7_CONCEPTION.md)). Les
étapes suivantes sont l'objet des lots suivants (à commencer par le
lot 8).

**Une table pour les clients.** Une table des livraisons (ce qui reste à
livrer à chaque client). Les fiches produit, les demandes clients et les
délais de réponse de chaque canal (dans la policy, à toute heure, décision
Q79) sont faits (version 35).

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
