# Lot 10 — Conception : concevoir, construire et tester les produits

Ce document décrit comment Serge conçoit un produit, le construit, le
teste comme le ferait un humain, puis le met en ligne : d'abord le POC
(étape 2), ensuite le vrai produit (étape 5). Il suit les réponses de Clem
du 13 octobre 2026 (décision Q91 de
[`DECISIONS_REVUE.md`](DECISIONS_REVUE.md)), les décisions déjà prises
sur les étapes 2 et 5 (Q34, Q35, Q39 à Q41, Q43, Q76), et la règle de
tous les lots : le code n'est qu'un interpréteur de la base, jamais de
code propre à une invocation.

Pourquoi ce lot est différent des autres : un produit sera utilisé par des
humains, qui cliquent et regardent l'écran. On ne peut pas se contenter
d'un LLM qui écrit du code et dit « ça marche ». Le constructeur doit
pouvoir lancer son produit, l'ouvrir dans un navigateur, regarder ce qu'il
a fait et cliquer dedans. Un relecteur, qui ne voit jamais le code,
l'essaie ensuite comme un prospect ordinaire. Puis un humain l'essaie
lui-même avant qu'aucun prospect ne le voie.

**Seulement des produits web.** Au lot 10, Serge construit des services
web, payants pour le produit fini : on paie pour avoir un compte et
utiliser le service. Les logiciels (application de bureau, extension de
navigateur, bot) attendent le lot 14.

Le lot se livre en cinq PR, l'une après l'autre ; chacune se fusionne dès
que sa CI est verte, et Clem l'essaie dans Mission Control (décision Q91) :

1. **Le chantier** (parties 1 et 3) : un conteneur par produit et ses
   quatre outils. Essai : le bouton « Essayer le chantier » de la page
   Système.
2. **Voir et cliquer** (parties 2, 3 et 4) : le navigateur, les captures
   envoyées au modèle, le niveau « code ». Essai : « Essayer l'interface
   web ».
3. **Publier** (partie 5) : les versions, le staging et la prod, les
   routes de Caddy en base. Essai : publier le chantier d'essai.
4. **L'étape 2** (parties 7, 8 et 10) : concevoir, challenger,
   construire, relire, les tickets, la prod du POC. Essai : le vrai
   chemin, depuis un cycle d'écoute.
5. **L'étape 5 et Stripe** (parties 6 et 9) : « Appeler une API », Stripe,
   l'achat du domaine, le paiement test.

Les parties de ce document, dans l'ordre où on les construit :

1. Le bac à sable : un chantier par produit (partie 1).
2. L'interface web des invocations (partie 2).
3. Ce que l'interpréteur apprend : les images, les longues sessions
   (partie 3).
4. Le niveau de modèle « code » (partie 4).
5. Publier : staging et prod (partie 5).
6. « Appeler une API », et Stripe (partie 6).
7. Les tables (partie 7).
8. L'étape 2 dans le pipeline (partie 8).
9. L'étape 5 dans le pipeline (partie 9).
10. Les tickets (partie 10).
11. Les réglages (partie 11).
12. Mission Control (partie 12).
13. La sécurité (partie 13).
14. Les tests (partie 14).

La partie 15 liste ce qui reste ouvert.

---

## 1. Le bac à sable : un chantier par produit

Un **chantier** est un conteneur Docker où le constructeur écrit son
produit et le lance. Ce n'est pas une vraie machine virtuelle : une vraie
VM demande la virtualisation imbriquée, rarement disponible sur un VPS,
et un conteneur suffit pour des produits web. Docker rootless tourne
déjà sur le VPS, pour l'utilisateur `serge` (vérifié le 13 octobre 2026).

Un chantier par business et par livrable. Il est gardé entre deux tâches :
ses fichiers restent sur un volume à lui. Exemple : le constructeur
s'arrête le soir parce que le plafond du jour est atteint ; le lendemain,
la tâche suivante retrouve ses fichiers et reprend.

**Un seul chantier allumé à la fois** sur le VPS (Q91) : allumer un
chantier éteint les autres, qui gardent leurs fichiers. La file des
travaux ne lance qu'une tâche à la fois : rien n'attend.

**Les profils de bac à sable sont des réglages de la page Policy**
(famille « Bac à sable ») : l'image de départ (un Linux avec git, Python,
Node et les outils courants), les processeurs, la mémoire, le disque, la
durée maximale d'une commande, et si le conteneur peut joindre Internet.
Une invocation dit quel profil elle utilise par un paramètre figé de ses
outils (`profile: chantier`). Le profil « chantier » de départ : 2
processeurs, 4 Go de mémoire, 20 Go de disque, 10 minutes au plus par
commande, Internet permis (pour installer des paquets). Ces chiffres se
règlent sur la page Policy. Le VPS a 4 processeurs, 15 Go de mémoire, pas
de swap, et 155 Go de disque libre (relevé le 13 octobre 2026) : un
chantier y tient largement, à côté de Serge, du navigateur et des
produits en ligne. Sans swap, la limite de mémoire compte : un programme
du conteneur qui la dépasse est arrêté, au lieu de ralentir tout le VPS.
Docker rootless y limite bien la mémoire, les processeurs et le nombre de
programmes d'un conteneur (vérifié le 13 octobre 2026). Il ne limite ni
la place sur le disque ni la vitesse des lectures et écritures : Serge
mesure lui-même la place prise par un chantier, et l'arrête quand il
dépasse son disque permis.

**Quatre outils**, des capacités générales comme les autres :

- **Lancer une commande** : rend la sortie et le code de retour, coupés à
  la taille maximale d'un résultat d'outil (20 000 caractères au départ,
  page Pipeline). Une commande peut tourner en arrière-plan (un serveur de
  développement, par exemple) : l'outil rend la main tout de suite, et la
  sortie va dans un fichier qu'on peut lire ensuite.
- **Lire un fichier**, avec un numéro de première ligne et un nombre de
  lignes, pour ne pas renvoyer un gros fichier en entier.
- **Écrire un fichier** entier.
- **Modifier un fichier** : remplacer un passage exact par un autre. C'est
  moins cher que de réécrire tout le fichier.

Le chantier d'une tâche est un paramètre figé, tiré du business de la
tâche : une invocation n'agit jamais dans le chantier d'un autre
business. Le modèle ne peut pas choisir un autre chantier.

**Aucune façon de coder n'est imposée** (Q91) : le constructeur choisit
ses langages et ses outils. Une seule règle, pour que Serge sache démarrer
le produit : le dossier du produit contient un `Dockerfile`, et le
programme écoute sur le port donné par la variable `PORT`.

---

## 2. L'interface web des invocations

Une invocation doit voir une page et y agir comme un humain. C'est ce
dont ont besoin le constructeur, pour vérifier son travail, et le
relecteur, qui ne fait que ça. Le lot 12 réutilisera la même interface
pour créer des comptes sur n'importe quel site.

**Un navigateur Chrome dans son propre conteneur**, piloté par Serge avec
Playwright, déjà installé. Le navigateur ne tourne jamais dans le
programme de Serge : une page inconnue ne peut pas l'atteindre. Une
session de navigateur par tâche ; le lot 12 ajoutera une session par
compte, qui garde ses cookies.

**Les outils**, chacun une capacité générale :

- **Ouvrir une adresse.**
- **Lire la page** : la page décrite comme la lit un lecteur d'écran,
  ligne par ligne (titres, textes, champs, boutons, liens), chaque élément
  avec un repère court qu'on cite pour agir. Exemple : `bouton « Créer un
  compte » [e7]`, `champ « E-mail » [e9]`. C'est ce que fait Playwright
  MCP, l'outil libre de Microsoft : bien moins cher qu'une capture, et
  plus sûr que de viser des pixels.
- **Cliquer** sur un repère.
- **Taper** du texte dans un champ, en validant ou non avec Entrée.
- **Taper un secret** : le modèle désigne le champ et le nom du secret
  (« numéro de carte de Serge ») ; Serge tape la valeur. Le modèle ne la
  voit jamais, et elle n'apparaît jamais au journal.
- **Choisir** une option dans une liste.
- **Appuyer sur une touche** (Échap, Tab…).
- **Faire défiler** la page.
- **Revenir** à la page précédente.
- **Prendre une capture** : l'image est envoyée au modèle, et gardée comme
  preuve si l'invocation le demande (partie 7).
- **Changer la taille de l'écran** : ordinateur (1280 × 800) ou mobile
  (390 × 844).
- **Lire les erreurs de la page** : les erreurs JavaScript et les requêtes
  qui ont échoué.
- **Attendre** qu'un texte apparaisse, ou quelques secondes.
- **Envoyer un fichier** dans un champ prévu pour ça.

Après chaque action, l'outil rend la page relue, en version courte : le
modèle voit l'effet de son clic sans appel de plus.

Exemple : le relecteur ouvre `https://staging-devis-artisan.<domaine>`,
lit la page, clique sur « Créer un compte » `[e7]`, tape une adresse
e-mail dans `[e9]`, valide, prend une capture en taille mobile, et voit
que le bouton « Payer » sort de l'écran. Il le note comme remarque « à
corriger », avec la capture.

---

## 3. Ce que l'interpréteur apprend

Le constructeur et le relecteur restent des invocations de l'interpréteur
de Serge, décrites en base comme les autres (Q91). On n'utilise pas un
agent tout fait (OpenHands, OpenCode) qui tournerait dans le conteneur
avec sa propre boucle : c'est Serge qui appelle le modèle, chaque appel
est noté avec son coût réel, le plafond du jour est vérifié à chaque tour,
et aucune clé de modèle n'entre dans un conteneur. L'interpréteur doit
apprendre trois choses :

1. **Envoyer des images au modèle.** Une capture revient au modèle comme
   une image, pas comme du texte. Le client du modèle ne sait pas encore
   le faire.
2. **Tenir de longues sessions.** Une construction, c'est 100 à 300 tours
   d'outils, contre 4 pour « Choisir les business ». Le nombre de tours
   est déjà un réglage de chaque invocation (`max_tool_turns`) : 200 au
   départ pour « Construire », 60 pour « Relire ». Chaque tour renvoie
   tout l'historique au modèle ; le cache déjà demandé à OpenRouter pour
   les modèles d'Anthropic rend cette relecture dix fois moins chère.
3. **Ne renvoyer que les dernières captures.** Sinon, chaque tour renvoie
   toutes les anciennes images. Seules les 3 dernières captures restent
   dans l'historique (réglage de la page Pipeline) ; les autres sont
   remplacées par « [capture retirée] ».

**Le plafond du jour.** Il n'y a pas de budget par construction : tout
compte dans le plafond du jour, comme les autres appels au modèle (Q91).
Aujourd'hui, quand le plafond est atteint pendant une tâche, le modèle
doit répondre sans plus d'outil (Q66). Le constructeur rend alors un
compte rendu « pas fini » qui dit où il en est. Ses fichiers restent dans
le chantier, et un nouveau passage de construction attend le lendemain,
comme toute tâche LLM au plafond. Ce passage interrompu ne compte pas
dans les trois passages permis.

---

## 4. Le niveau de modèle « code »

Le constructeur et le relecteur ont besoin du meilleur modèle disponible,
à un prix raisonnable, qui sait lire une image (Q91). Un quatrième niveau
s'ajoute aux trois de Q57 (rapide, moyen, intelligent) : **« code »**.
C'est une ligne de plus dans `llm_models`, et un critère de plus pour la
recommandation de modèle : **lit les images** (nouvelle colonne, cochée
pour ce niveau).

Sa tolérance est de 100 % : la recommandation prend toujours le modèle à
la meilleure note sous le prix maximum du niveau, au lieu du meilleur
rapport note / prix. Prix maximum de départ : 12 $ le million de jetons,
au mélange de jetons lus et écrits mesuré par Serge.

Au 13 octobre 2026, ce niveau donne `anthropic/claude-opus-5.5` : note
57,6, contre 56,0 pour `anthropic/claude-sonnet-5.5`, recommandé au niveau
intelligent le 30 septembre ; 4 $ par million de jetons lus et 20 $ par
million de jetons écrits, deux fois le prix de Sonnet 5.5.

« Concevoir » et « Challenger » restent au niveau intelligent : ils
écrivent un plan, ils ne codent pas.

---

## 5. Publier : staging et prod

Une **version** est une copie figée du dossier du chantier, rangée dans
`files/<business>/<livrable>/v<N>/` avec sa fiche dans `artifacts`
(Q40). Une version n'est jamais modifiée : une correction crée la version
suivante.

**« Publier »** est une capacité sans LLM, avec trois paramètres : le
business, la version et la cible (staging ou prod). Elle :

1. construit l'image du produit à partir du `Dockerfile` de la version ;
2. lance le conteneur, avec sa mémoire et ses processeurs (512 Mo et un
   demi-processeur au départ, page Policy) et son propre volume de
   données ;
3. attend que le produit réponde ;
4. ajoute la route dans Caddy ;
5. note en base la version publiée, son adresse et son conteneur.

**Les adresses** (Q91) :

- staging : `staging-<business>.<domaine de Serge>` ;
- prod d'un POC : `<business>.<domaine de Serge>` ;
- prod du produit fini : le domaine acheté pour lui (Q39).

Le staging et la prod sont sur le VPS et ouverts à tous, sans mot de
passe : Julien, Clem et le relecteur les ouvrent depuis n'importe où. Le
staging est invisible des moteurs de recherche (en-tête
`X-Robots-Tag: noindex`). Le staging a ses propres données, séparées de
celles de la prod. Une version validée en staging passe telle quelle en
prod : rien n'est reconstruit entre les deux.

Pour qu'un sous-domaine marche sans intervention humaine, il faut un
enregistrement DNS `*.<domaine de Serge>` qui pointe vers le VPS. Caddy
obtient ensuite seul le certificat HTTPS de chaque sous-domaine. Cet
enregistrement (type A, nommé `*`, vers l'adresse IPv4 du VPS) existe
depuis le 13 octobre 2026 : Clem l'a ajouté chez le gestionnaire DNS du
domaine. Une adresse qui n'est dans aucune route de Caddy n'obtient pas
de certificat et ne montre rien. Le
staging s'écrit `staging-<business>` et non `<business>.staging` pour
qu'un seul enregistrement DNS couvre tout.

**La liste des routes passe en base.** `serge/ingress/caddy.py` tient
déjà une liste de routes (une adresse vers un programme du VPS, chacune
rattachée à un business) et en tire la configuration de Caddy, qui se
recharge sans coupure. Mission Control et le webhook Stripe y passent.
Mais cette liste est un fichier JSON (`state/web-ingress/inventory.json`),
alors que la base est la seule source de vérité (charte, partie 5). Elle
devient une table, `web_routes`, et le fichier disparaît.

**Le paiement dans un produit.** Pour savoir qui a payé, un produit fini a
besoin d'une clé Stripe. Il reçoit une **clé restreinte**, aux droits
limités, créée une fois à la main dans le tableau de bord Stripe, à
l'installation. En staging, c'est la clé du mode test : on paie avec la
carte de test 4242 4242 4242 4242 sans débourser un centime. En prod,
c'est la clé du vrai mode. Le POC, lui, est gratuit : il n'a pas de clé
(Q91).

---

## 6. « Appeler une API », et Stripe

Cette capacité était prévue au lot 12 ; elle arrive au lot 10 (Q91). Un
service est décrit en base (`api_services`) : son adresse, le nom du
secret à utiliser (jamais sa valeur), ses points d'entrée et les
paramètres permis de chacun (`api_endpoints`). Un outil, c'est un point
d'entrée et des paramètres figés. Une seule capacité, « Appeler une API »,
sait appeler n'importe quel service décrit ainsi. Au lot 10, deux services
sont décrits : Stripe (en mode test et en vrai mode) et un bureau
d'enregistrement de domaines.

Les outils Stripe du lot 10 :

- **Créer un produit Stripe.**
- **Créer un prix Stripe** : l'identifiant du business est inscrit sur le
  prix (`metadata.venture_id`) par un paramètre figé, tiré de la tâche.
  Le modèle ne peut pas l'oublier, et chaque abonnement est rattaché au
  bon business (Q76).
- **Créer un lien de paiement**, pour le paiement test (partie 9).
- **Rembourser un paiement.**
- **Archiver un prix** et **archiver ou supprimer un produit**, pour le
  bouton de Mission Control (partie 12).

Les outils du bureau d'enregistrement : **acheter un domaine** et **le
faire pointer vers le VPS** (son enregistrement DNS). Le compte chez le
bureau d'enregistrement est créé une fois, à l'installation, avec la
carte de Serge (Q91).

Ces outils agissent hors de Serge : ils notent « en cours » avant
d'appeler Stripe et « fait » après, comme l'envoi d'un message (Q51). Ils
envoient aussi à Stripe une clé d'idempotence (le numéro de la tâche) :
une requête répétée après un arrêt ne crée jamais deux fois le même prix.

---

## 7. Les tables

Chaque table a sa vue, ses colonnes inscriptibles, ses statuts permis et
ses quotas en base, comme le demande la règle de tous les lots.

- **`product_plans`** : une ligne par version d'un plan, pour un POC
  comme pour un produit fini (`kind` = `poc` ou `product`). Le plan de A à
  Z (Q34) : hypothèse, cible, canaux, nombre de prospects, durée, prix
  (indicatif pour un POC, définitif pour le produit), rythme des
  relances, livrable, ce que le constructeur doit faire, et **les
  scénarios de test**. Un scénario, c'est ce que fait un prospect
  ordinaire, pas à pas ; c'est ce que suivent le relecteur et l'humain du
  ticket de test. Exemple : « Arriver sur la page d'accueil, créer un
  compte, faire un premier devis, le télécharger en PDF ». Pour le
  produit fini : aussi le nom de domaine proposé. Statut : `draft`,
  `challenged`, `validated`, `refused`.
- **`plan_critiques`** : une ligne par remarque de « Challenger » : le
  plan, le tour, la remarque. Une remarque « nouvelle capacité » passe par
  l'outil « Demander une nouvelle capacité » (charte, partie 4) ; la
  ligne garde le numéro de la demande.
- **`builds`** : une ligne par passage de construction : le plan, le
  numéro du passage, le compte rendu du constructeur (ce qui est fait, ce
  qui reste, fini ou non), la version produite, le verdict du relecteur
  (`bon`, `a_corriger`, `nouvelle_capacite`) et ses remarques. Statut :
  `building`, `interrupted` (plafond du jour), `reviewing`, `done`.
- **`artifacts`** (existe, vide) : complétée par la taille, l'adresse
  publique et le passage de construction (Q40). Une capture gardée comme
  preuve y a sa fiche, comme une version.
- **`deployments`** : ce qui tourne : le business, la version, la cible
  (staging ou prod), le conteneur, l'adresse, l'état.
- **`web_routes`** : les routes de Caddy (partie 5).
- **`sandboxes`** : les chantiers, avec leur business, leur livrable, leur
  état (allumé, éteint, supprimé), la place qu'ils prennent et pourquoi
  l'un a été arrêté (lot 10, PR 1).
- **`api_services`** et **`api_endpoints`** : les services qu'on sait
  appeler (partie 6).
- **`customer_requests`** (existe depuis le lot 8) : reçoit son état,
  `new`, `kept`, `delivered` ou `refused`, la version qui l'a livrée et la
  raison d'un refus (Q43, Q91). Ces demandes sont données d'office aux
  invocations qui conçoivent et construisent le produit. Rien n'est
  recopié sur la fiche produit.
- **`product_sheets`** et **`product_faq`** (lot 8) : écrites par la
  conception, mises à jour à chaque nouvelle version (Q50).
- **`ventures`** : un business passe de `POC_SELECTED` à `SMOKE_READY`
  quand son POC est validé, en ligne et sa campagne prête. Pour l'étape 5,
  deux statuts proposés : `PRODUCT_BUILDING` puis `PRODUCT_READY`. Le
  statut d'un business choisi comme principal sera fixé au lot 11, avec
  l'étape 4.

---

## 8. L'étape 2 dans le pipeline

Tout est en base : les invocations, les liens et les tickets. Aucune ligne
de code ne leur est propre.

1. **Concevoir le POC** (LLM, niveau intelligent, file des travaux).
   Lancée par le lien qui part de « Choisir les business », pour chaque
   business choisi. Elle reçoit d'office la fiche du business et ses
   preuves ; au tour suivant, son plan précédent et sa critique. Elle
   écrit le plan (`product_plans`), la fiche produit du POC et ses
   questions fréquentes, et la campagne de test (`campaigns`, au statut
   brouillon).
2. **Challenger le POC** (LLM, niveau intelligent). Elle relit le plan et
   rend ses remarques « à corriger » ; pour un manque, elle appelle
   « Demander une nouvelle capacité » (Q35). Lien : s'il y a des
   remarques et que moins de 3 tours sont faits, retour à « Concevoir le
   POC » ; sinon, ticket du plan.
3. **Ticket « Plan »** : plan final, fiche produit, critique, ce qui a été
   corrigé, ce qui reste. Julien valide, refuse ou discute. Sans réponse
   sous 48 heures, le plan s'applique (Q34).
4. **Construire** (LLM, niveau « code », file des travaux, profil
   « chantier »). Elle reçoit d'office le plan validé, la fiche produit,
   les demandes des clients du business (aucune pour un premier POC), et,
   au passage suivant, les remarques et les captures du relecteur, ou les
   consignes d'un humain. Ses outils : le chantier (partie 1),
   l'interface web (partie 2) pour essayer son produit, et « Demander une
   nouvelle capacité ». Elle rend son compte rendu (`builds`).
5. **Publier en staging** (sans LLM, partie 5).
6. **Relire** (LLM, niveau « code »). Elle ne voit jamais le code : elle
   n'a que l'interface web. Elle suit les scénarios de test du plan, sur
   ordinateur puis sur mobile, comme un prospect ordinaire, et garde ses
   captures comme preuves. Elle rend « bon », ou « à corriger » avec ses
   remarques ; pour un manque, elle appelle « Demander une nouvelle
   capacité ». Lien : « à corriger » et moins de 3 passages faits, retour
   à « Construire » ; sinon, ticket de test.
7. **Ticket « Tester le produit »** (partie 10), avec le lien du staging.
8. **Publier en prod** (sans LLM) la version validée, à
   `<business>.<domaine de Serge>`.
9. **Prêt pour le test léger** (sans LLM) : la campagne passe de
   brouillon à prête, le business à `SMOKE_READY`. L'étape 3 (trouver des
   prospects, lot 11) prend la suite.

---

## 9. L'étape 5 dans le pipeline

L'étape 5 part du business principal choisi à l'étape 4, qui arrive au
lot 11. En attendant, elle se lance par un bouton sur la fiche d'un
business, « Construire le vrai produit », réservé aux essais. Le lot 11
le remplacera par un lien depuis l'étape 4.

1. **Concevoir le produit** (LLM, niveau intelligent). Elle part du plan
   du POC et de la fiche produit, et reçoit d'office toutes les demandes
   des clients du business, les objections et les questions des prospects
   (avec leur texte), et les points du business. Elle écrit le plan du
   vrai produit (`kind` = `product`), le prix définitif proposé, le nom de
   domaine proposé, la fiche produit mise à jour, et marque chaque demande
   retenue ou refusée avec sa raison.
2. **Challenger le produit** : même boucle qu'à l'étape 2, 3 tours au
   plus (Q41).
3. **Ticket « Plan »** : Julien valide le plan, le prix, la fiche produit
   et le nom de domaine, et voit quelles demandes des clients sont
   retenues. Ce ticket n'expire jamais (Q91).
4. **Acheter le domaine** : Serge achète seul le nom validé dans le
   ticket, et le fait pointer vers le VPS, par les outils du bureau
   d'enregistrement (partie 6). Un domaine plus cher que le prix maximum
   (partie 11) n'est pas acheté : Serge en propose un autre dans un
   nouveau ticket.
5. **Construire, publier en staging, relire** : la même boucle qu'à
   l'étape 2. Le produit et son prix sont créés dans Stripe en mode test
   par les outils de la partie 6. Les scénarios de test vont jusqu'au
   paiement, avec la carte de test.
6. **Ticket « Tester le produit »**, avec le lien du staging.
7. **Mettre en vente** : le produit et son prix sont créés dans Stripe en
   vrai mode, puis la version validée est publiée en prod sur le domaine
   du produit.
8. **Le paiement test de 1 €** (Q41), fait par Serge seul (Q91) : Serge
   crée un prix de 1 € sur le produit et un lien de paiement. Une
   invocation (LLM, avec l'interface web) ouvre le lien et paie avec la
   carte de Serge, par l'outil « Taper un secret ». Serge vérifie que le
   paiement est arrivé par le webhook et qu'il est rattaché au business,
   puis se rembourse. Le parcours de paiement du produit lui-même a été
   essayé en staging, en mode test.
9. Le business passe à `PRODUCT_READY` ; l'étape 6 (lot 11) prend la
   suite.

**Les versions suivantes** (Q41, Q43) passent par la même boucle
« construire, publier en staging, relire ». Une version que le relecteur
juge bonne part seule en prod, avec un ticket d'information. Cette boucle
servira à l'étape 6, au lot 11.

---

## 10. Les tickets

Deux types de tickets nouveaux, en base comme les autres (lot 8 bis,
Q85), réglables sur la page Décisions :

- **« Plan »** : un plan et sa fiche produit à valider. Boutons :
  « Valider », « À corriger » (avec des consignes, qui repartent à la
  conception), « Refuser ». Pour un POC, sans réponse sous 48 heures, le
  plan s'applique (Q34). Pour le produit fini, le ticket n'expire jamais :
  il fixe le prix définitif et le nom de domaine (Q91).
- **« Tester le produit »** (Q91) : le lien du staging, les scénarios de
  test, la fiche produit, le verdict du relecteur et ses captures. Il
  **n'expire jamais** : rien ne part vers des prospects sans qu'un humain
  ait essayé le produit. Boutons : « Valider » (la version passe en
  prod) ; « À corriger », avec des consignes, qui repartent au
  constructeur pour un nouveau passage ; « Arrêter le business ». Il
  sert deux fois : entre la construction du POC et la prospection légère,
  et entre la construction du produit fini et la prospection lourde.

Ils remplacent les tickets d'information prévus aux étapes 2 et 5 (Q35,
Q41). Les tickets restent pour les achats importants et les étapes
importantes ; ailleurs, Serge est autonome avec sa carte (Q91).

---

## 11. Les réglages

Chaque grandeur discutable se règle dans Mission Control (Q68). Ce sont
« les bornes de la construction » que le TODO annonçait. Les anciennes
bornes du constructeur (au plus 20 fichiers et 200 000 caractères par
livrable) ne servent plus : le constructeur écrit dans un chantier.

Sur la page **Policy** :

- le profil « chantier » : image, processeurs, mémoire, disque, durée
  maximale d'une commande, réseau (partie 1) ;
- un produit en ligne : mémoire et processeurs (partie 5) ;
- le domaine des produits, par défaut celui de Mission Control ;
- le prix maximum d'un domaine acheté pour un produit fini : 30 € par an
  au départ.

Sur la page **Pipeline** : le niveau « code » (prix maximum, tolérance,
lecture des images) et le nombre de captures gardées dans l'historique.

Réglages des invocations, marqués « policy » : 3 tours de critique au
plus, 3 passages de construction au plus, les tours d'outils de
« Construire » (200) et de « Relire » (60).

---

## 12. Mission Control

- **La fiche du business** montre ses plans et leurs critiques, ses
  passages de construction avec le compte rendu du constructeur, le
  verdict du relecteur et ses captures, ses versions (staging et prod,
  avec leur adresse), et ses demandes des clients avec leur état.
- **Un bouton « Supprimer de Stripe »** sur la fiche du business (Q91) :
  il archive les prix du business (Stripe ne permet pas de supprimer un
  prix) et supprime ou archive son produit. Il sert à nettoyer après les
  essais. Il demande une confirmation.
- **Un bouton « Construire le vrai produit »**, temporaire (partie 9).
- **Un îlot « Chantiers »** sur la page Système : chaque chantier, allumé
  ou éteint, la place qu'il prend, les commandes lancées en 24 h, et
  pourquoi l'un a été arrêté. Les boutons d'essai du lot (« Essayer le
  chantier », puis ceux des PR suivantes) sont avec « Lancer un essai »,
  plus bas sur la même page.
- La page Policy et la page Pipeline montrent les réglages de la
  partie 11.

---

## 13. La sécurité

Le code écrit par le LLM tourne sur le VPS de Julien. Il ne doit jamais
atteindre Serge.

- Les conteneurs (chantiers, navigateur, produits) tournent sous Docker
  rootless, jamais en root.
- Aucun secret de Serge n'entre dans un conteneur, ni aucune clé de
  modèle : c'est Serge qui appelle le modèle. La seule clé qu'un produit
  reçoit est sa clé Stripe restreinte (partie 5).
- Un conteneur ne voit ni `serge.db`, ni Mission Control, ni les
  récepteurs de Serge sur le VPS : il ne joint qu'Internet.
- Le numéro de la carte de Serge est tapé par Serge, jamais montré au
  modèle (partie 2).
- Toute erreur de Docker, du navigateur, de Stripe ou du bureau
  d'enregistrement est notée au journal avec la raison donnée en face
  (code et message, sans secret), et se lit dans Mission Control (Q89).

---

## 14. Les tests

**Le test de scénario de l'étape 2** : un business `POC_SELECTED` →
« Concevoir le POC » (faux modèle) → « Challenger » (une remarque) →
deuxième tour → ticket validé → « Construire » (faux modèle qui écrit un
petit site et son `Dockerfile`) → « Publier en staging » → « Relire »
(faux modèle qui lit la page et clique) → ticket de test validé → prod →
campagne prête, business `SMOKE_READY`, chaque étape au journal. Le
modèle et Stripe sont faux ; le reste est réel, Docker compris quand il
est présent.

**Les cas refusés** : une invocation qui vise le chantier d'un autre
business ; un quatrième passage de construction ; un deuxième chantier
allumé ; un prix Stripe sans identifiant de business ; un ticket de test
qui expirerait.

**Le test de l'étape 5** : la même chaîne avec l'achat du domaine, Stripe,
le paiement test de 1 € et son remboursement, en faux. Cas refusé : un
domaine plus cher que le prix maximum.

**Le test navigateur de Mission Control** : la fiche du business, ses
versions et ses captures, le bouton « Supprimer de Stripe ».

**Le test réel**, avant le push : un petit produit construit et relu avec
le vrai modèle, sur une machine avec Docker.

---

## 15. Ce qui reste ouvert

- **Le bureau d'enregistrement** : à choisir à l'installation, avec Julien.
  Il doit savoir acheter un domaine et régler son DNS par son API
  (partie 6).
