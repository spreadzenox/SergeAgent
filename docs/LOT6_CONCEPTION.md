# Lot 6 — Les tables du pipeline en base (proposition)

Ce document est un brouillon de travail. Il propose les tables qui
décrivent tout le pipeline dans la base, pour qu'on les discute et qu'on
les corrige ensemble avant d'écrire le code. Quand elles seront validées et
construites, leur description rejoindra [`DB.md`](DB.md) et ce fichier sera
supprimé.

La règle de départ, décidée par Clem et Julien : **le code n'est qu'un
interpréteur de la base.** L'ordre des invocations et tous leurs paramètres
sont en base. Le code ne fournit que des briques de base (les tools, les
traitements sans LLM, les écritures avec leurs protections), et un seul
programme qui sait exécuter n'importe quelle invocation décrite en base.

Les noms des tables et des colonnes sont en anglais, comme le reste du
code ; les textes qu'elles contiennent sont en français.

---

## Vue d'ensemble

On peut ranger les tables en six familles, qui répondent chacune à une
question simple.

1. **Qu'est-ce que le code sait faire ?** Ce sont les briques de base,
   déclarées par le code au démarrage : `bricks` et `brick_params`.
2. **Quelles invocations existent, et comment chacune est-elle réglée ?**
   C'est la table `invocations`, une ligne par invocation, avec LLM ou sans.
3. **Qu'est-ce qu'une invocation reçoit, et qu'est-ce qu'elle peut
   appeler ?** C'est le lien entre une invocation et une brique :
   `invocation_tools` et `invocation_tool_params`.
4. **Que rend une invocation, et où est-ce écrit ?** C'est le format de sa
   réponse : `invocation_output_fields`.
5. **Qu'est-ce qui lance une invocation ?** Soit l'invocation d'avant, par
   un lien (`links`, `link_params`, `link_passages`), soit un événement ou
   une heure, par un déclencheur (`triggers`, `trigger_params`).
6. **Qu'est-ce qui tourne en ce moment ?** Ce sont les files et les tâches :
   `queues`, `tasks`, `task_params`, et le compte des lignes reçues,
   `task_inputs`.

Deux petites tables complètent le tout : `llm_models`, qui dit quel modèle
se cache derrière chaque niveau (rapide, moyen, intelligent), et
`serge_texts`, qui garde le texte de présentation de Serge.

---

## 1. Les briques du code

### `bricks` — ce que le code sait faire

Une ligne par brique fournie par le code. C'est la seule table que le code
remplit et vide lui-même au démarrage : si un développeur retire une brique
du code, sa ligne reste, mais elle est marquée absente, et Mission Control
signale les invocations qui s'en servaient.

Il y a trois sortes de briques. Un **tool** se lit ou s'appelle pendant une
invocation LLM : chercher sur le web, lire une table, chercher dans la
mémoire. Un **traitement** fait un travail sans LLM : figer les pages d'un
cycle, écarter les doublons, envoyer un e-mail. Une **écriture** range la
réponse d'une invocation dans la base, avec ses protections : par exemple,
« passer des business en POC_SELECTED » refuse tout business qui n'est plus
candidat.

Colonnes :

- `id` : le nom de la brique, par exemple `web_search` ou `select_poc`.
- `kind` : `tool`, `treatment` ou `writer`.
- `title` : son nom en français, par exemple « Chercher sur le web ».
- `doc_md` : ce qu'elle fait, en quelques phrases, pour Mission Control et
  pour le modèle.
- `acts_outside` : 1 si elle agit hors de Serge (envoyer un e-mail, passer
  un appel, rembourser). Le runner enregistre alors « en cours » avant de
  la lancer et « fait » après, pour ne jamais agir deux fois.
- `available` : 1 si le code la fournit encore, 0 sinon.
- `code_path`, `code_sha`, `files_sha`, `updated_at` : calculés au
  démarrage, comme aujourd'hui.

Cette table remplace `tools` et la colonne `kind` de `tech_invocations`.
Les tables qui décrivent ce qu'un tool de lecture a le droit de lire
(`tool_db_tables`, `tool_db_columns`, `tool_db_filters`, etc.) restent
telles quelles : elles décrivent déjà une brique en base.

### `brick_params` — ce qu'une brique accepte

Une ligne par paramètre d'une brique. Exemple : la brique « Lire les
business connus » accepte un paramètre `lifecycle` ; la brique « Envoyer un
e-mail » accepte `contact_id` et `text`.

Colonnes : `brick_id`, `name`, `type` (texte, nombre, liste, oui/non),
`required`, `description`, `position`.

---

## 2. Les invocations

### `invocations` — une ligne par invocation

C'est le cœur du lot. Une invocation LLM et une invocation sans LLM vivent
dans la même table, pour que les liens, les déclencheurs et les tâches
pointent tous vers la même chose. Cette table remplace `llm_points` et
`tech_invocations`.

Colonnes communes :

- `id` : par exemple `listen_discover_needs_a`.
- `title` : « Explorer les besoins A ».
- `role` : une phrase qui dit ce qu'elle fait, lisible par un humain.
  Exemple : « Chercher sur le web des besoins réels, différents de ceux
  déjà connus. »
- `step_id` : l'étape de la chaîne à laquelle elle appartient.
- `type` : `llm` ou `code`.
- `enabled` : allumée ou éteinte ; c'est l'interrupteur de l'invocation.
- `queue_id` : sa file, `conversations` ou `works`.
- `priority` : de 0 à 100. Copiée sur chaque tâche au moment où elle entre
  dans la file.
- `single_pending_param` : facultatif. Si on y écrit `contact_id`, une seule
  tâche de cette invocation peut attendre pour un même prospect. Exemple :
  si un prospect envoie deux messages coup sur coup, une seule tâche
  « Traiter une réponse » existe pour lui.
- `origin` : `code` (remplie au départ par le code) ou `mc` (créée dans
  Mission Control).
- `deleted_at` : rempli quand Julien supprime l'invocation dans Mission
  Control. La ligne reste, pour que le démarrage suivant ne la recrée pas.
- `updated_at`, `updated_by` : qui a changé quoi en dernier.

Colonnes pour une invocation LLM :

- `model_tier` : `fast`, `mid` ou `smart`. Le modèle réel est lu dans
  `llm_models`.
- `prompt` : les consignes.
- `gets_serge_intro` : 1 pour recevoir en tête le texte « Qui est Serge et
  quelle est ta place ».
- `default_max_rows` : le nombre maximum de lignes par information donnée
  d'office, 50 par défaut.
- `max_tool_turns` : le nombre maximum d'allers-retours avec les tools, 12
  par défaut.
- `writer_brick_id` : la brique d'écriture qui range la réponse dans la
  base (voir la partie 4).
- `writer_each_field` : facultatif. Si la réponse contient une liste, par
  exemple une liste de fiches de business, le nom de cette liste :
  l'écriture est alors appelée une fois par élément.

Colonne pour une invocation sans LLM :

- `brick_id` : le traitement à lancer, par exemple `open_listen_cycle`.
  Ses paramètres sont donnés par `invocation_tool_params` (partie 3), comme
  pour un tool.

---

## 3. Ce qu'une invocation reçoit et ce qu'elle peut appeler

### `invocation_tools` — le lien entre une invocation et une brique

Une ligne par brique qu'une invocation utilise. C'est ici que se règlent
les trois cercles de [`MEMOIRE.md`](MEMOIRE.md). Cette table remplace
`llm_point_tools` et les quatre tables des capsules (`db_readers`,
`llm_point_readers`, `db_reader_fixed_params`, `db_reader_fixed_joins`).

Colonnes :

- `id` : un numéro, parce qu'une même brique peut servir deux fois à la
  même invocation avec des réglages différents. Exemple : lire la fiche
  complète du business traité, et lire la liste courte des autres
  business.
- `invocation_id`, `brick_id`.
- `mode` : `given` ou `callable`. **Donné d'office** : Serge lance la
  brique avant l'appel au modèle et met le résultat dans le prompt.
  **Appelable** : le modèle décide s'il l'appelle pendant qu'il travaille.
- `label` : le titre de ce bloc dans le prompt, par exemple « Les business
  déjà connus ».
- `max_rows` : facultatif ; sinon, le maximum par défaut de l'invocation.
- `position` : l'ordre des blocs dans le prompt.

### `invocation_tool_params` — les paramètres figés

Une ligne par paramètre qu'on fixe pour ce lien. Le modèle ne peut pas les
changer. Exemple : « Choisir les business à tester » lit les business avec
`lifecycle` figé à `CANDIDATE` : elle ne verra jamais un business déjà en
test.

Colonnes :

- `invocation_tool_id`, `param_name`.
- `source` : `fixed` (une valeur écrite ici) ou `task` (la valeur d'un
  paramètre de la tâche en cours).
- `value` : la valeur, ou le nom du paramètre de la tâche. Exemple : pour
  lire les pages du cycle en cours, `cycle_id` vient de la tâche.

Les trois tools que toute invocation reçoit automatiquement (historique de
l'objet traité, leçons, demander une nouvelle capacité) ne sont pas
recopiés ici pour chaque invocation : ce sont des briques marquées
« partout », comme `montre_partout` aujourd'hui.

---

## 4. Ce que rend une invocation, et où c'est écrit

### `invocation_output_fields` — le format de la réponse

Une ligne par champ attendu dans la réponse du modèle. Serge s'en sert pour
dire au modèle quoi rendre, puis pour vérifier la réponse avant de
l'écrire. Une réponse mal formée est redemandée un nombre limité de fois,
avec l'erreur.

Colonnes :

- `invocation_id`, `name`, `position`.
- `parent_name` : facultatif, pour un champ à l'intérieur d'une liste.
  Exemple : `title` à l'intérieur de `fiches`.
- `type` : texte, nombre, oui/non, liste, ou choix dans une liste fermée.
- `choices` : pour un choix, les valeurs permises séparées par des
  virgules. Exemple : `intéressé, question, objection, refus,
  désinscription, hors sujet`.
- `required`, `description`.
- `writer_param` : le paramètre de la brique d'écriture qui reçoit ce
  champ. Exemple : le champ `title` d'une fiche va dans le paramètre
  `name` de l'écriture « Enregistrer des business candidats ».

Une invocation qui rend seulement un texte (par exemple une relance à
envoyer) a un seul champ, de type texte.

### Pourquoi une brique d'écriture, et pas « n'importe quelle table »

On aurait pu laisser la base dire « écris ce champ dans telle colonne de
telle table ». C'est dangereux : les protections qui ne doivent pas
dépendre d'un prompt disparaîtraient. Je propose donc que chaque écriture
passe par une brique du code, qui porte ses protections et écrit au
journal. Exemple : l'écriture « Enregistrer des business candidats » écarte
les doublons et note chaque fiche écartée ; l'écriture « Passer des
business en POC_SELECTED » refuse ceux qui ne sont plus candidats. Pour
l'éditeur sans code (lot 13), on pourra ajouter une brique d'écriture
générique, limitée à une liste de tables et de colonnes autorisées, sur le
modèle de ce qui existe déjà pour la lecture.

---

## 5. Ce qui lance une invocation

### `links` — l'invocation d'avant passe la main

Une ligne par lien entre deux invocations. Elle remplace `etape_liens`, qui
reliait des étapes et ne servait qu'à afficher un compteur.

Colonnes :

- `id`, `title` (par exemple « Chaque business choisi part en
  conception »).
- `from_invocation_id`, `to_invocation_id`.
- `when` : `on_finish` (une seule fois, quand l'invocation d'avant a fini)
  ou `per_row` (une fois pour chaque ligne qu'elle a écrite).
- `row_table`, `row_filter_column`, `row_filter_value` : pour `per_row`,
  quelles lignes comptent. Exemple : les lignes de `ventures` passées à
  `POC_SELECTED`.
- `auto` : 1 pour que le passage se fasse tout seul ; 0 pour attendre
  qu'on clique « passer à la suite » dans Mission Control.
- `delay` : `none` ou `channel`. Avec `channel`, la tâche suivante porte une
  date « pas avant », tirée entre le délai minimum et le délai maximum du
  canal. C'est ce qui fait attendre 5 à 20 minutes avant de répondre à un
  e-mail.
- `enabled`, `origin`, `deleted_at`, `updated_at`, `updated_by`.

### `link_params` — ce que le lien transmet

Une ligne par paramètre donné à la tâche suivante. Colonnes : `link_id`,
`param_name`, `source` (`row` pour une colonne de la ligne écrite, `task`
pour un paramètre de la tâche d'avant, `fixed` pour une valeur écrite ici),
`value`. Exemple : le lien « chaque business choisi part en conception »
donne `venture_id` = la colonne `id` de la ligne écrite.

### `link_passages` — ce qui est passé et ce qui attend

Une ligne par passage fait, ou en attente d'un clic. Colonnes : `link_id`,
`source_ref` (la tâche d'avant, ou la ligne écrite), `task_id` (la tâche
créée ; vide tant que le passage attend), `created_at`, `passed_at`. La clé
(`link_id`, `source_ref`) est unique : un même résultat n'est jamais
transmis deux fois. Mission Control lit cette table pour afficher, sur
chaque lien, ce qui est passé et ce qui attend.

### `triggers` — un événement ou une heure lance une invocation

Une ligne par déclencheur. Colonnes :

- `id`, `title`, `invocation_id`.
- `event` : `message_received` (un message d'un prospect arrive), `every`
  (à intervalle régulier), `at` (à une heure fixe, certains jours) ou
  `button` (un bouton de Mission Control).
- `channel_id` : pour `message_received`, le canal concerné, ou vide pour
  tous les canaux.
- `every_minutes` : pour `every`, par exemple 5.
- `at_time`, `at_days` : pour `at`, par exemple `08:30` et `lun`.
- `enabled`, `origin`, `deleted_at`, `updated_at`, `updated_by`.

### `trigger_params` — ce que le déclencheur transmet

Comme `link_params`. Colonnes : `trigger_id`, `param_name`, `source`
(`event` pour une donnée de l'événement, comme le `contact_id` de celui
qui a écrit ; `fixed` pour une valeur écrite ici ; `form` pour un champ
rempli dans Mission Control, comme le texte de guidage de l'écoute),
`value`.

---

## 6. Ce qui tourne

### `queues` — les deux files

Deux lignes : `conversations` et `works`. Colonnes : `id`, `title`,
`enabled` (pour couper une file entière). Un programme tourne en continu
pour chaque file.

### `tasks` — la file des tâches

Elle remplace `work_items`. Une tâche, c'est « lancer telle invocation,
avec tels paramètres ». Colonnes :

- `id`, `invocation_id`, `queue_id`, `priority`.
- `status` : `ready`, `running`, `done`, `failed`, `cancelled`, ou
  `to_check` (une tâche qui agissait hors de Serge s'est arrêtée au
  milieu : il faut vérifier avant de la relancer).
- `outside_state` : vide, `started` ou `done`, pour les briques qui
  agissent hors de Serge.
- `not_before` : la date avant laquelle la tâche ne part pas.
- `attempts`, `last_error`.
- `origin` : `link`, `trigger` ou `button`, et `origin_ref` (lequel).
- `idempotency_key` : unique ; calculée de façon stable, et pas avec la
  fonction de Python qui change à chaque redémarrage.
- `created_at`, `started_at`, `finished_at`.

### `task_params` — les paramètres d'une tâche

Une ligne par paramètre : `task_id`, `name`, `value`. Exemple : `cycle_id`
= `lc_12`, `venture_id` = `v_3`. Elle remplace la colonne `payload_json`,
pour qu'on puisse lire et chercher les paramètres sans ouvrir un texte
JSON.

### `task_inputs` — ce qu'une invocation a vraiment reçu

Une ligne par bloc donné d'office à chaque passage : `task_id`,
`invocation_tool_id`, `rows_given`, `rows_left_out`. Mission Control s'en
sert pour afficher « 50 business donnés, 90 laissés de côté ».

---

## 7. Les deux petites tables

### `llm_models` — quel modèle derrière chaque niveau

Trois lignes : `fast`, `mid`, `smart`. Colonnes : `tier`, `provider`,
`model`. Aujourd'hui, ce choix est fait dans le fichier d'instance ; le
mettre en base permet de le changer depuis Mission Control.

### `serge_texts` — les textes de Serge

Une ligne par texte : `id`, `body`, `updated_at`. Pour commencer, un seul
texte : `presentation`, le paragraphe « Qui est Serge », donné aux
invocations qui ont `gets_serge_intro` = 1.

---

## 8. Ce qui disparaît

- `llm_points` et `tech_invocations`, remplacées par `invocations`.
- `llm_point_tools`, remplacée par `invocation_tools`.
- Les quatre tables des capsules : `db_readers`, `llm_point_readers`,
  `db_reader_fixed_params`, `db_reader_fixed_joins`.
- `tools`, remplacée par `bricks`.
- `etape_liens`, remplacée par `links`.
- `work_items`, remplacée par `tasks` et `task_params`.
- La colonne `kinds_json` de `pipeline_steps`, et les interrupteurs
  `kind.*` de `runtime_flags`.

Une migration recopie tout ce qui existe : les réglages modifiés dans
Mission Control sont gardés.

---

## 9. Exemple complet : le cycle d'écoute d'aujourd'hui

Voici le cycle actuel de l'étape 1, décrit uniquement avec ces tables.
Aujourd'hui, il est écrit en dur dans une fonction du code.

**Le déclencheur.** Une ligne dans `triggers` : `event` = `button`, titre
« Lancer un cycle d'écoute », invocation `open_listen_cycle`. Une ligne
dans `trigger_params` : `guide` vient du formulaire (`source` = `form`).

**Les quatre invocations.**

1. `open_listen_cycle`, sans LLM, brique `open_listen_cycle` : crée le
   cycle avec le texte de guidage et fige les pages jamais utilisées.
2. `listen_discover_needs_a`, LLM, niveau moyen : « Explorer les besoins
   A ». Dans `invocation_tools` : le cycle en cours et les pages du cycle
   donnés d'office (avec `cycle_id` venu de la tâche), les business déjà
   connus donnés d'office en version courte, la recherche web et la
   recherche dans la mémoire appelables. Réponse : une liste `fiches`
   (titre, description, observations, offre vendable, pages de preuve),
   écrite par la brique `save_candidates`, une fois par fiche.
3. `listen_discover_needs_b`, réglée comme A. Elle ne reçoit pas la
   sortie de A : rien dans ses réglages ne la lui donne.
4. `listen_choose_poc`, LLM : « Choisir les business à tester ». Reçoit
   les business `CANDIDATE` (paramètre figé). Réponse : une liste de
   numéros de business, écrite par la brique `select_poc`, qui refuse tout
   business qui n'est plus candidat.

**Les liens.**

- `open_listen_cycle` → `listen_discover_needs_a`, `on_finish`, auto,
  transmet `cycle_id` depuis la tâche.
- `listen_discover_needs_a` → `listen_discover_needs_b`, `on_finish`,
  auto, transmet `cycle_id`.
- `listen_discover_needs_b` → `listen_choose_poc`, `on_finish`, auto,
  transmet `cycle_id`.
- Plus tard, au lot 10 : `listen_choose_poc` → « Concevoir le POC »,
  `per_row` sur les `ventures` passées à `POC_SELECTED`, transmet
  `venture_id`.

Si Julien veut ajouter une invocation « Trier les pages » avant
l'exploration, il ajoute une ligne dans `invocations`, ses lignes dans
`invocation_tools`, et il change deux liens. Aucune ligne de code.

## 10. Exemple : un prospect répond à un e-mail

1. Le déclencheur « Relever la boîte mail » (`every`, 5 minutes) lance
   l'invocation sans LLM `email_poll`, dans la file des conversations.
2. `email_poll` range chaque message reçu dans le fil du prospect. Pour
   chacun, le déclencheur `message_received` lance « Traiter une
   réponse », avec `contact_id` venu de l'événement. Comme
   `single_pending_param` = `contact_id`, un deuxième message du même
   prospect ne crée pas de deuxième tâche.
3. « Traiter une réponse » reçoit d'office le fil, la fiche du prospect, la
   fiche du business et la fiche produit. Sa réponse (réaction, texte à
   envoyer, besoin de Julien) est écrite par une brique qui range la
   réaction et, si besoin, ouvre un ticket complet.
4. Le lien vers « Envoyer la réponse » a `delay` = `channel` : la tâche
   d'envoi porte « pas avant 14 h 17 ». La brique d'envoi agit hors de
   Serge : le runner note « en cours », envoie, note « fait ». Juste avant,
   elle vérifie que le prospect n'a rien écrit de nouveau.

---

## 11. Questions ouvertes

1. **Une seule table pour les invocations avec et sans LLM**, comme
   proposé, ou deux tables ? Une seule rend les liens et les tâches plus
   simples ; deux évitent des colonnes vides.
2. **Les écritures passent toujours par une brique du code**, avec ses
   protections. D'accord pour garder cette limite jusqu'à l'éditeur sans
   code ?
3. **Le choix du modèle** : par niveau seulement (rapide, moyen,
   intelligent), ou aussi un modèle précis par invocation ?
4. **Où ranger le pipeline de départ dans le code** : un seul fichier
   YAML lisible (`config/pipeline.yaml`), qui décrit toutes les
   invocations, liens et déclencheurs d'une nouvelle instance ?
5. **L'historique des réglages** : faut-il garder chaque ancienne version
   d'un prompt ou d'un lien (pour revenir en arrière), ou le journal
   suffit-il pour commencer ?
