# À faire

Ce fichier liste tout ce qui reste à construire dans Serge. Chaque tâche
est une case à cocher suivie d'un paragraphe qui explique d'où on part, ce
qu'il faut faire, pourquoi, et ce qui doit être réglable depuis Mission
Control. Quand une tâche est finie, on la retire du fichier : l'historique
git en garde la trace. Les échanges qui ont mené à chaque décision sont
dans [`docs/DECISIONS_REVUE.md`](docs/DECISIONS_REVUE.md).

Quelques mots reviennent souvent. **Mission Control** (MC) est la console
web où Julien voit et règle tout Serge. Une **invocation** est une brique
de travail : soit un appel au LLM avec son prompt (on parlait avant de
« jugement »), soit un traitement sans LLM. Un **business** (appelé
« venture » dans le code) est une idée de produit que Serge teste puis
vend. Un **POC** est le petit livrable d'essai qu'on montre aux prospects
pendant le test. La **prospection légère** est ce premier test, sur une
quarantaine de prospects ; la **prospection lourde** est la vente à grande
échelle du business retenu. La **policy** est la liste des réglages
chiffrés de Serge, modifiable dans MC. Un **ticket Discord** est une
question posée à Julien, où l'on peut discuter avant qu'il tranche.

---

## Dans quel ordre

On avance par lots. Un lot est un ensemble de tâches qui vont ensemble ;
chaque lot se termine par des tests verts et un commit, puis Julien ou
Clem regarde le résultat avant qu'on attaque le suivant.

- [ ] **Lot « Invocations et liens ».** C'est la fondation de tout le
  reste, donc on le fait en premier. Aujourd'hui, l'enchaînement des
  invocations est écrit en dur dans le code, et MC ne montre pas vraiment
  ce qui tourne. Ce lot supprime les « kinds » (les types de tâches du
  code), fait circuler les données d'une invocation à la suivante par des
  liens visibles dans MC, remplace les « capsules » de lecture de la base
  par un réglage sur le lien entre une invocation et ses tools, donne une
  priorité à chaque invocation, et donne automatiquement à chaque
  invocation les quelques tools dont elle a toujours besoin. Les tâches
  détaillées sont dans la partie « Pour tout Serge » plus bas.
- [ ] **Lot « Étape 1 ».** On refait la pré-prospection en sept
  invocations qui ont chacune un seul rôle, on garde toutes les pages lues
  comme preuves, et on met la liste des flux RSS en base. Ce lot vient
  juste après le premier parce qu'il a besoin des liens entre invocations.
- [ ] **Lot « Conversations ».** On crée un fil de discussion par
  prospect, une seule invocation pour lire et traiter une réponse, et des
  relances qui ne partent jamais vers quelqu'un qui a déjà répondu. C'est
  ce qui permet de parler à de vrais prospects sans faire d'erreur gênante.
- [ ] **Lot « Grille de points ».** On donne des points à chaque réaction
  d'un prospect, avec un barème par canal, pour pouvoir comparer deux
  tests faits sur des canaux différents.
- [ ] **Lot « Concevoir et construire ».** On écrit le plan d'un POC, on
  le fait critiquer, Julien le valide, puis Serge construit et met en
  ligne, d'abord le POC, ensuite le vrai produit. Ce sont les étapes 2
  et 5.
- [ ] **Lot « Le reste des étapes ».** Trouver des prospects (étape 3),
  choisir le business principal (étape 4), la prospection lourde et la vie
  du business (étape 6), des leçons plus précises (étape 7) et une caisse
  propre (étape 8).
- [ ] **Lot « Web ».** On donne à Serge de quoi chercher, lire des pages
  et agir sur n'importe quel site : créer un compte, publier, écrire. On
  le met en dernier parce que c'est le plus gros chantier, mais plusieurs
  tâches des étapes 3 et 6 en dépendent.

---

## Pour tout Serge

- [ ] **Les places de test.** Serge ne doit pas tester plus de business
  qu'il ne peut en suivre. Il faut trois places en prospection légère et
  une seule en prospection lourde. Un business prend une place de
  prospection légère dès qu'il est choisi à l'étape 1 et la garde pendant
  les étapes 2 et 3. Il n'y a pas de file d'attente : quand les trois
  places sont prises, l'étape 1 ne lance plus de cycle et MC affiche
  « 3 places sur 3 occupées ». Les deux nombres (3 et 1) doivent être
  modifiables dans MC. Aujourd'hui, le code impose seulement « un seul
  business actif à la fois », ce qui ne correspond plus à ce qu'on veut.

- [ ] **Les livraisons et les demandes des clients.** Serge ne sait pas
  aujourd'hui ce qui reste à livrer à un client, ni ce que les clients lui
  ont demandé. Il faut une table des livraisons, avec une ligne par chose
  vendue à livrer : le business, le client, le paiement, ce qu'il faut
  livrer, la date promise, l'état (à faire, en cours, livrée, problème) et
  le fichier livré. Une ligne est créée à chaque paiement d'un produit qui
  n'est pas livré instantanément, et une livraison en retard apparaît dans
  MC et passe en priorité haute. Il faut aussi une table des demandes
  clients : les bugs, les insatisfactions et les idées d'amélioration. Ces
  deux tables sont créées en même temps que le code qui les remplit (le
  traitement des réponses et l'encaissement), pour ne pas laisser dans la
  base une table vide que personne n'écrit. Sans elles, on ne peut pas
  savoir quand un business peut être fermé.

- [ ] **Supprimer les « kinds ».** Aujourd'hui, le moteur qui exécute les
  tâches (le runner) reçoit des tâches typées par un « kind », par exemple
  « lancer un cycle d'écoute ». Un kind lance plusieurs invocations d'un
  coup, et chaque kind a son propre interrupteur. Résultat : ce que MC
  affiche comme catalogue d'invocations ne correspond pas exactement à ce
  qui tourne. Il faut qu'une tâche en file pointe directement vers une
  invocation, et que l'interrupteur pour couper quelque chose se trouve
  sur l'invocation elle-même. Au passage, il faut corriger la façon dont
  une tâche reçoit son identifiant : il est calculé avec une fonction de
  Python qui donne un résultat différent à chaque redémarrage, ce qui peut
  créer des doublons.

- [ ] **Des liens entre invocations qui transportent des données.**
  Aujourd'hui, les liens affichés dans MC relient des étapes et ne servent
  qu'à afficher un compteur ; l'enchaînement réel est écrit en dur dans le
  code. Il faut qu'un lien relie deux invocations et transmette des
  données de l'une à l'autre. Par exemple, chaque business choisi à
  l'étape 1 doit lancer la conception de son POC, avec l'identifiant du
  business en paramètre. Un même résultat ne doit être transmis qu'une
  seule fois. Dans MC, chaque lien a un bouton « passer à la suite » pour
  déclencher le passage à la main, et un interrupteur « passage
  automatique » ; quand il est allumé, une petite invocation sans LLM fait
  le passage toute seule. La structure en base doit rester simple à lire :
  une table des liens, et on voit dans MC ce qui est passé et ce qui
  attend. Cette tâche vient après la suppression des kinds.

- [ ] **Remplacer les « capsules » par un réglage sur le lien entre une
  invocation et un tool.** Une capsule est aujourd'hui un tool de lecture
  de la base avec des paramètres figés, décrit dans quatre tables à part.
  Le problème : quand le modèle appelle ce tool lui-même, les paramètres
  figés ne sont pas appliqués. Par exemple, la lecture des pages d'un
  cycle renvoie seulement leurs numéros, pas leur titre ni leur texte. Il
  faut supprimer ces quatre tables et mettre le réglage sur le lien entre
  l'invocation et le tool : ce lien dit si le tool est donné d'office
  (Serge fait la lecture avant l'appel et met le résultat dans le prompt)
  ou appelable (le modèle décide de l'appeler), et quels paramètres sont
  figés. En plus, chaque invocation doit recevoir automatiquement trois
  tools : lire l'historique de l'objet qu'elle traite, lire les leçons, et
  demander une nouvelle capacité à Julien.

- [ ] **Ce que voit chaque invocation.** Une invocation doit avoir tout
  ce qu'il lui faut pour travailler, sans qu'on noie son prompt sous des
  informations inutiles. Elle reçoit en entier ce que le lien entrant lui
  apporte (par exemple, la page qu'elle doit trier). Elle reçoit une
  version courte des tables où elle écrit, pour pouvoir comparer (par
  exemple, juste le numéro et le titre des business déjà connus). Chaque
  information donnée d'office a un nombre maximum de lignes, 50 par
  défaut, réglable invocation par invocation ; s'il y en a plus,
  l'invocation reçoit les plus récentes et une phrase qui dit combien ne
  sont pas montrées. Elle reçoit aussi ses propres leçons, et, si elle
  utilise un modèle moyen ou intelligent, un court texte qui lui explique
  qui est Serge et où elle se trouve dans la chaîne. MC affiche, à chaque
  passage, combien de lignes l'invocation a reçues. Le détail de ces
  règles est dans [`docs/MEMOIRE.md`](docs/MEMOIRE.md). Cette tâche vient
  après les liens et les tools.

- [ ] **Une priorité par invocation.** Quand plusieurs tâches sont
  prêtes, le runner doit toujours prendre la plus urgente. Chaque
  invocation a donc une priorité, modifiable dans MC. Valeurs de départ :
  100 pour traiter la réponse d'un prospect ou une désinscription, 80 pour
  relever les boîtes mail et les autres messages entrants, 50 pour les
  envois et les relances, 30 pour la construction, 10 pour l'écoute du
  web, la veille et la consolidation des leçons. Répondre à un prospect
  passe avant tout le reste.

- [ ] **La grille de points.** Chaque canal (e-mail, appel, publicité,
  réseau social, page web) traduit déjà ce qui se passe en réactions
  communes : a vu, a réagi, a répondu, veut acheter, refuse, se
  désinscrit. Il faut une table de barème, avec une ligne par canal et par
  réaction, qui donne de 0 à 10 points, modifiable dans MC. Exemple pour
  l'e-mail : ouvert 0,5 point, clic 1, réponse 4, veut acheter 10, refus 1
  (un refus poli montre quand même que le besoin intéresse). Chaque
  business affiche alors deux chiffres : le total de ses points, et ses
  points par euro dépensé. C'est ce qui permet de comparer un test fait
  par e-mail et un test fait par appel, sans rater les signaux faibles.

- [ ] **Remplir l'index de recherche dans la mémoire.** Le tool qui
  permet à une invocation de chercher dans la mémoire de Serge (leçons,
  événements, tickets) s'appuie sur un index de recherche. En production,
  rien ne remplit cet index, donc ce tool ne renvoie jamais rien. Il faut
  ajouter chaque nouvelle leçon, chaque nouvel événement et chaque nouveau
  ticket à l'index au moment où ils sont écrits.

- [ ] **Le web.** Serge doit pouvoir tout faire sur le web avec son
  e-mail, son téléphone et sa carte, sans qu'un humain intervienne à
  chaque nouveau site. Il faut d'abord installer sur le serveur un moteur
  de recherche gratuit et sans clé (SearXNG), et s'en servir à la place de
  la page de résultats de DuckDuckGo. Il faut ensuite un tool « Lire une
  page » qui monte d'un cran seulement si nécessaire : une simple requête,
  puis un vrai navigateur Chrome piloté si la page a besoin de JavaScript,
  puis un service de navigateur distant si le site bloque ; chaque montée
  est écrite au journal. Il faut une invocation « Agent web » qui
  accomplit une mission sur un site, par exemple « crée un compte sur ce
  forum », avec une session par compte qui garde ses cookies. Créer un
  compte doit marcher de bout en bout : identité de Serge, code de
  confirmation lu dans sa boîte mail ou ses SMS, captcha résolu par un
  humain via un ticket Discord qui donne un lien vers l'écran en direct
  dans MC, et compte enregistré dans la base. Enfin, quand un site a une
  API gratuite, une invocation « Construire un connecteur » écrit le code
  pour s'en servir, et Julien valide ce code par ticket avant qu'il soit
  activé. Le tool « navigateur » prévu jusqu'ici disparaît au profit de
  tout ça.

- [ ] **Brancher la garde de santé des comptes.** Un compte web trop
  sollicité se fait bannir. Le code d'une garde existe déjà : avant chaque
  action faite avec un compte, elle dit si c'est autorisé, et après, elle
  compte l'action. Mais personne ne l'appelle. Il faut que chaque action
  faite avec un compte web passe par elle. Cette tâche vient avec le web.

- [ ] **La page Identité de MC.** La fonction qui modifie l'identité de
  Serge (son nom, sa présentation) existe dans le code, mais aucun bouton
  de MC ne l'appelle. Il faut soit ajouter ce bouton, soit supprimer la
  fonction.

- [ ] **Réécrire les commentaires qui renvoient à des documents
  supprimés.** Une centaine de commentaires dans le code citent des
  repères d'anciens documents qui n'existent plus, comme « P2 »,
  « R6 » ou « matrice C ». Il faut les réécrire en phrases claires au fur
  et à mesure qu'on touche à ces fichiers, et en profiter pour passer en
  anglais les noms de fonctions et de variables.

- [ ] **Brancher ou supprimer les invocations jamais appelées.** Quatorze
  invocations LLM sont écrites, avec leur prompt, mais rien ne les lance :
  le script d'appel vocal, le dialogue vocal, le résumé d'un fil, le
  départage de deux prospects, le résumé d'un test, l'hypothèse de test
  lourd, les options de pivot, le plan de passage à l'échelle, l'arbitre
  du budget, la construction d'un livrable, la relecture d'un livrable, le
  résumé de la dette de construction, l'hypothèse de test léger, et la
  découverte de contacts. Pour chacune, il faut soit la brancher dans le
  nouveau pipeline, soit la supprimer. On ne garde pas de code mort.

---

## Étape 1 — Pré-prospection

- [ ] **Refaire l'étape en sept invocations qui ont chacune un seul
  rôle.** Aujourd'hui, deux invocations « Explorer les besoins » font tout
  à la fois : chercher sur le web, lire, repérer des besoins et en tirer
  des idées de business. Il faut découper le travail. D'abord, une
  invocation sans LLM lit les flux RSS suivis. Ensuite, « Explorer le
  web » cherche des pages à partir du petit texte de guidage que Julien
  écrit dans MC et des business déjà connus. « Trier les pages », avec un
  modèle rapide, met une étiquette sur chaque page nouvelle : elle
  enrichit un business déjà connu, elle signale un besoin nouveau, ou
  c'est du bruit. Deux invocations « Formuler des business », A et B,
  lisent les pages qui signalent un besoin et écrivent chacune des fiches
  de business avec leurs pages de preuve ; B ne voit jamais ce qu'a écrit
  A, pour avoir des idées variées. Une invocation sans LLM écarte les
  doublons et enregistre le reste comme candidats. « Choisir les business
  à tester » en choisit autant qu'il y a de places libres en prospection
  légère. Enfin, une invocation sans LLM refuse tout business déjà en
  test : c'est une protection écrite dans le code, pas une consigne dans
  un prompt. Le cycle se lance à la main depuis MC, et ne tourne que s'il
  reste une place libre. Le prompt des invocations qui formulent et
  choisissent doit dire que le business doit être légal, et les
  encourager à ne pas s'arrêter sur des scrupules moraux qui ne sont pas
  contraires à la loi. Le détail est dans
  [`docs/etapes/1-pre-prospection.md`](docs/etapes/1-pre-prospection.md).
  Cette tâche a besoin des liens entre invocations et des places de test.

- [ ] **Garder toutes les pages lues.** Aujourd'hui, les pages trouvées
  par la recherche web ne sont pas enregistrées, et comme aucun flux RSS
  n'est configuré, la table des pages est vide en production. Résultat :
  les business sont enregistrés sans aucune preuve du besoin. Il faut que
  chaque page lue, par un flux ou par le web, soit enregistrée avec sa
  source et le cycle qui l'a trouvée, pour pouvoir servir de preuve.

- [ ] **Mettre la liste des flux RSS en base.** Aucun flux n'est
  configuré aujourd'hui, et rien ne lance leur lecture. Il faut une table
  des flux, modifiable dans MC, avec pour chaque flux son adresse, qui l'a
  ajouté (Julien ou une invocation), s'il est actif, combien de pages il a
  ramenées et combien étaient utiles. L'invocation « Explorer le web » peut
  proposer de nouveaux flux. La lecture des flux tourne toute seule, à
  intervalle régulier, sans LLM.

- [ ] **Empêcher la base de grossir sans fin.** Il faut quatre réglages,
  modifiables dans MC : le nombre maximum de pages triées par cycle, le
  nombre de jours après lequel une page « bruit » est oubliée (une page qui
  sert de preuve est toujours gardée), le nombre de cycles après lequel un
  flux qui ne ramène que du bruit est désactivé, et la fréquence de
  lecture des flux.

---

## Étape 2 — Conception du POC

- [ ] **Concevoir, faire critiquer, valider, construire.** Un POC doit
  proposer quelque chose de concret à essayer, pas seulement une promesse.
  Pour chaque business choisi, une invocation « Concevoir le POC » écrit
  un plan de A à Z : le livrable d'essai, les prospects visés, les canaux,
  le rythme des relances. Une deuxième invocation, « Challenger le POC »,
  relit ce plan et ne peut répondre que deux choses par remarque : « à
  corriger » ou « il faut une nouvelle capacité ». On fait au plus trois
  allers-retours, et le plan final doit être réalisable avec ce que Serge
  sait faire. Julien valide ensuite le plan dans un ticket Discord ; sans
  réponse sous 48 heures, le plan s'applique. Serge construit alors le
  livrable, le met en ligne sur un sous-domaine, et crée la campagne de
  test. Le détail est dans
  [`docs/etapes/2-conception-poc.md`](docs/etapes/2-conception-poc.md).
  Cette tâche a besoin des liens entre invocations et de la construction
  de l'étape 5.

---

## Étape 3 — Prospection légère

- [ ] **Trouver des prospects.** Serge sait écrire des e-mails et passer
  des appels, mais il ne sait pas encore à qui. Aujourd'hui, l'invocation
  de découverte de contacts enregistre seulement les contacts qu'on lui
  donne ; elle ne cherche rien, et personne ne l'appelle. Il faut une
  invocation qui cherche et qualifie des prospects pertinents pour le
  business testé, avec des adresses qui ne rebondissent pas, et qui garde
  la page d'où vient chaque adresse (il faudra ajouter cette information à
  la table des adresses de contact). Par e-mail et par téléphone, on ne
  contacte que des professionnels. Ce que l'invocation rend exactement
  reste à définir. Cette tâche a besoin du web.

- [ ] **Un fil de discussion par prospect, et des relances qui ne gênent
  personne.** La règle est simple : on ne relance jamais quelqu'un qui a
  déjà répondu. Pour la tenir, il faut un fil par prospect, tous canaux
  confondus, qui garde aussi le texte de ce que Serge a envoyé. Chaque
  réponse reçue doit être rattachée au bon prospect, y compris quand elle
  arrive dans le fil d'un e-mail. Une relance ne part que si le dernier
  événement du fil est un envoi de Serge resté sans réponse, et ce
  contrôle est refait au moment exact de l'envoi. Si les réponses d'un
  canal n'ont pas été relevées depuis plus d'une heure, aucune relance ne
  part sur ce canal.

- [ ] **Prospecter sur LinkedIn.** LinkedIn est un canal important pour
  vendre à des professionnels. Serge l'utilise avec son propre compte, à
  un volume modéré, et Julien valide chaque message et chaque publication
  avant qu'ils partent. Les garde-fous d'envoi doivent connaître ce canal.
  Cette tâche a besoin du web.

- [ ] **Les autres canaux.** Chaque type de business n'a pas le même bon
  canal. Il faut ajouter WhatsApp, la publication sur des forums ou
  Reddit, la publicité (Google, Meta, LinkedIn, Reddit) et l'envoi de SMS.
  Pour chaque canal, il faut le code qui envoie vraiment, son barème de
  points et sa fiche dans le catalogue de MC. Cette tâche a besoin du web
  et de la grille de points.

---

## Étape 4 — Choix du business principal

- [ ] **Proposer le meilleur business, le faire valider, mettre les
  autres de côté.** C'est la décision la plus lourde de toute la chaîne.
  Quand les trois tests légers sont finis, une invocation compare les
  business testés et propose le meilleur, avec pour chacun ses points,
  ses points par euro dépensé et les réponses des prospects. Julien valide
  dans un ticket Discord ; sans réponse sous 48 heures, le choix proposé
  s'applique. Les autres business sont mis de côté : ils libèrent leur
  place, mais ils peuvent être repris plus tard. La comparaison inclut
  aussi les business mis de côté dont le test date de moins de 60 jours ;
  au-delà, ils redeviennent de simples candidats. Cette tâche a besoin des
  places de test et de la grille de points.

---

## Étape 5 — Construction

- [ ] **Construire le vrai produit.** Pas de prospection lourde sans
  pouvoir encaisser. Une invocation conçoit le produit, une autre le
  critique, puis Julien valide dans un ticket, en fixant le prix
  définitif. Serge construit ensuite le produit avec un duo : un
  constructeur qui écrit, un relecteur qui répond « bon », « à corriger »
  ou « il faut une nouvelle capacité ». Le produit est mis en ligne sur un
  domaine acheté pour lui. Serge crée le produit et son prix dans Stripe,
  en inscrivant sur le prix l'identifiant du business, pour que chaque
  abonnement soit rattaché au bon business. Il fait enfin un paiement de
  test de 1 € qu'il se rembourse, pour vérifier que tout marche.

- [ ] **Mettre en ligne et ranger les fichiers.** Les livrables doivent
  être en ligne et faciles à retrouver. Serge les publie sur son serveur,
  sur un sous-domaine pour un POC et sur un domaine acheté pour le
  business principal. Chaque version d'un livrable est rangée dans son
  propre dossier (le business, le livrable, puis le numéro de version), et
  n'est plus jamais modifiée une fois publiée. Chaque fichier a sa fiche
  dans la base.

---

## Étape 6 — Prospection lourde

- [ ] **Une seule invocation pour traiter une réponse.** Aujourd'hui,
  trois ou quatre invocations lisent le même message de prospect chacune
  de leur côté : l'une le classe, l'autre cherche l'intention, une autre
  cherche un rendez-vous. Il faut les remplacer par une seule invocation,
  « Traiter une réponse ». Elle lit le fil du prospect et rend trois
  choses : la réaction du prospect, la réponse à envoyer (ou « pas de
  réponse »), et si Julien doit intervenir. La réponse part entre 5 et 20
  minutes après le message du prospect pendant les heures de bureau, et le
  lendemain matin sinon. Cette invocation a son propre interrupteur, car
  elle sert aussi pendant la prospection légère. Elle a besoin du fil de
  discussion.

- [ ] **Faire le point chaque semaine sur le business principal.** Une
  seule question compte : on continue, et à quelle vitesse ? Une fois par
  semaine, une invocation propose de continuer, d'accélérer (50 % de
  prospects en plus ou un canal de plus), de pivoter ou d'arrêter. Pivoter
  et arrêter passent par Julien. Cette invocation remplace trois
  invocations qui existent aujourd'hui sans être appelées (plan de passage
  à l'échelle, options de pivot, arbitre du budget).

- [ ] **Améliorer le produit avec les retours des clients.** Serge repère
  dans les messages des clients ce qui concerne le produit : un bug, une
  insatisfaction, une idée. Il corrige tout de suite ce qui est urgent,
  prépare une nouvelle version par semaine pour le reste, et prévient les
  clients concernés quand leur demande est traitée. Cette tâche a besoin
  de la table des demandes clients et de la construction.

- [ ] **Maintenance et fermeture d'un business.** Arrêter de prospecter
  n'est pas fermer le business : il y a encore des clients à livrer, des
  messages à traiter et de l'argent à encaisser. Un business passe en
  maintenance quand les quotas de prospection lourde sont épuisés, ou
  quand Julien valide « arrêter » alors que le business a déjà des
  clients (sans aucun client, il est simplement arrêté). En maintenance,
  Serge ne contacte plus de nouveaux prospects, mais il livre, répond,
  corrige, encaisse les abonnements et relance les impayés ; un client qui
  revient de lui-même est servi. Le passage en maintenance libère la place
  de prospection lourde. Le business est fermé automatiquement quand il ne
  reste plus rien à faire : aucune livraison due, aucun abonnement actif,
  aucune demande client ouverte, et aucun message de client depuis 30
  jours (réglable dans MC). À la fermeture, il est archivé, Serge en tire
  une leçon et Julien reçoit un ticket d'information. Cette tâche a besoin
  des tables des livraisons et des demandes clients.

---

## Étape 7 — Mémoire

- [ ] **Des leçons plus précises.** Chaque invocation doit recevoir ce
  qu'on a appris sur son propre travail. Il faut donc rattacher chaque
  leçon à une invocation précise, sinon à une étape, sinon à tout Serge.
  Et chaque business arrêté ou fermé doit obligatoirement produire au
  moins une leçon, pour ne pas refaire les mêmes erreurs.

---

## Étape 8 — Caisse

- [ ] **Encaisser proprement.** L'argent doit rentrer sans jamais
  relancer un client qui a déjà répondu. Les relances d'impayés sont déjà
  écrites dans le code (polie après 7 jours, ferme après 14, puis arrêt et
  ticket), mais rien ne les lance : il faut les programmer, en les faisant
  passer par le fil du client. Un remboursement sous un seuil (par
  exemple 50 €, réglable dans MC) est fait automatiquement, avec un ticket
  pour informer Julien ; au-dessus, Julien décide dans un ticket. Les
  factures sont émises par Stripe, jamais fabriquées par Serge. MC
  affiche, business par business, ce qui a été encaissé, ce qui est dû et
  ce qui est en retard.
