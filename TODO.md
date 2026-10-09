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
Clem regarde le résultat avant qu'on attaque le suivant. Les lots 1 à 9,
sauf le 8 bis, sont faits (l'historique git en garde la trace) : le
runner et le pipeline en base, l'étape 1, les conversations par e-mail et
par téléphone (lot 8 : voir
[`docs/LOT8_CONCEPTION.md`](docs/LOT8_CONCEPTION.md)), et la grille de
points (lot 9, décision Q84).

- [ ] **Avant le lot 8 : les réglages en base.** Toute grandeur
  discutable se règle depuis Mission Control, sans réglage en double
  (décisions Q68 et Q78). Les réglages sont en base, sur les pages Policy
  et Pipeline ; il reste à remettre, lot par lot, les réglages retirés
  parce que rien ne les lisait. Le détail est dans la partie « Avant le
  lot 8 » plus bas.
- [ ] **Lot 8 bis « Julien dans la conversation ».** Les tickets qui font
  attendre une réponse : « besoin de Julien », valider un brouillon, la
  réponse de Julien qui repart dans la conversation, des tickets qu'on
  comprend sans suivre Serge.
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
  du code écrit pour une invocation. C'est aussi ce qui ouvre les canaux de
  conversation par machine virtuelle : un LLM qui se connecte à LinkedIn,
  Instagram, Facebook ou n'importe quel site, avec une invocation
  temporaire « Envoyer le premier LinkedIn » pour le tester (Q79).
- [ ] **Lot 13 « L'éditeur sans code ».** Une page de Mission Control
  pour modifier le pipeline en direct et créer une invocation de toutes
  pièces : ajouter ou retirer des invocations, changer leur ordre, leur
  rôle, leur modèle, ce qu'elles voient et où elles écrivent, sans
  toucher au code. Il n'est possible qu'une fois le lot 6
  fait.

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
  - lot 10 (construire) : les bornes de la construction ;
  - lot 11 (étapes 3, 4, 6, 7 et 8) : la répartition du budget, les invitations
    LinkedIn par mois, les devis et les essais de caisse, la consolidation
    de la mémoire (dont la leçon retirée après plusieurs démentis :
    aucune fonction en marche ne l'appelle aujourd'hui) ;
  - lot 12 (web) : le plafond du navigateur, les recherches en mémoire par
    cycle.
- La voix est réglée en base comme une invocation (« Parler au
  téléphone ») : son prompt, ses modèles, sa durée maximale et ses tours
  de secours ; ses heures d'appel et ses plafonds sont sur la page Policy
  (lot 8, PR 3).

---

## Lot 8 bis — Julien dans la conversation

Au lot 8, les réponses partent toutes seules (Q79). Ce lot ajoute ce qui
fait attendre une réponse jusqu'à ce que Julien ou Clem ait répondu :

- [ ] **« Besoin de Julien »** : « Traiter une réponse » dit aussi si
  Julien doit intervenir, et pourquoi. Un oui ouvre un ticket et fait
  attendre la tâche (`ask_julien_field`, et un statut « attend Julien »
  sur les tâches). Un garde-fou qui bloque un envoi fait de même. Sans
  réponse à l'expiration du ticket (délai réglable), Serge envoie une
  réponse d'attente prudente, sans s'engager, et le ticket reste ouvert
  (Q85).
- [ ] **Valider un brouillon avant l'envoi**, au début ou pour un business
  sensible : un interrupteur par business, éteint par défaut (Q85), et la
  validation d'un lien par ticket, à côté du passage à la main construit
  au lot 6 (bouton « Passer à la suite » sur la fiche du lien, fonction
  `pass_waiting`) ; les deux portes restent ouvertes (Q62).
- [ ] **La réponse de Julien repart dans la conversation** : trois
  boutons, « Envoyer le brouillon », « Envoyer ma réponse telle quelle »,
  « Réécrire avec mes consignes » (le nouveau brouillon revient dans le
  même ticket, Q85). Quand la question portait sur le produit, sa réponse
  s'ajoute aux questions fréquentes de la fiche produit : la fois
  suivante, Serge répond seul (Q50).
- [ ] **Des tickets qu'on comprend sans suivre Serge.** Quand un ticket
  arrive, Julien et Clem ne connaissent ni le business ni le prospect.
  Chaque ticket de conversation contient, dans cet ordre : le business en
  trois lignes (nom, ce qu'il vend, prix, où il en est) ; le prospect (nom,
  entreprise, où il en est) ; le fil, avec les derniers messages en
  entier ; le brouillon de Serge ; pourquoi il a besoin d'aide et la
  question précise ; un lien vers la fiche du prospect dans Mission
  Control (Q50). Ouvrir un ticket est une capacité générale : le ticket
  reprend ce que l'invocation a reçu et ce qu'elle a répondu, dans l'ordre
  réglé en base, jamais un modèle de ticket par invocation.
- [ ] **Une réponse réveille le pipeline.** Les types de tickets et les
  administrateurs Discord sont en base, et chaque ticket part en message
  privé à chacun ; la première réponse le tranche pour tous (PR 1, Q85 et
  Q86). Il reste à réveiller une ou plusieurs invocations quand un ticket
  est tranché, réglées en base par type de ticket, et à appliquer la
  décision par défaut d'un type à l'expiration.

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

## Étape 2 — Conception du POC

- [ ] **Concevoir, faire critiquer, valider, construire.** Un POC doit
  proposer quelque chose de concret à essayer, pas seulement une promesse.
  Pour chaque business choisi, une invocation « Concevoir le POC » écrit
  un plan de A à Z : le livrable d'essai, les prospects visés, les canaux,
  le rythme des relances, et la fiche produit du POC (table
  `product_sheets`, lot 8). Une
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
  de l'étape 5. En attendant les tickets du lot 8 bis, le lien entre la
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
  places de test et de la grille de points. Les seuils d'un essai (page
  Policy, « Taille des essais ») comptent encore les signaux « veut
  acheter » des anciennes campagnes, que plus rien n'écrit : ils doivent
  passer aux points.

---

## Étape 5 — Construction

- [ ] **Construire le vrai produit.** Pas de prospection lourde sans
  pouvoir encaisser. Une invocation conçoit le produit et écrit sa fiche
  produit (table `product_sheets`, lot 8), une autre les critique, puis
  Julien valide dans un ticket, en fixant le prix définitif. Serge construit ensuite le
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

- [ ] **Noter les appels, ou retirer la section qui les attend.** La page
  Voix de MC a une section « Qualité des appels », et
  `serge/voice/quality.py` sait ranger la note d'un appel, mais aucune
  invocation ne note les appels : la section dit « pas encore branché ».
  Il faut soit une invocation qui note chaque transcription (en base,
  comme les autres), soit retirer la section et ce code.

- [ ] **Avant le vrai lancement : retirer le kit d'essai des canaux.** Le
  bouton « Lancer un essai » et ses invocations temporaires (« Lancer un
  essai », « Créer le contact d'essai », « Écrire le premier message »,
  « Préparer le premier appel ») servent à essayer l'e-mail et la voix
  (lot 8, Q79). Les lister dans la section `deleted` de `pipeline.yaml`
  quand les vraies invocations de prospection (lot 11) écriront les
  premiers messages.

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
