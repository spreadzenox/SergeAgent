# Lot 6 — Le pipeline entièrement en base (proposition)

Ce document est un brouillon de travail. Il propose les tables qui
décrivent tout le pipeline dans la base, pour qu'on les discute et qu'on
les corrige ensemble avant d'écrire le code. Quand elles seront validées et
construites, leur description rejoindra [`DB.md`](DB.md) et ce fichier sera
supprimé.

Les noms des tables et des colonnes sont en anglais, comme le reste du
code ; les textes qu'elles contiennent sont en français.

---

## La règle

Julien et Clem ont fixé la règle : **tout se fait depuis la base, et le
code n'est qu'un interpréteur.** À terme, on doit pouvoir créer une
invocation de toutes pièces depuis Mission Control, sans écrire une ligne
de code : son rôle, son modèle, son prompt, ce qu'elle reçoit, ce qu'elle
peut appeler, le format de sa réponse, où cette réponse est écrite, avec
quelles protections, et ce qui la lance. **Il n'y a jamais de code propre
à une invocation**, même pour écrire en base.

Le code est rangé par **capacité**. Une capacité est un savoir-faire
général, réglé par des paramètres lus en base : lire la base, écrire dans
la base, appeler un modèle, chercher sur le web, agir dans un bac à sable,
appeler une API décrite en base, envoyer ou relever des messages sur un
canal, ouvrir un ticket. Une capacité ne connaît jamais une invocation,
une étape ou un business en particulier.

Un test automatique vérifie la règle : le nom d'une invocation ne doit
jamais apparaître dans le code, sauf dans le fichier qui remplit une
nouvelle instance.

---

## Ce que le lot 6 construit, et ce qu'il laisse aux lots suivants

Clem a fixé le périmètre. On passe directement à la version durable : tout
le code écrit en dur pour un enchaînement est retiré de la production, sans
période de transition. Il n'est pas détruit : il est rangé, avec ses tests
et ses prompts, dans le dossier `pas_encore_branche/` à la racine du dépôt,
pour que les lots suivants puissent s'en servir. Le lot construit le runner, les tables de ce
document, l'interpréteur, les premières capacités et l'affichage dans
Mission Control. À la fin du lot, Serge ne peut pas encore être allumé
pour de vrai, parce que certaines capacités manquent ; mais en modifiant la
base, on peut construire n'importe quel pipeline avec les capacités qui
existent.

**On ne crée que les colonnes dont ce lot a besoin.** Les colonnes des
fonctions futures (validation par Julien, bac à sable, délais par canal,
conditions sur les liens…) ne sont pas créées maintenant : chaque lot
ajoutera les siennes. La partie 9 de ce document les liste, pour montrer
qu'elles tiendront dans la règle, et le [`TODO.md`](../TODO.md) les note à
l'endroit où elles serviront.

**Les premières capacités** : lire la base (elle existe déjà), écrire dans
la base, appeler un modèle avec ses outils, chercher sur le web, chercher
dans la mémoire, demander une nouvelle capacité, et rendre les paramètres
de la tâche (pour une invocation sans LLM qui ne fait qu'écrire ce qu'on
lui donne).

**Mission Control** affiche tout ce qui est en base, en direct : les
invocations et leurs réglages, les capacités et les outils, les règles
d'écriture, les liens, les déclencheurs, les files et les tâches. Ce qui
existe déjà reste (modifier un prompt, allumer ou éteindre). Créer une
invocation depuis le site viendra au lot 13.

**Fusion dans `main`** après chaque étape du lot, avec des tests verts qui
portent seulement sur ce qui est construit.

---

## Comment se déroule une invocation

Toutes les invocations se déroulent de la même façon, qu'elles appellent
un LLM ou non. C'est ce qui permet d'avoir un seul programme pour toutes.
Pour chaque tâche prise dans la file, l'interpréteur fait, dans l'ordre
(un temps « demander à Julien » s'ajoutera entre la vérification et
l'écriture au lot 8) :

1. **Préparer.** Il lit les réglages de l'invocation en base, et lance les
   lectures données d'office (par exemple, les business déjà connus, en
   version courte, 50 au plus).
2. **Produire une réponse.** Pour une invocation LLM, il appelle le modèle
   indiqué avec le prompt, ce qui a été lu, et les tools appelables ; le
   modèle rend sa réponse finale au format déclaré. Pour une invocation
   sans LLM, il appelle la capacité indiquée avec ses paramètres (par
   exemple « relever la boîte mail » ou « envoyer un e-mail ») ; ce que
   rend la capacité tient lieu de réponse.
3. **Vérifier.** Il contrôle que la réponse a le format déclaré. Si ce
   n'est pas le cas, il redemande au modèle, avec l'erreur, un nombre
   limité de fois.
4. **Écrire.** Il écrit la réponse en base en suivant les règles
   d'écriture de l'invocation, et en appliquant les protections déclarées
   en base. Chaque écriture et chaque refus sont notés au journal.
5. **Passer la main.** Il marque la tâche comme finie, puis lance les
   invocations suivantes selon les liens, et les déclencheurs réagissent
   aux lignes écrites.

Le modèle n'écrit jamais lui-même en base, et ne choisit jamais où
écrire : la destination est fixée dans les réglages de l'invocation. Une
réponse ratée, ou un texte piégé lu sur le web, ne peut donc pas écrire
n'importe où.

---

## Vue d'ensemble des tables

Les tables se rangent en sept familles, qui répondent chacune à une
question.

1. **Qu'est-ce que le code sait faire, et quels outils en sont tirés ?**
   `capabilities`, `capability_params`, `tools`, et le catalogue de
   lecture qui existe déjà (`tool_db_*`).
2. **Quelles invocations existent, et comment sont-elles réglées ?**
   `invocations`.
3. **Qu'est-ce qu'une invocation reçoit, et qu'est-ce qu'elle peut
   appeler ?** `invocation_tools`, `invocation_tool_params`.
4. **Que rend-elle ?** `invocation_output_fields`.
5. **Où c'est écrit, et avec quelles protections ?** `writable_tables`,
   `writable_columns`, `invocation_writes`, `invocation_write_values`,
   `status_transitions`, `dedup_rules`, `dedup_rule_columns`.
6. **Qu'est-ce qui la lance ?** `links`, `link_params`, `link_passages`,
   `triggers`, `trigger_params`.
7. **Qu'est-ce qui tourne ?** `queues`, `tasks`, `task_params`,
   `task_inputs`.

Deux petites tables complètent le tout : `llm_models` et `serge_texts`.

---

## 1. Les capacités et les outils

### `capabilities` — ce que le code sait faire

Une ligne par capacité fournie par le code. C'est la seule table que le
code remplit lui-même au démarrage. Si un développeur retire une capacité
du code, sa ligne reste, marquée absente, et Mission Control signale tout
ce qui s'en servait.

Colonnes :

- `id` : par exemple `db_read`, `web_search`, `send_email`, `http_call`.
- `title`, `doc_md` : son nom et ce qu'elle fait, en français.
- `available` : 1 si le code la fournit encore.
- `code_path`, `code_sha`, `files_sha`, `updated_at` : calculés au
  démarrage.

### `capability_params` — ce qu'une capacité accepte

Une ligne par paramètre : `capability_id`, `name`, `type` (texte, nombre,
oui/non, liste), `required`, `description`, `position`. Exemple : `send_email`
accepte `contact_id`, `subject` et `text`.

### `tools` — une capacité avec ses réglages

Un outil, c'est une capacité réglée pour un usage précis, et c'est ce
qu'on donne à une invocation. Plusieurs outils peuvent utiliser la même
capacité. Exemple : « Lire les business connus » et « Lire les pages du
cycle » utilisent tous deux la capacité `db_read`, chacun avec son propre
catalogue de tables, de colonnes et de filtres ; « Chercher sur le web »
utilise `web_search` ; plus tard, « Stripe : créer un prix » utilisera
`http_call` avec la description de Stripe en base.

La table `tools` existe déjà. Elle garde ses colonnes (`id`, `titre`,
`doc_md`, `montre_partout` pour les outils donnés à toutes les
invocations), perd `kind` et gagne `capability_id`. Les tables du
catalogue de lecture (`tool_db_tables`, `tool_db_columns`,
`tool_db_filters`, `tool_db_joins`, `tool_db_params`…) restent telles
quelles : elles décrivent déjà, en base, ce qu'un outil de lecture a le
droit de lire. Un outil se crée dans Mission Control sans code.

---

## 2. Les invocations

### `invocations` — une ligne par invocation

Elle remplace `llm_points` et `tech_invocations`. Une invocation LLM et une
invocation sans LLM vivent dans la même table, pour que les liens, les
déclencheurs et les tâches pointent tous vers la même chose.

Colonnes communes :

- `id`, `title` (« Explorer les besoins A »), `role` (une phrase qui dit
  ce qu'elle fait, pour un humain), `step_id` (son étape).
- `type` : `llm` ou `capability`.
- `enabled` : son interrupteur.
- `queue_id` : `conversations` ou `works`.
- `priority` : de 0 à 100, copiée sur chaque tâche à sa création.
- `origin` (`code` ou `mc`), `deleted_at`, `updated_at`, `updated_by`.

Colonnes pour une invocation LLM :

- `model_tier` (`fast`, `mid`, `smart`), `prompt`. Il n'y a pas de
  colonne pour un modèle précis : le modèle se choisit seulement par
  niveau.
- `gets_serge_intro` : 1 pour recevoir en tête le texte « Qui est Serge et
  quelle est ta place ».
- `default_max_rows` (50 par défaut), `max_tool_turns` (12 par défaut).

Colonne pour une invocation sans LLM :

- `capability_id` : la capacité à appeler. Ses paramètres viennent de
  `invocation_tool_params` (partie 3), exactement comme pour un outil.

---

## 3. Ce qu'une invocation reçoit et ce qu'elle peut appeler

### `invocation_tools` — le lien entre une invocation et un outil

Elle remplace `llm_point_tools` et les quatre tables des capsules. Une
ligne par outil utilisé par une invocation.

- `id` : un numéro, parce qu'un même outil peut servir deux fois à la même
  invocation avec des réglages différents.
- `invocation_id`, `tool_id`.
- `mode` : `given` (lu avant l'appel, et mis dans le prompt) ou
  `callable` (le modèle décide de l'appeler).
- `label` : le titre du bloc dans le prompt, par exemple « Les business
  déjà connus ».
- `max_rows` : facultatif, sinon le maximum de l'invocation.
- `position` : l'ordre des blocs dans le prompt.

### `invocation_tool_params` — les paramètres figés

Une ligne par paramètre fixé. Le modèle ne peut pas le changer. Colonnes :
`invocation_tool_id`, `param_name`, `source` (`fixed` pour une valeur
écrite ici, `task` pour un paramètre de la tâche en cours), `value`.
Exemple : « Choisir les business à tester » lit les business avec
`lifecycle` figé à `CANDIDATE` ; « Explorer A » lit les pages du cycle avec
`cycle_id` venu de la tâche.

Pour une invocation sans LLM, les paramètres de sa capacité se règlent de
la même façon, avec `invocation_tool_id` vide.

---

## 4. Ce que rend une invocation

### `invocation_output_fields` — le format de la réponse

Une ligne par champ attendu. Serge s'en sert pour dire au modèle quoi
rendre, puis pour vérifier la réponse.

- `invocation_id`, `position`.
- `path` : le nom du champ, avec un point pour un champ à l'intérieur
  d'une liste. Exemple : `fiches` est une liste, `fiches.title` le titre
  de chaque fiche, `fiches.pages` la liste des pages de preuve de chaque
  fiche.
- `type` : texte, nombre, oui/non, liste, ou choix dans une liste fermée.
- `choices` : pour un choix, les valeurs permises. Exemple : `intéressé,
  question, objection, refus, désinscription, hors sujet`.
- `required`, `description`.

Une invocation sans LLM a aussi ses champs : ceux que rend sa capacité.
Exemple : « Relever la boîte mail » rend une liste `messages`, avec pour
chacun l'expéditeur, le sujet, le texte et l'identifiant du fil.

---

## 5. Où c'est écrit, et avec quelles protections

C'est la partie qui remplace tout le code d'écriture propre à chaque
invocation. Un seul code d'écriture lit ces tables et applique les règles.

### `writable_tables` et `writable_columns` — ce qu'on a le droit d'écrire

Le catalogue de ce qu'une invocation peut écrire, sur le modèle du
catalogue de lecture.

- `writable_tables` : `table_name`, `can_insert`, `can_update`,
  `description`.
- `writable_columns` : `table_name`, `column_name`, `description`.

Une table absente du catalogue ne peut jamais être écrite par une
invocation. Exemple : les paiements, les réglages de la policy, et ces
tables de règles elles-mêmes.

### `invocation_writes` — les règles d'écriture d'une invocation

Une ligne par écriture qu'une invocation fait avec sa réponse.

- `id`, `invocation_id`, `position`.
- `table_name` : la table visée, qui doit être dans le catalogue.
- `operation` : `insert` (ajouter une ligne) ou `update` (modifier une
  ligne existante).
- `for_each` : facultatif, le champ-liste qui donne une ligne par élément.
  Exemple : `fiches` pour une ligne par fiche, `fiches.pages` pour une
  ligne par page de chaque fiche.
- `parent_write_id` : pour une liste dans une liste, l'écriture dont on
  reprend la ligne. Exemple : chaque page de preuve est rattachée au
  business que l'écriture parente vient de créer.
- `key_column`, `key_source`, `key_value` : pour `update`, comment
  retrouver la ligne à modifier. Exemple : la colonne `id` des business,
  égale au champ `choix.venture_id` de la réponse.

### `invocation_write_values` — quelle colonne reçoit quoi

Une ligne par colonne écrite : `write_id`, `column_name`, `source`,
`value`. La source peut être :

- `field` : un champ de la réponse, par exemple `fiches.title` ;
- `fixed` : une valeur écrite ici, par exemple `CANDIDATE` ;
- `task` : un paramètre de la tâche, par exemple `cycle_id` ;
- `parent_row` : une colonne de la ligne écrite par l'écriture parente,
  par exemple son `id` ;
- `now` : la date et l'heure de l'écriture.

### `status_transitions` — les changements de statut permis

Une ligne par changement permis : `table_name`, `column_name`,
`from_value`, `to_value`. Dès qu'une colonne a des lignes ici, seuls ces
changements sont acceptés ; une valeur vide dans `from_value` désigne la
valeur à la création. Exemple : pour `ventures.lifecycle`, la ligne
(`CANDIDATE` → `POC_SELECTED`) permet de choisir un candidat, et comme il
n'existe aucune ligne (`SMOKE_RUNNING` → `POC_SELECTED`), un business déjà
en test est refusé, avec une note au journal. C'est la protection d'aujourd'hui
« refuser un business déjà en test », sans code spécial.

### `dedup_rules` et `dedup_rule_columns` — repérer un doublon

- `dedup_rules` : `id`, `table_name`, `method` (`exact` ou `shared_words`),
  `threshold` (par exemple 72, en pourcentage), `on_duplicate` (`skip`
  pour écarter la ligne, `refuse` pour refuser toute la réponse).
- `dedup_rule_columns` : `rule_id`, `column_name`. Exemple : pour les
  business, le nom et la description.

Chaque ligne écartée est notée au journal avec la ligne existante qui lui
ressemble.

Cette règle est un filet de sécurité, pas le moyen principal d'éviter les
doublons. L'invocation doit d'abord éviter elle-même de proposer ce qui
existe déjà : elle reçoit d'office la liste courte de ce qui est en base
(par exemple le nom de chaque business connu), et son prompt lui demande de
ne pas reproposer ce qui y figure. Si elle le fait quand même, la règle
l'écarte, et le journal le montre : on voit ainsi quand une invocation
travaille mal.

### Ce que le code d'écriture fait tout seul

Pour chaque écriture, il vérifie le catalogue, les champs obligatoires, les
changements de statut et les doublons ; il écrit ; il note au journal
l'invocation, la tâche, la table, la ligne et ce qui a été écrit, ou la
raison du refus. Il rend la liste des lignes écrites, dont se servent les
liens et les déclencheurs.

---

## 6. Ce qui lance une invocation

### `links` — l'invocation d'avant passe la main

Elle remplace `etape_liens`. Colonnes :

- `id`, `title` (« Chaque business choisi part en conception »).
- `from_invocation_id`, `to_invocation_id`.
- `when` : `on_finish` (une fois, quand l'invocation d'avant a fini) ou
  `per_row` (une fois par ligne écrite par l'une de ses écritures).
- `write_id` : pour `per_row`, l'écriture dont les lignes comptent.
- `auto` : 1 pour passer tout seul, 0 pour attendre un clic sur « passer à
  la suite » dans Mission Control.
- `enabled`, `origin`, `deleted_at`, `updated_at`, `updated_by`.

### `link_params` — ce que le lien transmet

`link_id`, `param_name`, `source` (`row` pour une colonne de la ligne
écrite, `task` pour un paramètre de la tâche d'avant, `fixed`), `value`.

### `link_passages` — ce qui est passé et ce qui attend

`link_id`, `source_ref` (la tâche ou la ligne d'origine), `task_id` (vide
tant que le passage attend un clic), `created_at`, `passed_at`. La paire
(`link_id`, `source_ref`) est unique : un même résultat n'est jamais
transmis deux fois.

### `triggers` — un événement ou une heure lance une invocation

- `id`, `title`, `invocation_id`.
- `event` : `row_written` (une ligne est écrite dans une table), `every`
  (à intervalle régulier), `at` (à une heure fixe, certains jours) ou
  `button` (un bouton de Mission Control).
- Pour `row_written` : `table_name`, et une condition facultative
  (`filter_column`, `filter_value`). Exemple : une ligne ajoutée dans la
  table des messages reçus, avec `direction` = `entrant`. Il n'y a donc pas
  d'événement spécial « message reçu » : c'est une ligne écrite comme une
  autre.
- Pour `every` : `every_minutes`. Pour `at` : `at_time` et `at_days`.
- `enabled`, `origin`, `deleted_at`, `updated_at`, `updated_by`.

### `trigger_params` — ce que le déclencheur transmet

`trigger_id`, `param_name`, `source` (`row` pour une colonne de la ligne
écrite, `form` pour un champ rempli dans Mission Control, `fixed`),
`value`.

---

## 7. Ce qui tourne

### `queues` — les deux files

Deux lignes : `conversations` et `works`, avec `title` et `enabled`. Un
programme tourne en continu pour chaque file.

### `tasks` et `task_params` — la file des tâches

`tasks` remplace `work_items`. Colonnes : `id`, `invocation_id`,
`queue_id`, `priority`, `status` (`ready`, `running`, `done`, `failed`,
`cancelled`), `not_before`, `attempts`, `last_error`, `origin`
(`link`, `trigger`, `button`), `origin_ref`, `idempotency_key` (unique,
calculée de façon stable), `created_at`, `started_at`, `finished_at`.

`task_params` : `task_id`, `name`, `value`. Elle remplace la colonne
`payload_json`, pour qu'on lise et cherche les paramètres sans ouvrir un
texte JSON.

### `task_inputs` — ce qu'une invocation a vraiment reçu

`task_id`, `invocation_tool_id`, `rows_given`, `rows_left_out`. Mission
Control affiche ainsi « 50 business donnés, 90 laissés de côté ».

---

## 8. Les deux petites tables

- `llm_models` : `tier`, `provider`, `model`. Trois lignes (`fast`,
  `mid`, `smart`). Le choix du modèle derrière chaque niveau passe du
  fichier d'instance à la base. C'est le seul endroit où un modèle précis
  est nommé.
- `serge_texts` : `id`, `body`, `updated_at`. Pour commencer, un texte :
  `presentation`, le paragraphe « Qui est Serge ».

---

## 9. Préparer les lots futurs sans code propre

Le lot 6 ne construit pas ce qui suit, et ne crée aucune de ces colonnes.
Mais la conception doit déjà montrer que tout tiendra dans la règle, pour
qu'on ne soit pas tenté, dans quelques semaines, d'écrire du code pour un
cas précis.

**Ce que le lot 8 (conversations) ajoutera** :

- sur `capabilities`, une colonne `acts_outside` (1 si la capacité agit
  hors de Serge : envoyer un e-mail, appeler, payer), et sur `tasks` un
  état `outside_state` et un statut `to_check`. L'interpréteur enregistre
  « en cours » avant d'agir et « fait » après ; une tâche arrêtée entre les
  deux attend qu'on vérifie, pour ne jamais agir deux fois ;
- sur `invocations`, `single_pending_param` (une seule tâche en attente
  par prospect), `approval` (validation par Julien avant d'écrire ou
  d'agir, par exemple pour LinkedIn) et `ask_julien_field` (un champ
  oui/non de la réponse qui ouvre un ticket), avec un statut
  `waiting_julien` sur les tâches ;
- sur `links` et `invocation_writes`, une condition simple (« seulement si
  le champ `reaction` vaut `désinscription` »), et sur `links` un délai
  tiré entre le minimum et le maximum du canal ;
- les capacités relever une boîte mail, envoyer un e-mail, ouvrir un
  ticket complet, bloquer les adresses d'une personne qui se désinscrit.

**Ce que le lot 12 (web) ajoutera** : les profils de bac à sable, la
colonne `sandbox_profile_id` sur `invocations`, les services décrits en
base pour la capacité « appeler une API », et une colonne `needs_approval`
sur `writable_tables` pour les écritures qui demandent l'accord de Julien.

**Le bac à sable** sera une table de profils, `sandbox_profiles` : ce qui y
est installé, les sites qu'il peut joindre, le temps et la mémoire permis,
le dossier qu'il garde entre deux passages. Deux tables disent à quels
secrets et à quels comptes web un profil a accès. Une invocation choisit
son profil (`invocations.sandbox_profile_id`). Les outils du bac à sable
(ouvrir une page, cliquer, remplir un champ, lire ou écrire un fichier,
lancer une commande) sont des capacités générales, données ou non à
l'invocation comme les autres outils.

**L'agent web** n'aura pas de code propre : c'est une invocation LLM,
réglée en base, qui reçoit sa mission en paramètre de tâche (« crée un
compte sur ce forum ») et les outils du navigateur dans son bac à sable.
Créer un compte de bout en bout est un enchaînement d'invocations en base,
reliées par des liens : remplir le formulaire, lire le code de
confirmation reçu par e-mail, demander un captcha à un humain par ticket,
écrire le compte en base.

**Les connecteurs** seront des descriptions de services en base,
`api_services` et `api_endpoints` : l'adresse du service, le secret à
utiliser, chaque point d'entrée et ses paramètres. Une seule capacité,
`http_call`, sait appeler n'importe quel service ainsi décrit. L'invocation
« Construire un connecteur » écrit ces descriptions avec le code d'écriture
générique ; comme `api_services` est marquée « validation par Julien »
dans le catalogue d'écriture, rien n'est utilisable avant son accord.

**Les canaux** relient chacun leurs outils d'envoi et de relève à leur
fiche (`canaux`), avec leurs délais de réponse. Un canal passe par un
service décrit en base ou par l'agent web ; un adaptateur de code n'existe
que si c'est impossible autrement (le téléphone), et il sert alors toutes
les invocations.

**L'agent vocal** est réglé comme une invocation : son prompt, son modèle,
ce qu'il reçoit au décrochage et ses outils sont en base. Seul le
programme qui transporte la voix en direct est du code, et il ne sait rien
de ce qu'on dit.

---

## 10. Le pipeline de départ

Une nouvelle instance démarre avec un pipeline complet, décrit dans un
seul fichier lisible, `config/pipeline.yaml` : les invocations, leurs
outils, le format de leurs réponses, leurs règles d'écriture, les liens,
les déclencheurs, et les règles de protection des tables. Au démarrage,
Serge ajoute en base ce qui n'y est pas encore ; il ne modifie jamais ce
qui existe, et ne recrée jamais ce que Julien a supprimé. Après
l'initialisation, la base est la seule source de vérité : modifier le
fichier ne change rien sur une instance qui tourne, sauf pour les objets
nouveaux. C'est le seul endroit du dépôt où les noms des invocations
apparaissent.

---

## 11. Ce qui disparaît

- `llm_points` et `tech_invocations`, remplacées par `invocations`.
- `llm_point_tools`, remplacée par `invocation_tools`.
- Les quatre tables des capsules : `db_readers`, `llm_point_readers`,
  `db_reader_fixed_params`, `db_reader_fixed_joins`.
- `etape_liens`, remplacée par `links`.
- `work_items`, remplacée par `tasks` et `task_params`.
- `brique_canaux`, qui reliait un canal aux anciennes invocations. Le
  lien entre un canal et ses outils d'envoi reviendra avec le lot 8.
- La colonne `kind` de `tools`, la colonne `kinds_json` de
  `pipeline_steps`, et les interrupteurs `kind.*` et `llm.*`.
- Tout le code propre à une invocation : les fonctions des enchaînements
  (cycle d'écoute, circuit des réponses…) et leur code d'écriture. Il est
  rangé dans `pas_encore_branche/`, pas détruit.

La migration v25 supprime ces tables sans les recopier (décision Q58) : les
réglages des anciennes invocations restent lisibles dans
`pas_encore_branche/`, et le pipeline est décrit de nouveau dans
`config/pipeline.yaml`.

---

## 12. Exemple : le cycle d'écoute d'aujourd'hui

Voici le cycle actuel de l'étape 1, décrit uniquement avec ces tables.

**Le déclencheur.** `event` = `button`, « Lancer un cycle d'écoute ». Il
lance « Ouvrir un cycle », avec `guide` venu du formulaire de Mission
Control.

**« Ouvrir un cycle »** (sans LLM). Sa capacité rend simplement les
paramètres de la tâche. Une écriture : `insert` dans `listen_cycles`, avec
`guide` ← la tâche et `status` ← `OPEN`.

**Lien** `per_row` sur cette écriture, vers « Figer les pages », avec
`cycle_id` ← la colonne `id` de la ligne écrite.

**« Figer les pages »** (sans LLM). Sa capacité est `db_read`, avec l'outil
« Pages jamais utilisées par un cycle ». Une écriture : `insert` dans
`listen_cycle_docs`, `for_each` = `pages`, avec `cycle_id` ← la tâche et
`doc_id` ← `pages.id`.

**Lien** `on_finish` vers « Explorer les besoins A », avec `cycle_id`.

**« Explorer les besoins A »** (LLM, niveau moyen). Outils donnés d'office :
le cycle en cours et les pages du cycle (`cycle_id` ← la tâche), les
business déjà connus en version courte. Outils appelables : la recherche
web et la recherche dans la mémoire. Réponse : une liste `fiches` avec
`title`, `description`, `observations`, `offer` et la liste `pages`. Deux
écritures :

1. `insert` dans `ventures`, `for_each` = `fiches` : `name` ←
   `fiches.title`, `description` ← `fiches.description`, `observations` ←
   `fiches.observations`, `sellable_offer` ← `fiches.offer`, `lifecycle` ←
   `CANDIDATE`. La règle de doublons des business (nom et description, 72 %
   de mots en commun, `skip`) écarte les fiches trop proches d'un business
   existant, avec une note au journal.
2. `insert` dans `venture_sources`, `for_each` = `fiches.pages`, rattachée
   à l'écriture 1 : `venture_id` ← `parent_row.id`, `doc_id` ←
   `fiches.pages`, `cycle_id` ← la tâche.

**Lien** `on_finish` vers « Explorer les besoins B », réglée comme A. Elle
ne reçoit pas la sortie de A : rien dans ses réglages ne la lui donne.

**Lien** `on_finish` vers « Choisir les business à tester » (LLM). Outil
donné d'office : les business avec `lifecycle` figé à `CANDIDATE`.
Réponse : une liste `choix`, avec `venture_id` et `rank`. Une écriture :
`update` de `ventures`, `for_each` = `choix`, ligne retrouvée par `id` ←
`choix.venture_id`, `lifecycle` ← `POC_SELECTED`. La règle des changements
de statut refuse tout business qui n'est plus `CANDIDATE`.

**Plus tard (lot 10)**, un lien `per_row` sur cette écriture lancera
« Concevoir le POC » pour chaque business choisi, avec `venture_id`.

Aucune ligne de ce pipeline n'est du code propre à l'écoute.

## 13. Exemple : un prospect répond à un e-mail (après le lot 8)

Cet exemple utilise des capacités et des colonnes qui viendront au lot 8.
Il sert à vérifier que la conception tiendra.

1. Un déclencheur `every` (5 minutes) lance « Relever la boîte mail »
   (sans LLM, capacité de relève du canal e-mail, file des conversations).
   Sa réponse, la liste `messages`, est écrite dans la table des messages
   reçus, une ligne par message, rattachée au prospect.
2. Un déclencheur `row_written` sur cette table lance « Traiter une
   réponse », avec `contact_id` ← la ligne écrite. Comme
   `single_pending_param` = `contact_id`, deux messages coup sur coup ne
   créent qu'une tâche.
3. « Traiter une réponse » reçoit d'office le fil, la fiche du prospect,
   la fiche du business et la fiche produit. Sa réponse : `reaction`,
   `text`, `besoin_de_julien`, `raison`. Comme `ask_julien_field` =
   `besoin_de_julien`, un oui ouvre un ticket avec tout ce qu'elle a reçu
   et répondu. Sinon, ses écritures rangent la réaction et le brouillon.
4. Un lien `per_row` sur le brouillon, avec `delay` = `channel`, lance
   « Envoyer la réponse » (sans LLM, capacité `send_email`, qui agit hors
   de Serge) avec « pas avant 14 h 17 ».

## 14. Exemple : créer une invocation de toutes pièces

Julien veut une nouvelle invocation « Chercheur d'idées », qui sonde le web
pour proposer des business. Il n'écrit aucune ligne de code. Dans Mission
Control, il ajoute :

1. une ligne dans `invocations` : titre, rôle, étape 1, LLM, niveau
   moyen, son prompt, file des travaux, priorité 10 ;
2. deux lignes dans `invocation_tools` : « Lire les business connus »
   donné d'office, et « Chercher sur le web » appelable ;
3. quatre lignes dans `invocation_output_fields` : la liste `fiches`, et
   pour chaque fiche `title`, `description` et `offer` ;
4. une ligne dans `invocation_writes` (`insert` dans `ventures`, une ligne
   par fiche) et quatre lignes dans `invocation_write_values` (le titre,
   la description, l'offre, et `lifecycle` ← `CANDIDATE`) ;
5. une ligne dans `triggers` : chaque lundi à 8 h 30.

La règle de doublons des business et les changements de statut permis
s'appliquent tout seuls, puisqu'ils sont réglés sur la table, pas sur
l'invocation.

---

## 15. Réponses de Clem

1. **Une seule table pour toutes les invocations**, avec ou sans LLM. Les
   colonnes vides ne gênent pas.
2. **Le modèle se choisit seulement par niveau** : rapide, moyen ou
   intelligent. Jamais un modèle précis sur une invocation : c'est plus
   lisible. Le modèle derrière chaque niveau se règle dans `llm_models`.
3. **Le pipeline de départ est dans `config/pipeline.yaml`.** Ce fichier
   ne sert qu'à remplir la base d'une nouvelle instance, et à ajouter les
   objets nouveaux sur une instance existante. Après l'initialisation, il
   n'est plus jamais la source de vérité : c'est la base.
4. **L'historique des réglages** attendra : le journal suffit pour
   commencer. On veut d'abord une petite version qui marche. C'est noté à
   la fin du [`TODO.md`](../TODO.md).
5. **Les méthodes de doublon** : « identique » et « mots en commun »
   suffisent pour une première version. La comparaison par le sens
   (embeddings ou LLM) viendra plus tard si besoin. La règle reste un
   filet de sécurité : l'invocation reçoit la liste courte de ce qui
   existe, et son prompt lui demande de ne pas le reproposer.
6. **Le vocabulaire** « capacité » et « outil » est validé.

---

## 16. Ce que voit une invocation, et l'outil pour lire le reste (validé, Q60)

Le principe est dans [`MEMOIRE.md`](MEMOIRE.md). Voici ce qu'il demande en
base. Rien n'y est propre à une invocation : les règles sont réglées une
fois par table, et chaque invocation peut seulement ajuster sa liste de
tables à comparer.

**Pour chaque table, une fois** :

- `table_views` : une ligne par table qu'une invocation peut voir.
  Colonnes : `table_name`, `description` (ce que contient la table, en
  français), `order_column` (la colonne qui dit quelles lignes sont les
  plus récentes, par exemple `created_at`).
- `table_view_columns` : une ligne par colonne lisible. Colonnes :
  `table_name`, `column_name`, `short` (1 si la colonne fait partie de la
  version courte), `description`. Une colonne absente n'est jamais lue par
  une invocation. Exemple pour les business : numéro et nom dans la
  version courte ; description, offre, statut et dates lisibles ; rien
  d'autre.

**Pour chaque invocation** :

- `invocation_compare_tables` : les ajustements de son deuxième cercle.
  Par défaut, elle voit en version courte les tables où elle écrit. Une
  ligne `included` = 1 ajoute une table à comparer, une ligne
  `included` = 0 en retire une. Réglable dans Mission Control.

**Ce que l'interpréteur en fait, à chaque appel** :

1. Il donne d'office la version courte de chaque table du deuxième
   cercle, les lignes les plus récentes d'abord, au plus le maximum de
   l'invocation, avec le nombre exact de lignes laissées de côté.
2. Il construit l'outil **« Lire les tables que je vois »** pour cette
   invocation. Ce n'est pas un outil écrit à la main : c'est la capacité
   de lecture, réglée à chaque appel avec l'ensemble des tables du
   deuxième cercle. Le modèle choisit une de ces tables et peut demander
   une ligne par son numéro, ou toutes les lignes, avec un filtre simple
   (une colonne égale à une valeur), page par page. Il reçoit toutes les
   colonnes lisibles.
3. Il donne l'outil **« Lire l'historique »** d'une ligne qu'elle voit :
   les derniers événements du journal qui la concernent.
4. Il donne d'office ses leçons : celles rattachées à l'invocation, puis
   à son étape, puis à tout Serge, les plus fiables d'abord.
5. Il écrit le bloc **« Qui est Serge »** complet, si l'invocation le
   demande : la présentation, la chaîne des 8 étapes, sa place, et ce qui
   vient juste avant et juste après elle, lu dans les liens.

---

## 17. Les réglages d'une invocation, et les quotas des tables (validé, Q61)

Le format de la réponse et l'écriture sont déjà décrits en base (parties 4
et 5). Ce qui manquait, c'est de les relier aux chiffres réglables. Clem a
validé cette organisation pour l'instant ; elle sera sans doute retouchée
quand on créera une invocation depuis Mission Control (lot 13).

**`invocation_settings` : les réglages d'une invocation.** Une ligne par
réglage, rattachée à l'invocation (la charte interdit de ranger une liste
de valeurs dans une seule case). Colonnes : `invocation_id`, `name`,
`type` (nombre, texte ou oui/non), `value`, `min_value` et `max_value`
(les bornes, pour un nombre), `description` (à quoi il sert, en
français), `policy` (1 pour qu'il apparaisse sur la page Policy de
Mission Control, modifiable en direct, chaque changement noté au
journal). Exemple : « Formuler des idées » a le réglage « nombre
d'idées = 2 », entre 1 et 10.

**Un réglage sert partout où l'invocation a une valeur** :

- **dans le prompt** : `{nombre_idees}` est remplacé par la valeur à
  chaque appel. Exemple : « Propose {nombre_idees} idées ».
- **dans le format de la réponse** : une liste peut avoir un nombre
  d'éléments minimum et maximum (colonnes `min_items` et `max_items` de
  `invocation_output_fields`), écrits comme un nombre ou comme le nom
  d'un réglage. L'interpréteur l'annonce au modèle et le vérifie ; sinon,
  il redemande avec l'erreur.
- **dans l'écriture** : une colonne peut recevoir un réglage (une source
  `setting` de plus dans `invocation_write_values`), et une écriture peut
  être limitée à « au plus N lignes » (colonne `max_rows` de
  `invocation_writes`, un nombre ou un réglage).
- **dans les paramètres des outils, de la capacité et des liens** : la
  même source `setting`. Exemple : « lire au plus N pages ».

**`table_quotas` : les quotas d'une table.** Une protection de plus, réglée
sur la table comme les changements de statut : « au plus N lignes de
cette table dont telle colonne vaut l'une de ces valeurs ». Colonnes :
`id`, `table_name`, `column_name`, `values` (la liste des valeurs
comptées, séparées par des virgules), `max_value`, `description`,
`policy`. Exemple : au plus 3 business en test léger en même temps. Le
code d'écriture refuse une ligne de trop, quelle que soit l'invocation qui
écrit, et le note au journal.

**Les capacités restent générales.** « Ajouter N lignes dans telle table »
n'est pas une capacité : c'est l'écriture, réglée comme ci-dessus. Une
capacité, c'est ce qui n'est ni lire ni écrire (chercher sur le web,
envoyer un e-mail, appeler une API). Elle reçoit ses chiffres par ses
paramètres, qui peuvent venir d'un réglage.

**Ce qu'on ne fait pas** : pas de calculs dans les réglages (par exemple
« places libres = 3 − business en test ») : le quota protège, et le
modèle compte lui-même ce qu'il voit. Les conditions (« écrire seulement
si… ») viennent au lot 8. Les très grosses sorties (un plan complet, du
code) restent un champ texte ou des fichiers du bac à sable (lot 12).

**Ce qui reste dans la policy générale** : ce qui ne concerne aucune
invocation en particulier (budget du jour, quotas d'envoi, heures
d'appel). La page Policy montre à la fois la policy générale, les
réglages des invocations et les quotas des tables marqués « policy ».
