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

### Ce que la règle demande concrètement (appris au lot 6)

Chaque lot qui ajoute une table, une invocation ou un événement doit aussi
remplir la base, dans `config/pipeline.yaml` (le détail est dans
[`docs/LOT6_CONCEPTION.md`](docs/LOT6_CONCEPTION.md)) :

- **Une table qu'une invocation doit voir a sa vue** (`table_views`) : un
  titre, la colonne qui dit quelles lignes sont les plus récentes, ses
  colonnes lisibles et celles de sa version courte. Sans vue, aucune
  invocation ne la voit : ni en version courte, ni avec « Lire les tables
  que je vois ». Une colonne sensible (mot de passe, secret, cookie,
  numéro de carte) n'est jamais marquée lisible.
- **Une table où une invocation écrit** est déclarée inscriptible
  (`writable_tables`, avec ses colonnes permises) et protégée : statuts
  permis (`status_transitions`), doublons (`dedup_rules`), quotas
  (`table_quotas`). Toute invocation qui y écrit en reçoit d'office la
  version courte, pour comparer ; on peut la lui retirer sur sa fiche.
- **Chaque chiffre d'une invocation** (nombre d'idées, de pages, de
  relances…) est un réglage de l'invocation (`invocation_settings`),
  marqué `policy` s'il doit se régler en direct sur la page Policy. Jamais
  une valeur dans le code, ni dans la policy générale, qui ne garde que ce
  qui ne concerne aucune invocation (budget du jour, quotas d'envoi,
  heures d'appel).
- **Un événement qui concerne une ligne la nomme** (`append_event(...,
  rows=[(table, id)])`) : un envoi à un contact, une réponse reçue, un
  paiement. C'est ce qui remplit l'historique que lit « Lire
  l'historique ». Les écritures des invocations et les événements d'un
  business le font déjà.
- **Une leçon est rattachée** à une invocation (`invocation:<id>`), à une
  étape (`etape:<id>`) ou à tout Serge (`global`) : elle est donnée
  d'office à qui la concerne.
- **Ce qu'on retire de `pipeline.yaml` est listé dans sa section
  `deleted`** : le fichier ajoute les objets nouveaux sur une instance
  existante, mais n'efface jamais rien de lui-même.
- **Changer une valeur d'un objet déjà en base passe par la section
  `changes`** de `pipeline.yaml` (des tours d'outils, un prompt, un
  réglage) : une seule fois par instance, et seulement si la valeur est
  encore celle d'origine. Jamais une migration qui nomme une invocation,
  jamais une retouche à la main sur le serveur. Un réglage nouveau
  s'ajoute tout seul.
- **Chaque appel au modèle coûte** : tout l'historique d'une invocation
  repart au modèle à chaque tour d'outils. Garder peu de tours, laisser
  le modèle appeler plusieurs outils d'un coup, borner ce qu'un outil
  rend (lignes lues, pages lues ; un résultat trop long est de toute
  façon coupé, taille réglée dans la policy), et regarder le coût réel
  noté pour chaque appel.

---

## Dans quel ordre

On avance par lots. Un lot est un ensemble de tâches qui vont ensemble ;
chaque lot se termine par des tests verts et un commit, puis Julien ou
Clem regarde le résultat avant qu'on attaque le suivant. Les lots 1 à 5
sont faits : fusion des branches, correction de deux bugs graves,
nettoyage du code mort, nouvelle documentation, et remise en ordre des
données (business, contacts, abonnements).

- [x] **Lot 6 « Le runner et le pipeline en base ».** Fait (septembre
  2026) : le détail est dans la partie « Lot 6 » plus bas. C'est la fondation
  de tout le reste, et Clem et Julien veulent l'attaquer ensemble. Il
  commence par le runner, le programme qui exécute les tâches : il doit
  exécuter une tâche après l'autre et enregistrer en base après chacune,
  sur deux files en parallèle, parce qu'aujourd'hui un plantage peut faire
  envoyer deux fois le même e-mail. Ensuite, tout le pipeline passe en
  base : l'ordre des invocations, leur modèle, leur prompt, ce qu'elles
  reçoivent, leurs outils, où elles écrivent, ce qui les déclenche. Le code
  ne fait plus que lire la base et exécuter ce qu'elle décrit. Tout le
  code écrit en dur pour un enchaînement est supprimé, sans chercher à le
  garder en marche. À la fin du lot, Serge ne peut pas encore être
  allumé pour de vrai, parce que certaines capacités manquent ; mais en
  modifiant la base, on peut déjà construire n'importe quel pipeline avec
  les capacités qui existent. Les tâches détaillées sont dans la partie
  « Lot 6 » plus bas.
- [x] **Lot 7 « Étape 1 ».** Fait (septembre 2026). On refait la pré-prospection avec des
  invocations qui ont chacune un seul rôle, on garde les pages retenues
  comme preuves, et Serge choisit et lit lui-même ses flux RSS. Ce lot est
  le premier à être décrit entièrement en base grâce au lot 6. Les
  réponses de Clem sur l'étape 1 sont dans la décision Q65 de
  [`docs/DECISIONS_REVUE.md`](docs/DECISIONS_REVUE.md).
- [ ] **Avant le lot 8 : les réglages en base.** Toute grandeur
  discutable se règle depuis Mission Control (décision Q68) : on retire
  les réglages que rien ne lit, on range les réglages généraux dans une
  table en base, et on réorganise les pages Pipeline et Policy. Le détail
  est dans la partie « Avant le lot 8 » plus bas.
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

Ce qui est fait (il ne reste rien à construire dans ce lot) :

- les tables du pipeline (version 24 de la base), les deux files du
  runner qui tournent en continu et enregistrent après chaque tâche,
  l'interpréteur qui exécute n'importe quelle invocation décrite en base
  (sans « kinds »), l'écriture générique et ses protections, la priorité
  et l'interrupteur de chaque invocation ;
- le remplissage de départ, qui n'efface et n'écrase rien, et un
  demi-cycle de démonstration de l'étape 1 dans `config/pipeline.yaml` ;
- le rangement de l'ancien code dans `pas_encore_branche/` (version 25)
  et le test qui vérifie la règle (`tests/test_regle_interpreteur.py`) ;
- les réglages des invocations et les quotas des tables, modifiables sur
  la page Policy (version 26), par exemple « nombre d'idées » de la démo,
  ou « au plus 3 business choisis pour un POC » ;
- ce que voit chaque invocation (version 27) : la version courte des
  tables où elle écrit, les plus récentes d'abord, les outils « Lire les
  tables que je vois » et « Lire l'historique », ses leçons et le bloc
  « Qui est Serge » complet ;
- le passage d'un lien à la main (version 28), depuis la fiche du lien
  dans MC, à côté de la validation par ticket du lot 8 ;
- Mission Control branché sur les nouvelles tables, dont la page
  « Pipeline » : la vue d'ensemble du pipeline en base, où l'on choisit
  le modèle de chaque niveau et réécrit le texte « Qui est Serge » ;
- Serge arrêté par défaut : il ne tourne qu'après un clic sur « Démarrer
  Serge » dans Mission Control.

Le vrai pipeline, étape par étape, est l'objet des lots suivants.

---

## Avant le lot 8 — Les réglages en base

Clem a fixé la règle le 1er octobre 2026 (décision Q68 de
[`docs/DECISIONS_REVUE.md`](docs/DECISIONS_REVUE.md)) : **toute grandeur
discutable, qui peut un jour changer, se règle depuis Mission Control.**

- [x] **Retirer les réglages que rien ne lit** (PR A, 1er octobre 2026).
  58 des 91 réglages de la policy n'étaient lus par aucun programme en
  marche, mais Mission Control les affichait. 4 sont maintenant branchés
  (voir plus bas) ; les 54 autres sont retirés de la policy, de sa
  vérification et de la page, avec les 2 réglages de « Ce qui pourrait
  passer tout seul ». Il en reste 35. Un ancien snapshot qui contient un
  réglage retiré ne l'affiche plus. Un test vérifie que chaque réglage restant
  est lu par au moins un programme. Les encarts « Demander un
  changement » et « Ce qui pourrait passer tout seul » sont retirés de la
  page Policy (Q68, point 8). **Le lot qui rebranche une capacité remet
  ses réglages**, lus par son code :
  - lot 8 (conversations, voix) : jours et heures d'appel, jours de
    prospection, marge avant un rendez-vous, jours fériés et fuseau du
    pays ; durée et tours de parole d'un appel, longueur du script,
    conservation des enregistrements, un numéro par business ; délai de
    réponse et heures ouvrées des réponses, relève de la boîte mail ;
    silences avant une relance ; seuils de lecture des réponses ;
  - lot 9 (grille de points) : le barème de prospection ;
  - lot 10 (construire) : les bornes de la construction ;
  - lot 11 (étapes 3 à 8) : la répartition du budget, les invitations
    LinkedIn par mois, les devis et les essais de caisse, la consolidation
    de la mémoire (dont la leçon retirée après plusieurs démentis :
    aucune fonction en marche ne l'appelle aujourd'hui) ;
  - lot 12 (web) : le plafond du navigateur, les recherches en mémoire par
    cycle.
- [x] **Brancher les chiffres en double sur leur réglage** (PR A) : les
  nouveaux essais d'une réponse mal formée (`quotas.llm_recalls_json`) et
  les plafonds anti-rafale des SMS reçus (`quotas.sms_*`), lus à chaque
  SMS.
- [x] **Température du fournisseur** (PR A). Le client du modèle n'envoie
  plus de température (Q62).
- [x] **Brancher le plafond du mois** (PR A) : il borne ce que Serge nous
  coûte en IA (coût réel des modèles, mois calendaire UTC comme le jour) ;
  atteint, les tâches LLM attendent le mois suivant, avec la raison dans
  la file. Une jauge « Ce que Serge coûte ce mois-ci » est sur En direct.
- [ ] **Les réglages généraux dans une table en base** (PR B), avec pour
  chacun sa valeur, son titre, son aide et ses bornes. Mission Control les
  affiche sans catalogue écrit dans le code. Chaque réglage garde sa
  valeur précédente (qui, quand) : un bouton « Remettre la valeur
  précédente » ; pas d'historique complet (Q68, point 7). Les valeurs en
  vigueur sur le serveur sont reprises, pas celles du fichier.
- [ ] **Les chiffres discutables du code deviennent des réglages** :
  appels au modèle (attente, nouveaux essais, pauses), lecture du web
  (longueur d'une ligne, taille et temps de lecture d'une page, résultats
  d'une recherche, articles d'un flux), valeurs par défaut des outils,
  filtres de la recommandation de modèle.
- [ ] **Les textes envoyés au modèle en base**, modifiables sur la page
  Pipeline, à côté de « Qui est Serge ».
- [ ] **Réorganiser les pages.** Pipeline : le modèle de chaque niveau et
  les filtres de la recommandation, les appels, les textes envoyés au
  modèle. Policy : les limites de Serge face au monde, avec les réglages
  des invocations et les quotas des tables.
- La voix n'est pas dans ce chantier : le lot 8 la règle en base comme une
  invocation (aujourd'hui, 3 minutes d'appel dans le code contre 10 dans
  la policy).

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
  ouvre un ticket et fait attendre la tâche. La validation d'un lien par
  ticket Discord vient à côté du passage à la main construit au lot 6
  (bouton « Passer à la suite » sur la fiche du lien, fonction
  `pass_waiting`) : la réponse de Julien au ticket passe le lien de la
  même façon, et les deux portes restent ouvertes (Q62). Il faut aussi
  des vues de tables (`table_views`) pour les contacts, leurs adresses,
  les envois, les réponses reçues, le fil et la fiche produit, et que les
  événements de ces tables nomment la ligne concernée, pour que « Lire
  l'historique » d'un prospect montre tout son fil.

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

- [ ] **Ajuster la recommandation de modèle avec le temps.** La page
  Pipeline cherche un modèle parmi ceux d'OpenRouter et recommande, pour
  chaque niveau, celui qui a le meilleur rapport note / prix (la note est
  l'indice d'Artificial Analysis que `/models` donne avec chaque modèle).
  Elle a été essayée sur le vrai catalogue le 30 septembre 2026 : 464
  modèles, 146 notés (31 %). Les plafonds de prix (0,30, 1,50 et 8 $ le
  million de jetons) et les tolérances (85 % pour le niveau rapide, 95 %
  pour les autres) ont été réglés ce jour-là et sont à revoir quand de
  nouveaux modèles sortent : ils donnaient alors
  `deepseek/deepseek-v4.1-flash`, `xiaomi/mimo-v2.6-pro` et
  `anthropic/claude-sonnet-5.5`. Ils se règlent dans Mission Control (page
  Pipeline), avec le modèle de chaque niveau. Limite connue : un modèle sans
  note n'est jamais recommandé. La note est l'indice d'intelligence général ;
  Julien a choisi de le garder plutôt que l'indice « agentique »
  (`agentic_index`).

- [ ] **Les places de test.** Serge ne doit pas tester plus de business
  qu'il ne peut en suivre. Il faut trois places en prospection légère et
  une seule en prospection lourde. Un business prend une place de
  prospection légère dès qu'il est choisi à l'étape 1 et la garde pendant
  les étapes 2 et 3. Il n'y a pas de file d'attente : quand les trois
  places sont prises, l'étape 1 ne lance plus de cycle et MC affiche
  « 3 places sur 3 occupées ». Les deux nombres (3 et 1) doivent être
  modifiables dans MC. Le lot 6 a posé la première pierre : un quota de
  table, au plus 3 business au statut `POC_SELECTED` en même temps,
  modifiable sur la page Policy. Le lot 7 lui fait compter aussi les
  statuts des étapes 2 et 3 (Q65). Il restera la place de prospection lourde, l'affichage « 3 places
  sur 3 occupées » et l'arrêt du cycle quand tout est pris. Par ailleurs,
  un ancien module, `serge/funnels/lifecycle.py`, impose encore en dur
  les statuts d'un business et « un seul business actif à la fois », ce
  qui ne correspond plus à ce qu'on veut : ses règles doivent passer en
  base (`status_transitions`, `table_quotas`) et le module disparaître.

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
  ticket à l'index au moment où ils sont écrits. Ensuite, « Chercher dans
  la mémoire » deviendra un outil donné à toutes les invocations
  (`everywhere` dans `pipeline.yaml`), comme « Lire les tables que je
  vois » ; aujourd'hui, il est donné invocation par invocation.

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
  base par la capacité d'écriture générique ; les colonnes secrètes des
  comptes (mot de passe, cookies) ne sont jamais marquées lisibles dans
  leur vue de table. **Un connecteur n'est pas du
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
  en dur. Ce qui se règle déjà dans MC à la fin du lot 6 : allumer ou
  éteindre une invocation, une étape, une file ; les réglages marqués
  « policy » et les quotas (page Policy) ; les tables qu'une invocation
  voit pour comparer (sa fiche) ; le passage d'un lien, à la main ou
  automatique (fiche du lien) ; le modèle de chaque niveau et le texte
  « Qui est Serge » (page Pipeline) ; le prompt, le niveau, la file et la
  priorité d'une invocation, par l'API seulement. Il restera à régler
  depuis le site : le prompt dans la page, les lectures d'office d'une
  invocation (ce qu'elle doit traiter), ses outils, le format de sa
  réponse, ses règles d'écriture, créer ou supprimer un réglage, les
  colonnes lisibles et courtes de chaque table, les liens, les
  déclencheurs et les protections des tables. Clem a prévenu que
  l'organisation actuelle des réglages pourra changer à ce moment-là
  (Q63) : la façon de tout régler reste à concevoir.

---

## Étape 1 — Pré-prospection

C'est le lot 7. Décisions de Clem sur cette étape : Q65 dans
[`docs/DECISIONS_REVUE.md`](docs/DECISIONS_REVUE.md) ; le détail de
l'étape est dans
[`docs/etapes/1-pre-prospection.md`](docs/etapes/1-pre-prospection.md),
et ce qui a été construit dans
[`docs/LOT7_CONCEPTION.md`](docs/LOT7_CONCEPTION.md). Fusionné dans `main`
et déployé le 28 septembre 2026 ; il reste à Julien de lancer le premier
vrai cycle.
Tout est décrit en base (`config/pipeline.yaml`) : aucune ligne de code
n'est propre à une de ces invocations.

- [x] **Le cycle, une invocation par rôle.** Il se lance à la main depuis
  la page Écoute (plus tard, automatiquement), un cycle à la fois : le
  bouton est refusé tant qu'un cycle est ouvert, et un bouton « Abandonner
  le cycle » ferme un cycle resté ouvert (une invocation qui a échoué, par
  exemple) et annule ses tâches en attente. Il s'enchaîne ainsi :
  1. **« Ouvrir un cycle »** (sans LLM) enregistre le cycle et le texte de
     guidage de Julien.
  2. **« Explorer le web »** (modèle moyen) cherche des pages à partir du
     texte de guidage (sinon, dans les 11 familles de business de Q32) et
     des business déjà connus, en France d'abord (recherches en français,
     pages en anglais acceptées), au plus 10 recherches (réglage). Elle
     ne lit qu'un aperçu de chaque page (5 lignes, réglage) et ne garde
     que les pages qu'elle retient, au plus 30 (réglage). Elle ajoute
     aussi les flux RSS qu'elle juge utiles, au plus 2 par cycle
     (réglage) : Serge choisit ses flux lui-même, sans accord de Julien.
  3. **Rattacher au cycle les pages pas encore triées** (sans LLM) : celles
     des flux et du web, les plus récentes d'abord, au plus 60 (réglage).
  4. **« Trier les pages »** (modèle rapide), par paquets de 20 pages
     (réglage), sur leur aperçu seulement : chaque page enrichit un
     business existant (elle lui est rattachée comme preuve), signale un
     besoin nouveau, ou c'est du bruit.
  5. **« Formuler des business A »** puis **« Formuler des business B »**
     (modèle intelligent, l'une après l'autre) reçoivent l'aperçu des pages
     « besoin nouveau » pas encore utilisées, lisent en entier celles
     qu'elles veulent (seulement des pages en base, au plus 150 lignes par
     page et 10 pages par passage, réglages), et écrivent chacune 3 idées
     (réglage). Une fiche cite au moins une page de preuve et sa famille
     de business (Q32). Une fois l'idée écrite, les pages utilisées sont
     reclassées : elles deviennent des preuves rattachées à ce business.
     B ne reçoit donc que les pages que A n'a pas utilisées ; celles qui
     restent après B repassent au cycle suivant, sans être retriées.
     B voit les business écrits par A (version courte donnée d'office) :
     Serge ne fait pas deux fois la même chose. Leur prompt dit de ne
     jamais reproposer un business qui existe déjà. Les doublons restants
     sont écartés à l'écriture par la règle de doublons des business.
  6. **« Choisir les business à tester »** (modèle moyen) en choisit au
     plus autant qu'il y a de places libres, parmi tous les candidats en
     base (y compris ceux des cycles précédents), sur la force des
     preuves, la facilité d'un test rapide, un premier revenu rapide et la
     légalité. La raison de chaque choix (une phrase) est gardée sur la
     fiche du business, visible dans MC.
     Un business déjà en test est refusé par la règle des statuts permis.
     Le cycle est ensuite fermé.

  Le prompt des invocations qui formulent et choisissent dit que le
  business doit être légal, et les encourage à ne pas s'arrêter sur des
  scrupules moraux qui ne sont pas contraires à la loi (Q33). Les prompts
  de l'ancien cycle sont dans `pas_encore_branche/`.

- [x] **Les places de test de l'étape 1.** Une place est occupée par un
  business `POC_SELECTED`, `SMOKE_READY`, `SMOKE_RUNNING` ou `SMOKE_DONE`
  (Q14 bis) : le quota `business_choisis` doit compter ces quatre statuts,
  et « Choisir » doit voir les business en test pour compter les places
  libres (une lecture d'office). La page Écoute affiche « places libres :
  2 sur 3 ». Quand tout est pris, le bouton du cycle est bloqué : une
  condition générale sur un bouton ou un lien, du type « seulement si
  moins de N lignes dans tel état » (avancée du lot 8).

- [x] **Lire une page, à la bonne dose.** Une capacité « lire une page »
  (une simple requête, sans navigateur, texte extrait avec la
  bibliothèque standard de Python), réglée par un nombre de lignes (une
  ligne = un titre, un paragraphe ou un élément de liste) : un aperçu de
  5 lignes (réglage) pour les invocations qui trient ou retiennent des
  pages, la page entière pour celles qui formulent des business. On ne sature pas
  les invocations d'informations. La recherche reste DuckDuckGo ;
  SearXNG vient au lot 12.

- [x] **Garder les pages retenues.** Les pages qu'« Explorer » retient et
  celles des flux sont enregistrées, avec leur adresse, leur source, le
  cycle qui les a trouvées, leur aperçu et leur étiquette de tri ; jamais
  leur texte entier. Pour une page de flux, l'aperçu est le résumé donné
  par le flux. Un résultat de
  recherche non retenu n'est pas gardé (la base ne doit pas exploser),
  mais une page déjà triée n'est jamais représentée comme nouvelle.

- [x] **Les flux RSS en base.** Une table des flux : adresse, ajouté par
  quelle invocation, actif ou non. La lecture des flux actifs tourne
  seule, toutes les 6 heures (réglage), sans LLM. Mission Control montre,
  pour chaque flux, les pages ramenées et les pages utiles, avec un
  bouton pour le couper ou le rallumer. Julien n'ajoute pas de flux au
  lot 7. Au plus 20 pages lues par flux à chaque passage (réglage) ; le
  surplus attend le cycle suivant, les plus récentes d'abord.

- [x] **Empêcher la base de grossir sans fin.** Des réglages (des
  invocations, marqués « policy », ou des quotas de table, pas la policy
  générale) : 60 pages triées au plus par cycle ; une page « bruit » est
  oubliée après 30 jours, c'est-à-dire que sa ligne est supprimée (jamais
  une page qui sert de preuve), avec une note au journal ; de même pour
  une page jamais triée au bout de 30 jours, et pour une page « besoin
  nouveau » jamais utilisée au bout de 60 jours (réglage). Couper un flux
  qui ne ramène que du bruit se fait à la main au lot 7 ; plus tard,
  automatiquement après 5 cycles de bruit.

- [x] **La page Écoute.** Les flux, le bouton du cycle avec les places
  libres, et le dernier cycle : les pages trouvées, leur étiquette, les
  fiches écrites et les business choisis.

- [x] **Un bouton temporaire « Effacer les idées ».** Il détruit toutes
  les idées (les business encore candidats ou choisis, et leurs
  preuves), pour tester le cycle en production autant de fois qu'on veut
  (Q65). À retirer avant le vrai lancement de Serge. Julien n'est pas
  averti à la fin d'un cycle ; « Choisir » peut ne rien choisir, en
  disant pourquoi ; une idée hors des 11 familles est rangée en
  « autre ».

- [x] **Avant la fusion.** Montrer tous les prompts à Clem (validés le
  28 septembre 2026). Une seule fusion dans `main`, à la fin du lot. Le premier vrai cycle est lancé par
  Julien après la fusion, avec 1 idée par invocation pour un essai peu
  cher, puis 3.

- [x] **Retirer la démo du lot 6.** Retirer le demi-cycle de
  `config/pipeline.yaml` et le marquer supprimé en base : ses trois
  invocations, ses deux liens, son bouton « Lancer un cycle (démo) », et
  l'outil « Lire les business connus » s'il ne sert plus. Supprimer aussi
  les business et les cycles qu'elle a laissés sur le serveur de Julien
  (Q65). Retirer une ligne du fichier ne l'efface pas d'une instance
  existante.

- [x] **Ce que le lot 6 demande ici.** Des vues de tables (`table_views`)
  pour les pages, les pages d'un cycle, les flux et les preuves d'un
  business ; les tables inscriptibles et leurs protections ; les chiffres
  en réglages des invocations (les chiffres de l'ancienne section
  « Écoute » de la policy y reviennent, Q64) ; et pour chaque invocation
  son niveau, le bloc « Qui est Serge », le maximum de lignes données
  d'office et le nombre d'appels d'outils.

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
  de l'étape 5. En attendant les tickets du lot 8, le lien entre la
  conception et la construction peut être réglé à la main : Julien donne
  son feu vert avec « Passer à la suite », sur la fiche du lien dans MC.

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
  qu'on a appris sur son propre travail. Depuis le lot 6, une leçon
  rattachée à une invocation (portée `invocation:<id>`) ou à une étape
  (`etape:<id>`) est donnée d'office à qui la concerne, avant celles de
  tout Serge. Il reste à ce que la consolidation propose ce rattachement.
  Une leçon encore candidate (pas encore gardée par Julien) est déjà
  donnée comme les autres ; seules les leçons dépassées ou expirées ne le
  sont pas.
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

- [ ] **L'étape 1 en automatique.** Au lot 7, le cycle se lance à la main
  et un flux qui ne ramène que du bruit se coupe à la main. Plus tard : un
  déclencheur qui lance le cycle tout seul quand une place se libère, et
  la coupure automatique d'un flux après 5 cycles de bruit (Q65). Avant
  le vrai lancement de Serge, retirer le bouton « Effacer les idées
  (test) » (le lister dans la section `deleted` de `pipeline.yaml`).

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
