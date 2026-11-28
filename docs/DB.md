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
   **63**.
   - Une base neuve saute directement à la version 7 (le socle,
     `serge/db/schema.py`), puis applique 8, 9, … 63.
   - Une base **plus récente** que le code refuse de démarrer
     (`MigrateError`). Revenir à un ancien commit ne défait pas une
     migration.
2. **Le remplissage de départ** : les 8 étapes, les canaux, les
   capacités déclarées par le code, puis le pipeline de départ
   (`config/pipeline.yaml` : files, outils, invocations, règles
   d'écriture, liens, déclencheurs).
3. **Le calcul des empreintes** du code de chaque objet
   (`serge/objet_sha.py`).

Ces trois choses ne passent qu'à la **première ouverture** d'une base par
un processus, c'est-à-dire au démarrage d'un service (lot 10) : le
remplissage relit `config/pipeline.yaml` en entier, plus d'une
demi-seconde, alors que Mission Control rouvre la base à chaque requête
et, pour chaque page ouverte, toutes les 2 secondes. Une base recréée
depuis, ou qui n'est pas à la version du code, repasse par tout. Un
changement de `config/` prend donc effet au redémarrage des services,
comme après une mise à jour.

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
  nouveau d'une invocation, un droit d'écriture, un changement de statut
  permis ou une colonne nouvelle d'une vue de table ; rien de ce qui existe
  n'est modifié ;
- une **valeur d'un objet existant** ne change que par la section
  `changes` : une seule fois par instance, et seulement si la valeur en
  base est encore celle d'origine (une valeur changée dans Mission Control
  est gardée). Le résultat est noté dans `pipeline_changes`. Détail :
  [`LOT7_CONCEPTION.md`](LOT7_CONCEPTION.md), partie 5. Un **outil
  nouveau d'une invocation existante** passe aussi par `changes`
  (`add_tools`) : il s'ajoute une seule fois, à la fin de ses outils, et
  un outil retiré ensuite ne revient pas. De même pour un paramètre
  nouveau d'un déclencheur existant (`add_trigger_params`), par exemple
  une case de plus dans le formulaire d'un bouton. À l'inverse, un champ
  de la réponse (`remove_outputs`), une valeur d'une écriture
  (`remove_write_values`) ou une colonne lue par un outil
  (`remove_tool_columns`) se retirent une seule fois : exemple, le rythme
  des relances, sorti du plan d'un POC (Q37, corrigée par Q92). Un
  paramètre figé d'un outil d'une invocation (`set_tool_params`) change
  comme une valeur, seulement s'il vaut encore celle d'origine : exemple,
  les secrets que tape le paiement test. Un paramètre figé de plus sur un
  outil d'une invocation (`add_tool_params`) s'ajoute une seule fois, et
  le modèle ne le choisit plus ; déjà là, il est gardé : exemple, les
  sites où le paiement test tape la carte, le montant et la monnaie de
  son prix de 1 €. Une règle d'écriture de plus
  d'une invocation existante (`add_writes`) s'ajoute à son rang, le même
  que dans `pipeline.yaml`, avant la pose des liens ; un rang déjà pris
  est gardé : exemple, « Concevoir le produit » écrit aussi les offres du
  produit (Q119) ;
- ce qui est **retiré** du fichier est listé dans la section `deleted` :
  marqué supprimé en base (invocations, liens, déclencheurs), ou effacé
  (outils avec leur description d'API, quotas, textes de Serge, services
  d'API). Exemple : Hostinger, remplacé par Cloudflare (lot 10).

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
| `ventures` | Les business, de leur découverte à leur fermeture. Colonne `lifecycle` : le statut (`TEST` : le business bidon de l'ancien bouton « Lancer un essai », retiré au lot 12 ; `PRODUCT_BUILDING` : son produit fini est en construction, puis `PRODUCT_READY` : en vente sur son domaine, étape 5, lot 10). Fiche : `name`, `description`, `observations`, `sellable_offer`, `family` (sa famille de business), `choice_reason` (pourquoi il a été choisi pour un test). `trial` (version 52, décisions Q98 et Q99) : 1 pour un business d'essai, celui de l'essai total ; il suit le pipeline dans le couloir d'essai, ne prend aucune place, et les vraies invocations ne le voient pas. Les statuts du lot 12 : `SMOKE_RUNNING` (test léger en cours, jusqu'à ce qu'il soit mesuré), `SMOKE_DONE` (test fini et retenu), `PARKED` (mis de côté par le choix du principal), `FULL_RUNNING` (prospection lourde) ; `smoke_ended_at` : la fin de son test. `dedup_key` sert à écarter les doublons. `validate_drafts` = 1 : chaque brouillon de ce business attend la validation d'un humain (version 39, décision Q85). |
| `venture_sources` | Les pages qui prouvent le besoin derrière un business. |
| `campaigns` | Les campagnes : un business, une phase (`phase` : `smoke`, le test léger, ou `full`, la prospection lourde) et un canal. `state` : `DRAFT`, `READY`, `RUNNING`, puis `FINISHED` ou `CANCELLED`, avec la raison (`end_reason`). `n_target` et `n_week` : ses prospects visés, au total et par semaine ; `target` et `angle` : sa cible et son angle ; `started_at`, `planned_end_at` : son début, la fin prévue d'un test ; `dry_searches`, `found_at_search` : ses recherches de prospects restées vides (version 53, lot 12). Ses prospects sont les contacts qui ont un premier message dans cette campagne (`touches.campaign_id`). |
| `test_reports` | Le compte rendu d'un test léger (version 53) : prospects contactés, réponses, points, dépense, points par euro, le détail (`figures`), le verdict (`retenu` ou `non_retenu`, avec `verdict_reason`) et le bilan (`summary`). |
| `principal_choices` | Une proposition de business principal (version 53) : le business proposé, une phrase par business comparé, puis ce que Julien a décidé et le business choisi. |
| `contacts` | Les prospects et clients : une fiche par personne dans un business. Colonne `funnel_state` : où la personne en est (`STOPPED` : Serge a arrêté avec elle, une conversation sans issue, lot 10 bis). Les contacts des anciens essais ont été effacés une fois, avec leurs adresses, au branchement de l'e-mail (version 36, décision Q81). `note` (version 53) : qui est ce prospect, et pourquoi il est visé. |
| `contact_addresses` | Les adresses d'une personne : une ligne par adresse (`channel` = `email`, `phone` ou un réseau, `value`, `active`). Une adresse n'est jamais écrasée : une nouvelle s'ajoute à côté. `source_url` (version 53) : la page où l'adresse a été trouvée (décision Q36). |
| `touches` | Ce que Serge envoie à un contact, une ligne par message, écrite avant l'envoi : à qui, pour quel business, par quel canal et vers quelle adresse ; la sorte (`first` premier message, `reply` réponse, `followup` relance) ; l'objet et le texte ; le statut (`to_write` relance à rédiger, `pending` à envoyer, `sending` en cours d'envoi, `waiting_owner` attend un humain, `sent`, `failed`, `cancelled` avec la raison dans `last_error`) ; pourquoi un humain doit le voir avant qu'il parte (`needs_owner`), la question du contact sur le produit sans réponse dans la fiche (`owner_question`) et quand un humain l'a validé (`owner_ok_at`, version 39) ; quand Serge a demandé le contact à la personne parce que le réseau ne le laissait pas encore lui écrire (`contact_asked_at`, version 57, décision Q110 : l'envoi reste `pending`, avec sa raison dans `last_error`, et repart plus tard) ; le message reçu auquel il répond (`reply_to`) ou l'envoi qu'il relance (`followup_of`) ; la référence rendue par le canal (`external_ref`, pour l'e-mail son Message-ID) et l'heure de départ (`sent_at`) ; la boîte d'où il est parti (`sender`, version 61, décision Q120 : `serge.chevalier@jpesquet.tech` ; vide, la boîte du serveur). Une conversation reste sur sa boîte : une réponse part de la boîte qui a reçu le message, une relance de celle du dernier envoi au contact, et un premier message de la boîte de la page Policy qui a le moins envoyé dans la journée. La moitié « Serge » du fil d'un contact (version 35, décision Q79). |
| `inbound_events` | Ce que Serge reçoit d'un contact, une ligne par message : canal, expéditeur, objet, texte, sa référence pour lui répondre dans le même fil (`message_ref`), sa référence chez le canal (`external_ref` : un message n'est jamais écrit deux fois), le contact et le business auxquels il est rattaché, son statut (`attached` ; `unattached` : d'un inconnu, pas traité, montré dans Mission Control ; `ignored` : une réponse automatique d'absence, qui n'arrête pas les relances, ou le message d'un contact arrêté, rangé dans son fil sans être traité) et sa réaction (`question`, `refus`…). Sa sorte (`native_type`) : `email`, ou `auto_reply` pour une réponse automatique reconnue à ses en-têtes (lot 10 bis). La boîte de Serge qui l'a reçu (`mailbox`, version 61, décision Q120 ; vide, la boîte du serveur). La moitié « contact » du fil (version 35). |
| `product_sheets`, `product_faq` | La fiche produit d'un business (ce que fait le produit et pour qui, ce qu'il ne fait pas, son prix, ses délais habituels, comment on l'utilise) et ses questions fréquentes. « Traiter une réponse » les lit pour répondre (version 35). |
| `customer_requests` | Les demandes des contacts sur le produit : `bug`, `insatisfaction` ou `idée`, avec le contact et le message d'où elles viennent (version 35). Leur état (`status`) : `new`, `kept` (retenue par le plan du produit fini), `refused` (avec sa raison, `reason`) ou `delivered` ; le plan qui en a décidé (`plan_id`) et la version qui l'a livrée (`delivered_version`) (version 49, lot 10). |
| `product_reviews` | Les points sur les produits finis en vente (version 60, lot 16, décision Q119) : un par semaine (`cause` : `semaine`) et un par bug signalé (`bug`, avec la demande du client, `request_id`). Ce qui est décidé pour le produit (`product_action` : `rien`, `corriger`, `faire_evoluer`, avec ses consignes, `product_notes`) et pour la prospection (`prospecting_action` : `rien`, `relancer`, `prospecting_notes`), et le compte rendu (`summary`). Un point qui lance une nouvelle version du produit en porte l'état (`version_status`) : `open` tant qu'elle se construit, `online` quand elle est en prod (avec son numéro, `version`), `dropped` si elle est abandonnée ; `none` : il n'a rien lancé. Un business n'a qu'une version `open` à la fois : la règle de doublon `une_version_a_la_fois` écarte l'écriture d'un second point qui voudrait en lancer une. |
| `product_offers` | Les offres payantes d'un produit, écrites avec son plan, à la place des précédentes (version 60, décision Q119) : son code (`code` : `standard`, `pro`), son nom, son prix en centimes (`amount_cents`), sa période (`interval` : `month` ou `year`), ce qu'elle comprend (`includes`), et si c'est l'offre principale (`main` : `oui` pour une seule). Chacune a son prix dans Stripe : celui de l'offre principale porte la clé de recherche du business (son numéro), celui d'une autre `<numéro du business>_<code>`. |
| `web_accounts` | Les comptes de Serge sur des sites (version 55, lot 13, décision Q104) : un par site, nommé d'un mot (`id` : `reddit`). L'adresse du site (`url`), l'identifiant de connexion (`login`), le nom public (`handle`), l'état (`status` : `creating`, `active`, `blocked` : fermé par le site), le dernier compte rendu (`note`). Deux secrets chiffrés par la clé du coffre de l'instance (`secrets/credential-vault.key`), que ni un modèle ni Mission Control ne lisent : le mot de passe (`password_enc`) et la session du navigateur (`session_enc` : ses cookies, gardés le `session_saved_at`). `used_by`, `used_since` : la tâche qui s'en sert ; un compte ne sert qu'à une tâche à la fois. Remplace `accounts_standing`, qui gardait le mot de passe en clair et n'a jamais été remplie. Comment on s'y connecte (`sign_in_with`, version 58, décision Q113) : vide, par son identifiant et son mot de passe ; `google`, avec Google : le compte n'a pas de mot de passe, ses tâches s'ouvrent dans le profil du vrai Chrome, où un humain a connecté Google, et sa session n'est pas gardée en base. Ses adresses de connexion validées (`login_hosts`, version 62, décision Q122) : des hôtes séparés par des virgules, par exemple `login.live.com` pour un compte sur `outlook.com`. Le mot de passe se tape sur le site du compte ou sur l'une d'elles, nulle part ailleurs. Seule la réponse d'un humain au ticket « Adresse de connexion » y ajoute un hôte (`serge/login_hosts.py`) : la colonne n'est pas dans le catalogue d'écriture des invocations, et elle est vidée si l'adresse du site change. |
| `web_account_days` | Les actions faites avec un compte web, jour par jour (UTC) : la garde des comptes refuse au-delà du plafond du jour (page Policy, « Comptes web »). |
| `consents`, `blocklist` | Consentements et personnes à ne plus contacter. Un accord a une sorte (`basis`) : `contract`, `consent`, ou `test` (un membre de l'équipe qui essaie Serge : l'appel part à toute heure et hors du plafond par personne, Q79). |
| `transactions` | Les paiements. Le paiement test de 1 € d'un produit fini (étape 5, lot 10) y est noté par l'invocation qui le fait : `kind` = `canary`, son paiement chez Stripe (`intent_id`), `status` = `succeeded`. |
| `subscriptions` | Les abonnements Stripe, chacun rattaché à son business (lu dans le champ `metadata.venture_id` du prix ou de l'abonnement Stripe). `venture_id` vide : business inconnu, signalé au journal. |
| `artifacts` | Les livrables. Aujourd'hui, les captures d'écran gardées par une invocation (`kind` = `capture`) : le fichier sous `files/<business>/<livrable>/captures/` (`path_or_url`), son empreinte, sa taille (`size_bytes`) et la tâche qui l'a prise (`task_id`), pour la fiche de la tâche (version 43). Les fichiers qu'une page a fait télécharger (`kind` = `telechargement`), rangés sous `files/<business>/<livrable>/telechargements/<tâche>/` (décision Q103). Et les versions d'un produit (`kind` = `version`) : le dossier `files/<business>/<livrable>/v<N>/`, le livrable (`deliverable`) et le numéro (`version`), jamais modifiées (version 45). |
| `product_plans` | Les plans d'un POC ou d'un produit fini (`kind`), une ligne par version : le tour de critique (`round`), l'état (`draft`, `challenged`, `validated`, `to_fix`, `refused`), l'hypothèse, la cible, le canal, les prospects, la durée, le prix, le livrable, le plan de A à Z, les scénarios de test, l'avis du critique (`challenge`) et les consignes d'un humain (`owner_notes`) (version 46, lot 10). Pour un produit fini, son nom de domaine (`domain`, version 49). `followups` n'est plus écrit : les relances suivent un rythme commun à tous les business (Q37, corrigée par Q92). |
| `plan_critiques` | Les remarques « à corriger » du critique sur un plan, par tour (version 46). |
| `builds` | Les passages de construction d'un livrable : le numéro (`pass`), l'état (`built`, `unfinished` : pas fini, `reviewed`), le compte rendu du constructeur (`report`), le verdict du relecteur (`verdict` : `bon` ou `a_corriger`), ses remarques et ce qu'il a essayé (`review`), et les consignes d'un humain (version 46). |
| `deployments` | Ce que Serge a publié : une ligne par cible et par chantier (`staging-essai-chantier`, `prod-…`), avec la version, son image, le conteneur, le port fixe sur 127.0.0.1 que vise la route de Caddy (`host_port`), l'adresse publique (`hostname`), l'état (`running`, `failed`, `stopped`) et pourquoi la dernière publication a raté (version 45, lot 10). L'adresse de contact que montre le produit (`contact_email`, version 60, décision Q119) : la boîte de Serge avec le nom court du produit après un « + » ; un e-mail qu'un inconnu y écrit est rattaché à ce business. Une adresse ne sert qu'un produit : publier sur une adresse déjà prise arrête l'ancien produit (`stopped`, « remplacé par … »). Les routes elles-mêmes restent dans `state/web-ingress/inventory.json` : le service Caddy ne peut pas ouvrir la base. |
| `sandboxes` | Les chantiers : un conteneur Docker par business et par livrable (`id` = `<business>-<livrable>`, par exemple `essai-chantier`), gardé entre deux tâches avec son volume monté sur `/work`. `status` : `running` (un seul à la fois), `stopped`, `removed` ; `disk_mb` : la place mesurée après la dernière commande ; `last_error` : pourquoi il a été arrêté (disque plein). Les chiffres d'un chantier sont sur la page Policy, famille « Bac à sable » (version 42, lot 10, décision Q91). |
| `listen_docs` | Les pages gardées par l'étape 1 : adresse, titre, aperçu (jamais le texte entier), source (`web` ou `rss`), flux (`feed_id`), cycle où elle a été triée (`cycle_id`), étiquette de tri (`label` : vide, `besoin_nouveau`, `bruit`, `enrichit`, `preuve`). `trial` (version 53) : 1 pour une page lue par un essai ; elle n'est pas « déjà gardée » pour la vraie écoute. |
| `listen_feeds` | Les flux RSS que Serge a choisis : adresse, titre, invocation qui l'a ajouté, actif ou coupé, dernière lecture. |
| `listen_cycles` | Les cycles de l'étape 1 : texte de guidage, état (`OPEN`, `CLOSED`, `ABANDONED`), dates, et ce que « Choisir » a dit du cycle (`choice_note`). `trial` (version 53) : 1 pour le cycle d'écoute d'un essai. |
| `tickets` | Les décisions à prendre par Julien et Clem. `tickets.trial` (version 53) : 1 pour un ticket ouvert par une tâche d'essai ; `tickets.task_id` : la tâche qui l'a ouvert. La réponse à un ticket (`ticket_answers`) garde la marque `trial`. La table `ticket_items` (les lignes d'un ticket à trancher une par une) est retirée à la version 54 : aucun ticket n'en a jamais eu. |
| `ticket_types` | Les types de tickets, remplis depuis `config/ticket-types.yaml` (seulement les types nouveaux) : leur délai avant expiration (`expiry_minutes`, vide : jamais), la décision annoncée à l'expiration et leurs boutons, réglables dans Mission Control ; le reste de la déclaration dans `spec_json` (version 38, décision Q85). Un type listé dans la section `deleted` du fichier est effacé de la base au démarrage (décision Q102). |
| `discord_admins` | Les administrateurs Discord de Serge, par leur identifiant : chaque ticket les mentionne, et eux seuls peuvent le trancher sur Discord. Ajoutés dans Mission Control ; le premier vient une fois du fichier d'instance (version 38, décision Q86). |
| `ticket_posts` | Le fil de chaque ticket dans le forum « tickets » du serveur de Serge (`thread_id`, qui est aussi l'identifiant de sa carte, le premier message), la version du ticket que montre la carte (son état et sa dernière mise à jour) si le fil est archivé (un ticket tranché), et le message qui porte la carte actuelle (`message_id`, version 44 ; vide : le premier) : un ticket rouvert après « Réécrire » repart en bas du fil, avec une mention. Le forum se règle dans Mission Control (`runtime_flags`, `discord.forum_tickets`) ; seuls les tickets ouverts après le réglage y ont un fil (version 41, décision Q88). Remplace `ticket_messages`, un message privé par administrateur (version 38). |
| `ticket_answers` | Chaque réponse à un ticket : le bouton (`acte`), le texte saisi, l'objet saisi avec « Ma réponse » (`subject`, version 44 ; sans objet saisi, celui du message), qui a répondu, et, recopié du ticket, ce dont il parle. Une expiration y écrit sa décision par défaut. Ses déclencheurs « une ligne est écrite », réglés par bouton, réveillent les invocations qui réagissent (version 39, décision Q85). Un ticket garde la ligne dont il parle (`ref_table`, `ref_id`), son business, son contact et la question posée. |
| `policy_sections`, `policy_settings`, `policy_relations` | Les réglages généraux (la « policy », page Policy de MC), une ligne par réglage : sa valeur (en JSON), son titre, son aide, sa sorte (`eur`, `curseur`, `liste`…), ses bornes et ses choix, et sa **valeur précédente** (qui l'a remplacée, quand) pour « Remettre la valeur précédente ». Les familles de réglages, avec leur page (`page` : `policy`, ou `pipeline` pour ce qui touche au modèle, version 34) (leurs colonnes `lock_*` ne servent plus : le verrou d'une famille a été retiré avec la famille « Taille des essais », le 16 novembre 2026), et les relations entre réglages (une recherche ne demande pas plus de résultats que le moteur n'en rend). Remplis par `config/policy.yaml`, sans jamais écraser une valeur ; un réglage renommé (section `renamed`) garde sa valeur (version 33, décision Q68 ; avant, la policy était une copie complète en JSON à chaque modification). |
| `runtime_flags` | Les interrupteurs à chaud. Aujourd'hui : Serge démarré (`scheduler.heartbeat` à `on`). Sans cette ligne, Serge est arrêté. |

### Le journal (ce qui s'est passé, jamais modifié)

| Table | Contenu |
|---|---|
| `events` | Le journal général : qui, quoi, quand, avec un contenu JSON. |
| `event_rows` | Quel événement concerne quelle ligne (une table et un numéro). C'est l'historique d'une ligne, que lit l'outil « Lire l'historique ». Rempli par chaque écriture d'invocation et par chaque événement d'un business. |
| `ticket_events` | L'historique de chaque ticket. |
| `llm_usage` | Chaque appel au modèle, noté aussitôt : invocation, modèle, jetons, durée, résultat (`ok`, `format_invalide`, `outil` pour un tour d'outils, `erreur` pour un appel raté) et coût réel facturé par OpenRouter (`cost_usd`, en dollars, vide s'il n'est pas donné). Les plafonds du jour et du mois comptent ce coût réel. `task_id` : la tâche de l'appel, qui rattache son coût à son business (paramètre `venture_id` de la tâche), pour les points par euro de la grille de points (version 37, décision Q84). `provider`, `cached_tokens`, `cache_write_tokens` : chez qui OpenRouter a envoyé l'appel, et les jetons lus et écrits dans le cache, qui expliquent son coût (version 51). |
| `episode_archives` | Les archives d'événements anciens. |

### La connaissance

| Table | Contenu |
|---|---|
| `lessons` | Les leçons, avec leur fiabilité et leurs sources. Leur statut (`status`) : `candidate` (proposée : son ticket « Leçon » attend un humain, et aucune invocation ne la reçoit), `active` (gardée par un humain : donnée aux invocations qu'elle concerne), `deprecated` (jetée ou dépassée). Une invocation n'écrit une leçon qu'au statut `candidate` ; seule la réponse au ticket la fait passer à `active` ou à `deprecated` (décision Q121). `venture_id` (version 62) : le business d'où elle vient, que montre son ticket ; vide si elle ne vient pas d'un business. |
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
| `invocation_settings` | Les réglages d'une invocation, une ligne par réglage (exemple : « nombre d'idées = 2 », entre 1 et 5). Ils servent dans le prompt (`{nombre_idees}`), le format de la réponse, l'écriture et les paramètres. `policy` = 1 : modifiable sur la page Policy de MC, qui garde la valeur précédente (`previous_value`, `previous_at`, `previous_by`). `trial_value` (version 53) : la valeur du réglage dans une tâche d'essai (vide : la même). Exemple : « Explorer le web » fait 10 recherches, et 2 dans l'essai total. |
| `invocation_output_fields` | Le format de la réponse de chaque invocation. Une liste peut avoir un nombre d'éléments minimum et maximum (un nombre ou le nom d'un réglage). |
| `writable_tables`, `writable_columns` | Ce qu'une invocation a le droit d'écrire : ajouter, modifier, supprimer, table par table, et les colonnes permises. |
| `invocation_writes`, `invocation_write_values` | Où chaque invocation écrit sa réponse, avec au besoin « au plus N lignes par passage » et une condition (`condition_field`, `condition_op` parmi `=`, `!=`, `non_vide`, `condition_value`). Exemple : la réponse n'est écrite que si `reply` est non vide (version 35). `skip_dedup` = 1 : l'écriture passe outre les règles de doublon ; seul l'essai « Bout en bout : le POC d'une calculatrice » s'en sert, pour créer un business neuf à chaque essai (version 48). |
| `status_transitions`, `dedup_rules`, `dedup_rule_columns` | Les protections : changements de statut permis, doublons. |
| `task_cancel_rules` | Les tâches à annuler quand une ligne change d'état : « quand un cycle passe à `ABANDONED`, ses tâches en attente (paramètre `cycle_id`) sont annulées ». |
| `table_quotas` | Une protection de plus : « au plus N lignes dont telle colonne vaut l'une de ces valeurs » (exemple : au plus 3 business choisis pour un POC). Un quota peut ne compter que certaines lignes (`where_column`, `where_value`, version 52) : les places de test, la place lourde et le cycle d'écoute ouvert ne comptent que les lignes dont `trial` vaut 0, pas celles d'un essai. Modifiable sur la page Policy, qui garde la valeur précédente. |
| `links`, `link_params`, `link_passages`, `link_passage_params` | Les liens entre invocations, ce qui est déjà passé, et ce qui attend un clic « Passer à la suite » avec ses paramètres (lien réglé à la main). Un lien peut avoir une condition (comme une écriture : lue dans la réponse, ou dans la ligne écrite pour un lien `per_row`) et un délai tiré entre deux réglages de la policy (`delay_min_setting`, `delay_max_setting` ; `{channel}` y est remplacé par le canal de la ligne, version 35). `links.lane` (version 53) : vide (le lien existe partout), `real` (seulement dans le vrai pipeline) ou `trial` (seulement dans l'essai total) ; `link_passages.from_task` : la tâche d'où vient le passage. |
| `triggers`, `trigger_params`, `trigger_conditions` | Ce qui lance une invocation : une ligne écrite, une heure (une tâche par ligne d'une table, si le déclencheur en vise une), un bouton (avec sa question de confirmation). `trigger_params` : ce que le déclencheur transmet à la tâche, pris dans la ligne écrite (`row`), dans un champ du formulaire du bouton (`form`), dans une case à cocher de ce formulaire (`form_case` : `1` cochée, `0` sinon, version 40) ou fixe (`fixed`). `trigger_conditions` : les quotas qui doivent avoir de la place. `triggers.lane` (version 53) : comme pour un lien ; un bouton dont le couloir est `trial` démarre un essai. `trigger_row_conditions` : un déclencheur ne part que si un nombre de lignes est atteint, ou pas dépassé (exemple : au plus 0 business en test léger), compté dans le couloir de la tâche à créer. |
| `pipeline_changes` | Les modifications d'objets déjà en base passées par la section `changes` de `pipeline.yaml`, une ligne par modification, avec son résultat. |
| `queues`, `tasks`, `task_params`, `task_inputs`, `task_seen_tables` | Les files (conversations, travaux, et « Appels » : chaque appel téléphonique est une tâche de l'agent vocal, menée en direct par le pont téléphonique, lot 8), leurs tâches, et ce que chaque tâche a reçu : ses lectures d'office, les tables à comparer et ses leçons (lignes données, lignes laissées de côté). La réponse d'une tâche LLM, après vérification de son format, est gardée dans `tasks.answer_json` et se lit sur la fiche de la tâche (version 42). Une tâche gelée par une demande à Julien a le statut `blocked` : elle repart avec sa réponse (version 51). Le couloir d'essai (version 53, décision Q99) : `tasks.trial_run` est l'essai dont une tâche fait partie (vide : le vrai pipeline ; le numéro de l'essai en cours est dans `runtime_flags`, sous `essai_en_cours`) ; `tasks.parent_id`, la tâche qui l'a créée ; `tasks.rerun`, la marque d'un redémarrage (« Repartir d'ici »), héritée par toute sa suite. |
| `llm_models` | Chaque niveau (rapide, moyen, intelligent, « code » depuis la version 43, décision Q91, et « web » depuis la version 51, décision Q96 : voir et cliquer des pages, moins cher que « code ») : le modèle derrière lui, et pour la recommandation de la page Pipeline son prix maximum (`max_price_usd`, $ par million de jetons), sa tolérance (`tolerance_pct`, % de la meilleure note sous ce prix) et s'il doit lire les images (`needs_image`, 1 pour « code » et « web »). |
| `serge_texts` | Les textes de Serge, modifiables sur la page Pipeline : la présentation de Serge (« Qui est Serge »), le message quand ses outils sont épuisés, le début de la consigne de format, la redemande d'une réponse mal formée, la note d'un résultat d'outil coupé, et la phrase de fin de chaque e-mail (`footer_email` : « …répondez STOP »). Chacun a un titre, une aide, et sa valeur précédente (qui l'a remplacée, quand) pour « Remettre » (version 34). |
| `api_services`, `api_endpoints`, `api_endpoint_params` | Les services qu'appelle la capacité « Appeler une API » (version 47, lot 10, Q56 et Q91). Un service : son adresse, son authentification (`bearer` ou `none`), le nom du fichier de secret sous `config_root/secrets/` (jamais sa valeur) et le format du corps (`form` pour Stripe, `json` ailleurs). Un point d'entrée est un outil (`tool_id`) : son service, sa méthode et son chemin (`/v1/prices/{id}`). Ses paramètres permis : nom, type (`text`, `number`, `bool`, `json`), obligatoire ou non, description pour le modèle. Exemple : `stripe_test` et `stripe_live`, et l'outil « Créer un prix Stripe » (`POST /v1/prices`). Un point d'entrée payant peut porter un verrou de prix (`guard`, un objet JSON, version 50) : l'outil qui vérifie le prix, ses paramètres tirés de l'appel, ce qui doit être vrai ou refusé dans sa réponse, les prix à comparer, un taux de prudence et le réglage de l'invocation qui fixe le plafond. Exemple : l'achat d'un domaine chez Cloudflare, plafonné par `prix_max_eur`. |
| `canaux` | Les canaux par lesquels Serge parle à un tiers, remplis au démarrage. Un canal porté par du code (e-mail, voix) : `connected` = 1 si son adaptateur existe (`serge/channels/`) et que le canal est configuré sur ce serveur (l'e-mail : une boîte Gmail ou SMTP/IMAP dans le fichier d'instance ; la voix : `features.phone_voice`). Un canal du navigateur (LinkedIn, Instagram, X ; version 56, lot 13) : décrit dans `config/pipeline.yaml` (`web_channels`), avec le compte web qui lui sert (`account`), l'invocation qui envoie (`send_invocation`) et celle qui relève (`poll_invocation`) ; `connected`, `etat` et `polls` suivent l'état de ce compte, tenus à jour par des déclencheurs de la base. Pour tous : la sorte d'adresse (`address_channel` : `email`, `phone`, ou le nom du canal pour un profil), s'il se relève (`polls`), à quel rythme (`poll_pace` : `fast`, toutes les 2 minutes ; `slow`, toutes les 4 heures) et sa dernière relève (`polled_at`, version 35). |

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

**La mesure des tests.** Faite au lot 9 sans table nouvelle : le barème
de la grille de points est un réglage par canal et par réaction, dans
`policy_settings` (famille `points`, décision Q84). Les points se
recalculent à partir des réactions des messages reçus
(`inbound_events.reaction`).

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
