# Lot 7 : l'étape 1 décrite en base

Ce document décrit ce que le lot 7 a construit : l'étape 1 (la
pré-prospection) entièrement décrite dans la base, et ce qu'il a fallu
ajouter à l'interpréteur pour y arriver, sans jamais écrire de code propre
à une invocation. Les décisions de Clem sont dans la question Q65 de
[`DECISIONS_REVUE.md`](DECISIONS_REVUE.md). Ce que fait l'étape, vu de
l'extérieur, est dans [`etapes/1-pre-prospection.md`](etapes/1-pre-prospection.md).
Le fonctionnement général de l'interpréteur est dans
[`LOT6_CONCEPTION.md`](LOT6_CONCEPTION.md).

Tout ce qui suit est écrit dans `config/pipeline.yaml`, puis rangé en
base au démarrage.

---

## 1. Les deux processus

**La veille** : le déclencheur « Lire chaque flux RSS suivi » part toutes
les 6 heures et crée une tâche par flux actif de `listen_feeds`, avec
l'adresse du flux. L'invocation « Lire un flux RSS » (sans LLM, capacité
`rss_read`) rend les pages du flux, avec un aperçu de 5 lignes tiré du
résumé du flux ; sa règle d'écriture les ajoute à `listen_docs`. Une page
déjà gardée (même adresse) est écartée par la règle de doublons
`page_deja_gardee`.

**Le cycle** : un bouton de la page Écoute, « Lancer un cycle d'écoute »,
avec le texte de guidage de Julien. Il ne crée de tâche que si les quotas
`places_de_test` (au plus 3 business en test) et `cycles_ouverts` (un seul
cycle ouvert) ont de la place. Les invocations s'enchaînent par des liens
« à la fin de chaque passage », qui transmettent le numéro du cycle :

| # | Invocation | Sorte | Ce qu'elle reçoit | Ce qu'elle écrit |
|---|---|---|---|---|
| 1 | Ouvrir un cycle d'écoute | sans LLM (`echo`) | le texte de guidage | un cycle `OPEN` |
| 2 | Explorer le web | LLM moyen | le cycle ; la version courte des business, des pages gardées et des flux | les pages retenues (adresse, titre, aperçu) et les nouveaux flux |
| 3 | Rattacher les pages au cycle | sans LLM (`db_read`) | les pages ni triées ni rattachées, au plus 60 | le numéro du cycle sur ces pages |
| 4 | Trier les pages | LLM rapide, par paquets de 20 | l'aperçu des pages du cycle ; la version courte des business | l'étiquette de chaque page ; une preuve pour chaque page qui enrichit un business |
| 5 | Formuler des business A | LLM intelligent | l'aperçu des pages « besoin nouveau » ; la version courte des business | au plus 3 business `CANDIDATE`, leurs preuves ; les pages utilisées deviennent « preuve » |
| 6 | Formuler des business B | la même chose | la même chose, avec les business écrits par A | la même chose |
| 7 | Choisir les business à tester | LLM moyen | les business en test, les candidats, leurs preuves | des business `POC_SELECTED` avec la raison du choix ; le cycle `CLOSED` |

**Chaque jour**, « Oublier les vieilles pages » supprime les pages
« bruit » ou jamais triées de plus de 30 jours, et « Oublier les besoins
jamais utilisés » les pages « besoin nouveau » de plus de 60 jours. Une
page qui sert de preuve (« preuve » ou « enrichit ») n'est jamais visée.

**Deux boutons de plus** sur la page Écoute : « Abandonner le cycle en
cours » (ferme un cycle resté ouvert et annule ses tâches en attente : sa
chaîne s'arrête après la tâche en cours) et « Effacer les idées (test) »,
temporaire, qui détruit les business candidats ou choisis et leurs
preuves. Les deux demandent une confirmation.

---

## 2. Les étiquettes d'une page

Une page gardée (`listen_docs`) a une étiquette (`label`) :

- vide : pas encore triée ;
- `besoin_nouveau` : elle montre un besoin qu'aucun business connu ne
  couvre ;
- `bruit` : rien d'utile ;
- `enrichit` : elle concerne un business connu, et lui est rattachée comme
  preuve (`venture_sources`) ;
- `preuve` : A ou B l'a citée comme preuve d'une nouvelle idée.

Les changements permis sont déclarés en base (`status_transitions`) : une
page vide peut recevoir n'importe quelle étiquette ; une page « besoin
nouveau » ou « bruit » peut devenir « preuve » ; rien d'autre. B ne reçoit
donc que les pages « besoin nouveau » que A n'a pas utilisées, et une page
déjà triée n'est jamais représentée comme nouvelle.

---

## 3. Ce que l'interpréteur sait faire en plus

Chaque ajout est général : il sert à toutes les invocations.

- **Lire une page** (capacité `page_read`, `serge/listen/page.py`) : une
  simple requête, sans navigateur. Le texte est découpé en lignes (un
  titre, un paragraphe ou un élément de liste, jamais plus de 300
  caractères : un paragraphe plus long est coupé à la fin d'un mot), sans
  le menu ni le pied de page. Réglée par un nombre de lignes : l'outil « aperçu » (5 lignes,
  pour Explorer) et l'outil « page entière » (150 lignes, pour A et B,
  seulement une page déjà en base, par son numéro). Les adresses du
  serveur et des réseaux privés sont refusées, même après une
  redirection. On ne garde jamais le texte entier en base : seulement
  l'adresse et l'aperçu.
- **Lire un flux RSS** (capacité `rss_read`) : le lecteur de flux qui
  existait, avec la même protection des adresses.
- **Une lecture d'office par paquets** (`invocation_tools.batch_size`,
  un nombre ou un réglage) : le modèle est appelé une fois par paquet, et
  les réponses sont réunies (les listes bout à bout) avant l'écriture.
- **Au plus N appels d'un outil** par passage
  (`invocation_tools.max_calls`) : au-delà, l'outil répond « limite
  atteinte ». Exemple : au plus 10 recherches pour Explorer.
- **Un déclencheur conditionné par des quotas** (`trigger_conditions`) :
  il ne crée pas de tâche si l'un de ses quotas est plein. La page Écoute
  affiche « Places de test occupées : 2 sur 3 » et grise le bouton quand
  il est refusé, en disant pourquoi.
- **Une question avant un bouton** (`triggers.confirm_text`).
- **Un déclencheur horaire par ligne** : un déclencheur `every` ou `at`
  qui vise une table (et, si besoin, un filtre) crée une tâche par ligne,
  avec les colonnes de la ligne en paramètres.
- **Annuler les tâches d'une ligne qui change d'état**
  (`task_cancel_rules`, version 32 de la base) : une protection réglée
  sur la table. « Quand un cycle passe à `ABANDONED`, ses tâches en
  attente (paramètre `cycle_id`) sont annulées. » La file ne fait qu'une
  tâche à la fois : l'abandon passe juste après la tâche en cours, et
  annule aussi celle qu'elle vient de créer. La fiche d'une tâche en
  attente a aussi un bouton « Annuler la tâche ».
- **Supprimer** : une règle d'écriture peut supprimer les lignes où une
  colonne vaut une valeur (`operation` = `delete`, permis table par table
  avec `writable_tables.can_delete`). Une seule note au journal par règle
  (`write.deleted`), avec le nombre de lignes.
- **Une écriture « fille » sur la même liste** que sa « mère » retrouve la
  ligne du même élément (exemple : mettre l'étiquette « enrichit », puis
  rattacher la preuve).
- **Le catalogue de lecture** accepte un filtre sur une liste de valeurs
  (`fixed: [a, b]`), un filtre « plus vieux que N jours » (`days_ago`), un
  filtre ou une jointure sur une colonne qu'il ne rend pas, et un nombre
  écrit en texte pour un paramètre numérique (un réglage vaut « 60 »).
- **Un prompt peut citer un quota** : `{quota.places_de_test}` donne son
  maximum, réglé une seule fois, sur le quota.
- **Les appels au modèle**, revus après le premier essai en production
  (une réponse vide a fait échouer « Explorer le web » au bout de 22
  minutes, puis un cycle a consommé près de 3 millions de jetons) :
  - une erreur passagère (réponse vide, délai dépassé, trop de requêtes,
    panne du fournisseur) est réessayée deux fois, après 3 puis 10
    secondes ; le modèle a 3 minutes pour répondre ; une réponse vide
    garde ce qu'OpenRouter en dit (raison de la fin, modèle, erreur) ;
  - le modèle peut appeler plusieurs outils dans le même tour, et les
    consignes le lui demandent : moins d'allers-retours, donc moins de
    jetons renvoyés (à chaque tour, tout l'historique repart au modèle) ;
  - quand ses tours d'outils sont épuisés, ou que le plafond de dépense du
    jour est atteint en plein travail, un message lui demande sa réponse
    finale, sans plus d'outil ;
  - chaque appel est noté dans `llm_usage`, tours d'outils (`outil`) et
    échecs (`erreur`) compris, même si la tâche échoue ensuite, avec son
    **coût réel** : celui qu'OpenRouter facture (`cost_usd`, en dollars),
    converti en euros par le taux de la policy (`budget.eur_per_usd`). Le
    plafond du jour et la page Économie comptent ce coût réel ; un appel
    sans coût connu n'est pas estimé : ses jetons sont comptés à part et la
    jauge les signale ;
  - tout l'historique repart au modèle à chaque tour : un résultat d'outil
    plus long que la taille réglée dans la policy
    (`quotas.llm_outil_resultat_max_caracteres`, 20 000 caractères) est
    coupé, avec une note ; les résultats ne sont jamais envoyés en double ;
    et une redemande de format se fait sans outil (le modèle corrige sa
    réponse, il ne recommence pas ses recherches). Au premier cycle en
    production, un seul aperçu de page (une « ligne » sans longueur
    maximale) a ajouté 126 000 jetons, renvoyés ensuite à chaque tour ;
  - les réglages qui renvoient moins de jetons : « Explorer le web » a 10
    tours d'outils ; A et B en ont 5, lisent au plus 10 pages en entier
    par passage (`pages_entieres_max`, par la limite d'appels de l'outil)
    et 150 lignes par page.
- **La file dans Mission Control** dit pourquoi une tâche attend : une
  tâche LLM n'est pas annoncée comme « prochaine » quand le plafond du
  jour (ou, depuis Q68, du mois) est atteint, et la raison est donnée
  (« Plafond du jour atteint : 1 tâche(s) LLM attendent demain… »).
---

## 4. Ce qui est retiré, et la mise à jour d'une instance

- Le demi-cycle de démonstration du lot 6 est listé dans la section
  `deleted` de `config/pipeline.yaml` : au démarrage, ses invocations, ses
  liens et son bouton sont marqués supprimés, ses outils et le quota
  `business_choisis` sont effacés. Une instance existante est ainsi mise à
  jour sans code propre à la démo.
- Les droits d'écriture ne font que grandir : une colonne ou une opération
  nouvelle de `writable_tables` s'ajoute aussi sur une instance
  existante ; rien n'est jamais retiré. Même chose pour les colonnes des
  vues des tables (`table_views`).
- La migration v29 retire `listen_cycle_docs` (le cycle d'une page est sur
  la page), `listen_docs.cluster_id` et deux colonnes des cycles
  (`needs_target`, `business_target`), et nettoie le catalogue qui les
  visait.
- **Sur le serveur de Julien**, après la mise à jour : si la démo a laissé
  un cycle ouvert, le bouton du cycle reste grisé (« Cycle d'écoute en
  cours : 1 sur 1 ») jusqu'à un clic sur « Abandonner le cycle en
  cours » ; « Effacer les idées (test) » détruit les business de la démo.

---

## 5. Modifier un objet déjà en base : la section `changes`

`config/pipeline.yaml` n'écrase jamais un objet déjà en base, pour ne pas
défaire ce que Julien a réglé dans Mission Control. Quand il faut quand
même changer une valeur d'un objet qui existe déjà sur les instances, on
l'écrit dans la section `changes` du fichier
(`serge/pipeline_changes.py`) :

```yaml
changes:
  - id: lot7_explorer_10_tours
    why: Moins de jetons renvoyés ; avec plusieurs outils par tour, 10 tours suffisent.
    table: invocations
    where: {id: explorer_web}
    set: {max_tool_turns: {from: 25, to: 10}}
```

- Chaque modification n'est appliquée qu'**une fois** par instance, et
  seulement si la valeur en base est **encore celle d'origine** (`from`).
  Une valeur changée dans Mission Control est gardée.
- Le résultat est noté dans la table `pipeline_changes` (version 30 de la
  base) : « max_tool_turns : 25 → 10 », « déjà à jour » (instance neuve)
  ou « gardé (changé dans Mission Control) ».
- Seules les tables du pipeline peuvent être visées (invocations, leurs
  outils et réglages, liens, déclencheurs, quotas, vues des tables).
- Un prompt se change de la même façon : l'ancien texte exact en `from`
  (une ancre YAML évite de le recopier deux fois).
- Un **réglage nouveau** d'une invocation existante n'a pas besoin de
  `changes` : il s'ajoute tout seul, comme une colonne nouvelle d'une vue
  ou un droit d'écriture nouveau. Un réglage existant n'est jamais
  modifié autrement.

---

## 6. Ce qui reste pour plus tard

- La recherche passe par DuckDuckGo ; SearXNG viendra au lot 12, avec le
  navigateur pour les pages qui en ont besoin.
- Couper automatiquement un flux qui ne ramène que du bruit (après 5
  cycles) : à la main pour l'instant, depuis la page Écoute.
- Le lancement automatique du cycle.
- Le bouton « Effacer les idées (test) » est à retirer avant le vrai
  lancement de Serge (le lister dans `deleted`).
