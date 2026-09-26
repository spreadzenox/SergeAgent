# Revue des specs SergeAgent — décisions validées par Julien

Ce fichier rassemble les réponses de Julien aux questions posées pendant la
revue du projet (septembre 2026, branche `Clem`). Chaque réponse, une fois
discutée, fait foi : le code et la doc doivent être corrigés pour s'y
conformer.

C'est un fichier de travail temporaire. Il sert de référence pendant le
chantier de refonte, puis il sera supprimé quand la vraie documentation
(`README.md`, `docs/PIPELINE.md`, `docs/etapes/…`) l'aura remplacé.

Plan de travail (Q30) : finir les questions sur les étapes 2 à 8, puis
corriger par petits lots (un sujet = un commit, tests verts), en relisant ce
fichier au début de chaque lot.

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
- Jamais d'UPDATE d'un objet déjà présent depuis les seeds.
- Exception (tranchée en Q24) : le boot met à jour les informations
  techniques qu'il calcule lui-même (empreinte, chemin du code), jamais les
  réglages owner.

### Q4 — Capsules → SUPPRIMÉES (option A)
- Plus d'objet/table capsule (db_readers, llm_point_readers,
  db_reader_fixed_params, db_reader_fixed_joins à retirer).
- Tout passe par la jonction invocation ↔ tool (llm_point_tools), qui porte :
  - le mode : « contexte injecté » (l'hôte lit avant l'appel et met le
    résultat dans le prompt) ou « appelable » (le modèle décide) ;
  - les paramètres figés pour cette invocation.
- Un même tool peut être injecté pour une invocation, appelable pour une autre.
- Vaut pour tous les tools (db_read, web_search, memory_search…).
- But final (Julien) : passations entre étapes — le résultat d'une étape
  fournit des paramètres au lancement d'une invocation de l'étape suivante
  → pipelines où la donnée circule.

### Q5 — Lien = contrat de passation (validé dans l'esprit)
Un lien devient un contrat de passation de données :
1. ce qui sort de l'amont (table + lignes « prêtes ») ;
2. ce qui est lancé en aval (invocation LLM ou technique) ;
3. mapping champs → paramètres des tools de l'invocation aval ;
4. une ligne transmise = un lancement, une seule fois (idempotent).
Trois origines de paramètres : figé (jonction) / fourni par le lien /
libre (modèle). Déclenchement : bouton MC « passer à la suite » +
interrupteur « passage automatique » + tick runner (cf. TODO ponts).
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
Liste des flux en base (listen_feeds : url, ajouté par owner/invocation,
actif, compteurs pages ramenées / utiles).
Garde-fous volume (réglages policy) : N pages max triées par cycle ; pages
« bruit » oubliées après X jours (preuves conservées) ; flux désactivé après
K cycles de bruit ; fréquence de la veille.
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
  Julien — à reconfirmer à la relecture).
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

### Q17 — Contacts : une fiche par personne (validé)
- Table contacts = une ligne par personne.
- Table à part pour les adresses : une ligne par adresse (canal, valeur,
  active ou non). Rien n'est écrasé ; plusieurs emails possibles.
- Regroupement automatique seulement sur email identique ou numéro de
  téléphone identique (pas sur nom, pas sur profil réseau). Adresses
  génériques (contact@, info@…) ne déclenchent pas de regroupement
  (proposé, non contesté).
- Remplace la règle du TODO « deux lieux, deux lignes » et le JSON
  contact_reference_by_canal de la branche Clem.
- Désabonnement (OPT_OUT) global à la personne.

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
- À la fusion avec main (PR #27), réintégrer serge/demande_capacite.py dans
  ce mécanisme (Clem avait supprimé le « offert partout »).

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
- Rangé par étape 1 à 8 + une section « Transverse ».
- Tout ce qui est fait est retiré (historique = git).
- Chaque élément : Quoi (avec exemple) / Pourquoi (une phrase) / Dépend de.
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
  → question à poser plus tard : que doit devenir le lien.

### Q30 — Méthode (validé)
- Pas de correction géante d'un seul coup. D'abord toutes les questions
  (cohérence d'ensemble), puis des petits lots relisibles.
- Ce fichier est poussé sur `Clem` pour ne pas perdre les réponses.
