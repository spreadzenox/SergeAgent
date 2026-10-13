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

Le lot se livre en sept PR, l'une après l'autre ; chacune se fusionne dès
que sa CI est verte, et Clem l'essaie dans Mission Control (décision Q91) :

1. **Le chantier** (parties 1 et 3) : un conteneur par produit et ses
   quatre outils. Essai : le bouton « Essayer le chantier » de la page
   Système.
2. **Voir et cliquer** (parties 2, 3 et 4) : le navigateur, les captures
   envoyées au modèle, le niveau « code ». Essai : « Essayer l'interface
   web ».
3. **Publier** (partie 5) : les versions, le staging et la prod, les
   routes de Caddy. Essai : publier le chantier d'essai.
4. **L'étape 2** (parties 7, 8 et 10) : concevoir, challenger,
   construire, relire, les tickets, la prod du POC. Essai : « Essayer
   l'étape 2 », depuis un business d'essai.
5. **Appeler une API, et Stripe** (partie 6) : les services décrits en
   base, les outils Stripe, taper un secret dans le navigateur. Essai :
   « Essayer Stripe (mode test) » puis « Supprimer de Stripe » sur la
   fiche d'un business.
6. **Le bout en bout du POC** (demandé par Clem le 13 octobre 2026) : un
   business et un plan tout faits, une calculatrice, entrent directement
   en construction ; tout le reste est le vrai pipeline. Essai : « Bout
   en bout : le POC d'une calculatrice ».
7. **L'étape 5** (partie 9) : le vrai produit, l'achat du domaine, le
   paiement test de 1 €. Essais : « Bout en bout : le produit fini d'une
   calculatrice », et « Construire le vrai produit » sur la fiche d'un
   business.

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

**Trois outils**, chacun une capacité générale (lot 10, PR 2) :

- **Agir dans une page** (`browser_action`), avec une action :
  `ouvrir` une adresse, `cliquer` sur un repère, `taper` du texte dans un
  champ (en validant ou non avec Entrée), `choisir` une option dans une
  liste, appuyer sur une `touche` (Entrée, Échap, Tab), `defiler` vers le
  haut ou le bas, `revenir` à la page précédente, `attendre` qu'un texte
  apparaisse, passer l'`ecran` en ordinateur (1280 × 800) ou mobile
  (390 × 844). Une seule capacité plutôt qu'une par action : chaque outil
  proposé au modèle repart à chaque tour, et coûte à chaque fois.
- **Lire la page** (`browser_read`) : la page entière décrite comme la lit
  un lecteur d'écran (`serge/sandbox/page.js`), ligne par ligne (titres,
  textes, champs, boutons, liens), chaque élément avec un repère court
  qu'on cite pour agir. Exemple : `[e7] bouton « Créer un compte »`,
  `[e9] champ email « E-mail » (vide)`. C'est l'idée de Playwright MCP,
  l'outil libre de Microsoft : bien moins cher qu'une capture, et plus sûr
  que de viser des pixels. Avec la page, les dernières erreurs : erreurs
  JavaScript, requêtes ratées, réponses HTTP 400 et plus.
- **Prendre une capture** (`browser_screenshot`) : l'écran, ou la page
  entière ; l'image est envoyée au modèle (partie 3), et gardée comme
  preuve si l'invocation le demande, sous
  `files/<business>/<livrable>/captures/`, avec sa fiche dans
  `artifacts` (sa taille, la tâche qui l'a prise).

**Taper un secret** (action `taper_secret`, PR 5) : le modèle désigne le
champ et le nom du fichier de secret, parmi ceux figés en base sur
l'invocation (paramètre `secrets`, exemple `carte-numero.key`) ; Serge
tape la valeur sans la lui montrer. La page relue cache la valeur, même
remise en forme par la page (`4242 4242 4242 4242`), comme les erreurs
de la page ; le temps d'une capture, le champ qui l'a reçue montre des
points, comme un mot de passe. Il sert au paiement test de l'étape 5.

Le business, le livrable et la tâche sont des paramètres figés de ces
outils. Une session (un onglet et ses cookies) par tâche, fermée à la fin
de la tâche. Le navigateur (profil « navigateur » de la page Policy :
image `chromedp/headless-shell`, 2 Go de mémoire) et les chantiers sont
sur un même réseau Docker, `serge-chantiers` : l'adresse
`http://chantier:3000` mène au chantier du business de la tâche, pour que
le constructeur essaie le serveur qu'il vient de lancer. Une connexion
perdue au navigateur (conteneur relancé) est refaite une fois.

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
   dans l'historique (page Pipeline, « Captures gardées dans
   l'historique ») ; les autres sont remplacées par un texte court,
   modifiable sur la même page. Une capture part dans un message à part,
   juste après les résultats des outils du tour : tous les fournisseurs
   n'acceptent pas une image comme résultat d'outil. Le texte rendu par
   l'outil dit seulement « montrée dans le message suivant » : l'image
   n'est jamais envoyée en texte.

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
recommandation de modèle : **lit les images** (colonne `needs_image`,
cochée pour ce niveau ; OpenRouter le dit par `input_modalities`). La
liste fermée des niveaux permis en base est élargie (migration v43).

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

**« Publier »** (`publish_version`, lot 10, PR 3) est une capacité sans
LLM. Ses paramètres sont figés en base : le business, le livrable, la
cible (staging ou prod), le nom court du produit, et pour la prod d'un
produit fini son domaine. En staging, elle :

1. fige le chantier en version N : une archive de `/work` sans ce qui se
   reconstruit (`node_modules`, `.git`, `.venv`, `__pycache__`), rangée
   dans `files/<business>/<livrable>/v<N>/` ;
2. construit l'image du produit à partir du `Dockerfile` de la version
   (`serge-produit-<chantier>:v<N>`) ;
3. remplace le conteneur du staging par un neuf : les limites du profil
   « produit » de la page Policy (512 Mo et un demi-processeur au départ),
   le volume de données `/data` (gardé d'une version à l'autre), les
   variables `PORT` (8080, où le produit doit écouter), `DATA_DIR` et
   `PUBLIC_URL`, un redémarrage automatique avec le serveur, et un port
   fixe sur `127.0.0.1` (18000 et suivants, gardé d'une version à
   l'autre pour que la route de Caddy reste juste après un redémarrage) ;
4. attend que le produit réponde, une minute au plus ;
5. ajoute la route dans Caddy et lui fait relire sa configuration, sans
   coupure, par son API d'administration ;
6. note la publication dans `deployments`.

En prod, elle reprend l'image de la version passée en staging : rien
n'est reconstruit. Une construction ratée, un produit qui ne répond pas
ou un chantier sans `Dockerfile` ne mettent rien en ligne : la
publication est notée ratée avec sa raison, et la fin du journal de
construction ou du produit est rendue, pour que le constructeur corrige.

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

**La liste des routes reste dans son fichier.** `serge/ingress/caddy.py`
tient une liste de routes (une adresse vers un programme du VPS, chacune
rattachée à un business) et en tire la configuration de Caddy. Mission
Control, le webhook Stripe et les produits y passent. Elle reste un
fichier (`state/web-ingress/inventory.json`), et pas une table : le
service Caddy relit cette liste à son démarrage, dans un bac à sable
systemd où il ne peut écrire que dans `state/web-ingress` ; il ne peut
pas ouvrir la base de façon sûre, et un démarrage raté de Caddy couperait
Mission Control. C'est la contrainte technique dure que demande la charte
pour une exception à « la base fait foi » (partie 5). Ce que Serge publie
est, lui, en base (`deployments`).

**Le paiement dans un produit.** Pour savoir qui a payé, un produit fini a
besoin d'une clé Stripe. Il reçoit une **clé restreinte**, aux droits
limités, créée une fois à la main dans le tableau de bord Stripe, à
l'installation. En staging, c'est la clé du mode test : on paie avec la
carte de test 4242 4242 4242 4242 sans débourser un centime. En prod,
c'est la clé du vrai mode. Le POC, lui, est gratuit : il n'a pas de clé
(Q91).

---

## 6. « Appeler une API », et Stripe

Cette capacité était prévue au lot 12 ; elle arrive au lot 10 (Q91, fait
en PR 5). Un service est décrit en base (`api_services`) : son adresse,
comment s'authentifier, le nom du fichier de secret à lire (jamais sa
valeur) et le format du corps (`form` pour Stripe, `json` ailleurs). Un
point d'entrée est un outil (`api_endpoints`) : sa méthode, son chemin et
ses paramètres permis (`api_endpoint_params`). Une seule capacité,
« Appeler une API » (`serge/connecteurs/appel.py`), sait appeler
n'importe quel service décrit ainsi. Le modèle ne voit que les paramètres
permis qui ne sont pas figés en base ; un paramètre inconnu est refusé
sans rien envoyer.

Le service vient du point d'entrée, ou d'un paramètre figé `service` sur
l'invocation : le même outil sert en mode test (`stripe_test`, secret
`stripe-test.key`) et en vrai mode (`stripe_live`, secret
`stripe-live.key`). Ce sont les fichiers que pose déjà l'installeur
([`installation/STRIPE.md`](installation/STRIPE.md)).

Les outils Stripe du lot 10 :

- **Créer un produit Stripe.**
- **Créer un prix Stripe** : l'identifiant du business est inscrit sur le
  prix (`metadata[venture_id]`) par un paramètre figé, tiré de la tâche.
  Le modèle ne peut pas l'oublier ni en mettre un autre, et chaque
  abonnement est rattaché au bon business (Q76). Le produit et le lien de
  paiement le portent aussi.
- **Créer un lien de paiement Stripe**, pour le paiement test (partie 9).
- **Rembourser un paiement Stripe.**
- **Chercher des produits Stripe** (par le business inscrit dessus),
  **lister les prix d'un produit**, **archiver un prix** et **archiver un
  produit**, pour le bouton de Mission Control (partie 12). Stripe ne
  permet pas de supprimer un prix, ni un produit qui a un prix : on
  archive.

Le bureau d'enregistrement de domaines (acheter un domaine, le faire
pointer vers le VPS) est décrit de la même façon en PR 6 (partie 15).

Une écriture envoie une clé d'idempotence tirée de la tâche, de l'outil
et du contenu (`Idempotency-Key: serge-…`) : une requête répétée après un
arrêt ne crée jamais deux fois le même prix (Stripe garde la clé
24 heures). Une erreur du service revient au modèle avec sa raison, et la
même raison est notée au journal (`connecteur : stripe_test POST
/v1/prices : HTTP 400 …`, Q89). Un secret absent aussi. Chaque appel est
un événement `api.call` (service, méthode, chemin, statut, jamais le
secret ni le corps).

---

## 7. Les tables

Chaque table a sa vue, ses colonnes inscriptibles, ses statuts permis et
ses quotas en base, comme le demande la règle de tous les lots.

- **`product_plans`** : une ligne par version d'un plan, pour un POC
  comme pour un produit fini (`kind` = `poc` ou `product`). Le plan de A à
  Z (Q34) : hypothèse, cible, canaux, nombre de prospects, durée, prix
  (indicatif pour un POC, définitif pour le produit), livrable, ce que
  le constructeur doit faire, et **les scénarios de test**. Pas le
  rythme des relances : il est commun à tous les business (Q37,
  corrigée par Q92). Un scénario, c'est ce que fait un prospect
  ordinaire, pas à pas ; c'est ce que suivent le relecteur et l'humain du
  ticket de test. Exemple : « Arriver sur la page d'accueil, créer un
  compte, faire un premier devis, le télécharger en PDF ». Pour le
  produit fini : aussi le nom de domaine proposé. Statut : `draft`,
  `challenged`, `validated`, `refused`.
- **`plan_critiques`** : une ligne par remarque « à corriger » du
  critique : le plan, le tour, la remarque. Un manque de Serge (« il
  faut une nouvelle capacité ») passe par l'outil « Demander une nouvelle
  capacité » (charte, partie 4), pas par cette table.
- **`builds`** : une ligne par passage de construction : le numéro du
  passage, le compte rendu du constructeur, le verdict du relecteur
  (`bon`, `a_corriger`), ses remarques, ce qu'il a essayé, et les
  consignes d'un humain. Statut : `built`, `unfinished` (pas fini : le
  plafond du jour, ou trop long), `reviewed`.
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

Fait au lot 10, PR 4 : le détail, invocation par invocation, est dans
[`etapes/2-conception-poc.md`](etapes/2-conception-poc.md). Tout est en
base : les invocations, les liens et les tickets ; aucune ligne de code
ne leur est propre. Trois briques générales ont suffi :

- **« Compter les tours »** (`next_round`), une capacité sans LLM :
  « encore » et le tour suivant tant que le tour est sous un maximum
  (un réglage), sinon « fini ». Elle borne chaque boucle : 3 tours de
  critique, 3 passages de construction, 3 reprises d'un même passage.
- **Un paramètre de lien peut venir de la réponse** de l'invocation qui
  vient de finir (source `field`) : exemple, le tour suivant, ou
  l'adresse du staging rendue par « Publier ».
- **Trois boutons de ticket** : « Valider », « À corriger » (avec un
  texte, les consignes) et « Arrêter le business ».

Une réponse à un ticket réveille une invocation sans LLM (« Suite du
ticket ») par un déclencheur sur `ticket_answers` filtré par type de
ticket ; ses liens, conditionnés sur le bouton, lancent la suite. Exemple :
« Valider » sur le ticket « Plan » lance « Construire le POC ».

Pour l'essayer sans cycle d'écoute, le bouton « Essayer l'étape 2 » de la
page Système crée un business, le choisit pour un POC (il prend une place
de test) et lance l'étape. Le bouton « Bout en bout : le POC d'une
calculatrice » saute aussi la conception : un business et un plan tout
faits (une calculatrice) entrent directement en construction, puis tout
est réel jusqu'à la prod
([`etapes/2-conception-poc.md`](etapes/2-conception-poc.md)).

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

Les types de tickets nouveaux, en base comme les autres (lot 8 bis,
Q85), réglables sur la page Décisions. Leurs boutons : « Valider »,
« À corriger » (avec des consignes), « Arrêter le business » et
« Discuter ».

- **« Plan » d'un POC** (`PLAN_POC`, PR 4) : le business, le plan, la
  critique, la fiche produit. Sans réponse sous 48 heures, le plan
  s'applique (Q34).
- **« Tester le produit » d'un POC** (`TEST_POC`, PR 4) : le business,
  l'adresse du staging, les scénarios de test, le verdict du relecteur.
  Il **n'expire jamais** : rien ne part vers des prospects sans qu'un
  humain ait essayé le produit (Q91).
- **« Plan » et « Tester le produit » du produit fini** (PR 7) : le
  ticket du plan n'expire pas non plus, puisqu'il fixe le prix définitif
  et le nom de domaine (Q91).

Ils remplacent les tickets d'information prévus aux étapes 2 et 5 (Q35,
Q41). Les tickets restent pour les achats importants et les étapes
importantes ; ailleurs, Serge est autonome avec sa carte (Q91).

## 11. Les réglages

Chaque grandeur discutable se règle dans Mission Control (Q68). Ce sont
« les bornes de la construction » que le TODO annonçait. Les anciennes
bornes du constructeur (au plus 20 fichiers et 200 000 caractères par
livrable) ne servent plus : le constructeur écrit dans un chantier.

Sur la page **Policy** :

- le profil « chantier » : image, processeurs, mémoire, disque, durée
  maximale d'une commande, réseau (partie 1) ;
- un produit en ligne : mémoire et processeurs (partie 5) ;
- le profil « produit » : processeurs et mémoire de chaque produit en
  ligne (partie 5) ;
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
- **Deux boutons « Supprimer de Stripe »** sur la fiche du business
  (Q91, PR 5), un pour le mode test et un pour le vrai mode : ils
  cherchent les produits qui portent le business, archivent leurs prix
  puis les produits (Stripe ne permet pas de supprimer un prix). Ils
  servent à nettoyer après les essais, et demandent une confirmation.
  Avec eux, le bouton d'essai « Essayer Stripe (mode test) » crée un
  produit, un prix de 1 € par mois et un lien de paiement pour ce
  business. Un bouton qui attend un business (un champ `venture_id`) est
  sur la fiche du business, rempli par elle, et pas sur la page Système.
- **Un bouton « Construire le vrai produit »**, temporaire (partie 9).
- **La fiche d'une tâche** montre ses captures gardées ; un clic ouvre
  l'image en grand. Mission Control sert un fichier rangé sous `files/`,
  et rien d'autre, à une session connectée (`/owner/api/fichier`).
- **La fiche du business** montre ses publications (staging et prod :
  version, adresse, état, raison d'un échec) et ses versions.
- **Un îlot « Produits en ligne »** sur la page Système, et le bouton
  « Publier le chantier d'essai » (cible staging ou prod) avec les autres
  essais.
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
