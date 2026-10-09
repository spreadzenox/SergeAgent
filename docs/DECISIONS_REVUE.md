# Décisions de SergeAgent — les questions et les réponses validées

Ce fichier est le journal des décisions du projet. Chaque fois qu'un agent
pose des questions à Julien ou à Clem et qu'ils répondent, la réponse est
notée ici sous un numéro (Q1, Q2…). Une réponse validée fait foi : le code
et la doc doivent être corrigés pour s'y conformer. Le fichier est
permanent. Il a commencé avec la revue du projet (septembre 2026).

## Comment ajouter une entrée

Seulement après une vraie question-réponse avec Julien ou Clem. Une
décision prise sans question n'a pas sa place ici. On ajoute l'entrée à la
fin du fichier, avec le numéro qui suit la dernière (les entrées restent
dans l'ordre des numéros, qui est l'ordre des questions : plus le numéro
est grand, plus la réponse est récente) :

```
### Q<numéro> — Titre court (validé par Clem, 2 octobre 2026)
Constat : ce qui a amené la question.
Décidé : ce qui a été répondu, point par point.
Arguments : pourquoi cette réponse plutôt qu'une autre (si la personne en a donné).
```

- **Qui a répondu** est toujours dans le titre : « validé par Julien »,
  « validé par Clem », ou « validé par Clem et Julien », avec la date.
- **Les arguments** sont notés quand la personne en donne. Sinon on ne les
  invente pas.
- On ne retire pas une entrée parce que son travail est fait. Si une
  réponse devient fausse (le code actuel ou une réponse plus récente la
  contredit), on la corrige dans son entrée d'origine. Le texte dit ce qui
  est vrai maintenant, et on ajoute à la fin de l'entrée : « Corrigé le
  <date> (Q<numéro>) : ce qui a changé, et pourquoi ».
- Qui décide de la correction : si une réponse plus récente contredit
  l'ancienne, la plus récente a raison, mais seulement sur les points où
  elle la contredit ; sur le reste, elle ajoute de l'information et
  l'ancienne garde sa valeur (Q71). On corrige alors l'ancienne sans
  demander. Même chose pour un détail explicitement périmé (un numéro
  d'étape ou de lot, un « à faire » déjà fait) et pour une correction qui
  ne change pas le sens fonctionnel (Q74). Si c'est le code ou un autre
  texte qui contredit la réponse et que le sens change, on demande à un
  humain laquelle fait foi.

Méthode de travail (Q30) : corriger par petits lots relisibles (un sujet =
un commit, tests verts), en relisant ce fichier au début de chaque lot.

## Principes transverses (valent pour tout le chantier)
- Clarté avant tout : MC + SQLite doivent suffire à comprendre toute la
  pipeline. Éviter que la logique vive, obscure, dans le code.
- Docs et TODO : écrites pour un humain ET un autre LLM qui arrivent à froid.
  Français simple, pas de mots-valises ni de jargon vague ; décrire
  fonctionnellement ce qui se passe.
- Style (recadrage Julien en Q11) : phrases courtes, un exemple concret
  chiffré plutôt qu'une formule abstraite. Pas de jargon d'ingénieur :
  « l'hôte », « jonction », « de façon prévisible », « contrat », « canon »…
  Contre-exemple à ne jamais reproduire : « Chaque accès injecté a une taille
  maximale (nombre de lignes) sur sa jonction. Si le contenu dépasse, l'hôte
  coupe de façon prévisible (les plus récents d'abord). »
  Version acceptable : « On donne au plus 50 business à l'invocation. S'il y
  en a plus, elle reçoit les 50 plus récents et un message qui dit combien
  ont été laissés de côté. »
  S'applique à la doc, au TODO ET aux conversations.
- Style des documents (demande de Clem, après la réécriture du TODO) :
  chaque tâche du TODO est une case à cocher, un titre en gras, puis un
  paragraphe descriptif qui dit d'où on part, ce qu'il faut faire,
  pourquoi, et ce qui doit être réglable dans Mission Control. Pas de
  rubriques du type « Quoi / Pourquoi / Dépend de », pas de renvoi à un
  numéro seul (« voir Q13 ») : on écrit ce que dit la décision, puis son
  numéro entre parenthèses (Q69). Les autres documents suivent le même
  esprit : des phrases qui
  décrivent, avec des exemples, plutôt que des listes de mots-clés.

## Questions / réponses

### Q1 — Squelette du produit
La chaîne de 8 étapes est LE squelette du projet, dans cet ordre :
1. pre_prospection — écouter le web, repérer des besoins, choisir des business à tester
2. conception_poc — concevoir le test (hypothèse, prix)
3. prospection_light — premiers contacts (email, voix)
4. choix_venture — garder ou tuer un business
5. build_venture — construire ce qui se vend
6. prospection_lourde — prospection à l'échelle, classement des réponses entrantes
7. collect_feedback — mémoire, leçons
8. caisse — facturation, encaissement
Toute doc doit partir de cette chaîne.

### Q2 — Vocabulaire + source de vérité des réglages LLM
- Terme : « jugement LLM » est banni → remplacer PARTOUT (code, doc, UI MC)
  par « invocation LLM ».
- Ce qui fait foi pour les réglages d'une invocation LLM (enabled, tier,
  prompt, tools…) : la base SQLite, modifiable depuis Mission Control.
- Règle générale : SQLite = source de vérité unique, systématiquement et le
  plus possible (structuré + éditable depuis MC). Exception tolérée seulement
  pour une contrainte fonctionnelle/architecturale dure, et à justifier.

### Q3 — Rôle des seeds (YAML / prompts code) → option A
Contexte : chaque push sur main déploie sur le VPS de Julien
(.github/workflows/deploy.yml → scripts/serge-deploy.py) : un Serge + MC
tournent en continu.
- Instance existante : une modif de seed côté code ne doit JAMAIS écraser la
  base d'une instance qui tourne (prompts, réglages édités ou non dans MC).
- Nouvelle instance (Serge open source, nouvel utilisateur) : la base est
  peuplée à l'init avec la dernière version des seeds du code.
- Objet NOUVEAU dans le code (nouvelle invocation, tool, clé de policy…) :
  INSÉRÉ sur l'instance existante au déploiement, avec ses valeurs seed.
- Nouveau TYPE d'objet (nouvelle table) : la table est créée par migration
  et ses objets seed sont insérés.
- Jamais d'UPDATE d'un objet déjà présent depuis les seeds, sauf par la
  section `changes` de `pipeline.yaml` : une seule fois par instance, et
  seulement si la valeur est encore celle d'origine (Q66, point 5).
- Exception (tranchée en Q24) : le boot met à jour les informations
  techniques qu'il calcule lui-même (empreinte, chemin du code), jamais les
  réglages owner.
Corrigé le 1er octobre 2026 (Q74) : Q66 a ajouté la section `changes`.

### Q4 — Capsules → SUPPRIMÉES (option A)
- Plus d'objet/table capsule (db_readers, llm_point_readers,
  db_reader_fixed_params, db_reader_fixed_joins à retirer).
- Tout passe par la liaison invocation ↔ tool (llm_point_tools), qui porte :
  - le mode : « contexte injecté » (Serge lit avant l'appel et met le
    résultat dans le prompt) ou « appelable » (le modèle décide) ;
  - les paramètres figés pour cette invocation.
- Un même tool peut être injecté pour une invocation, appelable pour une autre.
- Vaut pour tous les tools (db_read, web_search, memory_search…).
- But final (Julien) : passations entre étapes — le résultat d'une étape
  fournit des paramètres au lancement d'une invocation de l'étape suivante
  → pipelines où la donnée circule.

### Q5 — Lien = passation de données (validé dans l'esprit)
Un lien devient une passation de données entre invocations :
1. ce qui sort de l'amont (table + lignes « prêtes ») ;
2. ce qui est lancé en aval (invocation LLM ou technique) ;
3. mapping champs → paramètres des tools de l'invocation aval ;
4. une ligne transmise = un lancement, une seule fois (idempotent).
Trois origines de paramètres : figé (liaison) / fourni par le lien /
libre (modèle). Déclenchement : bouton MC « passer à la suite » +
interrupteur « passage automatique » + tick runner.
Granularité (étape↔étape ou invocation↔invocation) : voir Q6.

### Q6 — Liens entre invocations (option B)
- Un lien relie deux invocations (LLM ou technique), dans la même étape ou
  entre deux étapes. L'étape = regroupement + coupe-circuit. Le pipeline
  entier est un graphe décrit en base, visible/modifiable dans MC.
- Exigence : belle structure relationnelle (tables propres, pas de JSON
  fourre-tout), compréhensible depuis MC puis, pour le détail, depuis la base.
- Construction progressive : cycle Écoute d'abord, puis étape 1 → étape 2.
- Conséquence : ORDRE/RESTE (serge/mc/proj_etape.py) et l'enchaînement codé
  en dur dans les workers (ex. run_business_cycle) sont remplacés par les liens.

### Q7 — « kind » supprimé
- La notion de kind disparaît (work_items.kind, runtime_flags.kind.*,
  KIND_DEFAUT, dispatch par kind, champ `kind` des invocations techniques).
- L'invocation (LLM ou technique) est la seule unité exécutée : une tâche en
  file = une invocation = un nœud du graphe. Coupe-circuit sur l'invocation
  (et sur l'étape).
- Observation annexe : scheduler.enqueue calcule work_id avec hash() Python
  (randomisé par process) → id non stable ; à vérifier au moment du refacto.

### Q8 — Pages web lues → enregistrées en base (validé)
- Toute page renvoyée par web_search est écrite dans listen_docs (source,
  url, titre, extrait, cycle qui l'a trouvée).
- Elle peut servir de preuve (evidence_ids) et n'est plus re-présentée comme
  nouvelle au cycle suivant.
- Pourquoi ce n'était pas le cas : la doc de Clem définit web_search comme
  « lecture seule, sans écriture dans le canon » ; les preuves étaient
  censées venir de listen_docs, alimentée par la collecte RSS… que rien ne
  lance en production.

### Q9 — Étape 1 (pre_prospection) : 7 invocations à rôle unique (validé)
Deux processus : veille (auto, périodique, sans LLM) + cycle (manuel,
auto plus tard via liens). Graphe :
1. Lire les flux (technique) : flux actifs → pages (listen_docs)
2. Explorer le web (LLM) : guide owner + business connus → pages + flux proposés
3. Trier les pages (LLM rapide) : étiquette par page = enrichit un business
   existant / signal nouveau / bruit
4. Formuler des business A et B (LLM) : pages « signal » → fiches avec
   preuves (plus de recherche web ici)
5. Dédoublonner (technique) → ventures au statut CANDIDATE (voir Q13)
6. Choisir les business à tester (LLM)
7. Refuser les business déjà en POC (technique) → statut POC_SELECTED
Corrigé le 1er octobre 2026 (Q74) : les points 5 et 7 ne sont plus des
invocations mais des règles d'écriture de la table des business (doublons
écartés, statuts permis : Q56). Le cycle compte en plus « Ouvrir un cycle »
et « Rattacher au cycle les pages pas encore triées », sans LLM (Q65).
Liste des flux en base (listen_feeds : url, ajouté par owner/invocation,
actif, compteurs pages ramenées / utiles).
Garde-fous volume (réglages des invocations) : N pages max triées par
cycle ; pages « bruit » oubliées après X jours (preuves conservées) ; flux
désactivé après K cycles de bruit (à la main au lot 7, automatique plus
tard : Q65) ; fréquence de la veille.
L'ancienne chaîne RSS (listen.collect planifié sans flux, listen.cluster
Jaccard, cluster_demand) est supprimée : remplacée par 1 + 3.
Inquiétude Julien : dédoublonnage / veto POC impliquent de stocker ces
événements → rattaché à la question mémoire (Q10).

### Constat mémoire (avant Q10)
- memory_search = index FTS5 (mots), pas d'embeddings (doc §7 « local dès
  jour 1 » faux). rebuild_index n'est appelé nulle part → index vide en
  prod → memory_search ne renvoie rien.
- Tables doc absentes : registre_snapshots, quotas_counters, ledger_entries,
  owner_id.
- Existent : events (journal), lessons/playbooks/pitfalls, summaries,
  episode_archives, consolidation tous les 3 jours (runner).

### Q10 — Mémoire : 3 familles + un outil (validé)
- Remplace les « 5 couches » de docs/MEMORY_ARCHITECTURE.md :
  1. État : ce qui est vrai maintenant (tables métier, modifiables).
  2. Journal : ce qui s'est passé (events, ajout seul, jamais modifié).
     Dédoublonnages, refus POC, etc. y sont écrits avec l'invocation auteur.
  3. Connaissance : leçons, procédures, pièges, résumés (consolidation
     validée par Julien).
  + La recherche (memory_search) n'est pas une mémoire : c'est un tool.
- Principe Julien : simplifier au maximum, n'ajouter de la complexité que
  face à un vrai problème rencontré.
- Question suivante (Q11) : qui a accès à quoi, comment on injecte sans
  saturer le contexte.

### Q11 — Accès mémoire des invocations : 4 règles (validé)
1. Rien par défaut ; tout accès est écrit sur la fiche MC de l'invocation.
2. Trois cercles : ce qu'elle traite → reçu en entier ; ce qui sert à
   comparer → version courte ; le reste → sur demande (tool appelable).
3. Le journal n'est jamais donné d'office ; sur demande, et seulement
   l'historique de l'objet traité (ex. 20 derniers événements du business).
4. Maximum de lignes par information donnée d'office (ex. 50 business ; au-
   delà : les 50 plus récents + message « 140 autres non montrés »). Réglable
   par invocation dans MC ; MC affiche combien de lignes reçues à chaque
   passage. Résumés par objet seulement si un objet dépasse vraiment.

### Q12 — Les cercles sont déduits automatiquement (validé)
- Cercle 1 = ce que le lien entrant apporte.
- Cercle 2 = version courte des tables où l'invocation écrit ou auxquelles
  sa réponse fait référence.
- Cercle 3 = deux outils donnés automatiquement : « historique de l'objet
  traité » et « leçons de cette étape ».
- Seuls réglages : colonnes de la version courte, une fois par table (ex.
  business = numéro + titre ; page = adresse + titre) ; maximum de lignes
  par défaut dans la policy (ex. 50) ; exceptions à la main dans MC.

### Q13 — Un business = une seule ligne dans `ventures` (validé)
- business_candidates et poc_selections supprimées ; colonnes de la fiche
  (titre, description, observations, offre vendable) ajoutées à ventures.
- Nouveau statut POC_SELECTED entre CANDIDATE et SMOKE_READY.
- Table de liens business ↔ page (preuves) conservée.
- Chaque changement de statut est écrit dans le journal (qui, quand,
  pourquoi, cycle).
- « Déjà en POC » = statut ≠ CANDIDATE.
Notes :
- Julien : pas de coexistence business_candidates / poc_selections. Un
  business, un POC, une venture = la même chose à des moments différents →
  une seule table, seul le statut change.
- Constat : la table `ventures` existe déjà avec lifecycle CANDIDATE →
  SMOKE_READY → SMOKE_RUNNING → SMOKE_DONE → FULL_READY → FULL_RUNNING →
  SCALE | PIVOT | EXTEND | KILLED | INVALID_RETRY, et la règle « une seule
  venture active à la fois ».

### Q14 — Places limitées, pas de file d'attente (validé, détails en Q14 bis)
- « Business à retenir pour le prochain POC » ≠ test en cours.
- Deux réglages seulement (policy) :
  - max business en prospection légère en même temps : 3 ;
  - max business en prospection lourde (= « actif », business principal de
    Serge) : 1.
- Pas de file d'attente qui grossit. Quand les places sont prises, tout est
  figé. Les 3 en prospection légère font office de file pour la place en
  prospection lourde.
- La recherche de nouveaux POC (cycle étape 1) ne tourne que s'il reste une
  place libre en prospection légère.

### Q14 bis — Entrée en prospection légère / choix du principal
- Entrée en prospection légère : premier arrivé, premier servi, dès qu'un
  business a été choisi par l'étape 1 (POC_SELECTED). Il occupe sa place
  pendant les étapes 2 et 3.
- Le réglage « business à retenir pour le prochain POC » disparaît : le
  choix prend autant de business que de places libres (non contesté par
  Julien ; confirmé en Q65 : « Choisir » en prend au plus autant qu'il y a de
  places libres).
- Choix de la prospection lourde (étape 4) : déclenché SEULEMENT quand les
  3 business en prospection légère ont tous fini leur test léger ; on
  choisit alors le meilleur des 3.
- Existant : invocation technique `select_pre_venture` (« algo de
  sélection parmi les N smokes ») décrite mais pas codée.

### Q15 — Les 2 non choisis sont mis en pause hors des places (option C)
- Nouveau statut PARKED : libère les places de prospection légère (l'écoute
  repart), reste récupérable si le principal échoue.
- Garder les dates du test léger (début, fin) : sur la fiche de la venture
  (colonnes lisibles dans MC) + dans le journal. Important pour savoir si un
  business parqué a été testé il y a longtemps.

### Q16 — Mesure des tests : grille de points par canal × signal (validé)
- Constat : 9 signaux universels (SEEN, ENGAGED, REPLIED, INTENT, NEGATIVE,
  OPT_OUT, TECH_OK, TECH_FAIL, OTHER) ; U1–U5 calculés dessus, mais seuls
  U3/U4 comparables entre canaux ; argent encaissé absent ; seuls email et
  voix produisent des signaux.
- Décision : chaque signal rapporte des points (0 à 10) selon un barème par
  canal (table en base, une ligne canal × signal, modifiable dans MC ; un
  nouveau canal arrive avec un barème de départ).
- Deux chiffres par business : total de points et points par euro dépensé.
- Les signaux faibles comptent (utile à faible volume).
- Le détail (chaque signal + texte du prospect) reste dans le journal.
- Barème de départ proposé (à reprendre) : email SEEN 0,5 / ENGAGED 1 /
  REPLIED 4 / INTENT 10 / NEGATIVE 1 ; appel ENGAGED 2 / REPLIED 4 /
  INTENT 10 ; pub SEEN 0 / ENGAGED 0,5 / REPLIED 4 / INTENT 10 ; réseau
  SEEN 0,1 / ENGAGED 1 / REPLIED 5 / INTENT 10 ; page web SEEN 0,1 /
  ENGAGED 1 / REPLIED 5 / INTENT 10.

### Q16 bis — Choix du business principal (étape 4) : option B (validé)
- Une invocation LLM reçoit les 3 business (points, points/€, détail des
  signaux et réponses) et propose un choix motivé.
- Julien valide ou change via un ticket Discord où l'on peut discuter.
- Sans réponse sous 48 h, le choix proposé s'applique (proposé dans B).
- Les 2 autres passent PARKED (Q15).

### Q17 — Contacts : une fiche par personne dans un business (validé)
- Table contacts = une ligne par personne dans un business.
- Table à part pour les adresses : une ligne par adresse (canal, valeur,
  active ou non). Rien n'est écrasé ; plusieurs emails possibles.
- Regroupement automatique, dans un même business : une adresse déjà connue
  sur le même canal désigne la même personne (même e-mail, même numéro de
  téléphone, même profil sur le même réseau). Pas de regroupement sur le
  nom, ni sur un même pseudo sur deux réseaux différents. Adresses
  génériques (contact@, info@…) ne regroupent jamais (proposé, non
  contesté).
- Remplace la règle du TODO « deux lieux, deux lignes » et le JSON
  contact_reference_by_canal de la branche Clem.
- Désabonnement : une personne qui se désabonne, par n'importe quel
  business, n'est plus contactée sur aucun canal ni pour aucun business, et
  un ticket prévient Julien et Clem (Q79).
Corrigé le 1er octobre 2026 (Q73) : ce point disait « une ligne par
personne », ce que le choix plus récent d'une fiche par personne dans un
business remplace.
Corrigé le 1er octobre 2026 (Q75) : le regroupement suit le code, plus
récent (27 septembre, contre le 26 pour cette entrée), et le désabonnement
n'est plus « global à la personne ».
Corrigé le 7 octobre 2026 (Q79) : le désabonnement est de nouveau valable
pour tous les business et tous les canaux, avec un ticket ; ce point disait
« propre à la fiche, donc au business concerné ».

### Q18 — Organisation de la doc (validé)
- README court (Serge, chaîne en 8 étapes, où lire la suite).
- docs/PIPELINE.md : objets (étape, invocation, tool, lien, canal), places
  3 + 1, statuts d'une venture, grille de points.
- docs/etapes/1-pre-prospection.md … 8-caisse.md : entrée, invocations dans
  l'ordre, sortie, ce qui n'est pas construit.
- docs/MEMOIRE.md : 3 familles, 3 cercles, règles d'accès.
- docs/MISSION_CONTROL.md : écrans et boutons.
- docs/DB.md : tables, migrations, règle « insérer sans écraser ».
- docs/CHARTE.md : écrite AVEC Julien (voir Q19 à Q24), point de départ
  = skill Ponytail.
- docs/installation/*.md : tutos actuels regroupés.
- Nettoyage maximal autorisé : supprimer tout fichier zombie, écrit « à
  l'arrache », en pseudo-jargon, ou contradictoire avec ces décisions
  (MC_BUILD_PROMPT.md, ETAT_REPRISE…, LEGACY_REUSE.md, docs/slides/…).
- Rappel style : pas de jargon LLM compressé, des exemples, intelligible.

### Q19–Q20 — Charte : base Ponytail (validé)
- Source : https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md
- La charte part de l'échelle Ponytail : (1) doit-ce exister ? (2) existe
  déjà dans le dépôt ? (3) bibliothèque standard ? (4) outil déjà présent
  (ex. contrainte SQLite) ? (5) dépendance déjà installée ? (6) une ligne ?
  (7) sinon le minimum de code qui marche.
- Comprendre avant d'écrire ; bug corrigé à la cause (fonction partagée).
- Pas d'abstraction inutile, pas de code « pour plus tard », supprimer
  plutôt qu'ajouter, simple plutôt que malin, peu de fichiers, raccourci
  assumé = commentaire qui dit sa limite.
- Jamais simplifié : validation des entrées externes, gestion d'erreur
  anti-perte de données, sécurité.
- Tests : on garde « passant + refusé » pour tout ce qui touche le monde
  extérieur. Julien valorise AVANT TOUT les tests end-to-end, pas des
  centaines de tests unitaires qui ne testent rien.

### Q21 — Trois sortes de tests (validé)
Constat : 840 tests / 160 fichiers ; ~15 fichiers navigateur MC.
1. Test de scénario par étape (le cœur) : vrai point d'entrée, vraie base
   SQLite, vraies invocations et liens ; faux LLM et faux monde extérieur
   (réponses écrites à l'avance) ; on vérifie l'état final en base + journal.
   Ex. étape 1 : 5 pages + 1 place libre → « lancer le cycle » → 1 venture
   POC_SELECTED avec preuves, doublons écartés, décisions au journal.
2. Tests navigateur MC (Playwright) : gardés.
3. Test réel avec vraie clé LLM : avant push seulement, jamais en CI.
Tests de fonction isolée : seulement pour logique piégeuse (grille de
points, regroupement contacts, refus 4e venture en prospection légère…).
Les autres sont supprimés dès qu'un scénario couvre le même comportement.

### Q22 — Langue (validé : option A)
- Noms en anglais : fonctions, variables, modules, tables, colonnes.
  (ex. « invocation LLM » → `llm_invocation` dans le code.)
- Textes en français : docstrings, commentaires, doc, messages, MC.
- Renommage fait au fil du nettoyage, pas en une seule fois.

### Q23 — Règles de travail (validé)
- Garder : pas de fichier Python > 500 lignes (test automatique).
- Remplacer « < 300 lignes par changement » par : un changement fait une
  seule chose, et sa description le dit en une phrase.
- Remplacer la revue « P1–P5 » des messages de commit par une description
  de PR en français clair, 4 questions : qu'est-ce qui change vu de
  l'extérieur ? pourquoi ? comment on vérifie (quel test de scénario) ?
  qu'est-ce qui a été supprimé ?

### Q24 — Empreintes (SHA) : calculées au démarrage, sans verrou (option B)
- Supprimer serge/catalogue_lock.py, serge/code_lock.py, les SHA recopiés
  dans les seeds (outils.py, canaux.py…), tests test_catalogue_sha /
  test_code_lock.
- Au boot, Serge calcule l'empreinte des fichiers de chaque objet et
  l'enregistre en base ; MC peut afficher « code modifié depuis le … ».
- Conséquence (résout la question laissée en Q3) : le boot MET À JOUR les
  métadonnées techniques calculées (empreinte, chemin du code) des objets
  existants ; il ne touche jamais aux réglages owner (prompt, enabled,
  tier, tools…).

### Q25 — « Demander une nouvelle capacité » = 3e tool automatique (validé)
- Chaque invocation reçoit automatiquement : historique de l'objet traité,
  leçons de cette étape, demander une nouvelle capacité (ticket REQUESTED,
  pas de doublon si besoin déjà ouvert). Retirable à la main dans MC.
- Fait à la fusion avec main (PR #27) : `demande_capacite` est réintégré
  dans ce mécanisme (Clem avait supprimé le « offert partout »).

### Q26 — Arrêt d'urgence voix : fichier KILL_SWITCH supprimé (validé)
- Supprimer la route /owner/api/voice/kill et toute lecture de fichiers
  KILL_SWITCH (serge/voice/policy.py, serge/mc/proj_voice.py,
  serge/mc/policy_actions.py), y compris le vieux chemin orchestrator/runtime.
- Couper la voix = couper l'invocation qui passe les appels (coupe-circuit
  commun, en base, depuis MC).

### Q27 — Longueur des réponses LLM : aucune limite, jamais (validé)
- Pas de max_tokens, nulle part, voix comprise (on garde la suppression
  faite par Clem). Pas de réglage de longueur à ajouter.

### Q28 — Forme du TODO (validé)
- TODO actuel = charabia écrit par Grok ; à réécrire entièrement, TRÈS
  clair et intelligible pour un humain (priorité absolue de Julien).
- Rangé par lot et par étape 1 à 8, avec une section « Pour tout Serge ».
- Tout ce qui est fait est retiré (historique = git).
- Chaque élément : une case à cocher, un titre en gras, puis un paragraphe
  descriptif (demande de Clem, voir « Principes transverses »).
  Corrigé le 1er octobre 2026 (Q74) : ce point disait
  « Quoi / Pourquoi / Dépend de ».
- Ajouter le chantier de refonte issu de ces questions, en tête (même si on
  le fera ensemble ensuite).
- Section « En attente d'une décision d'architecture » supprimée.

### Q29 — Champ `requested` supprimé (validé)
- Retirer `requested` de toutes les réponses d'invocation, des prompts, des
  validateurs (jsonio), de la consolidation (requested_text) et de MC
  (compteur requested_pending → compter les tickets REQUESTED).
- Seul mécanisme pour signaler un manque : le tool « Demander une nouvelle
  capacité ».


### Notes de discussion (Q4)
- Julien aime l'idée de capsule : invocation LLM dotée de tools dont une
  partie des paramètres est figée, une partie variable → invocations
  paramétriques. Ouvert à une meilleure archi inspirée de l'agentique moderne.
- Liens : pour Julien = simples liens entre étapes, sans spécification de la
  donnée qui circule. Constat code : etape_liens = arête + libellé + `debit`
  (nom d'une table dont MC compte les lignes pour l'onglet En direct). Aucun
  mécanisme de passage de données (les « ponts » du TODO ne sont pas codés).
  → question posée ensuite, et tranchée en Q5 et Q6 : que doit devenir le lien.

### Q30 — Méthode (validé)
- Pas de correction géante d'un seul coup. D'abord toutes les questions
  (cohérence d'ensemble), puis des petits lots relisibles.
- Ce fichier est poussé sur `Clem` pour ne pas perdre les réponses.

### Q31 — Construire quelque chose dès le POC (validé)
- Le POC ne teste pas seulement un message : l'étape 2 construit déjà un
  livrable, pour pouvoir proposer des essais aux futurs prospects.
- Construction « complète » toujours en étape 5 pour le business principal.
- Avant de concevoir l'étape 2 : dresser la liste la plus complète possible
  des types de business que Serge peut lancer avec ses moyens (email,
  téléphone, carte bancaire, Stripe, comptes web, Internet permanent,
  bacs à sable de code, stockage illimité) → Q32.

### Q32 — Familles de business et limites (validé)
- Liste des 11 familles acceptée : produits numériques, petits logiciels en
  ligne, services faits par Serge, automatisation sur mesure, téléphone/SMS
  pour les autres, veille et rapports, médias et audience, mise en
  relation, formation, commerce sans stock, prospection pour les autres.
- La seule vraie limite de Serge : la LÉGALITÉ. Tout le reste est ouvert.
- Conseil financier / juridique : autorisé dans le cadre légal (les LLM
  sont bons là-dessus). Attention aux activités réservées par la loi (voir
  Q33).
- Crypto-monnaies : évité pour l'instant (nid à arnaques), porte pas fermée.
- Tromperie interdite (faux avis, fausse urgence, IA qui se fait passer pour
  un humain…).
- Présence physique : possible via des sous-traitants humains (ex.
  plateforme Rent a Human citée par Julien) si Serge juge ça rentable.

### Q33 — Légalité : pas d'invocation ni de filtre dédiés (validé)
- Pas d'invocation « vérifier la légalité », pas de filtre déterministe.
- On écrit simplement dans le prompt des invocations qui créent les business
  (formuler, choisir) que le business doit être légal.
- Les modèles sont déjà très frileux : au contraire, leurs prompts doivent
  les encourager à ne pas s'arrêter sur des considérations morales qui ne
  sont pas contraires à la loi.

### Q34 — Étape 2 : plan complet, challenge, validation Discord (validé)
- Validation par Julien sur Discord, avec discussion possible (option B :
  rien ne part vers des prospects sans son accord ; défaut 48 h proposé).
- L'invocation « Concevoir le POC » rédige : hypothèse, cible, canaux,
  nombre de prospects, durée, prix indicatif, description du livrable
  d'essai ET un plan de A à Z : de quoi le produit a besoin, ce que le
  builder doit faire, pourquoi, comment ça va marcher.
- Une invocation distincte « Challenger le POC » critique ce plan :
  faisabilité technique, limites du produit, réalisme commercial.
  Exemple de Julien : un POC qui commence par « se connecter à l'ERP / au
  CRM d'une grande entreprise contactée par e-mail » doit être signalé
  comme irréaliste.
- Construction par la même mécanique que l'étape 5 (construire, relire,
  corriger, 3 essais max). Mise en ligne, puis création de la campagne.
- Ordre ticket / construction : voir Q35.

### Q35 — Étape 2 : ordre et boucle de critique (validé)
1. Concevoir le POC (plan de A à Z).
2. Challenger le POC : chaque remarque est de l'un de ces deux types
   seulement (jamais « bloquant ») :
   - « à corriger » : le plan est mal fait mais faisable avec les capacités
     actuelles de Serge ;
   - « nouvelle capacité nécessaire » : il manque un outil ou autre chose
     (via le tool « Demander une nouvelle capacité »).
3. La conception reprend son plan ; 3 tours maximum. Les prompts forcent à
   ATTERRIR sur un plan qui fonctionne.
4. Ticket Discord à Julien AVANT construction : plan final, critique, ce
   qui a été corrigé, ce qui reste. Julien valide, refuse ou discute.
   Si après 3 tours il reste « nouvelle capacité nécessaire », le ticket
   arrive dans cet état : c'est à Julien de créer la capacité.
5. Construction + mise en ligne après accord.
6. Lancement du test automatique + ticket d'information avec le lien.

### Q36 — Étape 3 : trouver les prospects (validé)
- Invocation « Trouver des prospects » (LLM + recherche web) : cherche ET
  qualifie en une seule invocation. L'invocation « qualifier un prospect »
  (qualify_prospect) est supprimée.
- À travailler : trouver des prospects PERTINENTS et des adresses qui ne
  rebondissent pas (pas d'adresses de contact génériques pourries).
  Définir précisément sa sortie (champs, source de chaque adresse…).
- Cette étape n'existe que pour les canaux qui ont besoin d'une liste de
  personnes (email, appel, LinkedIn peut-être). Une pub n'a pas besoin de
  prospects mais d'un PROFIL de cible.
- Emails et appels à froid : seulement vers des professionnels (règle
  légale française ; les particuliers exigent un accord préalable).
- Programmation des envois et relances : à discuter dans une question
  dédiée (Q37).

### Q37 — Envois et relances : système réactif (validé)
- Priorité absolue : ne jamais relancer quelqu'un qui a déjà répondu (bug
  déjà vécu dans une version précédente de Serge).
1. Un fil de discussion unique par prospect, tous canaux : envois
   (touches, avec leur TEXTE, à ajouter) + réponses (inbound_events), par
   date. Visible sur la fiche prospect dans MC ; lu par les invocations qui
   rédigent relances et réponses.
2. Rattachement de chaque réponse au prospect : par adresse (email,
   téléphone) et, pour l'email, par le fil de messages (réponse depuis
   l'adresse d'un collègue). Non rattachée → file d'examen visible dans MC,
   jamais ignorée.
3. Une relance ne part que si le dernier événement du fil est un envoi de
   Serge sans réponse depuis ; vérifié AU MOMENT DE L'ENVOI. Sinon annulée
   et écrite au journal.
4. Jamais de relance à l'aveugle : si les réponses d'un canal n'ont pas été
   relevées récemment (ex. boîte mail non lue depuis > 1 h), aucune relance
   sur ce canal ; alerte dans MC.
5. Rythme (délais, nombre max de messages) écrit dans le plan du POC et
   validé par Julien à l'étape 2.
Le séquenceur fixe (supprimé par Clem, jamais branché) n'est pas recréé.

### Q38 — Circuit des réponses, priorités, délais (validé)
- Une seule invocation « Traiter une réponse » : lit le fil complet du
  prospect, rend (1) le signal dans une liste fermée (intéressé, question,
  objection, rendez-vous, refus, désinscription, absence, hors sujet ; Q79),
  (2) la réponse à envoyer ou
  « pas de réponse », (3) « besoin de Julien : oui/non » + raison.
  Remplace classify_reply, reply_intent, review_other, extract_meeting.
- Envoi automatique. Les tickets qui font attendre une réponse (« besoin de
  Julien », brouillon à valider, réponse de Julien dans le ticket) viennent
  au lot « Julien dans la conversation », après le lot 8 (Q79).
  Corrigé le 7 octobre 2026 (Q79) : ce point disait « Envoi automatique
  sauf « besoin de Julien » ou refus d'un garde-fou → ticket Discord avec
  le brouillon (discussion possible). »
- Circuit transverse (étapes 3 et 6), avec son propre coupe-circuit.
- Priorité par invocation, réglable dans MC. Départ : 100 traiter une
  réponse / désinscription ; 80 relever boîtes et canaux entrants ; 50
  envois et relances ; 30 construction ; 10 écoute, veille, consolidation.
- Relève des réponses toutes les 5 min (invocation technique programmée).
- Délai de réponse : entre 5 et 20 minutes après réception (tirage au
  hasard), à toute heure et tous les jours : Serge est une IA qui travaille
  24 heures sur 24. Les valeurs se règlent canal par canal dans Mission
  Control, et peuvent valoir 0 (réponse immédiate, pour les tests) (Q79).
  Corrigé le 1er octobre 2026 (Q74) : ce point disait
  « valeurs dans la policy ».
  Corrigé le 7 octobre 2026 (Q79) : ce point disait « en heures ouvrées
  (ex. 8 h–20 h, lundi–samedi) [...] ; hors heures : le lendemain entre
  8 h et 9 h ».
- Bugs constatés (corrigés au lot 2, Q49) :
  1. email.poll n'est programmé par personne → la boîte n'est jamais
     relevée automatiquement.
  2. scheduler.next_ready ne prend que les tâches liées à une venture
     « schedulable » → une tâche sans venture (cycle d'écoute lancé depuis
     MC) ne s'exécute jamais (vérifié par script).

### Q39 — Mise en ligne des livrables (validé : option C)
- Par défaut sur le serveur de Serge (VPS), via Caddy déjà en place, avec
  le nom de domaine que Serge possède déjà sur le VPS.
- Plateforme externe seulement quand le type de business l'exige (Chrome
  Web Store pour une extension, Telegram pour un bot…).
- POC : sous-domaine du domaine de Serge. Business principal (étape 5) :
  nom de domaine dédié acheté avec la carte.
- Le STOCKAGE (logiciels, documents, fichiers) est une question à part (Q40).

### Q40 — Stockage des fichiers (validé, sans sauvegarde externe)
- Fichiers sur le disque du VPS, un seul dossier rangé par venture /
  livrable / version (ex. files/devis-artisan/generateur/v2/). Une version
  publiée n'est jamais modifiée : une correction crée la version suivante.
- La base garde la fiche de chaque fichier (table artifacts) : venture,
  type, version, chemin, empreinte, taille, date, adresse publique si en
  ligne. MC les liste par venture.
- Pas de sauvegarde automatique hors du VPS pour le moment (décision de
  Julien, malgré l'absence totale de sauvegarde de serge.db aujourd'hui).

### Q41 — Étape 5 : construire le business principal (validé)
1. Concevoir le produit (LLM) : part du livrable d'essai, du plan du POC et
   des retours des prospects ; plan du vrai produit, prix définitif, page
   de vente.
2. Challenger le produit : même boucle qu'à l'étape 2 (3 tours, « à
   corriger » / « nouvelle capacité nécessaire »).
3. Ticket Discord à Julien avant construction (valide notamment le prix).
4. Construire avec le couple builder / reviewer existant (build_artifact +
   review_build, 3 passages max), réponses alignées : « bon » / « à
   corriger » / « nouvelle capacité nécessaire ». Même mécanique aux
   étapes 2 et 5.
5. Mise en ligne sur un nom de domaine dédié.
6. Encaissement : produit + prix dans Stripe, paiement test de 1 € fait et
   remboursé automatiquement.
7. Ticket d'information, puis étape 6.
Versions suivantes : publication automatique si la relecture est bonne,
ticket d'information seulement.

### Q42 — Étape 6 : vie du business principal (validé)
- Prospection lourde en continu avec les briques de l'étape 3 (trouver,
  envoyer, relancer, répondre), plus de volume, canaux en plus (pub…).
- Une fois par semaine, une seule invocation « Faire le point sur le
  business principal » : lit points, points/€, argent encaissé, réponses ;
  propose continuer / accélérer (+50 % max ou un canal de plus) / pivoter
  (un seul élément : cible, prix, offre ou canal) / arrêter.
- Continuer et accélérer : automatiques + ticket d'information. Pivoter et
  arrêter : ticket Discord validé par Julien.
- Remplace plan_scale, options_pivot, judge_allocator.
- Retours clients / demandes des prospects → nouvelle version : voir Q43.

### Q43 — Retours clients → nouvelle version (validé)
1. « Traiter une réponse » rend aussi, s'il y en a une, une demande sur le
   produit : bug / insatisfaction / demande. Chaque demande → une ligne
   dans une nouvelle table product_requests (business, personne, message
   d'origine, type, texte, état : nouvelle / retenue / livrée dans la
   version N / refusée + raison).
2. Urgent (bug touchant un client qui a payé) : correction lancée tout de
   suite, priorité haute. Le reste : invocation hebdomadaire « Préparer la
   prochaine version » (regroupe les doublons, choisit, explique, refuse
   avec raison).
3. Construction avec le couple builder / reviewer habituel.
4. Corrections et petites améliorations : publication automatique + ticket
   d'information. Nouvelle fonctionnalité importante, changement de prix
   ou nouvelle capacité nécessaire : ticket Discord validé par Julien.
5. Après publication, message aux personnes dont la demande est livrée
   (via le fil du prospect, mêmes règles que les relances).
Le point hebdomadaire (Q42) lit aussi ces demandes.

### Q44–Q45 — Maintenance, fermeture, suivi technique (validé)
- Fin de la prospection lourde ≠ fin du business. Nouveaux statuts :
  - MAINTENANCE : plus aucun nouveau prospect contacté ; on livre ce qui
    est vendu, répond aux clients, corrige (product_requests), encaisse les
    abonnements, relance les impayés ; un client qui revient seul est servi.
    Entrée : quotas de prospection lourde épuisés, ou « arrêter » validé
    alors que le business a des clients (sans client → KILLED).
  - CLOSED : automatique quand zéro livraison due, zéro abonnement actif,
    zéro demande client ouverte, aucun message client depuis 30 jours
    (réglable) ; archivé + leçon ; ticket d'information.
- L'entrée en MAINTENANCE libère la place de prospection lourde.
  Remplacement : choix normal (Q16 bis) si les 3 tests légers sont finis,
  en comparant aussi les PARKED testés il y a moins de 60 jours (réglable) ;
  sinon la place reste vide jusqu'à la fin des tests. Un PARKED de plus de
  60 jours repasse CANDIDATE.
- Plusieurs business peuvent être en MAINTENANCE en même temps.
- Technique :
  1. subscriptions : chaque abonnement est rattaché à son vrai business,
     via l'identifiant inscrit dans Stripe (lu sur le prix, Q76), et non à
     un faux business ; les colonnes ajoutées à la volée sont une vraie
     migration (v23).
     Corrigé le 1er octobre 2026 (Q76) : ce point décrivait l'état d'avant le
     lot 5 (tout rattaché à 'serge-collect-stripe', en dur dans
     serge/collect/abonnements.py).
  2. Nouvelle table deliveries (business, client, paiement, quoi livrer,
     date promise, état à faire / en cours / livrée / problème, date de
     livraison, fichier livré). Créée automatiquement à chaque paiement d'un
     produit non instantané ; produit instantané = livré tout de suite.
     Livraison en retard → MC + correction en priorité haute.
  3. product_requests (Q43).

### Q46 — Étape 7 : consolidation, leçons, contexte Serge (validé)
- Consolidation gardée telle quelle (tous les 3 jours, ticket Mémoire,
  acceptée après 48 h sans réponse) + leçon obligatoire à chaque KILLED
  ou CLOSED.
- Chaque leçon est rattachée au niveau le plus précis : une invocation
  (grâce au journal qui sait quelle invocation a produit quoi), sinon une
  étape, sinon tout Serge.
- Une invocation reçoit d'office SES leçons (les plus fiables d'abord,
  maximum de lignes habituel) ; les leçons de son étape et globales sur
  demande (tool automatique « leçons »).
- SERGE.md et l'invocation edit_serge_md sont supprimés.
- Nouveau bloc « Qui est Serge et quelle est ta place », généré depuis la
  base à chaque appel : présentation de Serge (texte en base, modifiable
  dans MC) + la chaîne des 8 étapes (fiches des étapes) + la place de
  l'invocation (son étape, qui est avant elle, qui est après, via les
  liens). Donné aux invocations de niveau moyen et intelligent, pas aux
  rapides ; case à cocher sur la fiche de l'invocation.

### Q47 — Étape 8 : la caisse (validé)
1. Tout encaissement passe par Stripe (liens de paiement, pages de
   paiement, abonnements). Stripe émet les factures conformes (numérotation,
   mentions) avec l'identité de Serge en base. Serge ne fabrique pas ses
   propres factures.
2. Relances d'impayés programmées (J+7 polie, J+14 ferme, puis arrêt +
   ticket), via le fil du client, mêmes règles que Q37 (pas de relance si
   le client a répondu). Aujourd'hui serge/collect/dunning.py n'est jamais
   programmé.
3. Remboursements : sous un seuil (ex. 50 €, policy) automatiques + ticket
   d'information ; au-dessus, ticket Discord.
4. Invocation « Proposer un prix » (draft_price) supprimée : prix indicatif
   dans le plan du POC (étape 2), définitif validé par Julien (étape 5),
   modifié seulement par un pivot validé (étape 6).
5. MC montre par business : encaissé, dû, en retard.

### Q48 — Web (validé)
- Gratuit d'abord : pas d'API payante qui livre une donnée accessible
  gratuitement ; pas de nouvelle clé pour rien. API gratuite = OK.
- Chercher : SearXNG hébergé sur le VPS (méta-moteur open source, sans clé).
- Trois niveaux : (1) requête HTTP simple ; (2) vrai navigateur sur le VPS
  piloté par Playwright avec Google Chrome installé (pas seulement le
  Chromium de test), une session par compte ; (3) Browserbase (clé déjà là)
  seulement si un site bloque le niveau 2, avec l'identité d'agent vérifiée.
  Chaque montée de niveau est écrite au journal.
- Invocation « Agent web » (Browser Use, open source) : reçoit une mission
  (créer un compte, publier, réserver un humain…). Création de compte :
  identité de Serge, codes lus dans sa boîte mail / SMS, captcha résolu par
  un humain (ticket + écran en direct dans MC), compte enregistré dans
  accounts_standing.
- Serge assume d'être un agent IA partout où ça suffit.
- Connecteurs : quand une API gratuite existe, l'invocation « Construire un
  connecteur » lit la doc, crée le compte et la clé via l'agent web, écrit
  et teste le code en bac à sable, le déclare comme tool. Julien valide par
  ticket avant activation (code exécuté sur le VPS avec les secrets).
- LinkedIn : utilisé via le compte de Serge, volume modéré, AVEC validation
  humaine de chaque message et publication. Claude ne construit pas de
  mécanisme destiné à échapper à la détection de robots (déguisement,
  rotation d'IP, empreinte falsifiée) ; Julien fera ses propres recherches.
- Selenium vs Playwright : même détectabilité par défaut ; on garde
  Playwright (déjà installé) avec Chrome.

### Q49 — Ordre des lots (validé, lots 1 à 4 en une passe)
1. Fusionner main dans Clem. 2. Corriger les deux bugs graves. 3. Supprimer
code mort et doublons. 4. Nouvelle doc + TODO + charte. Puis 5. Données,
6. Le runner et le pipeline en base (invocations, liens, déclencheurs),
7. Étape 1, 8. Conversations, 9. Grille de points, 10. Étapes 2 et 5,
11. Étapes 3, 4, 6, 7, 8, 12. Web, 13. L'éditeur sans code dans MC.
Corrigé le 1er octobre 2026 (Q71) : le lot 6 devient « le runner et le
pipeline en base » et un lot 13 s'ajoute, comme le dit Q55.

---

## Suite de la revue, avec Clem (septembre 2026)

Clem a repris la conversation après le lot 5. Les décisions suivantes ont
été prises avec lui, puis validées avec Julien pour la Q54.

### Q50 — Répondre aux prospects et aux clients (validé)
Les messages des prospects et des clients sont imprévisibles : questions
sur le produit, demandes de changement, questions de délais, sujets sans
rapport. On ne peut pas tout prévoir, mais on calibre les cas classiques.
- Chaque business a une fiche produit détaillée, en base : ce que fait le
  produit et pour qui, ce qu'il ne fait pas, le prix, les délais habituels
  de livraison, comment on l'utilise, et une liste de questions fréquentes
  avec leurs réponses. Elle est écrite par l'invocation qui conçoit le
  produit (étape 2 pour le POC, étape 5 pour le vrai produit) et validée
  par Julien avec le plan (il y en aura peu). Elle est mise à jour à chaque
  nouvelle version du produit.
- On ne fait pas appel à l'invocation qui a construit le produit : elle ne
  garde aucun souvenir d'un appel à l'autre. Tout ce qu'il faut savoir est
  dans la fiche.
- « Traiter une réponse » reçoit en entier, dans ce qu'elle traite, la
  fiche du business, la fiche produit, la fiche du prospect et tout son
  fil de discussion. Les tables doivent être assez bien écrites pour
  qu'elle puisse répondre aux questions.
- Questions de délais : le LLM répond seul avec la fiche produit, avec des
  consignes de prudence dans son prompt. Il ne promet jamais une date ou un
  délai absent de la fiche, ni une fonctionnalité qui n'existe pas (elle
  devient une demande client). En cas de doute, il répond sans s'engager
  et ouvre un ticket.
- Quand Julien répond à un ticket sur une question produit, la réponse est
  ajoutée aux questions fréquentes de la fiche : la fois suivante, Serge
  répond seul.
- Un ticket de conversation doit être compréhensible par quelqu'un qui ne
  suit pas Serge. Il contient toujours, dans cet ordre : le business en
  trois lignes, le prospect, le fil de la conversation, le brouillon de
  Serge, pourquoi Serge a besoin d'aide et la question précise, et un lien
  vers la fiche du prospect dans MC.

### Q51 — Le runner : une tâche après l'autre, deux files (validé)
Constat : le runner est relancé une minute après la fin du passage
précédent, traite jusqu'à 10 tâches, et n'enregistre en base qu'à la fin
du passage. Ce n'était pas une décision de Julien. Conséquences : un
plantage à la 7e tâche annule tout ce qui a été écrit depuis le début, y
compris la note « e-mail envoyé » alors que l'e-mail est parti (risque de
double envoi) ; MC ne peut pas écrire pendant un passage (jusqu'à
15 minutes) ; deux files en parallèle se bloqueraient.
- L'idée de Julien d'une file de priorité où s'ajoutent les invocations
  déclenchées est gardée.
- Chaque file est un programme qui tourne en continu : il prend la tâche
  prête la plus prioritaire, l'exécute, enregistre en base, puis prend la
  suivante. Plus d'attente d'une minute, plus de limite de 10.
- Deux files en parallèle : la file des conversations (relever les
  boîtes, traiter une réponse, envoyer, relancer : des tâches courtes) et
  la file des travaux (écoute du web, conception, construction, point
  hebdomadaire : des tâches longues). Une construction de 40 minutes ne
  retarde plus la réponse à un prospect. Deux invocations en même temps ne
  posent pas de problème : la machine ne fait qu'attendre la réponse du
  fournisseur du LLM.
- Une tâche qui agit à l'extérieur (envoyer un e-mail, rembourser)
  enregistre « en cours » avant d'agir, puis « fait » après : même un
  plantage au mauvais moment ne provoque jamais de double action.
- Priorité : le runner a été la première chose faite au lot 6, à cause du
  risque de double envoi. La protection « en cours / fait » d'une tâche qui
  agit à l'extérieur vient avec la première capacité qui agit hors de Serge
  (lot 8).

### Q52 — Délais de réponse par canal (validé)
Le délai avant de répondre à un prospect se règle canal par canal dans
MC : délai minimum et délai maximum, à toute heure (pas d'heures ni de
jours ouvrés, Q79). Exemple : e-mail entre 5 et 20 minutes, LinkedIn entre
1 et 4 heures, SMS tout de suite. Un délai à 0 répond tout de suite.
Corrigé le 7 octobre 2026 (Q79) : ce point disait « délai minimum, délai
maximum, heures et jours ouvrés », sur la fiche du canal.

### Q53 — L'agent vocal (validé)
Un appel ne passe pas par la file : le standard téléphonique décroche et
confie l'appel à un programme vocal séparé, qui tourne en parallèle du
reste. Il n'y a rien à interrompre. Ce qui change :
- Au décrochage, le numéro est cherché en base. S'il est connu, l'agent
  reçoit dans ce qu'il traite la fiche du prospect, son fil, la fiche du
  business et la fiche produit.
- S'il est inconnu, l'agent dit « Bonjour, je suis Serge, en quoi puis-je
  vous aider ? », demande à qui il parle, et cherche la fiche avec un tool
  (nom, entreprise, e-mail, numéro).
- Si l'appelant propose quelque chose à Serge (partenariat, offre),
  l'agent répond poliment qu'il ne peut pas traiter ce genre de demande
  pour l'instant. Le résumé est quand même écrit au journal.
- Une personne reconnue seulement parce qu'elle a dit son nom (pas par son
  numéro) : l'agent se sert de sa fiche pour comprendre, mais ne répète
  aucune information sensible (montants, adresses, propos d'un collègue).
- Après l'appel, le résumé entre dans le fil du prospect, et « Traiter une
  réponse » est lancée s'il y a une suite à donner.
- Aujourd'hui, l'agent vocal a le même prompt fixe pour tous les appels et
  aucun tool.

### Q54 — Le pipeline entièrement en base : le code n'est qu'un interpréteur (validé par Clem et Julien)
- L'ordre des invocations et tous leurs paramètres sont uniquement en
  base. Jamais un paramètre en dur dans le code. Le code lit la base et
  crée chaque invocation, une tâche après l'autre, dans l'ordre donné par
  le runner.
- Paramètres en base pour chaque invocation LLM : son rôle, le modèle
  appelé, le prompt, ce qu'elle reçoit dès le départ, les tools qu'elle
  peut appeler et avec quels paramètres figés, le format de sa réponse et
  où cette réponse est écrite, sa priorité, sa file, ses liens avec les
  invocations d'avant et d'après, et les déclencheurs qui la lancent.
- Plus tard, les accès à un bac à sable (pour tester, concevoir un
  produit, naviguer sur le web, créer des comptes) seront eux aussi
  déclarés en base.
- Le code garde les briques de base : les tools, les traitements sans LLM
  (exemple : écarter les doublons) et les écritures autorisées dans chaque
  table. La base dit lesquelles utiliser, dans quel ordre, avec quels
  paramètres. Exemple déjà existant : la liste des tables et colonnes
  qu'un tool de lecture a le droit de lire est en base.
- Conséquence sur Q3 : les réglages du code ne servent qu'à remplir une
  nouvelle instance. Une invocation ou un lien créé ou modifié dans MC
  n'est jamais supprimé au démarrage. Seule une brique de base retirée du
  code disparaît ; les invocations qui s'en servaient sont signalées dans
  MC.
- Validé ensuite par Clem : une invocation supprimée dans MC ne revient
  pas au démarrage suivant. La base garde la trace de la suppression et
  reste la source de vérité, pour que le code et la base ne se
  désynchronisent pas.
- Conception des tables : [`LOT6_CONCEPTION.md`](LOT6_CONCEPTION.md).
- But à terme (lot 13) : un éditeur sans code dans MC, pour
  modifier en direct le pipeline : le nombre d'invocations, leur ordre,
  leur rôle, leur modèle, ce qu'elles voient.

### Q55 — Nouvel ordre des lots (validé)
Lots 1 à 5 faits. Ensuite :
6. Le runner et le pipeline en base : d'abord le runner (une tâche après
   l'autre, un enregistrement après chaque tâche, deux files), puis les
   invocations, les liens et les déclencheurs entièrement en base (Q54).
   Clem et Julien veulent l'attaquer ensemble.
7. Étape 1.
8. Conversations (fil, traiter une réponse, fiche produit, tickets, délais
   par canal, agent vocal).
9. Grille de points.
10. Étapes 2 et 5.
11. Étapes 3, 4, 6, 7, 8.
12. Web.
13. L'éditeur sans code dans MC.

### Q56 — Jamais de code propre à une invocation, même pour écrire (validé par Clem)
- On doit pouvoir créer une invocation de toutes pièces depuis MC, à terme,
  donc depuis la base. Le code est un interpréteur très paramétrique, sans
  rien de scripté pour une invocation particulière.
- L'écriture en base est générique elle aussi : un seul code d'écriture,
  piloté par des règles en base (quelle table, quelle opération, quelle
  colonne reçoit quel champ de la réponse). Ce n'est jamais le modèle qui
  choisit où écrire : la destination est fixée dans les réglages de
  l'invocation.
- Les protections deviennent des règles en base : tables et colonnes
  autorisées, changements de statut permis, repérage des doublons, champs
  obligatoires, validation par Julien avant d'agir. Chaque refus est écrit
  au journal automatiquement.
- Le code est rangé par capacité, jamais par invocation : lire la base,
  écrire la base, appeler un modèle, chercher sur le web, agir dans un bac
  à sable, appeler une API décrite en base, envoyer ou relever sur un
  canal, ouvrir un ticket. Test simple : le nom d'une invocation ne doit
  jamais apparaître dans le code, sauf dans le fichier qui remplit une
  nouvelle instance.
- Vaut pour tous les lots futurs : le bac à sable, l'agent web, les
  connecteurs vers des services, les canaux, l'agent vocal, les tickets.
  Chacun est une capacité générique réglée en base. Exemple : un connecteur
  vers un service n'est pas du code écrit par Serge, mais la description du
  service en base (adresse, secret à utiliser, points d'entrée), exécutée
  par une seule capacité « appeler une API ».

### Q57 — Réponses de Clem sur la conception du lot 6 (validé)
1. Une seule table pour toutes les invocations, avec ou sans LLM.
2. Le modèle se choisit seulement par niveau (rapide, moyen,
   intelligent), jamais un modèle précis par invocation.
3. Le pipeline de départ est dans `config/pipeline.yaml`. Il remplit la
   base à l'initialisation ; ensuite, la base est la seule source de
   vérité.
4. L'historique des réglages attendra : le journal suffit pour commencer.
   Noté à la fin du TODO.
5. Vocabulaire validé : une « capacité » est un savoir-faire général du
   code ; un « outil » est une capacité réglée en base qu'on donne à une
   invocation.
6. Doublons : les méthodes « identique » et « mots en commun » suffisent
   pour une première version. C'est un filet de sécurité : l'invocation
   reçoit d'office la liste courte de ce qui existe, et son prompt lui
   demande de ne pas le reproposer. Un doublon écarté est visible au
   journal.

### Q58 — Comment mener le lot 6 (validé par Clem)
1. Pas de transition : on passe directement à la version durable. Tout le
   code écrit en dur pour un enchaînement est retiré de la production. Ce
   qui existait avant n'a pas à rester en marche. (Précisé en Q59 : ce
   code n'est pas détruit, il est rangé dans le dossier « pas encore
   branché ».)
2. On ne crée que les colonnes et les capacités dont le lot a besoin. Les
   fonctions futures (conditions sur les liens, validation par Julien, une
   seule tâche en attente par prospect, délais par canal, actions hors de
   Serge, bac à sable, désinscription…) ajouteront leurs colonnes et leurs
   capacités dans leur propre lot ; elles sont notées dans le TODO.
3. Les capacités sont listées en base et affichées dans MC ; c'est là
   qu'on les choisira pour une invocation. Première capacité importante :
   écrire en base, de façon générique, à partir de la réponse d'une
   invocation.
4. À la fin du lot 6, MC affiche tout ce qui est en base, en direct, et
   garde ce qui existe déjà. Créer une invocation depuis le site viendra
   plus tard.
5. Fusion dans `main` après chaque étape, avec des tests verts qui portent
   seulement sur ce qui est construit. Serge ne peut pas être allumé pour
   de vrai tant que toutes les capacités ne sont pas là ; c'est accepté.

### Q59 — Ce qui reste, ce qui est débranché (validé par Clem)
1. Le code de bas niveau qui ne connaît aucune invocation (envoi d'e-mail,
   pont téléphonique, réception des SMS et de Stripe, garde-fous, fiches de
   contacts) reste en place avec ses tests : ce sont les futures
   capacités, pas encore branchées.
2. Tous les appels au LLM devront passer par le pipeline, y compris la
   consolidation de la mémoire et le bot Discord. Pas dans le lot 6 : leur
   code est rangé dans un dossier « pas encore branché », hors de la
   production, et débranché du runner, du bot et de MC. Leur passage dans
   le pipeline est noté en fin de TODO.
3. La production, c'est tout ce qui a été fait aux lots 1 à 6 et la
   structure qui ne change pas.
4. Clem s'est corrigé : le code des enchaînements en dur (écoute,
   réponses, envois, relances, code propre à chaque invocation) n'est pas
   détruit non plus. Il va dans le même dossier `pas_encore_branche/`, à la
   racine du dépôt, avec ses tests et ses prompts, parce qu'il contient
   beaucoup de choses utiles et que les prochains LLM doivent pouvoir le
   lire facilement. Ce dossier n'est ni importé, ni testé, ni vérifié par
   les outils de qualité, et le test « aucun nom d'invocation dans le
   code » l'ignore.

### Q60 — Ce que voit une invocation : version courte systématique et « Lire les tables que je vois » (validé par Clem)
1. Toute invocation reçoit d'office la version courte des tables où elle
   écrit. C'est systématique mais pas écrit dans le code : la base dit,
   une fois pour chaque table, quelles colonnes forment sa version courte,
   et l'interpréteur applique la règle. On peut ajuster, invocation par
   invocation, les tables à comparer dans MC.
2. Le détail (ce qu'une ligne contient maintenant) et l'historique (ce qui
   lui est arrivé, lu dans le journal) sont deux choses différentes.
3. Un nouvel outil, « Lire les tables que je vois » : ce n'est pas un outil
   codé, mais une sorte d'outil. Il y en a un par invocation, construit à
   partir de ses réglages en base, en particulier de l'ensemble des tables
   qu'elle voit en version courte. Dans ces tables seulement, le modèle
   peut demander toutes les lignes et toutes les colonnes marquées
   lisibles. Il ne peut pas lire une table qu'il ne voit pas.
4. Les autres outils donnés à toutes les invocations : « Lire
   l'historique » d'une ligne qu'elle voit, « Chercher dans la mémoire »,
   « Demander une nouvelle capacité ». Ses propres leçons sont données
   d'office.

### Q61 — Les réglages des invocations, marqués « policy » (validé par Clem)
Les réglages chiffrés propres à une invocation (par exemple « combien de
business choisir ») sont rangés avec l'invocation, et non dans la policy
générale. Mais ils portent une étiquette « policy » : la page Policy de MC
cherche en base tous les réglages ainsi marqués et les rend modifiables en
direct.

### Q62 — Suite du lot 6 (validé par Clem)
1. Les messages reçus de l'extérieur qui ne lancent pas les déclencheurs
   (SMS, e-mail, paiements) : plus tard, au lot 8.
2. Le passage à la main d'un lien est construit (bouton « passer à la
   suite » dans MC). Il existera à côté de la validation par ticket
   Discord du lot 8 : les deux fonctionnements servent.
3. Pas de réglage de créativité (« température ») par invocation : le
   modèle garde le réglage par défaut du fournisseur.

### Q63 — Relier les réglages au format de la réponse et à l'écriture (validé par Clem, pour l'instant)
1. Les réglages d'une invocation sont rangés dans une petite table
   rattachée à l'invocation, une ligne par réglage (nom, type, valeur,
   bornes, description, étiquette « policy »).
2. Un réglage sert partout où l'invocation a une valeur : dans le prompt
   (`{nom}` remplacé à chaque appel), dans le format de la réponse (nombre
   d'éléments minimum et maximum d'une liste), dans l'écriture (une
   colonne reçoit un réglage, « au plus N lignes »), et dans les
   paramètres des outils, de la capacité et des liens.
3. Une nouvelle protection par table, le quota : « au plus N lignes dans
   tel état », par exemple 3 business en test léger. Le chiffre est un
   réglage marqué « policy ».
4. Les capacités restent générales et reçoivent leurs chiffres par leurs
   paramètres. Pas de calculs dans les réglages.
5. Clem : l'organisation sera sans doute retouchée quand on pourra créer
   une invocation depuis Mission Control. Détail :
   [`LOT6_CONCEPTION.md`](LOT6_CONCEPTION.md), partie 17.

### Q64 — Avant de finir le lot 6 (validé par Clem)
1. Le premier cercle (ce que l'invocation doit traiter) reste réglé
   invocation par invocation : c'est le lien qui détermine ce qui est lu
   d'office. Ce n'est pas un « outil » que le modèle appelle : Serge fait
   la lecture avant l'appel et la met directement dans le prompt. Dans la
   doc et MC, on dit « lecture donnée d'office » ; « outil » est réservé à
   ce que le modèle appelle lui-même.
2. Le quota est construit au lot 6 avec un premier quota simple (au plus
   3 business choisis pour un POC). La règle complète des places de test
   viendra en planifiant étape par étape.
3. La section « Écoute » de la policy générale est retirée : ses chiffres
   reviendront comme réglages des invocations du lot 7.
4. La vue d'ensemble (capacités, outils, liens, déclencheurs, modèle par
   niveau, texte « Qui est Serge ») est une nouvelle page « Pipeline » de
   MC.
5. En général, une session de travail = une branche = une pull request,
   de préférence sur une seule idée ; on reste souple (voir
   `docs/DEV_TOOLING.md`). `main` ne bouge que par une PR relue par un
   humain, avec la CI verte.
   Corrigé le 1er octobre 2026 (Q75, précisé en Q76) : ce point disait « On
   travaille toujours sur `Clem`. Chaque fusion dans `main` est demandée à
   Clem avant d'être faite. »

### Q65 — Lot 7, l'étape 1 (validé par Clem, 28 septembre 2026)
0. **B voit ce qu'a écrit A.** Clem revient sur « B ne voit jamais A » :
   Serge ne doit pas faire deux fois la même chose. A et B tournent l'une
   après l'autre ; B reçoit, comme toute invocation qui écrit des
   business, la version courte des business déjà en base, dont ceux de A.
   Le prompt des deux dit de ne jamais reproposer un business qui existe
   déjà. Ce qui différencie B, pour l'instant, c'est seulement qu'elle
   voit les business de A ; on verra avec l'expérience.
1. Marché : la France d'abord, recherches en français, pages en anglais
   acceptées.
2. Les flux RSS sont choisis par Serge lui-même, sans accord de Julien.
   Julien ne propose pas de flux au lot 7 (peut-être plus tard).
3. Ne pas saturer les invocations : celles qui trient ou retiennent des
   pages (« Explorer le web », « Trier les pages ») ne lisent qu'un
   nombre de lignes par page, réglable. Seules celles qui formulent des
   business lisent une page en entier. Une capacité « lire une page »,
   réglée par ce nombre de lignes.
4. Recherche : DuckDuckGo au lot 7, SearXNG au lot 12.
5. On ne garde que les pages qu'« Explorer » retient (et celles des
   flux), pas tous les résultats de recherche. Une fois leur idée
   formulée, A et B reclassent les pages utilisées : une page « besoin
   nouveau » devient une preuve rattachée à leur business.
6. Enchaînement : bouton → Ouvrir le cycle → Explorer le web → rattacher
   au cycle les pages pas encore triées → Trier → Formuler A → Formuler
   B → Choisir → le cycle est fermé. A et B l'une après l'autre.
7. Trier par paquets de n pages, n réglable (20 au départ).
8. Une page qui enrichit un business existant lui est seulement
   rattachée comme preuve.
9. Nombre d'idées par invocation : un réglage, 3 au départ.
10. Une fiche cite au moins une page de preuve, et sa famille (Q32).
11. Critères de « Choisir » : force des preuves, facilité d'un test
    rapide, premier revenu rapide, légalité ; au plus autant de business
    que de places libres.
12. Une place est occupée par un business `POC_SELECTED`, `SMOKE_READY`,
    `SMOKE_RUNNING` ou `SMOKE_DONE`.
13. Le cycle s'arrête après « Choisir » (rien n'est encore prévu après).
14. Niveaux : Explorer moyen, Trier rapide, Formuler intelligent (beaucoup
    à lire), Choisir moyen.
15. Lancement à la main seulement au lot 7.
16. Valeurs de départ : flux lus toutes les 6 h, 60 pages triées au plus
    par cycle, page « bruit » oubliée après 30 jours, flux coupé après 5
    cycles de bruit (plus tard : voir 18).
17. Oublier une page bruit = supprimer sa ligne (jamais une preuve), avec
    une note au journal.
18. Couper un flux qui ne ramène que du bruit : à la main au lot 7, depuis
    MC, qui montre pour chaque flux les pages ramenées et utiles.
19. Page Écoute : les flux, le bouton du cycle avec les places libres, le
    dernier cycle (pages trouvées, par étiquette, fiches, choix).
20. Les business et cycles laissés par la démo sur le serveur de Julien
    sont supprimés avec elle.
21. Précisions (validé par Clem) :
    - « Explorer le web » ajoute les flux, au plus 2 nouveaux par cycle
      (réglage) ; pas d'invocation à part.
    - L'aperçu d'une page compte des lignes : une ligne = un titre, un
      paragraphe ou un élément de liste ; 5 au départ (réglage). Pour une
      page de flux, l'aperçu est le résumé donné par le flux. Le texte est
      extrait avec la bibliothèque standard de Python.
    - En base, on garde seulement l'aperçu et l'adresse d'une page ; A et
      B lisent la page en ligne quand ils en ont besoin.
    - B ne reçoit que les pages « besoin nouveau » que A n'a pas
      utilisées. Celles qui restent après B repassent au cycle suivant,
      sans être retriées.
    - Quand les places sont toutes prises, le bouton du cycle est bloqué
      (« 3 places sur 3 occupées ») : une condition générale sur un
      bouton, du type « seulement si moins de N lignes dans tel état ».
    - Les pages des flux en surplus attendent le cycle suivant, les plus
      récentes d'abord ; une page jamais triée au bout de 30 jours est
      oubliée, comme une page « bruit ».
    - Valeurs de départ : au plus 10 recherches par « Explorer », 30 pages
      retenues par cycle, 20 pages lues par flux à chaque passage.
22. Dernières précisions (validé par Clem) :
    - Un cycle à la fois : le bouton est refusé tant qu'un cycle est
      ouvert. Un bouton « Abandonner le cycle » sur la page Écoute ferme un
      cycle resté ouvert (une invocation qui a échoué, par exemple).
    - « Choisir » choisit parmi tous les candidats encore en base, y
      compris ceux des cycles précédents, sans limite d'âge au lot 7.
    - A et B ne lisent en entier que des pages déjà en base (par leur
      numéro), au plus 150 lignes par page et 10 pages par passage
      (réglages).
      Corrigé le 1er octobre 2026 (Q74) : 300 lignes au départ, ramenées à
      150 par Q66.
    - Une page « besoin nouveau » jamais utilisée est oubliée après 60
      jours (réglage), jamais si elle sert de preuve.
    - La raison du choix (une phrase) est gardée sur la fiche du
      business, visible dans MC. « Trier » ne garde que l'étiquette.
    - Sans texte de guidage, « Explorer » cherche librement dans les 11
      familles de Q32.
    - Les prompts sont montrés à Clem avant la fusion.
    - Le premier vrai cycle est lancé par Julien après la fusion, avec 1
      idée par invocation pour un essai peu cher, puis 3.
    - Une seule fusion dans `main`, à la fin du lot 7.
23. Après « Choisir » (validé par Clem) :
    - « Choisir » choisit au plus autant que de places libres ; il peut
      n'en choisir aucun, en disant pourquoi.
    - Les places bloquées jusqu'au lot 10 ne posent pas de problème :
      Serge ne sera vraiment lancé qu'une fois terminé. Un bouton
      temporaire « Effacer les idées » détruit toutes les idées, pour
      pouvoir tester en production autant de fois qu'on veut.
    - Julien n'est pas averti à la fin d'un cycle.
    - Une douzième famille, « autre », pour une idée qui n'entre dans
      aucune des 11 familles.
24. Les prompts de l'étape 1 sont validés par Clem (28 septembre 2026),
    et la fusion du lot 7 dans `main` est accordée.

### Q66 — Après le premier vrai cycle en production (validé par Clem, 29 septembre 2026)
Constats : « Explorer le web » a échoué sur une réponse vide du modèle au
bout de 22 minutes, sans nouvel essai ; un cycle a consommé près de 3
millions de jetons (« ~11,80 € » estimés par le taux fixe de la policy) ;
le plafond du jour ne s'appliquait qu'entre deux tâches, et la file
annonçait comme « prochaine » une tâche LLM qui attendait le lendemain.
Décidé, pour toutes les invocations, sans bricolage :
1. Les appels au modèle : une erreur passagère est réessayée deux fois ;
   180 secondes pour répondre ; plusieurs outils par tour ; un message
   demande la réponse finale quand les outils sont épuisés ; une réponse
   vide garde l'explication d'OpenRouter.
2. Chaque appel est noté avec son coût réel (celui qu'OpenRouter facture),
   converti en euros par la policy (`budget.eur_per_usd`) ; c'est ce coût
   qui compte dans le plafond du jour. Un appel sans coût connu ne compte pas
   dans le plafond : ses jetons sont comptés à part et signalés, jamais
   estimés.
   Corrigé le 1er octobre 2026 (Q74) : ce point disait « estimé par ses
   jetons », ce que la PR #39 (dépense au coût réel) a retiré.
3. Le plafond est aussi vérifié pendant une tâche : atteint, le modèle doit
   répondre sans plus d'outil.
4. Moins de jetons renvoyés : « Explorer » 10 tours d'outils ; A et B 5
   tours, 10 pages lues en entier au plus (limite d'appels de l'outil),
   150 lignes par page (au lieu de 300, Q65).
5. Une valeur d'un objet déjà en base (tours, prompt, réglage) ne change
   que par la section `changes` de `pipeline.yaml` : une fois, et
   seulement si elle n'a pas été changée dans Mission Control. Un réglage
   nouveau s'ajoute tout seul à une invocation existante.
6. La file dit pourquoi une tâche attend (le plafond du jour).
7. Les 2,9 millions de jetons venaient d'un seul aperçu de page géant (une
   « ligne » sans longueur maximale : 126 000 jetons), renvoyé à chacun
   des ~20 appels suivants. Corrigé pour tout Serge : une ligne fait au
   plus 300 caractères ; un résultat d'outil est coupé au-delà d'une
   taille réglée dans la policy (20 000 caractères) ; un résultat n'est
   jamais envoyé en double ; une redemande de format se fait sans outil.

### Q67 — Abandonner un cycle arrête sa chaîne (validé par Clem, 29 septembre 2026)
Constat : après un abandon, la tâche « Trier les pages » de l'ancien cycle
est partie (elle attendait le plafond du jour) et a lancé « Formuler des
business A » pour l'ancien cycle, avant l'« Explorer » du nouveau.
Décidé : abandonner un cycle annule ses tâches en attente, par une règle
réglée sur la table (`task_cancel_rules` : un cycle `ABANDONED` annule les
tâches dont le paramètre `cycle_id` est le sien) ; la chaîne s'arrête
après la tâche en cours. La fiche d'une tâche en attente a un bouton
« Annuler la tâche ». La question du bouton et le rôle de l'invocation sont
mis à jour sur l'instance existante par la section `changes`.

### Q68 — Tout réglage discutable se change dans Mission Control (validé par Clem, 1er octobre 2026)
Règle posée par Clem : **toute grandeur discutable, qui peut un jour
changer, se règle depuis Mission Control.** Elle ne reste dans le code que
si elle n'a rien de discutable : un port, la taille d'une trame audio, la
sécurité de Mission Control (durée d'une session, essais de connexion),
le format d'un message Discord.

Constats (inventaire du 1er octobre 2026, sur main) :
- 52 des 84 réglages de la policy ne sont lus par aucun programme en
  marche : leur code est dans `pas_encore_branche/` ou a disparu. Mission
  Control les affiche pourtant. Exemples : « plafond du mois, au-delà plus
  rien ne part » (rien ne le vérifie), « tours d'outils max » (le vrai
  réglage est sur chaque invocation), la relève de la boîte mail, le
  barème de prospection.
- Des chiffres en double : le code garde sa valeur pendant que la policy
  en affiche une autre (nouveaux essais d'une réponse invalide, leçon
  retirée après 3 démentis, plafonds de SMS ; pour la voix, 3 minutes
  d'appel dans le code contre 10 dans la policy).
- Des chiffres discutables écrits dans le code, sans réglage : attente
  d'une réponse du modèle (180 s), pauses avant de réessayer (3 s puis
  10 s), température (0,3, contraire à Q62), lecture du web (300
  caractères par ligne, 2 Mo et 15 s par page, 8 s et 10 résultats par
  recherche, 20 s et 50 articles par flux), valeurs par défaut des outils
  (5 résultats, 20 articles, 50 lignes vues), filtres de la
  recommandation de modèle (128 000 jetons, un an, 75 % de jetons lus,
  100 000 jetons mesurés, 30 jours).
- Des textes envoyés au modèle écrits dans le code : « Tu ne peux plus
  appeler d'outils… », la consigne de format, le message d'une réponse
  invalide.
- Les titres, aides et bornes de la page Policy sont dans un fichier
  JavaScript de 757 lignes.

Décidé :
1. Les réglages que rien ne lit sont retirés de la policy, de sa
   vérification et de Mission Control. Le lot qui rebranche une capacité
   remet ses réglages.
2. Température : celle du fournisseur, comme le disait Q62. Le 0,3 est
   retiré ; le prompt fait le reste.
3. Le plafond du mois est branché : au-delà, Serge s'arrête, comme pour
   le plafond du jour.
4. Les réglages généraux passent dans une vraie table en base, avec pour
   chacun sa valeur, son titre, son aide et ses bornes. Mission Control
   les affiche sans catalogue écrit dans le code. C'est un gros chantier,
   accepté.
5. Les pages : **Pipeline** réunit tout ce qui touche au modèle (le modèle
   de chaque niveau et les filtres de la recommandation, les appels, les
   textes envoyés au modèle) ; **Policy** réunit les limites de Serge face
   au monde (argent, lecture du web, envois et canaux, horaires et pays,
   accord des gens, mémoire, encaissement), avec les réglages des
   invocations et les quotas des tables.
6. Pas de réglage en double : toute la policy est en base, avec une seule
   valeur, celle que lit le code ; seuls les hyperparamètres non
   discutables restent écrits dans le code. Un réglage qui ne sert à rien
   est supprimé, et recréé quand on code ce qui s'en sert. Les chiffres
   discutables écrits dans le code deviennent des réglages. Les textes
   envoyés au modèle passent en base, modifiables sur la page Pipeline.
   La voix attend le lot 8, qui la règle en base comme une invocation.
   Corrigé le 2 octobre 2026 (Q78) : ce point disait « Les chiffres en
   double sont branchés sur leur réglage », ce qui déformait la réponse de
   Clem.

Précisions de Clem (1er octobre 2026) :
7. Chaque réglage garde seulement sa valeur précédente (qui l'a changée,
   quand) : un bouton « Remettre la valeur précédente ». Pas d'historique
   complet.
8. « Proposer un changement » et « Candidats à l'auto » sont retirés de
   la page Policy, avec leurs réglages : rien ne s'en sert.
9. Le plafond du mois borne **ce que Serge nous coûte** : tous les appels
   à une IA, quelle qu'elle soit (modèles de texte, modèles vocaux des
   appels téléphoniques). Il ne compte pas les achats que Serge fait pour
   mener ses business : ils passent par son propre compte en banque.
   Aujourd'hui, seul le coût des modèles de texte est mesuré ; le lot 8
   ajoute celui de la voix au même compte.
10. Le chantier se livre en trois PR : A (retirer les réglages morts,
    brancher les doubles, température, plafond du mois), B (la table des
    réglages et la page Policy), C (les nouveaux réglages, les textes
    envoyés au modèle et la page Pipeline).
11. En faisant la PR A, le test « chaque réglage est lu » a trouvé 6
    réglages de plus que rien ne lisait, dans « Pays et appels » (jours et
    heures d'appel, jours de prospection, marge avant un rendez-vous, jours
    fériés, fuseau du pays) : l'inventaire comptait les réglages d'un pays
    pour un seul. En tout, 58 des 91 réglages n'étaient lus par rien. Ils
    sont retirés comme les autres ; le lot 8 les remet avec la voix.

### Q69 — Citer une décision, et signaler toute incohérence à un humain (validé par Julien, 1er octobre 2026)
Constat : les principes de ce fichier disaient « pas de renvois Q13 »
dans le TODO, alors que le TODO, les docs et les commentaires du code
citent des numéros (Q62, Q68…). Un lecteur qui arrive à froid ne sait pas
ce que veut dire « Q68 ». Julien a demandé si le style d'écriture était
écrit quelque part ; la réponse a fait apparaître cette contradiction.
Décidé :
1. On ne cite jamais une décision par son seul numéro : on écrit ce
   qu'elle dit, puis son numéro entre parenthèses (« Tout réglage
   discutable se change dans Mission Control (Q68) »). Cela précise la
   demande de Clem (« pas de renvois Q13 ») : ce sont les numéros nus
   qu'on évite. La règle est dans la charte (section 7) ; le TODO et les
   docs de l'étape 1 sont corrigés.
2. Il ne doit y avoir d'incohérence nulle part. Quand on en trouve une
   (deux textes qui se contredisent, une doc et le code, deux décisions),
   on ne tranche pas soi-même : on la signale à un humain, qui tranche.
   Ensuite tous les textes concernés sont corrigés dans le même
   changement. La règle est dans la charte (section 7).
Arguments de Julien : il préfère qu'il n'y ait pas d'incohérence nulle
part ; quand il y en a, c'est à un humain de dire laquelle fait foi.

### Q70 — Les anciennes réponses restent, et se corrigent quand elles deviennent fausses (validé par Julien, 1er octobre 2026)
Constat : en relisant le fichier, deux entrées étaient restées dans le
désordre (Q55 après Q59, Q63 avant Q62), et la règle d'ajout écrite en
début de fichier disait « on ne réécrit pas l'ancienne » réponse. Julien a
répondu à la question de savoir quoi faire du plan de travail et des
réponses anciennes.
Décidé :
1. Les entrées sont dans l'ordre des numéros. Q55 et Q62 sont remises à
   leur place.
2. On ne retire pas une question et sa réponse parce que le travail
   qu'elles décrivent est déjà fait : elles gardent le « pourquoi ».
3. Si une réponse n'est plus en accord avec le code actuel, ou si le code
   ou une réponse plus récente la contredit, l'ancienne réponse est
   corrigée proprement, dans son entrée d'origine. Elle ne reste pas fausse
   avec un renvoi vers la nouvelle. Cela remplace la règle d'ajout écrite
   en début de fichier.
Arguments de Julien : l'historique de ce qu'on a demandé garde son intérêt
même quand le travail est fait ; ce qui ne doit pas rester, c'est une
réponse devenue fausse.

### Q71 — La réponse la plus récente a raison, seulement là où elle contredit (validé par Julien, 1er octobre 2026)
Constat : en relisant le plan de travail, Q49 (l'ordre des lots 6 à 12) et
Q55 (« nouvel ordre des lots ») ne disaient plus la même chose. Il fallait
savoir laquelle fait foi.
Décidé :
1. Les réponses ne s'ajoutent pas simplement les unes aux autres : elles
   fonctionnent comme un « upsert » de base de données. Une réponse plus
   récente (le numéro le plus grand) a raison sur toutes les précédentes,
   mais seulement sur les points où elle les contredit. Si elle ne
   contredit rien, elle ajoute de l'information et les précédentes gardent
   leur contenu.
2. Quand deux réponses se contredisent, on corrige donc soi-même l'ancienne,
   dans son entrée d'origine (Q70), sans demander. Quand c'est le code ou un
   autre texte qui contredit une réponse, on demande toujours à un humain.
3. Appliqué tout de suite : Q49 est corrigée d'après Q55 (le lot 6 devient
   « le runner et le pipeline en base », un lot 13 s'ajoute). Q68 ne
   corrige pas Q55 : elle ajoute le chantier « avant le lot 8 » sans
   contredire l'ordre des lots. Le TODO dit « lot 11 : étapes 3, 4, 6, 7 et
   8 », comme Q55.
Arguments de Julien : sémantiquement, la dernière question a raison sur
celles d'avant, et elle ne retire leur contenu que si elle le contredit.

### Q72 — Supprimer les documents de reprise et de contexte une fois finis, et tenir le TODO selon ses règles (validé par Julien, 1er octobre 2026)
Constat : `docs/REPRISE_LOT6.md` annonçait qu'il serait supprimé à la fin du
lot 6, qui est fait, et le TODO y renvoyait encore.
`docs/CONTEXTE_2026-09-27.md` résumait la revue au 27 septembre : il s'arrête
au lot 6 et répète le README, la charte et le TODO.
Décidé :
1. Les deux fichiers sont supprimés. Leurs commandes de vérification et
   leurs règles de travail sont dans `docs/DEV_TOOLING.md` et la charte ;
   l'historique git garde le reste.
2. Le TODO ne renvoie plus à ces documents, et il suit sa propre règle :
   une tâche finie est retirée. Les lots 6 et 7, et leurs tâches faites, ne
   sont plus dans le TODO. Ce qui restait à faire dedans y est gardé (les
   réglages retirés que chaque lot remet).
Arguments de Julien : si le lot est terminé, le TODO n'a plus besoin de
renvoyer à son document ; le contexte daté « ne sert plus à rien ».

### Q73 — Contacts : la décision la plus récente est une fiche par personne dans un business (validé par Julien, 1er octobre 2026)
Constat : Q17 disait « une ligne par personne », alors que le code et
`docs/DB.md` (choix fait au lot 5) disent « une fiche par personne dans un
business ».
Décidé : le choix le plus récent fait foi, donc Q17 est obsolète sur ce
point. Une même personne qui répond à deux business a deux fiches. Q17 est
corrigée dans son entrée d'origine.
Arguments de Julien : c'est la décision la plus récente.

### Q74 — Corriger sans demander ce qui est explicitement périmé (validé par Julien, 1er octobre 2026)
Constat : après Q71, il restait dans les anciennes réponses des détails
devenus faux : une phase « finir les questions sur les étapes 2 à 8 » déjà
faite, un « à corriger » déjà corrigé, « valeurs dans la policy » alors que
Q52 les règle par canal, un « jamais d'UPDATE » que Q66 assouplit.
Décidé :
1. Si une réponse contient un détail explicitement périmé (un numéro
   d'étape ou de lot, un « à faire » déjà fait, un renvoi à ce qui n'existe
   plus), on le corrige soi-même, sans demander.
2. On corrige aussi sans demander la cohérence générale, tant que cela ne
   change pas le sens fonctionnel. Dès que le sens fonctionnel change, on
   demande à un humain.
3. Chaque correction est datée dans l'entrée (« Corrigé le … (Qnn) »).
4. Appliqué tout de suite, à la relecture des 73 entrées. Corrigées : Q3 (la section
   `changes` de Q66), Q9 (Dédoublonner et Refuser sont des règles d'écriture,
   Q56 ; Ouvrir et Rattacher s'ajoutent, Q65), Q14 bis (« à reconfirmer »,
   confirmé par Q65), Q25 (réintégration faite), Q28 (forme du TODO, demande
   de Clem), Q38 (délais par canal, Q52 ; bugs corrigés au lot 2), Q51 (le
   runner est fait), Q54 (conception terminée ; éditeur au lot 13), Q65
   (150 lignes par page, Q66), Q66 (plus d'estimation du coût, PR #39), les
   notes de discussion de Q4 et l'en-tête du fichier. Les mots que la charte écarte
   (« jonction », « hôte », « contrat ») sont remplacés dans Q4 et Q5.
Arguments de Julien : un détail comme « étape X à X » ou « lot X à X à
faire » qui est périmé n'a pas besoin de lui ; il faut le corriger.

### Q75 — Contacts (désabonnement, regroupement), branche de travail et REPRISE_LOT7 (validé par Julien, 1er octobre 2026)
Constat : en corrigeant Q17 d'après Q73, quatre points restaient à trancher.
Q17 disait le désabonnement « global à la personne », alors que le code ne
marque que la fiche du business. Q17 interdisait de regrouper sur un
profil de réseau, alors que le code regroupe sur une même adresse sur le
même canal. Q64 disait « on travaille toujours sur `Clem` », alors que
`docs/DEV_TOOLING.md` dit « une idée = une branche + une PR ».
`docs/REPRISE_LOT7.md` était dans le même cas que celui du lot 6.
Décidé :
1. `docs/REPRISE_LOT7.md` est supprimé.
2. Une personne désabonnée n'est plus contactée par aucun business, sur
   aucun canal, et un ticket prévient Julien et Clem (Q79).
   Corrigé le 7 octobre 2026 (Q79) : ce point disait « Une personne
   désabonnée du business A peut encore être contactée par le business B :
   le désabonnement est propre à la fiche. »
3. Quand le code est plus récent qu'une réponse, on suit le code. Ici le
   code (27 septembre) est plus récent que Q17 (26 septembre) : le
   regroupement de Q17 est corrigé d'après lui.
4. Q64, point 5, a tort : la bonne règle est celle de `docs/DEV_TOOLING.md`.
   Q64 est corrigée.
   Corrigé le 1er octobre 2026 (Q76) : cette entrée disait « une idée = une
   branche = une PR ». C'est l'idéal ; en général, c'est une session de
   travail = une branche = une PR, et on reste souple. Julien en parle à
   Clem ; si sa réponse change cela, elle sera notée.
Arguments de Julien : sur le désabonnement, une personne qui quitte un
business n'a pas quitté les autres. Sur la branche, c'est le
fonctionnement de l'équipe, et `docs/DEV_TOOLING.md` est la meilleure règle.

### Q76 — Abonnements Stripe : l'identifiant du business est lu sur le prix ; une session de travail = une branche = une PR (validé par Julien, 1er octobre 2026)
Constat : au lot 5, le code rattache chaque abonnement Stripe à son
business (`serge/collect/abonnements.py`). Il lit l'identifiant du business
dans `metadata.venture_id`, sur l'abonnement, son prix ou son plan, et pas
sur le produit. Ce choix n'avait jamais été validé. Il reste à faire côté
Serge : écrire cet identifiant sur le prix quand il crée le produit (étape
5, lot 10). Julien a aussi précisé la règle de branche posée en Q75.
Décidé :
1. L'identifiant du business est lu sur le prix (ou l'abonnement, ou le
   plan), pas sur le produit. Sans identifiant, ou avec un business
   inconnu, l'abonnement est gardé sans business et une note est écrite au
   journal. Il n'est jamais perdu ni bloqué, et un rattachement déjà fait
   n'est jamais remplacé. À l'étape 5, Serge inscrit l'identifiant sur le
   prix qu'il crée.
2. La règle de branche : en général, une session de travail = une branche =
   une PR, de préférence sur une seule idée. On reste souple. Q64, Q75 et
   `docs/DEV_TOOLING.md` sont corrigés en ce sens.
Arguments : c'était la recommandation de Claude, suivie par Julien. Stripe
envoie le prix dans ses événements, mais pas le produit : lire le produit
demanderait un appel de plus à Stripe à chaque événement. Le choix est sans
risque : le pire cas est un abonnement sans business, visible au journal.
Julien, sur la règle de branche : l'idéal est une idée par PR, mais en
pratique c'est une session de travail ; on garde une cohérence et on reste
souple.

### Q77 — La branche de travail : une session = une branche = une PR, et Clem valide chaque fusion (validé par Clem, 2 octobre 2026)
Constat : Clem avait demandé de toujours travailler sur la branche `Clem`
et de lui demander avant chaque fusion dans `main`. Julien a corrigé Q64
(point 5) : en général, une session de travail = une branche = une PR, de
préférence sur une seule idée, et on reste souple (Q75, Q76). Il a dit
qu'il en parlerait à Clem.
Décidé :
1. Clem suit la règle de Julien : une session de travail = une branche =
   une PR (`docs/DEV_TOOLING.md`). Exemple : les réglages généraux en base
   (la PR B de Q68) partent sur leur propre branche, `reglages-en-base`,
   avec leur propre PR.
2. Claude demande toujours à Clem avant de fusionner une PR dans `main` :
   chaque fusion redéploie Serge sur le serveur de Julien. C'était la
   proposition de Claude, et Clem l'a acceptée.

### Q78 — Pas de réglage en double, et un réglage inutile est supprimé (validé par Clem, 2 octobre 2026)
Constat : Q68 (point 6) disait « les chiffres en double sont branchés sur
leur réglage », et l'inventaire y rangeait « une leçon est retirée après
3 démentis ». La PR A a retiré ce réglage au lieu de le brancher : aucun
programme en marche ne retire une leçon après des démentis.
Décidé :
1. Le retrait est validé. Un réglage qui ne sert à rien est supprimé ; on
   le recrée quand on code ce qui s'en sert.
2. Pas de réglage en double : toute la policy est en base, avec une seule
   valeur, celle que lit le code. Seuls les hyperparamètres non
   discutables restent écrits dans le code. Q68 (point 6) est corrigée
   en ce sens.
Arguments de Clem : c'était déjà le sens de sa réponse à Q68 (« mon propos
a été déformé », « normalement c'était clair »).

### Q79 — Lot 8 : les canaux de conversation, l'e-mail et la voix d'abord (validé par Clem, 7 octobre 2026)
Constat : avant de commencer le lot 8, Claude a posé des questions sur son
périmètre, l'e-mail, « Traiter une réponse », les délais, les relances, la
voix et le test.
Décidé :
1. **Une architecture des canaux qui accueille facilement un nouveau
   canal.** Les plus évidents sont la voix, l'e-mail et LinkedIn. LinkedIn
   et les autres sites (Instagram, Facebook…) demanderont une machine
   virtuelle pilotée par un LLM : ce sera plus tard (lot 12, « Web »).
   Le lot 8 se concentre sur l'e-mail et la voix, dont le code existe
   déjà en partie, et prépare le terrain pour les canaux à venir.
2. **Un message reçu réveille le pipeline** pour répondre au contact.
3. **Le découpage en PR** : (1) l'architecture des canaux, sans canal
   réel (tables, code, réveil du pipeline à la réception) ; (2) le canal
   e-mail, qui marche de bout en bout ; (3) le canal appel ; (4) une
   demi-fiche produit et des invocations temporaires (« Écrire le premier
   message », « Faire le premier appel ») pour que Clem teste tout depuis
   Mission Control.
4. **Le test** : Clem se fait pitcher un projet bidon par e-mail et par
   appel, répond, et appelle ou écrit lui-même ; Serge doit répondre tout
   seul et savoir qui il est. Ses coordonnées sont saisies dans Mission
   Control, jamais dans le dépôt (public).
5. **Les fiches produit** : pour les tests, des demi-fiches produit en
   base, sans les relier encore à la conception des produits (lot 10).
6. **Les canaux** : l'e-mail, puis l'agent vocal ; le SMS plus tard.
7. **Envoi automatique** : les réponses partent sans ticket. Les tickets
   qui font attendre (valider un brouillon, répondre à la place de Serge)
   viennent dans un lot à part, après le lot 8.
8. **La désinscription vaut partout** : une personne qui se désinscrit, par
   n'importe quel business, n'est plus contactée sur aucun canal ni pour
   aucun business. Un ticket prévient Julien et Clem, pour qu'ils voient ce
   qui se passe et débloquent un cas rare. Serge ne lui répond rien.
   Q17 et Q75 sont corrigées.
9. **Les réactions d'un message reçu** : intéressé, question, objection,
   rendez-vous, refus, désinscription, absence, hors sujet. Rendez-vous :
   Serge confirme et prévoit un appel. Refus : il remercie, puis plus rien
   pour ce business. Désinscription : silence. Absence (réponse
   automatique) et hors sujet : pas de réponse ; après une absence, la
   relance continue.
10. **Délai de réponse** : entre 5 et 20 minutes, à toute heure et tous les
    jours, réglable dans Mission Control, et 0 possible pour les tests.
    Q38 et Q52 sont corrigées.
11. **Les relances, quel que soit le canal**, réglées en base : la
    première 3 jours après le premier message, la seconde 7 jours après la
    première, deux au plus ; une réponse les arrête ; les délais se règlent
    en minutes pour les tests. Une relance garde le canal du premier
    message (changer de canal va dans la boîte à idées du TODO).
12. **Ne jamais agir deux fois** : chaque canal a sa fonction qui confirme
    un envoi (l'e-mail est cherché dans les messages envoyés ; l'appel a
    son journal : joint ou non, durée). On fait confiance à ces
    vérifications : pas de bouton dans Mission Control.
13. **L'appel de test** : le bouton d'essai enregistre l'accord de Clem
    pour son numéro ; un appel de test vers un numéro qui a donné son
    accord peut partir à toute heure ; un appel de prospection reste dans
    les heures légales.
14. **Se désinscrire par e-mail** : chaque e-mail finit par une phrase du
    type « Répondez STOP pour ne plus être contacté », réglable dans les
    textes de la page Pipeline ; cette réponse est une désinscription.
15. **Un message d'un inconnu** (aucun contact connu, aucun de nos fils)
    n'est pas traité : il apparaît dans Mission Control, dans les messages
    non rattachés (Q37, gardée).
16. **Une boîte à idées** dans le TODO, pour les fonctions marginales à
    faire une fois tout le reste fini.
Arguments de Clem : Serge est une IA qui travaille 24 heures sur 24, il ne
faut pas l'imiter avec des heures ouvrées ; une personne qui ne veut plus
être contactée par Serge ne le veut plus pour aucun business ; un canal par
machine virtuelle ouvrira n'importe quel site, mais plus tard ; l'e-mail et
la voix existent déjà en partie dans le code.

### Q80 — Le délai de réponse est une policy par canal, pas un réglage d'invocation (validé par Clem, 7 octobre 2026)
Constat : en relisant la PR 1 du lot 8, Clem a demandé si les réglages des
relances et le délai de réponse étaient bien des réglages d'invocation
affichés sur la page Policy.
Décidé :
1. **Un réglage d'invocation marqué « policy » en base s'affiche tout seul
   sur la page Policy.** C'est le cas des relances : 3 jours avant la
   première, 7 jours entre deux, deux au plus, réglages de l'invocation
   « Préparer les relances ».
2. **Le délai de réponse n'est qu'une policy, et elle dépend du canal**
   (famille « Canaux » de la page Policy). Exemple : l'e-mail répond entre
   5 et 20 minutes ; l'appel aura ses propres valeurs. Ce n'est pas un
   réglage d'invocation : c'est le temps qu'on attend avant de lancer
   l'envoi d'une réponse. Chaque canal branché reçoit ses deux réglages de
   délai dans la PR qui le branche.
Argument de Clem : le délai dépend du canal, et il ne règle pas ce que fait
une invocation mais le moment où on la lance.

### Q81 — Effacer les contacts des anciens essais quand l'e-mail se branche (demandé par Clem, 7 octobre 2026)
Constat : une fois le canal e-mail branché (lot 8, PR 2), Serge relève sa
boîte toutes les 2 minutes et répond tout seul à un message dont
l'expéditeur est un contact en base. Les tables des contacts ne changent
pas avec le lot 8 : une base existante garde ses contacts d'anciens essais.
Décidé :
1. **Les contacts et leurs adresses sont effacés une seule fois**, au
   déploiement de la PR 2, par la migration v36. Une migration ne tourne
   qu'une fois par base : les contacts créés ensuite ne sont jamais
   touchés.
2. **La liste de blocage et les accords sont gardés** : une personne qui
   s'est désinscrite le reste. L'historique (envois, messages reçus,
   journal) est gardé, et le journal note combien de contacts ont été
   effacés.

### Q82 — Les étapes où Serge n'écrit plus à un contact sont en base (validé par Clem, 7 octobre 2026)
Constat : la liste des étapes « finales » d'un contact (refus, client,
injoignable, désinscrit, bloqué, fiche invalide), où Serge n'envoie plus
ni premier message ni relance, était écrite dans le code. Claude l'a
signalée comme discutable.
Décidé : **cette liste se règle sur la page Policy** (famille
« Contacts », « Étapes où Serge n'écrit plus de lui-même »). Serge répond
encore à un contact à l'une de ces étapes s'il écrit ; une personne
désinscrite n'a jamais de réponse (Q79). Plus généralement, tout ce qui
reste en dur et qui est discutable passe en base ; le reste du lot 8 est
validé tel quel.
Argument de Clem : l'étape de chaque contact est déjà une valeur en base ;
la liste des étapes qui arrêtent Serge doit l'être aussi.

### Q83 — Lot 8, canal appel : la suite d'un appel et les heures légales (validé par Clem, 8 octobre 2026)
Constat : avant la PR 3 du lot 8 (le canal appel), Claude a demandé ce que
fait Serge après un appel, et quand un appel tombe hors des heures légales.
Décidé :
1. **La suite d'un appel** : « Traiter une réponse » lit la transcription.
   Si une suite est utile, elle part par e-mail si Serge a l'adresse
   e-mail du contact ; s'il n'a que son numéro, Serge rappelle.
2. **L'agent vocal demande l'adresse e-mail** dès qu'un document doit être
   envoyé, et la note sur la fiche du contact.
3. **Un appel hors des heures légales attend le prochain créneau légal**
   (lundi au vendredi, 10 h – 13 h et 14 h – 20 h, jours fériés exclus),
   comme un e-mail attend le lendemain quand le plafond du jour est
   atteint. Il n'est pas refusé.

### Q84 — Lot 9 : la grille de points (validé par Clem, 9 octobre 2026)
Constat : avant le lot 9, Claude a demandé comment compter les points d'un
business. Les réactions existent depuis le lot 8 : « Traiter une réponse »
classe chaque e-mail reçu et chaque appel transcrit parmi huit réactions
(intéressé, question, objection, rendez-vous, refus, désinscription,
absence, hors sujet). Le coût d'un business n'était pas mesuré : le coût
des modèles est noté sans sa tâche, et les minutes d'appel ne sont notées
nulle part.
Décidé :
1. **Un prospect compte une fois, pour sa meilleure réaction** dans un
   business : on mesure jusqu'où chacun est allé. Un prospect qui écrit
   cinq fois ne gonfle pas le total. Précise Q16 (« chaque signal rapporte
   des points »).
2. **Le barème porte sur ces réactions, par canal**, de 0 à 10 points,
   modifiable dans Mission Control. Barème de départ, le même pour
   l'e-mail et l'appel : rendez-vous 10, intéressé 8, question 4,
   objection 3, refus 1, absence 0, hors sujet 0, désinscription 0. Les
   points sont recalculés avec le barème du moment : le changer recompte
   tous les business de la même façon.
3. **« Dépensé », pour les points par euro** : le coût réel des modèles
   des tâches du business, plus ses minutes d'appel au prix réglé sur la
   page Policy. Les achats (publicité, domaines) s'ajouteront quand ils
   existeront.
4. **Pas de suivi des ouvertures ni des clics des e-mails** : seules les
   réponses comptent. Remplace, pour l'e-mail, les signaux « a vu » et
   « a cliqué » de Q16.
5. **Pas de réaction « veut acheter »** : rendez-vous et intéressé
   couvrent l'intention d'achat ; l'argent encaissé reste un chiffre à
   part (Q16 bis, Q42).

### Q85 — Lot 8 bis : Julien dans la conversation (validé par Clem, 9 octobre 2026)
Constat : pendant le lot 9, Clem a voulu discuter du lot 8 bis, où un envoi
attend la réponse d'un humain. Les tickets existent (cycle de vie,
expiration et décision par défaut, réponse dans Mission Control ou sur
Discord), mais rien ne fait attendre un envoi ni ne relance la conversation
quand un ticket est tranché. Les types de tickets sont dans un fichier
(`config/ticket-types.yaml`), pas en base.
Décidé :
1. **Un ticket « Besoin de Julien » sans réponse** : à l'expiration (délai
   réglable dans Mission Control), Serge envoie une réponse d'attente
   prudente, sans s'engager (« je vérifie et je reviens vers vous ») ; le
   ticket reste ouvert. Le prospect n'est jamais laissé sans nouvelles.
2. **Valider les brouillons avant l'envoi** : un interrupteur par business,
   éteint par défaut. Allumé (business sensible, premiers jours), chaque
   brouillon ouvre un ticket.
3. **« Réécrire avec mes consignes »** : le nouveau brouillon revient dans
   le même ticket pour un dernier clic ; rien ne part sans avoir été vu.
4. **Les types de tickets passent en base** dans ce lot (boutons, délai,
   décision par défaut), réglables dans Mission Control.
5. **Les administrateurs Discord de Serge sont en base**, et on en ajoute
   depuis Mission Control. Chaque ticket est envoyé à tous les
   administrateurs, pour l'instant en message privé.
6. **La première réponse ferme le ticket pour tous** : dès qu'un
   administrateur répond, le ticket est fermé instantanément chez tous les
   autres, et une ou plusieurs invocations sont réveillées pour réagir à
   la réponse.
