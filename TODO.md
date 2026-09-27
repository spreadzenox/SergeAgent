# À faire

La liste de ce qui reste à construire. Ce qui est fait n'y est plus : c'est
dans l'historique git.

Chaque élément suit le même modèle :

- **Quoi** : ce qu'on veut pouvoir faire, avec un exemple.
- **Pourquoi** : en une phrase.
- **Dépend de** : ce qui doit exister avant, s'il y a lieu.

Les décisions derrière chaque élément sont dans
[`docs/DECISIONS_REVUE.md`](docs/DECISIONS_REVUE.md) (le numéro de question
est indiqué entre parenthèses, exemple : Q13).

---

## Ordre de travail

On avance par petits lots : un sujet, un commit, des tests verts.

1. **Données** : ventures, contacts, livraisons, demandes clients,
   abonnements (section Transverse).
2. **Invocations et liens** : suppression des kinds et des capsules,
   liens entre invocations, priorités, tools automatiques (Transverse).
3. **Étape 1** refaite.
4. **Conversations** : fil par prospect, « Traiter une réponse », relances
   (Étapes 3 et 6).
5. **Grille de points** (Transverse).
6. **Étapes 2 et 5** : concevoir, challenger, construire, mettre en ligne.
7. **Étapes 3, 4, 6, 7, 8.**
8. **Web** : navigation, agent web, connecteurs (Transverse).

---

## Transverse

### Une seule table pour les business (Q13, Q15, Q44)

- **Quoi** : fondre `business_candidates` et `poc_selections` dans
  `ventures`. Ajouter les colonnes de la fiche (titre, description,
  observations, offre vendable), les statuts `POC_SELECTED`, `PARKED`,
  `MAINTENANCE`, `CLOSED`, et les dates de début et de fin du test léger.
  Écrire chaque changement de statut dans le journal.
- **Pourquoi** : aujourd'hui, un même business peut exister dans trois
  tables qui se contredisent.

### Les places de test (Q14)

- **Quoi** : deux réglages dans la policy, 3 places en prospection légère
  et 1 en prospection lourde. Pas de file d'attente. Exemple : si les
  3 places légères sont prises, l'étape 1 ne lance pas de cycle et Mission
  Control affiche « 3 places sur 3 occupées ».
- **Pourquoi** : ne pas tester plus de business qu'on ne peut en suivre.
- **Dépend de** : une seule table pour les business.

### Contacts : une fiche par personne (Q17)

- **Quoi** : une ligne par personne dans `contacts`, et une nouvelle table
  avec une ligne par adresse (canal, valeur, active ou non). Regroupement
  automatique seulement sur un e-mail ou un téléphone identique, jamais sur
  une adresse générique comme `contact@…`. Supprimer la colonne JSON
  `contact_reference_by_canal`.
- **Pourquoi** : aujourd'hui, une nouvelle adresse écrase l'ancienne sans
  prévenir, et un désabonnement doit valoir pour la personne entière.

### Livraisons, demandes clients, abonnements (Q43, Q45)

- **Quoi** :
  - une table `deliveries` : une ligne par chose vendue à livrer, créée à
    chaque paiement d'un produit qui n'est pas instantané ;
  - une table `product_requests` : les bugs, insatisfactions et demandes
    des clients ;
  - rattacher chaque abonnement Stripe à son vrai business. Aujourd'hui
    ils sont tous rattachés à `serge-collect-stripe`, écrit en dur dans
    `serge/collect/abonnements.py`. Remplacer aussi les colonnes ajoutées à
    la volée (`assurer_colonnes`) par une migration.
- **Pourquoi** : sans ça, Serge ne sait pas ce qui reste à livrer ni quand
  un business peut être fermé.

### Supprimer les kinds (Q7)

- **Quoi** : une tâche en file pointe directement vers une invocation (LLM
  ou technique). Le coupe-circuit se pose sur l'invocation. Supprimer
  `work_items.kind`, les interrupteurs `kind.*`, `KIND_DEFAUT` et le
  dispatch par kind. Au passage, vérifier `scheduler.enqueue`, qui calcule
  l'identifiant avec `hash()` (différent à chaque redémarrage de Python).
- **Pourquoi** : ce que Mission Control affiche doit être exactement ce qui
  tourne.

### Liens entre invocations (Q5, Q6)

- **Quoi** : un lien relie deux invocations et transporte des données.
  Exemple : « chaque business `POC_SELECTED` lance Concevoir le POC, avec
  son identifiant en paramètre ». Un résultat n'est transmis qu'une fois.
  Un bouton « passer à la suite » dans Mission Control, un interrupteur
  « passage automatique », et une invocation technique qui fait le passage
  toute seule quand l'interrupteur est allumé. Structure relationnelle
  propre, lisible depuis Mission Control.
- **Pourquoi** : aujourd'hui l'enchaînement est écrit en dur dans les
  workers et les liens ne servent qu'à afficher un compteur.
- **Dépend de** : supprimer les kinds.

### Tools : remplacer les capsules (Q4, Q12, Q25)

- **Quoi** : supprimer `db_readers`, `llm_point_readers`,
  `db_reader_fixed_params`, `db_reader_fixed_joins`. Le lien invocation ↔
  tool (`llm_point_tools`) porte le mode (donné d'office ou appelable) et
  les paramètres figés. Chaque invocation reçoit automatiquement trois
  tools : « historique de l'objet traité », « leçons »,
  « demander une nouvelle capacité ».
- **Pourquoi** : aujourd'hui les capsules ne sont pas appliquées quand le
  modèle appelle le tool. Exemple : la lecture des pages d'un cycle
  renvoie seulement leurs identifiants.

### Ce que voit une invocation (Q11, Q12, Q46)

- **Quoi** :
  - donner d'office ce que le lien apporte, en entier ;
  - donner la version courte des tables où l'invocation écrit ;
  - un maximum de lignes par défaut (exemple : 50), réglable ;
  - les leçons propres à l'invocation ;
  - le bloc « Qui est Serge et quelle est ta place » aux invocations de
    niveau moyen et intelligent.

  Mission Control affiche combien de lignes chaque invocation a reçues.
- **Pourquoi** : que chaque invocation ait ce qu'il lui faut, sans noyer
  son contexte.
- **Dépend de** : liens entre invocations ; tools.

### Priorités (Q38)

- **Quoi** : une priorité par invocation, réglable dans Mission Control.
  Valeurs de départ : 100 traiter une réponse, 80 relever les boîtes,
  50 envois et relances, 30 construction, 10 écoute et consolidation.
- **Pourquoi** : répondre à un prospect passe avant tout le reste.

### Grille de points (Q16)

- **Quoi** : une table de barème, une ligne par canal et par signal, de
  0 à 10 points, modifiable dans Mission Control. Deux chiffres par
  business : total de points et points par euro. Exemple de barème
  e-mail : ouvert 0,5, clic 1, réponse 4, veut acheter 10, refus 1.
- **Pourquoi** : comparer des tests faits sur des canaux différents, sans
  rater les signaux faibles.

### Recherche dans la mémoire

- **Quoi** : remplir l'index de `memory_search` au fil de l'eau (à chaque
  nouvelle leçon, nouvel événement, nouveau ticket).
- **Pourquoi** : aujourd'hui rien ne remplit cet index en production :
  `memory_search` ne renvoie jamais rien.

### Web (Q48)

- **Quoi** :
  - installer **SearXNG** sur le VPS et l'utiliser pour chercher ;
  - un tool « Lire une page » : requête simple, puis Chrome piloté par
    Playwright si la page a besoin de JavaScript, puis Browserbase si le
    site bloque. Chaque montée de niveau est écrite au journal ;
  - une invocation **« Agent web »** (Browser Use) qui accomplit une
    mission. Exemple : « crée un compte sur X ». Une session par compte,
    qui garde les cookies (`accounts_standing.profile_path`) ;
  - créer un compte de bout en bout : identité de Serge, code lu dans sa
    boîte mail ou ses SMS, captcha résolu par un humain (ticket Discord
    avec un lien vers l'écran en direct dans Mission Control), compte
    enregistré dans `accounts_standing` ;
  - une invocation **« Construire un connecteur »** quand une API gratuite
    existe. Julien valide le code par ticket avant activation.

  Le tool prévu `navigateur` disparaît au profit de ceux-ci.
- **Pourquoi** : Serge doit pouvoir tout faire sur le web avec son e-mail,
  son téléphone et sa carte, sans intervention humaine à chaque nouveau
  site.

### Garde de santé des comptes

- **Quoi** : chaque action faite avec un compte web appelle la garde
  (`serge/comptes_sante.py` : `autoriser` avant, `consommer` après).
- **Pourquoi** : la garde existe mais personne ne l'appelle ; un compte
  trop sollicité se fait bannir.
- **Dépend de** : web.

### Page Identité

- **Quoi** : un bouton pour modifier l'identité, qui appelle
  `ecrire_identite`, ou supprimer cette fonction.
- **Pourquoi** : aujourd'hui la fonction existe mais aucun bouton ne
  l'appelle.

### Docstrings qui renvoient à des documents supprimés

- **Quoi** : environ 100 docstrings et commentaires de `serge/` et `kit/`
  citent des repères d'anciens documents (« P2 », « R6 », « B §2.6 »,
  « matrice C », « D-spec »). Les réécrire en phrases claires au fil des
  changements, avec le renommage en anglais des noms.
- **Pourquoi** : ces repères ne mènent plus nulle part.

### Invocations écrites mais jamais appelées

- **Quoi** : pour chacune, la brancher dans le nouveau pipeline ou la
  supprimer. Liste : `voice_script`, `voice_dialog`, `summarize_thread`,
  `score_lead_departage`,
  `resume_test`, `draft_hypothesis_full`, `options_pivot`, `plan_scale`,
  `judge_allocator`, `build_artifact`, `review_build`,
  `summarize_build_debt`, `draft_hypothesis_smoke`, `discover_contacts`.
- **Pourquoi** : pas de code mort.

---

## Étape 1 — Pré-prospection

### Refaire l'étape en 7 invocations (Q8, Q9)

- **Quoi** : Lire les flux (technique), Explorer le web, Trier les pages
  (étiquette : enrichit un business / signal nouveau / bruit), Formuler
  des business A et B, Dédoublonner (technique), Choisir les business à
  tester (autant que de places libres), Refuser ceux déjà en test
  (technique). Détail : [`docs/etapes/1-pre-prospection.md`](docs/etapes/1-pre-prospection.md).
- **Pourquoi** : une invocation, un rôle ; aujourd'hui les découvertes font
  tout à la fois.
- **Dépend de** : liens entre invocations ; une seule table pour les
  business ; places.

### Garder toutes les pages lues (Q8)

- **Quoi** : chaque page lue par un flux ou par le web est enregistrée dans
  `listen_docs`, avec le cycle qui l'a trouvée. Elle peut servir de preuve.
- **Pourquoi** : aujourd'hui les business sont enregistrés sans aucune
  preuve.

### Les flux en base (Q9)

- **Quoi** : une table `listen_feeds` (adresse, ajouté par qui, actif,
  pages ramenées, pages utiles), éditable dans Mission Control. L'étape
  « Explorer le web » peut proposer des flux. La veille tourne toute seule.
- **Pourquoi** : aujourd'hui aucun flux n'est configuré et rien ne lance
  la collecte.

### Garde-fous de volume (Q9)

- **Quoi** : réglages de policy : N pages triées au maximum par cycle,
  pages « bruit » oubliées après X jours, flux désactivé après K cycles de
  bruit, fréquence de la veille.
- **Pourquoi** : que la base ne grossisse pas sans fin.

---

## Étape 2 — Conception du POC

### Concevoir, challenger, valider, construire (Q31, Q34, Q35, Q39)

- **Quoi** : Concevoir le POC (plan de A à Z, rythme des relances,
  livrable d'essai), Challenger le POC (remarques « à corriger » ou
  « nouvelle capacité nécessaire », 3 tours), ticket Discord à Julien avant
  construction, construction, mise en ligne sur un sous-domaine, création
  de la campagne. Détail : [`docs/etapes/2-conception-poc.md`](docs/etapes/2-conception-poc.md).
- **Pourquoi** : un POC doit proposer quelque chose de concret à essayer.
- **Dépend de** : liens entre invocations ; construction (étape 5).

---

## Étape 3 — Prospection légère

### Trouver des prospects (Q36)

- **Quoi** : une invocation qui cherche et qualifie des prospects
  pertinents, avec des adresses qui ne rebondissent pas, et garde la page
  source de chaque adresse. Sortie exacte à définir. Seulement vers des
  professionnels pour l'e-mail et l'appel.
- **Pourquoi** : Serge sait écrire et appeler, mais ne sait pas encore à
  qui.
- **Dépend de** : web ; contacts.

### Fil de discussion et relances réactives (Q37)

- **Quoi** : un fil par prospect, tous canaux (garder aussi le texte des
  envois). Rattacher chaque réponse au prospect, y compris par le fil
  e-mail. Une relance ne part que si le dernier événement est un envoi de
  Serge sans réponse, vérifié au moment de l'envoi. Aucune relance si les
  réponses d'un canal n'ont pas été relevées depuis plus d'une heure.
- **Pourquoi** : ne jamais relancer quelqu'un qui a déjà répondu.
- **Dépend de** : contacts.

### LinkedIn (Q48)

- **Quoi** : utiliser LinkedIn avec le compte de Serge, à un volume
  modéré, chaque message et publication validé par Julien. Les guards
  (`KNOWN_CHANNELS`) doivent connaître `linkedin`.
- **Pourquoi** : un canal de prospection B2B important.
- **Dépend de** : web.

### Autres canaux

- **Quoi** : WhatsApp, publication sur des forums ou Reddit, publicité
  (Google, Meta, LinkedIn, Reddit), SMS sortant. Pour chacun : le code qui
  écrit vraiment, son barème de points, sa fiche au catalogue.
- **Pourquoi** : chaque type de business n'a pas le même bon canal.
- **Dépend de** : web ; grille de points.

---

## Étape 4 — Choix du business principal

### Proposer, valider, mettre de côté (Q15, Q16 bis, Q44)

- **Quoi** : quand les 3 tests légers sont finis, une invocation propose
  le meilleur (avec points, points par euro et réponses), Julien valide par
  ticket (48 h sinon ça s'applique), les autres passent en `PARKED`.
  Comparer aussi les `PARKED` de moins de 60 jours.
- **Pourquoi** : c'est la décision la plus lourde du pipeline.
- **Dépend de** : places ; grille de points.

---

## Étape 5 — Construction

### Construire le vrai produit (Q41)

- **Quoi** : Concevoir le produit, le challenger, ticket Julien (prix
  définitif), construire avec le couple builder / reviewer (réponses
  « bon », « à corriger », « nouvelle capacité nécessaire »), mettre en
  ligne sur un domaine dédié, créer le produit Stripe et faire un paiement
  test de 1 € remboursé.
- **Pourquoi** : pas de prospection lourde sans pouvoir encaisser.

### Mettre en ligne et stocker (Q39, Q40)

- **Quoi** : publier via Caddy sur le VPS (sous-domaine pour un POC,
  domaine acheté pour le business principal). Ranger les fichiers dans
  `files/<business>/<livrable>/v<N>/`, jamais modifiés une fois publiés,
  avec leur fiche dans `artifacts`.
- **Pourquoi** : les livrables doivent être en ligne et retrouvables.

---

## Étape 6 — Prospection lourde

### Une seule invocation pour répondre (Q38)

- **Quoi** : « Traiter une réponse » lit le fil et rend le signal, la
  réponse ou « pas de réponse », et « besoin de Julien ». Elle remplace
  `classify_reply`, `reply_intent`, `review_other`, `extract_meeting`.
  Envoi entre 5 et 20 minutes après le message en heures ouvrées, le
  lendemain matin sinon. Son propre interrupteur, pour servir aussi
  l'étape 3.
- **Pourquoi** : aujourd'hui trois invocations lisent le même message
  chacune de leur côté.
- **Dépend de** : fil de discussion.

### Le point hebdomadaire (Q42)

- **Quoi** : « Faire le point sur le business principal » propose
  continuer, accélérer (+50 % ou un canal), pivoter ou arrêter. Pivoter et
  arrêter passent par Julien. Elle remplace `plan_scale`, `options_pivot`
  et `judge_allocator`.
- **Pourquoi** : une seule question, « on continue et à quelle vitesse ? ».

### Retours clients (Q43)

- **Quoi** : repérer les demandes sur le produit, corriger l'urgent tout
  de suite, préparer une version par semaine pour le reste, prévenir les
  clients concernés.
- **Pourquoi** : le produit s'améliore avec ses vrais utilisateurs.
- **Dépend de** : `product_requests` ; construction.

### Maintenance et fermeture (Q44)

- **Quoi** : passage en `MAINTENANCE` quand les quotas de prospection
  lourde sont épuisés ou que Julien valide « arrêter » ; passage
  automatique en `CLOSED` quand il ne reste rien à faire.
- **Pourquoi** : arrêter de prospecter n'est pas fermer le business.
- **Dépend de** : `deliveries`, `product_requests`, abonnements rattachés.

---

## Étape 7 — Mémoire

### Leçons plus précises (Q46)

- **Quoi** : une leçon obligatoire à chaque `KILLED` ou `CLOSED`.
  Rattacher chaque leçon à une invocation, sinon à une étape, sinon à tout
  Serge.
- **Pourquoi** : chaque invocation doit recevoir ce qu'on a appris sur son
  propre travail.

---

## Étape 8 — Caisse

### Encaisser proprement (Q47)

- **Quoi** : programmer les relances d'impayés (codées dans
  `serge/collect/dunning.py`, jamais lancées) en passant par le fil du
  client. Remboursement automatique sous un seuil (exemple : 50 €), ticket
  au-dessus. Factures émises par Stripe. Encaissé, dû et en retard par
  business dans Mission Control.
- **Pourquoi** : l'argent doit rentrer sans relancer un client qui a déjà
  répondu.
