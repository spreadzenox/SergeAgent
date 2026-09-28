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

## La règle qui vaut pour tous les lots

Julien et Clem ont fixé une règle qui s'applique à chaque tâche de ce
fichier, y compris celles qu'on attaquera dans plusieurs semaines : **tout
se fait depuis la base de données, et le code n'est qu'un interpréteur.**
Il n'y a jamais de code propre à une invocation. À terme, on doit pouvoir
créer une invocation de toutes pièces depuis Mission Control : son rôle,
son modèle, son prompt, ce qu'elle reçoit, ce qu'elle peut appeler, où elle
écrit sa réponse, avec quelles protections, et ce qui la lance.

Le code est donc rangé par **capacité**, jamais par invocation. Une
capacité est un savoir-faire général, réglé par des paramètres lus en
base : lire la base, écrire dans la base, appeler un modèle, chercher sur
le web, agir dans un bac à sable, appeler une API décrite en base, envoyer
ou relever des messages sur un canal, ouvrir un ticket. Une capacité ne
connaît jamais une invocation, une étape ou un business en particulier.

Un test simple permet de vérifier la règle : **le nom d'une invocation ne
doit jamais apparaître dans le code**, sauf dans le fichier qui remplit une
nouvelle instance. Si une tâche semble demander du code pour une
invocation précise, c'est qu'il manque une capacité générique, ou un
réglage en base : on ajoute ce qui manque, de façon générale. Exemple :
pour qu'une invocation refuse un business déjà en test, on n'écrit pas une
fonction spéciale, on déclare en base que le statut d'un business peut
passer de `CANDIDATE` à `POC_SELECTED`, et jamais d'un autre statut.

Les parties sur le web, le bac à sable, les connecteurs, les canaux et
l'agent vocal, plus bas, rappellent comment cette règle s'y applique.

---

## Dans quel ordre

On avance par lots. Un lot est un ensemble de tâches qui vont ensemble ;
chaque lot se termine par des tests verts et un commit, puis Julien ou
Clem regarde le résultat avant qu'on attaque le suivant. Les lots 1 à 5
sont faits : fusion des branches, correction de deux bugs graves,
nettoyage du code mort, nouvelle documentation, et remise en ordre des
données (business, contacts, abonnements).

- [ ] **Lot 6 « Le runner et le pipeline en base ».** C'est la fondation
  de tout le reste, et Clem et Julien veulent l'attaquer ensemble. Il
  commence par le runner, le programme qui exécute les tâches : il doit
  exécuter une tâche après l'autre et enregistrer en base après chacune,
  sur deux files en parallèle, parce qu'aujourd'hui un plantage peut faire
  envoyer deux fois le même e-mail. Ensuite, tout le pipeline passe en
  base : l'ordre des invocations, leur modèle, leur prompt, ce qu'elles
  reçoivent, leurs tools, où elles écrivent, ce qui les déclenche. Le code
  ne fait plus que lire la base et exécuter ce qu'elle décrit. Tout le
  code écrit en dur pour un enchaînement est supprimé, sans chercher à le
  garder en marche. À la fin du lot, Serge ne peut pas encore être
  allumé pour de vrai, parce que certaines capacités manquent ; mais en
  modifiant la base, on peut déjà construire n'importe quel pipeline avec
  les capacités qui existent. Les tâches détaillées sont dans la partie
  « Lot 6 » plus bas.
- [ ] **Lot 7 « Étape 1 ».** On refait la pré-prospection en sept
  invocations qui ont chacune un seul rôle, on garde toutes les pages lues
  comme preuves, et on met la liste des flux RSS en base. Ce lot est le
  premier à être décrit entièrement en base grâce au lot 6.
- [ ] **Lot 8 « Conversations ».** On crée un fil de discussion par
  prospect, une seule invocation pour lire et traiter une réponse, une
  fiche produit détaillée pour répondre juste, des tickets qu'on comprend
  sans suivre Serge, des délais de réponse réglables par canal, et un agent
  vocal qui sait à qui il parle. C'est ce qui permet de parler à de vrais
  prospects sans faire d'erreur gênante.
- [ ] **Lot 9 « Grille de points ».** On donne des points à chaque
  réaction d'un prospect, avec un barème par canal, pour pouvoir comparer
  deux tests faits sur des canaux différents.
- [ ] **Lot 10 « Concevoir et construire ».** On écrit le plan d'un POC
  et sa fiche produit, on les fait critiquer, Julien les valide, puis
  Serge construit et met en ligne, d'abord le POC, ensuite le vrai
  produit. Ce sont les étapes 2 et 5.
- [ ] **Lot 11 « Le reste des étapes ».** Trouver des prospects (étape 3),
  choisir le business principal (étape 4), la prospection lourde et la vie
  du business (étape 6), des leçons plus précises (étape 7) et une caisse
  propre (étape 8).
- [ ] **Lot 12 « Web ».** On donne à Serge de quoi chercher, lire des
  pages et agir sur n'importe quel site : créer un compte, publier,
  écrire. On le met tard parce que c'est un gros chantier, mais plusieurs
  tâches des étapes 3 et 6 en dépendent. Le bac à sable, l'agent web et
  les connecteurs y sont des capacités générales réglées en base, jamais
  du code écrit pour une invocation.
- [ ] **Lot 13 « L'éditeur sans code ».** Une page de Mission Control
  pour modifier le pipeline en direct et créer une invocation de toutes
  pièces : ajouter ou retirer des invocations, changer leur ordre, leur
  rôle, leur modèle, ce qu'elles voient et où elles écrivent, sans
  toucher au code. Il n'est possible qu'une fois le lot 6
  fait.

---

## Lot 6 — Le runner et le pipeline en base

La règle, décidée par Clem et Julien : **le code n'est qu'un interpréteur
de la base de données.** L'ordre des invocations et tous leurs paramètres
sont en base, et seulement en base. Aucun paramètre n'est écrit en dur
dans le code. Le runner prend les tâches une par une ; pour chacune, le
code lit en base la description de l'invocation à lancer, et l'exécute
exactement comme elle est décrite. Exemple : si Julien change dans MC le
modèle de « Trier les pages », ou ajoute une invocation entre « Trier les
pages » et « Formuler des business », le prochain cycle en tient compte,
sans redéploiement.

Le code garde seulement des capacités générales, comme expliqué dans « La
règle qui vaut pour tous les lots » : lire la base, écrire dans la base,
appeler un modèle, chercher sur le web, envoyer un e-mail. La base dit
lesquelles utiliser, dans quel ordre et avec quels paramètres. C'est déjà
le cas pour la lecture de la base : la liste des tables et des colonnes
qu'une invocation a le droit de lire est en base, et un seul bout de code
sait lire n'importe laquelle. Ce lot fait la même chose pour l'écriture,
et pour tout le reste.

La conception des tables, validée avec Clem, est dans
[`docs/LOT6_CONCEPTION.md`](docs/LOT6_CONCEPTION.md).
Pour reprendre le lot en cours de route, lire d'abord
[`docs/REPRISE_LOT6.md`](docs/REPRISE_LOT6.md).

Clem a fixé la façon de mener ce lot. On passe directement à la version
durable : tout ce qui est écrit en dur pour un enchaînement (le cycle
d'écoute, le circuit des réponses, les envois, la relève, la
consolidation) est retiré de la production, sans période de transition,
et rangé avec ses tests et ses prompts dans le dossier
`pas_encore_branche/`, pour les lots suivants.
On ne crée que les colonnes et les capacités dont ce lot a besoin : celles
des fonctions futures (validation par Julien, bac à sable, délais par
canal, désinscription…) seront ajoutées par leur propre lot, et elles sont
notées dans ce fichier à l'endroit où elles serviront. On fusionne dans
`main` après chaque étape du lot, avec des tests verts qui portent
seulement sur ce qui est construit. Mission Control affiche tout ce qui
est en base, en direct ; créer une invocation depuis le site viendra au
lot 13.

Ce qui est fait : les tables du pipeline (version 24 de la base), les
deux files du runner qui tournent en continu et enregistrent après chaque
tâche, l'interpréteur qui exécute n'importe quelle invocation décrite en
base (sans « kinds »), l'écriture générique et ses protections, la
priorité et l'interrupteur de chaque invocation, le remplissage de départ
qui n'efface et n'écrase rien, le rangement de l'ancien code dans
`pas_encore_branche/` (version 25 de la base), Mission Control branché sur
les nouvelles tables, un demi-cycle de démonstration de l'étape 1 dans
`config/pipeline.yaml`, et le test qui vérifie la règle
(`tests/test_regle_interpreteur.py`), les réglages des invocations et les
quotas des tables, modifiables sur la page Policy (par exemple « nombre
d'idées » de la démo, ou « au plus 3 business choisis pour un POC »).
Serge est arrêté par défaut : il ne
tourne qu'après un clic sur « Démarrer Serge » dans Mission Control. Le
vrai pipeline, étape par étape, est l'objet des lots suivants. Ce qui
reste dans ce lot :

- [ ] **Ce que voit chaque invocation, et l'outil pour lire le reste.**
  Aujourd'hui, une invocation reçoit ce qu'on lui déclare un par un, au
  plus 50 lignes par défaut, et la fiche de la tâche dans MC dit combien
  de lignes elle a reçues. Il faut appliquer les règles validées dans
  [`docs/MEMOIRE.md`](docs/MEMOIRE.md), sans rien écrire en dur :
  - **La version courte, systématique.** La base dit, une fois pour
    chaque table, quelles colonnes forment sa version courte (pour un
    business, son numéro et son nom) et quelles colonnes sont lisibles
    (jamais un mot de passe). Toute invocation reçoit d'office la version
    courte des tables où elle écrit. Sur sa fiche dans MC, on peut ajouter
    une table à comparer ou en retirer une.
  - **Les plus récentes d'abord.** Au-delà du maximum, elle reçoit les
    lignes les plus récentes (aujourd'hui, ce sont les premières lues), et
    le compte des lignes laissées de côté est juste même au-delà de 200.
  - **L'outil « Lire les tables que je vois ».** Ce n'est pas un outil
    codé pour une invocation, mais une sorte d'outil : il y en a un par
    invocation, construit à chaque appel à partir de ses réglages en base,
    et en particulier de l'ensemble des tables qu'elle voit en version
    courte. Dans ces tables seulement, le modèle peut demander toutes les
    lignes et toutes les colonnes lisibles. Exemple : « Formuler des
    business » peut lire la fiche complète du business n° 12 vu dans sa
    liste courte, mais pas les paiements. Il faudra sans doute des tables
    ou des colonnes de plus (les tables vues par une invocation, les
    colonnes lisibles et courtes de chaque table).
  - **L'outil « Lire l'historique »** d'une ligne qu'elle voit : ses
    derniers événements dans le journal.
  - **Ses propres leçons**, données d'office, les plus fiables d'abord.
    Elles dépendent du rattachement d'une leçon à une invocation (étape 7).
  - **Le bloc « Qui est Serge » complet** : la chaîne des 8 étapes, la
    place de l'invocation, et ce qui vient juste avant et juste après
    elle, lu dans les liens. Aujourd'hui, il ne contient que la
    présentation de Serge et le titre de l'invocation.

  Détail des tables prévues :
  [`docs/LOT6_CONCEPTION.md`](docs/LOT6_CONCEPTION.md), partie 16.

- [ ] **Passer un lien à la main.** Un lien peut être réglé pour attendre
  un clic avant de lancer l'invocation suivante. Exemple : après
  « Concevoir le POC », attendre le feu vert avant de construire.
  Aujourd'hui, l'attente est notée en base, mais rien ne permet de la
  débloquer : un lien réglé ainsi bloquerait la chaîne pour toujours. Il
  faut, dans MC, voir pour chaque lien ce qui est déjà passé et ce qui
  attend, un bouton « passer à la suite » et un interrupteur « passage
  automatique ». Ce passage à la main existera à côté de la validation
  par ticket Discord du lot 8 : les deux servent.

- [ ] **Mission Control affiche le pipeline tel qu'il est en base.** La
  fiche d'une invocation montre déjà tous ses réglages ; la page Cerveau,
  toutes les invocations ; la page En direct, les étapes, les deux files
  et les coupe-circuits. Il manque une vue d'ensemble des capacités, des
  outils, des liens et des déclencheurs ; le modèle choisi derrière
  chaque niveau (rapide, moyen, intelligent) et le texte « Qui est
  Serge », à afficher et à rendre modifiables. Ce sera une nouvelle page
  « Pipeline ». Créer une invocation depuis le site reste le travail du
  lot 13.

---

## Lot 8 — Conversations avec les prospects et les clients

Les messages des prospects et des clients sont imprévisibles : questions
sur le produit, demandes de changement, questions de délais, sujets sans
rapport. On ne peut pas tout prévoir, mais on calibre les cas classiques,
et Serge sait demander de l'aide quand il ne sait pas.

- [ ] **Ne jamais agir deux fois à l'extérieur.** À faire quand on crée la
  première capacité qui agit hors de Serge (envoyer un e-mail). Une tâche
  qui agit hors de Serge (envoyer un e-mail, passer un appel, rembourser
  un client) doit enregistrer « en cours » en base avant d'agir, puis
  « fait » juste après. Si le programme plante entre les deux, la tâche
  reste marquée « en cours » et n'est pas relancée toute seule : elle
  apparaît dans MC pour qu'on vérifie. Chaque envoi porte déjà une clé
  unique, qu'il faut garder. Il faudra pour cela une colonne sur les
  capacités (« agit hors de Serge ») et un état de plus sur les tâches.

- [ ] **Les capacités et réglages des conversations.** Ce lot ajoute ce
  que le lot 6 a volontairement laissé de côté. Des capacités : relever
  une boîte mail, envoyer un e-mail, ouvrir un ticket complet, et bloquer
  toutes les adresses d'une personne qui se désinscrit. Des réglages en
  base : une condition simple sur un lien ou une écriture (par exemple
  « seulement si le champ `reaction` vaut `désinscription` »), pour que la
  suite dépende de la réponse sans code propre ; que les programmes qui
  reçoivent de l'extérieur (SMS, e-mail, paiements) préviennent les
  déclencheurs « une ligne est écrite », comme le fait l'interpréteur,
  pour qu'un message reçu lance bien « Traiter une réponse » ; « une
  seule tâche en attente par prospect », pour que deux messages coup sur
  coup ne créent qu'une réponse ; un délai sur un lien, tiré entre le
  minimum et le maximum du canal ; et « demander à Julien si tel champ vaut oui », qui
  ouvre un ticket et fait attendre la tâche.

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

- [ ] **Une seule invocation pour traiter une réponse.** Aujourd'hui,
  trois ou quatre invocations lisent le même message de prospect chacune
  de leur côté : l'une le classe, l'autre cherche l'intention, une autre
  cherche un rendez-vous. Il faut les remplacer par une seule invocation,
  « Traiter une réponse ». Elle reçoit en entier le fil du prospect, sa
  fiche, la fiche du business et la fiche produit, et rend trois choses :
  la réaction du prospect, la réponse à envoyer (ou « pas de réponse »),
  et si Julien doit intervenir. Elle repère aussi les demandes sur le
  produit (bug, insatisfaction, idée) et les range dans la table des
  demandes clients. La réponse part après le délai réglé pour le canal
  (voir plus bas). Si Julien doit intervenir, ou si un garde-fou bloque
  l'envoi, il reçoit un ticket avec le brouillon. Cette invocation a son
  propre interrupteur, car elle sert aussi pendant la prospection légère.
  Elle a besoin du fil de discussion.

- [ ] **Une fiche produit détaillée pour chaque business.** Pour
  répondre juste à une question sur le produit, l'invocation qui répond
  doit tout savoir du produit. Aujourd'hui, la fiche d'un business n'a que
  trois textes courts (description, observations, offre vendable), et
  aucune fiche produit n'existe. Il faut une fiche produit par business, en
  base : ce que fait le produit et pour qui, ce qu'il ne fait pas, le prix,
  les délais habituels de livraison, comment on l'utilise, et une liste de
  questions fréquentes avec leurs réponses. Elle est écrite par
  l'invocation qui conçoit le produit (à l'étape 2 pour le POC, à l'étape 5
  pour le vrai produit) et validée par Julien avec le plan ; il y en aura
  peu. Elle est mise à jour à chaque nouvelle version du produit. On ne
  fait jamais appel à l'invocation qui a construit le produit pour
  répondre : elle ne garde aucun souvenir d'un appel à l'autre, tout doit
  être dans la fiche. Quand Julien répond à un ticket sur une question
  produit, sa réponse est ajoutée aux questions fréquentes : la fois
  suivante, Serge répond seul.

- [ ] **Répondre prudemment aux questions de délais.** Les questions de
  délais sont les plus difficiles à prévoir. On laisse le LLM répondre
  seul, avec la fiche produit, mais son prompt contient trois consignes de
  prudence : ne jamais promettre une date ou un délai qui n'est pas dans la
  fiche ; ne jamais promettre une fonctionnalité qui n'existe pas (la
  demande devient une demande client, étudiée pour une prochaine
  version) ; en cas de doute, répondre sans s'engager, par exemple « je
  vérifie et je reviens vers vous », et ouvrir un ticket.

- [ ] **Des tickets qu'on comprend sans suivre Serge.** Julien et Clem
  ne regardent pas ce que fait Serge au quotidien : c'est tout l'intérêt.
  Quand un ticket leur arrive, ils ne connaissent ni le business ni le
  prospect. Aujourd'hui, un ticket de réponse ne contient que le brouillon
  et une phrase de motif. Il faut que chaque ticket de conversation
  contienne toujours, dans cet ordre : le business en trois lignes (nom, ce
  qu'il vend, prix, où il en est) ; le prospect (nom, entreprise, où il en
  est) ; le fil de la conversation, avec les derniers messages en entier ;
  le brouillon de réponse proposé par Serge ; pourquoi Serge a besoin
  d'aide et la question précise posée ; un lien vers la fiche du prospect
  dans MC. La réponse donnée dans Discord repart dans la conversation.
  Ouvrir un ticket est une capacité générale : le ticket reprend ce que
  l'invocation a reçu et ce qu'elle a répondu, dans l'ordre réglé en base.
  On n'écrit pas un modèle de ticket par invocation.

- [ ] **Des délais de réponse réglables canal par canal.** Serge ne
  répond pas à la seconde, pour paraître humain. Aujourd'hui, le délai est
  un seul réglage pour tous les canaux. Il faut le mettre sur la fiche de
  chaque canal, modifiable dans MC : délai minimum, délai maximum, heures
  et jours ouvrés. Exemple : par e-mail entre 5 et 20 minutes, sur
  LinkedIn entre 1 et 4 heures, par SMS tout de suite. On pourra ainsi
  essayer différents réglages et voir ce qui marche le mieux.

- [ ] **Un agent vocal qui sait à qui il parle.** Un appel ne passe pas
  par la file des tâches : le standard téléphonique installé sur le
  serveur décroche et confie l'appel à un programme vocal séparé, qui
  parle en direct avec un modèle vocal et tourne en parallèle du reste. Il
  n'y a donc rien à interrompre quand un appel arrive. Mais aujourd'hui,
  l'agent vocal a le même prompt fixe pour tous les appels et ne sait rien
  de celui qui appelle. Il faut qu'au décrochage, le numéro soit cherché en
  base ; s'il est connu, l'agent reçoit la fiche du prospect, son fil, la
  fiche du business et la fiche produit. S'il est inconnu, l'agent dit
  « Bonjour, je suis Serge, en quoi puis-je vous aider ? », demande à qui
  il parle, et cherche la fiche avec un tool (par nom, entreprise, e-mail
  ou numéro). Si l'appelant propose quelque chose à Serge, comme un
  partenariat, l'agent répond poliment qu'il ne peut pas traiter ce genre
  de demande pour l'instant, et le résumé est quand même écrit au journal.
  Quand la personne est reconnue seulement parce qu'elle a dit son nom, et
  pas par son numéro, l'agent se sert de sa fiche pour comprendre, mais ne
  répète aucune information sensible (montants, adresses, propos d'un
  collègue) : n'importe qui peut prétendre être quelqu'un au téléphone.
  Après l'appel, le résumé entre dans le fil du prospect, et « Traiter une
  réponse » est lancée s'il y a une suite à donner, par exemple envoyer le
  devis promis par e-mail. L'agent vocal suit la même règle que le reste :
  son prompt, son modèle, ce qu'il reçoit au décrochage et ses tools sont
  réglés en base, comme une invocation ; seul le programme qui transporte
  la voix en direct est du code, et il ne sait rien de ce qu'on dit.

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
  chaque nouveau site. C'est le chantier où la tentation d'écrire du code
  pour un cas précis sera la plus forte ; la règle de ce fichier s'y
  applique entièrement. Il faut d'abord installer sur le serveur un
  moteur de recherche gratuit et sans clé (SearXNG), et s'en servir à la
  place de la page de résultats de DuckDuckGo. Il faut ensuite une
  capacité « Lire une page » qui monte d'un cran seulement si nécessaire :
  une simple requête, puis un vrai navigateur Chrome piloté si la page a
  besoin de JavaScript, puis un service de navigateur distant si le site
  bloque ; chaque montée est écrite au journal. **Le bac à sable est une
  capacité générique, réglée en base.** Un bac à sable est un espace isolé
  où Serge peut naviguer, écrire des fichiers et lancer des commandes. La
  base décrit chaque profil de bac à sable : ce qui y est installé, les
  sites qu'il peut joindre, le temps et la mémoire permis, les secrets et
  les comptes auxquels il a accès. Une invocation dit en base quel profil
  elle utilise ; les tools du bac à sable (ouvrir une page, cliquer,
  remplir un formulaire, lire un fichier, lancer une commande) sont des
  capacités comme les autres, qu'on lui donne ou non. **L'« Agent web »
  n'est donc pas du code** : c'est une invocation LLM réglée en base, qui
  reçoit une mission en paramètre (par exemple « crée un compte sur ce
  forum ») et les tools du navigateur dans son bac à sable, avec une
  session par compte qui garde ses cookies. Créer un compte de bout en
  bout est un enchaînement d'invocations en base : l'agent web remplit le
  formulaire, une invocation lit le code de confirmation dans la boîte
  mail ou les SMS, un ticket demande à un humain de résoudre un captcha
  (avec un lien vers l'écran en direct dans MC), et le compte est écrit en
  base par la capacité d'écriture générique. **Un connecteur n'est pas du
  code non plus** : quand un site a une API gratuite, le service est
  décrit en base (son adresse, le secret à utiliser, ses points d'entrée
  et leurs paramètres), et une seule capacité « Appeler une API » sait
  appeler n'importe quel service décrit ainsi. L'invocation « Construire
  un connecteur » lit la documentation du service et écrit cette
  description en base ; Julien la valide par ticket avant qu'elle soit
  utilisable, grâce à une règle d'écriture « validation par Julien »,
  qui sera ajoutée au catalogue d'écriture à ce moment-là. Le choix d'un
  profil de bac à sable par invocation sera aussi une colonne ajoutée par
  ce lot. Le
  tool « navigateur » prévu jusqu'ici disparaît au profit de tout ça.

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
  découverte de contacts. Pour chacune, il faut soit la décrire en base
  dans le nouveau pipeline, soit la supprimer, et dans les deux cas
  supprimer le code qui lui était propre. On ne garde pas de code mort.

- [ ] **L'éditeur sans code dans Mission Control.** C'est le but du
  lot 6 à terme. Une fois tout le pipeline décrit en base, une page de MC
  doit permettre de le modifier en direct, sans écrire de code, et de
  créer une invocation de toutes pièces : son rôle, son modèle, son
  prompt, ce qu'elle reçoit et les tools qu'elle peut appeler, le format
  de sa réponse, où elle l'écrit et avec quelles protections, les liens
  qui l'enchaînent aux autres et les déclencheurs qui la lancent. La page
  montre le pipeline comme un schéma, et chaque changement est écrit au
  journal avec la date et l'auteur, pour pouvoir revenir en arrière.
  C'est le dernier lot. Il ne doit demander aucun code nouveau pour une
  invocation : s'il en manque, c'est que le lot 6 a laissé quelque chose
  en dur.

---

## Étape 1 — Pré-prospection

- [ ] **Refaire l'étape en sept invocations qui ont chacune un seul
  rôle.** Aujourd'hui, deux invocations « Explorer les besoins » font tout
  à la fois : chercher sur le web, lire, repérer des besoins et en tirer
  des idées de business. Il faut découper le travail. D'abord, une
  invocation sans LLM lit les flux RSS suivis. Ensuite, « Explorer le web »
  cherche des pages à partir du petit texte de guidage que Julien écrit
  dans MC et des business déjà connus. « Trier les pages », avec un modèle
  rapide, met une étiquette sur chaque page nouvelle : elle enrichit un
  business déjà connu, elle signale un besoin nouveau, ou c'est du bruit.
  Deux invocations « Formuler des business », A et B, lisent les pages qui
  signalent un besoin et écrivent chacune des fiches de business avec
  leurs pages de preuve ; B ne voit jamais ce qu'a écrit A, pour avoir des
  idées variées. Les doublons sont écartés au moment de l'écriture, par la
  règle de doublons déclarée en base pour la table des business, et le
  reste est enregistré comme candidat. « Choisir les business à tester »
  en choisit autant qu'il y a de places libres en prospection légère. Tout
  business déjà en test est refusé par la règle des changements de statut
  permis, déclarée en base : c'est une protection appliquée par le code
  d'écriture générique, pas une consigne dans un prompt, et pas du code
  propre à cette invocation. Le cycle se lance à la main depuis MC, et ne
  tourne que s'il reste une place libre. Le prompt des invocations qui
  formulent et choisissent doit dire que le business doit être légal, et
  les encourager à ne pas s'arrêter sur des scrupules moraux qui ne sont
  pas contraires à la loi. Le détail est dans
  [`docs/etapes/1-pre-prospection.md`](docs/etapes/1-pre-prospection.md).
  Cette tâche a besoin du lot 6 et des places de test : les sept
  invocations, leurs liens et leurs réglages sont décrits en base. Les
  prompts de l'ancien cycle sont dans `pas_encore_branche/`. Le demi-cycle
  de démonstration du lot 6 est alors retiré de `config/pipeline.yaml` et
  marqué supprimé en base : retirer une ligne du fichier ne l'efface pas
  d'une instance existante.

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
  le rythme des relances, et la fiche produit du POC (voir le lot 8). Une
  deuxième invocation, « Challenger le POC », relit ce plan et ne peut
  répondre que deux choses par remarque : « à corriger » ou « il faut une
  nouvelle capacité ». On fait au plus trois allers-retours, et le plan
  final doit être réalisable avec ce que Serge sait faire. Julien valide
  ensuite le plan et la fiche produit dans un ticket Discord ; sans
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

- [ ] **Prospecter sur LinkedIn.** LinkedIn est un canal important pour
  vendre à des professionnels. Serge l'utilise avec son propre compte, à
  un volume modéré, et Julien valide chaque message et chaque publication
  avant qu'ils partent. Cette validation n'est pas du code propre à
  LinkedIn : c'est un réglage en base sur l'invocation d'envoi, « validation
  par Julien avant d'agir », que n'importe quelle invocation peut avoir.
  Les garde-fous d'envoi doivent connaître ce canal. Cette tâche a besoin
  du web.

- [ ] **Les autres canaux.** Chaque type de business n'a pas le même bon
  canal. Il faut ajouter WhatsApp, la publication sur des forums ou
  Reddit, la publicité (Google, Meta, LinkedIn, Reddit) et l'envoi de SMS.
  Pour chaque canal, il faut une façon d'envoyer et de relever, son barème
  de points et sa fiche dans le catalogue de MC. Envoyer et relever passent
  soit par un service décrit en base et la capacité « Appeler une API »,
  soit par l'agent web ; on n'écrit un adaptateur de code que si le canal
  ne peut vraiment pas passer par là (le téléphone, par exemple), et cet
  adaptateur sert alors toutes les invocations, jamais une seule. Cette
  tâche a besoin du web et de la grille de points.

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
  pouvoir encaisser. Une invocation conçoit le produit et écrit sa fiche
  produit (voir le lot 8), une autre les critique, puis Julien valide dans
  un ticket, en fixant le prix définitif. Serge construit ensuite le
  produit avec un duo : un constructeur qui écrit, un relecteur qui répond
  « bon », « à corriger » ou « il faut une nouvelle capacité ». Ce duo est
  fait de deux invocations LLM réglées en base, qui travaillent dans un bac
  à sable avec ses tools génériques (écrire un fichier, lancer les tests,
  ouvrir la page) ; aucune ligne de code ne leur est propre. Le produit
  est mis en ligne sur un domaine acheté pour lui. Serge crée le produit
  et son prix dans Stripe, par la capacité « Appeler une API » et la
  description de Stripe en base, en inscrivant sur le prix l'identifiant
  du business, pour que chaque abonnement soit rattaché au bon business. Il
  fait enfin un paiement de test de 1 € qu'il se rembourse, pour vérifier
  que tout marche.

- [ ] **Mettre en ligne et ranger les fichiers.** Les livrables doivent
  être en ligne et faciles à retrouver. Serge les publie sur son serveur,
  sur un sous-domaine pour un POC et sur un domaine acheté pour le
  business principal. Chaque version d'un livrable est rangée dans son
  propre dossier (le business, le livrable, puis le numéro de version), et
  n'est plus jamais modifiée une fois publiée. Chaque fichier a sa fiche
  dans la base. Publier est une capacité générale (« publier ce dossier à
  cette adresse »), réglée par ses paramètres, qui sert à tous les
  livrables.

---

## Étape 6 — Prospection lourde

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

---

## Plus tard

- [ ] **La consolidation de la mémoire dans le pipeline.** Aujourd'hui,
  la consolidation (étape 7) relit chaque jour le journal et propose des
  leçons, avec des appels au LLM écrits en dur. Au lot 6, son code est
  rangé dans le dossier « pas encore branché ». Il faudra la décrire en
  base comme le reste : un déclencheur quotidien, une invocation qui lit
  le journal, et une règle d'écriture qui ajoute des leçons au statut
  « proposée », que Julien garde ou jette.

- [ ] **La conversation avec Julien sur Discord, dans le pipeline.**
  Quand Julien écrit à Serge sur Discord, trois invocations écrites en dur
  traduisent le contexte, lisent son intention et jugent les conséquences.
  Au lot 6, ce code est rangé dans le dossier « pas encore branché » et le
  bot ne traite plus les messages libres. Il faudra que le bot range
  chaque message de Julien dans une table, et qu'un déclencheur « ligne
  écrite » lance les invocations, décrites en base comme les autres. C'est
  le même mécanisme que la réponse à un prospect : on le fera en même
  temps que les conversations, ou juste après.

- [ ] **Garder l'historique des réglages.** Pour l'instant, chaque
  changement de réglage fait dans Mission Control (un prompt, une règle
  d'écriture, un lien) est seulement noté au journal. Clem a décidé que
  ça suffit pour commencer : on veut d'abord une petite version qui
  marche. Plus tard, il faudra garder chaque ancienne version d'un
  réglage, avec sa date et son auteur, et un bouton dans Mission Control
  pour revenir à une version précédente.
