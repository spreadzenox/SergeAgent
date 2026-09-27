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
- Style des documents (demande de Clem, après la réécriture du TODO) :
  chaque tâche du TODO est une case à cocher, un titre en gras, puis un
  paragraphe descriptif qui dit d'où on part, ce qu'il faut faire,
  pourquoi, et ce qui doit être réglable dans Mission Control. Pas de
  rubriques du type « Quoi / Pourquoi / Dépend de », pas de renvois
  « Q13 ». Les autres documents suivent le même esprit : des phrases qui
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
  objection, refus, désinscription, hors sujet), (2) la réponse à envoyer ou
  « pas de réponse », (3) « besoin de Julien : oui/non » + raison.
  Remplace classify_reply, reply_intent, review_other, extract_meeting.
- Envoi automatique sauf « besoin de Julien » ou refus d'un garde-fou →
  ticket Discord avec le brouillon (discussion possible).
- Circuit transverse (étapes 3 et 6), avec son propre coupe-circuit.
- Priorité par invocation, réglable dans MC. Départ : 100 traiter une
  réponse / désinscription ; 80 relever boîtes et canaux entrants ; 50
  envois et relances ; 30 construction ; 10 écoute, veille, consolidation.
- Relève des réponses toutes les 5 min (invocation technique programmée).
- Délai de réponse « humain » : en heures ouvrées (ex. 8 h–20 h, lundi–
  samedi) entre 5 et 20 min après réception (tirage au hasard) ; hors
  heures : le lendemain entre 8 h et 9 h. Valeurs dans la policy.
- Bugs constatés à corriger :
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
  1. subscriptions : aujourd'hui toutes rattachées au faux business
     'serge-collect-stripe' (en dur dans serge/collect/abonnements.py) →
     rattacher au vrai business via l'identifiant inscrit dans Stripe ;
     colonnes ajoutées à la volée (assurer_colonnes) → vraie migration.
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
6. Invocations et liens, 7. Étape 1, 8. Conversations, 9. Grille de points,
10. Étapes 2 et 5, 11. Étapes 3, 4, 6, 7, 8, 12. Web.

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
- Priorité : c'est la première chose à faire dans le lot 6, à cause du
  risque de double envoi.

### Q52 — Délais de réponse par canal (validé)
Le délai avant de répondre à un prospect se règle canal par canal dans
MC, sur la fiche du canal : délai minimum, délai maximum, heures et jours
ouvrés. Exemple : e-mail entre 5 et 20 minutes, LinkedIn entre 1 et
4 heures, SMS tout de suite. Aujourd'hui c'est un seul réglage pour tous.

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
- Conception des tables en cours : [`LOT6_CONCEPTION.md`](LOT6_CONCEPTION.md).
- But à terme (lot plus loin) : un éditeur sans code dans MC, pour
  modifier en direct le pipeline : le nombre d'invocations, leur ordre,
  leur rôle, leur modèle, ce qu'elles voient.

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
   code écrit en dur pour un enchaînement est supprimé avec ses tests. Ce
   qui existait avant n'a pas à rester en marche.
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
