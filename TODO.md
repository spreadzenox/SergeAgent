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
Clem regarde le résultat avant qu'on attaque le suivant. **Les lots 1 à
13, le 8 bis et le 10 bis sont faits** (l'historique git en garde la
trace). **Le lot 12 reste à essayer sur le serveur**, avec l'essai total,
et le lot 13 avec de vrais comptes sur les réseaux.
Ce que chaque lot a vraiment livré :

- **Lots 1 à 7** : le runner, le pipeline en base (lot 6 : un seul
  programme, l'interpréteur, exécute toute invocation décrite en base) et
  l'étape 1, de l'écoute du web au choix des business (lot 7).
- **Lot 8** : les conversations par e-mail et par téléphone
  ([`docs/LOT8_CONCEPTION.md`](docs/LOT8_CONCEPTION.md)). **Lot 8 bis** :
  Julien dans la conversation (décisions Q85 et Q86). **Lot 9** : la
  grille de points (Q84). **Lot 10 bis** : les réponses automatiques
  (Q93).
- **Lot 10 « Concevoir et construire »** (Q91,
  [`docs/LOT10_CONCEPTION.md`](docs/LOT10_CONCEPTION.md)) : les étapes 2
  et 5 en base. Le plan d'un POC ou d'un produit et sa fiche produit, la
  critique, la validation par ticket, la construction dans un chantier
  (un conteneur par business et par livrable), la relecture dans un
  navigateur par un relecteur qui ne voit pas le code, le staging puis la
  prod, le domaine (acheté chez Cloudflare, ou un sous-domaine du domaine
  commun), la mise en vente dans Stripe et le paiement test de 1 €. Trois
  capacités générales : le bac à sable, l'interface web des invocations,
  et « Appeler une API ». Seulement des produits web.
- **Lot 11**, parti des e-mails des produits et devenu bien plus gros
  (Q95, Q96, Q97) :
  - **les e-mails des produits** : en chantier et en staging, une boîte
    d'essai (Mailpit) garde tout, et la fiche du business les montre ; en
    prod, Resend, avec une clé par produit, depuis un sous-domaine de
    Serge ; le relecteur a sa propre boîte, une adresse par essai ;
  - **des tâches qui s'arrêtent** : le bouton rouge arrête aussi la tâche
    en cours, une tâche a un plafond de dépense, une demande à Julien la
    gèle jusqu'à sa réponse (« Répondre » ou « Faire sans »), et sans
    crédit chez le fournisseur du modèle elle attend au lieu d'échouer ;
  - **une construction moins chère** : le constructeur ne navigue plus,
    un niveau de modèle « web » pour naviguer, le cache des modèles
    d'Anthropic, les captures retirées par paquets, chaque appel d'outil
    au journal. La construction d'une calculatrice est passée de 17 $ à
    2 $ ;
  - **des tickets lisibles** : « En bref » d'abord, puis « Voir en
    entier » ;
  - **le web dynamique** : un vrai Chrome sur un écran virtuel, donné par
    ses outils à une invocation à la place du navigateur sans écran ;
    « Appeler un humain » pour un captcha, en deux temps ; l'écran du
    vrai Chrome dans Mission Control, derrière la connexion ; un bouton
    de la page Système pour essayer ce passage de main sans captcha
    réel ;
  - **Anthropic en direct** pour les essais : un réglage envoie les
    modèles `anthropic/…` chez Anthropic, avec la clé et le workspace de
    l'instance.

  Essayé de bout en bout sur le serveur le 16 novembre 2026 : une
  calculatrice conçue, construite, relue, mise en ligne sur son domaine
  et mise en vente ; son paiement test de 1 € payé dans le vrai Chrome,
  vérifié dans Stripe et remboursé (12 appels au modèle, 0,08 $) ; le
  produit a ensuite été essayé à la main, inscription et paiement
  compris. Il reste, du lot 10, les versions suivantes d'un produit :
  elles sont au lot 16.

- [ ] **Avant le lot 8 : les réglages en base.** Toute grandeur
  discutable se règle depuis Mission Control, sans réglage en double
  (décisions Q68 et Q78). Les réglages sont en base, sur les pages Policy
  et Pipeline ; il reste à remettre, lot par lot, les réglages retirés
  parce que rien ne les lisait. Le détail est dans la partie « Avant le
  lot 8 » plus bas.
- [x] **Lot 12 « Jusqu'aux premières ventes ».** Le pipeline entier est
  en base, de l'écoute du web à la vente, par e-mail et par appel : les
  campagnes (un business, une phase, un canal), « Trouver des prospects »
  et son outil « Ajouter un prospect » (jamais d'adresse générique), la
  fin d'un test mesurée avec des seuils chiffrés, le choix du principal
  et son ticket, la prospection lourde, les ventes enregistrées, les
  places, et l'étape 1 qui repart toute seule. Un canal se branche sans
  toucher au reste. **Un seul essai, « l'essai total »**, remplace tous
  ceux de la page Système : il suit le vrai chemin dans un couloir à
  part (Q99). **« Repartir d'ici »** fait repartir une chaîne d'une tâche
  précise. Le détail est dans
  [`docs/LOT12_CONCEPTION.md`](docs/LOT12_CONCEPTION.md) (décisions Q92,
  Q93, Q98 et Q99). Il reste, à part :
  - **essayer le lot sur le serveur** : lancer l'essai total, étape par
    étape ;
  - **le téléphone pour des inconnus** : tant que le canal « voice »
    demande l'accord de la personne avant tout appel (page Policy,
    « Accord des gens », c'est le cas au départ), une campagne par
    téléphone ne démarre pas pour des prospects jamais contactés. C'est
    voulu (décision Q100) ; la voix sera reprise dans un lot suivant ;
  - **Mission Control** : les campagnes sur la page Système, les places
    sur la page En direct, le compte rendu d'un test sur la fiche de son
    business ; aujourd'hui, une campagne se lit sur sa fiche.
- [x] **Lot 13 « Web » : des comptes, les réseaux pour chercher et pour
  prospecter** (décision Q104). Serge savait déjà naviguer comme une
  personne (lots 10 et 11, Q103). Ce lot a mis cette capacité au service
  de deux choses : chercher sur Reddit, Instagram et X pendant l'écoute
  du web, en option ; et prospecter par LinkedIn, Instagram et X. Il a
  livré : les comptes web, un par site, avec leur mot de passe et leur
  session chiffrés en base, une session de navigateur par compte et la
  garde du jour ; « Créer un compte web » et « Vérifier un compte web » ;
  une invocation qui confie une mission à une autre ; « Fouiller un
  réseau », en option dans « Explorer le web » et « Trouver des
  prospects » ; les trois canaux, décrits en base, sans code à eux, avec
  la validation des messages par un humain réglée par canal ; cinq
  boutons d'essai sur la page Système. Le détail :
  [`docs/LOT12_CONCEPTION.md`](docs/LOT12_CONCEPTION.md), partie 17, et
  [`docs/LOT10_CONCEPTION.md`](docs/LOT10_CONCEPTION.md), partie 2.
  **Reste à essayer sur le serveur**, avec de vrais comptes : les créer,
  fouiller un réseau, envoyer un message d'essai. Les réseaux ne sont pas
  dans l'essai total : leurs boutons d'essai sont à part.
- [ ] **Lot 14 « L'éditeur sans code ».** Une page de Mission Control
  pour modifier le pipeline en direct et créer une invocation de toutes
  pièces : ajouter ou retirer des invocations, changer leur ordre, leur
  rôle, leur modèle, ce qu'elles voient et où elles écrivent, sans
  toucher au code. Il n'est possible qu'une fois le lot 6
  fait.
- [ ] **Lot 15 « Les logiciels ».** Construire et essayer des produits
  qui ne sont pas des services web : une application de bureau, une
  extension de navigateur, un bot. Il faudra un bac à sable avec un vrai
  bureau, où une invocation lance le logiciel, voit son écran et clique
  dedans, comme l'interface web du lot 10 le fait pour une page (Q91).
- [ ] **Lot 16 « Faire vivre les produits ».** Un produit qui a des
  clients s'entretient : ce n'est plus un pipeline avec un début et une
  fin. Ce lot clarifie puis imagine le système complet d'entretien des
  produits qui existent : le point de la semaine et ce que fait chacune de
  ses décisions, les retours des clients et les nouvelles versions, un
  service sur mesure (ajouter à un produit existant les fonctionnalités
  qu'un client demande, en rappelant le constructeur), les livraisons,
  les impayés et les remboursements, la maintenance et la fermeture d'un
  business. Ses tâches sont dans la partie « Lot 16 » plus bas ; les
  décisions qu'elles citent sont à revoir (Q92, Q93).

---

## Avant le lot 8 — Les réglages en base

Clem a fixé la règle le 1er octobre 2026 (décision Q68 de
[`docs/DECISIONS_REVUE.md`](docs/DECISIONS_REVUE.md)) : **toute grandeur
discutable, qui peut un jour changer, se règle depuis Mission Control.**

- [ ] **Remettre les réglages retirés, lot par lot.** La PR A (1er octobre
  2026) a retiré de la policy 54 réglages que rien ne lisait : leur code
  est rangé dans `pas_encore_branche/`. Un test vérifie que chaque réglage
  de la policy est lu par au moins un programme. **Le lot qui rebranche une
  capacité remet ses réglages**, lus par son code :
  - lot 8 (conversations, voix) : jours de prospection, marge avant un
    rendez-vous, jours fériés et fuseau du pays ; longueur du script,
    conservation des enregistrements, un numéro par business ; seuils de
    lecture des réponses. Sont remis : le délai de réponse, la relève
    récente de la boîte et les délais des relances (PR 1 du lot 8, sans
    heures ouvrées : Serge répond à toute heure, Q79) ; les jours et
    heures d'appel, la durée et les tours de parole d'un appel (PR 3) ;
  - lot 10 (construire) : les bornes de la construction, qui deviennent
    les ressources d'un chantier, les tours d'outils et les passages
    (partie 11 de [`docs/LOT10_CONCEPTION.md`](docs/LOT10_CONCEPTION.md)) ;
  - lot 12 (étapes 3, 4, 6, 7 et 8) : la répartition du budget, les invitations
    LinkedIn par mois, les devis et les essais de caisse, la consolidation
    de la mémoire (dont la leçon retirée après plusieurs démentis :
    aucune fonction en marche ne l'appelle aujourd'hui) ;
  - lot 13 (web) : le plafond du navigateur, les recherches en mémoire par
    cycle.
- La voix est réglée en base comme une invocation (« Parler au
  téléphone ») : son prompt, ses modèles, sa durée maximale et ses tours
  de secours ; ses heures d'appel et ses plafonds sont sur la page Policy
  (lot 8, PR 3).

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
  l'ancien module `serge/funnels/lifecycle.py`, qui imposait en dur les
  statuts d'un business et « un seul business actif à la fois », a été
  retiré au lot 12 : ses règles sont en base (`status_transitions`,
  `table_quotas`).

- [ ] **Remplir l'index de recherche dans la mémoire.** Le tool qui
  permet à une invocation de chercher dans la mémoire de Serge (leçons,
  événements, tickets) s'appuie sur un index de recherche. En production,
  rien ne remplit cet index, donc ce tool ne renvoie jamais rien. Il faut
  ajouter chaque nouvelle leçon, chaque nouvel événement et chaque nouveau
  ticket à l'index au moment où ils sont écrits. Ensuite, « Chercher dans
  la mémoire » deviendra un outil donné à toutes les invocations
  (`everywhere` dans `pipeline.yaml`), comme « Lire les tables que je
  vois » ; aujourd'hui, il est donné invocation par invocation.

- [ ] **Le web : ce qui reste après le lot 13.** Serge navigue comme une
  personne, avec ses comptes (lots 10, 11 et 13 : le bac à sable,
  l'interface web, le vrai Chrome, « Appeler un humain », les comptes web
  et leur garde). Il reste trois choses, à faire seulement quand un
  besoin réel les demande ; la règle de ce fichier s'y applique
  entièrement. **Un moteur de recherche gratuit et sans clé** sur le
  serveur (SearXNG), à la place de la page de résultats de DuckDuckGo.
  **« Lire une page » qui monte d'un cran** seulement si nécessaire : une
  simple requête, puis le navigateur sans écran si la page a besoin de
  JavaScript, puis le vrai Chrome si le site bloque (Q97) ; chaque montée
  est écrite au journal. **« Construire un connecteur »** : quand un site
  a une API gratuite, le service est décrit en base (son adresse, le
  secret à utiliser, ses points d'entrée et leurs paramètres), et la
  capacité « Appeler une API », construite au lot 10 pour Stripe et
  l'achat des domaines, sait appeler n'importe quel service décrit
  ainsi. L'invocation « Construire un connecteur » lit la documentation
  du service et écrit cette description en base ; Julien la valide par
  ticket avant qu'elle soit utilisable, grâce à une règle d'écriture
  « validation par Julien », qui sera ajoutée au catalogue d'écriture à
  ce moment-là.

- [ ] **Réécrire les commentaires qui renvoient à des documents
  supprimés.** Une centaine de commentaires dans le code citent des
  repères d'anciens documents qui n'existent plus, comme « P2 »,
  « R6 » ou « matrice C ». Il faut les réécrire en phrases claires au fur
  et à mesure qu'on touche à ces fichiers, et en profiter pour passer en
  anglais les noms de fonctions et de variables.

- [ ] **Brancher ou supprimer les invocations jamais appelées.** Douze
  invocations LLM sont écrites, avec leur prompt, mais rien ne les lance :
  le script d'appel vocal, le dialogue vocal, le résumé d'un fil, le
  départage de deux prospects, le résumé d'un test, l'hypothèse de test
  lourd, les options de pivot, le plan de passage à l'échelle, l'arbitre
  du budget, le résumé de la dette de construction, l'hypothèse de test léger, et la
  découverte de contacts. Pour chacune, il faut soit la décrire en base
  dans le nouveau pipeline, soit la supprimer, et dans les deux cas
  supprimer le code qui lui était propre. On ne garde pas de code mort.
  Le lot 12 en remplace cinq, et le point de la semaine du lot 16 trois
  autres (voir [`docs/LOT12_CONCEPTION.md`](docs/LOT12_CONCEPTION.md),
  partie 13).

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

## Étape 3 — Prospection légère

- [ ] **Trouver des prospects.** Serge sait écrire des e-mails et passer
  des appels, mais il ne sait pas encore à qui. Aujourd'hui, l'invocation
  de découverte de contacts enregistre seulement les contacts qu'on lui
  donne ; elle ne cherche rien, et personne ne l'appelle. Il faut une
  invocation qui cherche et qualifie des prospects pertinents pour le
  business testé, avec des adresses qui ne rebondissent pas, et qui garde
  la page d'où vient chaque adresse (il faudra ajouter cette information à
  la table des adresses de contact). Par e-mail et par téléphone, on ne
  contacte que des professionnels, et jamais une adresse générique
  (`contact@`, `info@`…) : on cherche une personne nommée, avec son rôle
  et son adresse directe (Q93). Au lot 12, elle cherche avec la
  recherche web et l'interface web du lot 10, et rend ses prospects par
  paquets de 10 (voir
  [`docs/LOT12_CONCEPTION.md`](docs/LOT12_CONCEPTION.md), partie 4) ; le
  lot 13 lui donne les comptes de Serge sur les réseaux.

- [ ] **Publier sur LinkedIn.** Serge écrit à des prospects sur LinkedIn,
  Instagram et X depuis le lot 13, avec la validation d'un humain réglée
  par canal. Il n'y publie rien : une publication (un post, un
  commentaire) reste à faire, avec la même validation.

- [ ] **Les autres canaux.** Chaque type de business n'a pas le même bon
  canal. Il reste WhatsApp, la publication sur des forums ou Reddit, la
  publicité (Google, Meta, LinkedIn, Reddit) et l'envoi de SMS. Un canal
  qui passe par le navigateur s'ajoute sans code : un compte, une ligne
  en base, ses réglages et son lien (conception du lot 12, partie 17). Un
  service qui a une API passe par « Appeler une API ». On n'écrit un
  adaptateur de code que si le canal ne peut vraiment pas passer par là
  (le téléphone, par exemple).

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
  places de test et de la grille de points. Les seuils d'un test sont
  passés aux points au lot 12 (réglages de « Mesurer le test »).

---

## Étape 5 — Construction

Faite aux lots 10 et 11 : concevoir le produit et sa fiche, le
construire dans un chantier, le relire, le mettre en ligne sur son
domaine, le mettre en vente et faire le paiement test de 1 € (voir
[`docs/etapes/5-construction.md`](docs/etapes/5-construction.md)). Les
versions suivantes d'un produit sont au lot 16.

---

## Étape 6 — Prospection lourde

La vente en masse du produit fini est au lot 12 (voir
[`docs/LOT12_CONCEPTION.md`](docs/LOT12_CONCEPTION.md), partie 7) ; le
suivi pendant la vente est au lot 16.

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
  moins une leçon, pour ne pas refaire les mêmes erreurs. Pour un business
  arrêté, c'est au lot 12 (« Tirer la leçon d'un business arrêté ») ; pour
  un business fermé, au lot 16.

---

## Lot 16 — Faire vivre les produits

Ces tâches viennent des étapes 5, 6 et 8. Elles décrivent ce qui avait été
décidé (Q43 à Q47) ; le lot 16 commence par les clarifier, puis imagine le
système complet (Q92, Q93).

- [ ] **Faire le point chaque semaine sur le business principal.** Une
  seule question compte : on continue, et à quelle vitesse ? Une fois par
  semaine, une invocation propose de continuer, d'accélérer (50 % de
  prospects en plus ou un canal de plus), de pivoter ou d'arrêter. Pivoter
  et arrêter passent par Julien. Cette invocation remplace trois
  invocations qui existent aujourd'hui sans être appelées (plan de passage
  à l'échelle, options de pivot, arbitre du budget).

- [ ] **L'adresse de contact des produits.** Un client écrit au produit
  (une question, un mot de passe, la suppression de son compte) : ses
  e-mails arrivent dans la boîte de Serge, rattachés au produit et au
  client, et Serge y répond. D'ici là, aucun produit n'a d'adresse ni de
  formulaire de contact, et les prompts le disent (Q96).

- [ ] **Un service sur mesure.** Proposer à un client d'ajouter à un
  produit existant les fonctionnalités qu'il demande, en rappelant le
  constructeur du lot 10 sur ce produit : le pipeline devient récursif.
  Pas pour tout de suite (Q93).

- [ ] **Les livraisons et les demandes des clients.** Serge ne sait pas
  aujourd'hui ce qui reste à livrer à un client. Il faut une table des
  livraisons, avec une ligne par chose
  vendue à livrer : le business, le client, le paiement, ce qu'il faut
  livrer, la date promise, l'état (à faire, en cours, livrée, problème) et
  le fichier livré. Une ligne est créée à chaque paiement d'un produit qui
  n'est pas livré instantanément, et une livraison en retard apparaît dans
  MC et passe en priorité haute. Cette table est créée en même temps que
  le code qui la remplit (l'encaissement), pour ne pas laisser dans la
  base une table vide que personne n'écrit. Les demandes des clients (les
  bugs, les insatisfactions et les idées d'amélioration) ont déjà leur
  table depuis le lot 8 (`customer_requests`), remplie par « Traiter une
  réponse » ; le lot 10 lui ajoute son état : nouvelle, retenue, livrée
  dans telle version, refusée avec sa raison (Q91). Sans ces deux tables,
  on ne peut pas savoir quand un business peut être fermé.

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

- [ ] **Couper tout seul un flux qui ne ramène que du bruit.** Au lot 7,
  un flux se coupe à la main. Plus tard : la coupure automatique d'un flux
  après 5 cycles de bruit (Q65). Le cycle qui repart tout seul quand une
  place se libère est fait au lot 12 (Q92). Le bouton « Effacer les
  idées (test) » est retiré (nettoyage du 16 novembre 2026).

- [ ] **Avant le vrai lancement : retirer le kit d'essai des canaux.** Le
  bouton « Lancer un essai » et ses invocations temporaires (« Lancer un
  essai », « Créer le contact d'essai », « Écrire le premier message »,
  « Préparer le premier appel ») servent à essayer l'e-mail et la voix
  (lot 8, Q79). Les lister dans la section `deleted` de `pipeline.yaml`
  quand les vraies invocations de prospection (lot 12) écriront les
  premiers messages.
  Même chose pour les essais du lot 10 (Q91) : « Essayer le chantier »,
  « Essayer l'interface web », « Publier le chantier d'essai »,
  « Essayer l'étape 2 », « Bout en bout : le POC d'une calculatrice »,
  « Bout en bout : le produit fini d'une calculatrice » et « Essayer
  Stripe (mode test) », avec leurs invocations temporaires
  (essayer_chantier, essayer_navigateur, publier_essai,
  creer_business_essai, choisir_business_essai, bout_en_bout_poc,
  bout_en_bout_produit, essayer_stripe), et les changements de statut
  qu'ils permettent (un business qui naît choisi pour un POC ou en
  construction de son produit, un plan qui naît validé). Le bouton
  « Construire le vrai produit » (lancer_produit) part quand l'étape 4
  (lot 12) choisira le business principal. Les boutons « Supprimer de Stripe » restent : ils
  nettoient après un business d'essai.

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

---

## Boîte à idées

Des fonctions marginales, à faire une fois tout le reste fini : Serge
marche très bien sans elles (Q79).

- **Une relance qui change de canal**, par exemple un e-mail, puis un
  appel si le contact a un numéro. Au lot 8, une relance garde le canal du
  premier message.
