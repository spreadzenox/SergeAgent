# Le pipeline de Serge

Ce document explique comment Serge fonctionne, de bout en bout. Il est
écrit pour quelqu'un qui arrive sans rien connaître du projet, humain ou
LLM. Chaque partie distingue ce que le code fait **aujourd'hui** de ce que
Julien et Clem ont **décidé** et qui reste à construire. La liste des
chantiers, dans l'ordre, est dans [`TODO.md`](../TODO.md) ; les échanges qui
ont mené à chaque décision sont dans
[`DECISIONS_REVUE.md`](DECISIONS_REVUE.md).

---

## Serge en quelques phrases

Serge est un programme qui cherche des besoins sur le web, teste des idées
de business auprès de vrais prospects, garde la meilleure, la construit, la
vend et encaisse. Il agit seul la plupart du temps, et demande à Julien de
valider les décisions importantes par un ticket Discord, où l'on peut
discuter avant de trancher.

Serge tourne en continu sur un serveur (le VPS de Julien). Chaque fois
qu'une modification du code arrive sur la branche `main`, il est
redéployé automatiquement. Julien le voit et le règle depuis **Mission
Control**, une console web.

Quelques mots reviennent souvent. Une **invocation** est une brique de
travail : soit un appel au LLM avec son prompt, soit un traitement sans
LLM. Un **business** (appelé « venture » dans le code) est une idée de
produit que Serge teste puis vend. Un **POC** est le petit livrable d'essai
qu'on montre aux prospects pendant le test.

---

## La chaîne des 8 étapes

Tout Serge est organisé autour d'une chaîne de huit étapes. Un business
avance d'étape en étape. Chaque étape a sa page dans
[`docs/etapes/`](etapes/), et un interrupteur dans Mission Control (page
En direct) : une étape coupée ne lance plus rien.

1. **La pré-prospection.** Serge lit le web et des flux RSS, repère des
   besoins réels, en tire des idées de business et choisit celles à
   tester.
2. **La conception du POC.** Serge écrit le plan du test et la fiche du
   produit d'essai, les fait critiquer par une deuxième invocation, Julien
   les valide, puis Serge construit le livrable et le met en ligne.
3. **La prospection légère.** Serge trouve une quarantaine de prospects,
   leur écrit ou les appelle, relance ceux qui n'ont pas répondu, et
   répond à ceux qui ont répondu. Chaque réaction rapporte des points.
4. **Le choix du business principal.** Quand les trois tests légers sont
   finis, Serge propose le meilleur, Julien valide, et les autres sont mis
   de côté.
5. **La construction.** Serge construit le vrai produit, écrit sa fiche
   produit, le met en ligne sur un domaine acheté pour lui et branche le
   paiement.
6. **La prospection lourde.** Serge prospecte à plus grande échelle, vend,
   livre, et améliore le produit avec les retours des clients.
7. **La mémoire.** Serge tire des leçons de ce qui s'est passé, et Julien
   garde ou jette chaque leçon.
8. **La caisse.** Serge encaisse par Stripe, relance les impayés et
   rembourse.

---

## La vie d'un business

Un business est une seule ligne dans la table des business. Seul son
statut change au fil de sa vie. Les business trouvés par l'étape 1 y sont
écrits directement, avec leur fiche (description, observations, offre
vendable) ; les pages web qui prouvent le besoin sont rangées à côté. Les
dates de début et de fin du test léger sont sur la fiche.

Aujourd'hui, les statuts possibles sont : candidat, choisi pour un POC,
prêt pour le test léger, en test léger, test léger fini, prêt pour le test
lourd, en test lourd, passage à l'échelle, pivot, extension, arrêté, et
invalide.

Julien a décidé le parcours suivant, qui reste à construire en entier :

```text
CANDIDATE        trouvé par l'étape 1
   ↓
POC_SELECTED     choisi pour être testé (prend une place de test léger)
   ↓
SMOKE_READY → SMOKE_RUNNING → SMOKE_DONE     test léger (étapes 2 et 3)
   ↓
choisi comme business principal (étape 4)  ──→  sinon PARKED
   ↓
construction (étape 5), puis prospection lourde (étape 6)
   ↓
MAINTENANCE      plus de nouveaux prospects, mais on livre, on répond,
   ↓             on corrige et on encaisse
CLOSED           plus rien à faire : fermé et archivé
```

Un business mis de côté (`PARKED`) a été testé mais pas choisi. Il libère
sa place, et il peut être repris si le business principal s'arrête, tant
que son test date de moins de 60 jours. Un business arrêté (`KILLED`)
n'avait aucun client. Chaque changement de statut est écrit au journal,
avec qui l'a décidé, quand et pourquoi. Les noms exacts des statuts entre
le choix du principal et la maintenance seront fixés pendant le chantier.

### Les places de test

Serge ne teste pas tout en même temps. Il a trois places en prospection
légère et une seule en prospection lourde, et ces deux nombres se règlent
dans Mission Control. Un business prend une place de prospection légère dès
qu'il est choisi à l'étape 1, et la garde pendant les étapes 2 et 3. Il n'y
a pas de file d'attente : quand les trois places sont prises, rien de
nouveau n'entre, et l'étape 1 ne cherche plus de business. Le business
principal n'est choisi que lorsque les trois tests légers sont finis, et
son passage en maintenance libère la place de prospection lourde.

Aujourd'hui, le code impose seulement « un seul business actif à la
fois ». Les places sont à construire.

---

## Comment Serge exécute le travail

Tout le travail de Serge passe par une **file de tâches**. Une tâche, c'est
« lancer telle invocation, avec tels paramètres ». Un programme, le
**runner**, prend toujours la tâche prête la plus prioritaire et l'exécute.
Une tâche entre dans la file de trois façons : parce que l'invocation
d'avant l'a lancée, parce qu'un événement s'est produit (un prospect a
répondu), ou parce qu'une heure est arrivée (relever la boîte mail toutes
les 5 minutes). Une tâche peut aussi porter une date « pas avant », ce qui
permet d'attendre quelques minutes avant de répondre à un prospect.

C'est ce qui permet à une chaîne fixe (les huit étapes) de réagir à ce qui
arrive : quand un prospect répond, une tâche « Traiter une réponse »
s'ajoute à la file, avec la priorité la plus haute.

Le runner tourne en continu, en deux copies, une par file
(`scripts/serge-queue.py`, services `serge-queue@conversations` et
`serge-queue@works`) :

- **Serge est arrêté par défaut.** Les deux services tournent, mais ne
  créent ni ne prennent aucune tâche tant que personne n'a cliqué
  « Démarrer Serge » dans Mission Control. Un déploiement ou une instance
  neuve ne démarre jamais Serge tout seul. Même chose pour la voix : elle
  ne décroche pas et n'appelle pas tant que Serge est arrêté.
- La file des conversations prend les tâches courtes (relever les boîtes,
  traiter une réponse, envoyer, relancer). La file des travaux prend les
  tâches longues (écoute du web, conception, construction). Ainsi, une
  construction de quarante minutes ne retarde jamais la réponse à un
  prospect. La file de chaque invocation se règle dans Mission Control.
- Chaque file exécute une tâche après l'autre et enregistre en base après
  chacune. Si une tâche échoue, seules ses écritures sont annulées ; elle
  est marquée en échec, avec la raison, et la file continue. Si le
  programme est arrêté au milieu d'une tâche (un redéploiement, par
  exemple), la tâche est reprise depuis le début au redémarrage, et c'est
  noté au journal.
- Chaque invocation a une priorité, réglable dans Mission Control. Valeurs
  de départ : 100 pour traiter une réponse ou une désinscription, 80 pour
  relever les boîtes et les messages entrants, 50 pour les envois et les
  relances, 30 pour la construction, 10 pour l'écoute, la veille et la
  consolidation.
- Dans une boucle d'outils, tout l'historique repart au modèle à chaque tour.
  Pour les modèles d'Anthropic, qui n'ont pas de cache automatique, le client
  demande à OpenRouter de le garder en cache (`cache_control`) dès que
  l'historique contient des résultats d'outils : lire en cache coûte dix fois
  moins que lire normalement, écrire 25 % de plus, donc le gain commence au
  troisième appel d'une conversation. Les autres fournisseurs cachent seuls.
  À vérifier sur un vrai appel : le coût de chaque appel d'une boucle doit
  cesser de croître à chaque tour.
- Deux plafonds de dépense, réglés sur la page Policy : celui du jour (par
  exemple 5 €) et celui du mois (par exemple 50 €), qui borne ce que Serge
  nous coûte en IA ; les achats de Serge pour ses business n'y comptent pas.
  Quand l'un est atteint, les tâches LLM attendent le lendemain ou le mois
  suivant ; les autres continuent. La dépense est le coût réel facturé par
  OpenRouter pour chaque appel (`llm_usage.cost_usd`), jamais une
  estimation ; les appels dont le coût n'est pas connu sont signalés à part.
- Aucune température n'est envoyée au modèle : il garde celle de son
  fournisseur, et le prompt fait le reste (décisions Q62 et Q68).
- Les appels au modèle se règlent sur la page Pipeline (famille « Appels
  au modèle ») : l'attente maximale d'une réponse (180 secondes au
  départ), les pauses avant de réessayer un appel raté pour une raison
  passagère (3 puis 10 secondes), le nombre de redemandes d'une réponse
  mal formée (2, sans outil) et la taille maximale d'un résultat d'outil
  (20 000 caractères). Les textes ajoutés au modèle (outils épuisés,
  consigne de format, redemande, résultat coupé) sont en base, modifiables
  sur la même page.
- À chaque tour, les tickets dont le délai est passé sont expirés : leur
  choix par défaut s'applique.

Une capacité qui agit à l'extérieur (aujourd'hui : envoyer un message)
enregistre « en cours » avant d'agir et « fait » après, pendant la tâche,
pour ne jamais agir deux fois : reprise après un arrêt, elle demande
d'abord au canal si son message est parti (décision Q79).

Les appels téléphoniques sont à part : le standard téléphonique décroche et
confie l'appel au pont vocal, qui parle en direct et tourne en parallèle
du runner. L'agent vocal est pourtant une invocation comme les autres
(« Parler au téléphone », file « Appels ») : chaque appel devient une de
ses tâches, menée en direct par le pont, avec son prompt, ce qu'il reçoit
et ses outils lus en base.

---

## Le pipeline est décrit dans la base

La base de données SQLite (`state/serge.db`) est la seule source de
vérité. Julien et Clem ont décidé d'aller jusqu'au bout de cette idée : **le
code n'est qu'un interpréteur de la base.** L'ordre des invocations et tous
leurs paramètres sont en base, et seulement en base. Pour chaque tâche, le
code lit en base la description de l'invocation à lancer et l'exécute
exactement comme elle est décrite.

Pour une invocation LLM, la base dit : son rôle, son étape, le modèle
appelé, son prompt, ce qu'elle reçoit dès le départ, les outils qu'elle peut
appeler et avec quels paramètres figés, le format de sa réponse et où
cette réponse est écrite, sa priorité et sa file, et si elle est allumée.
Ce qu'elle voit des autres tables pour comparer suit des règles réglées
une fois par table, les mêmes pour toutes les invocations (voir
[`MEMOIRE.md`](MEMOIRE.md)).
Les **liens** entre invocations sont aussi en base : un lien dit
« quand cette invocation a produit tel résultat, lance celle-ci, avec ces
données en paramètre ». Par exemple, chaque business choisi à l'étape 1
lance la conception de son POC, avec l'identifiant du business. Un lien
peut avoir une condition (« seulement si la réaction est
`désinscription` ») et un délai tiré entre deux réglages (la réponse à un
e-mail part entre 5 et 20 minutes plus tard). Les
**déclencheurs** sont en base eux aussi : « quand un message arrive d'un
prospect, lance "Traiter une réponse" pour ce prospect ». Plus tard, le bac
à sable (pour tester du code, naviguer sur le web, créer des comptes), les
connecteurs vers des services et les canaux suivront la même règle : des
capacités générales, réglées en base. Un connecteur, par exemple, n'est
pas du code écrit par Serge, mais la description du service en base,
utilisée par une seule capacité « Appeler une API ».

Le code, lui, est rangé par **capacité**, jamais par invocation : lire la
base, écrire dans la base, appeler un modèle, chercher sur le web, agir
dans un bac à sable, appeler une API décrite en base, envoyer ou relever
sur un canal, ouvrir un ticket. Chaque capacité est générale et réglée par
des paramètres lus en base. Il n'y a **jamais de code propre à une
invocation** : le nom d'une invocation n'apparaît dans le code que dans le
fichier qui remplit une nouvelle instance.

Même l'écriture en base est générale. Pour chaque invocation, la base dit
dans quelle table elle écrit, si elle ajoute ou modifie des lignes, et
quelle colonne reçoit quel champ de sa réponse. Ce n'est jamais le modèle
qui choisit où écrire. Les protections qui ne doivent pas dépendre d'un
prompt sont, elles aussi, des règles en base appliquées par ce code
d'écriture : les tables et colonnes autorisées, les changements de statut
permis, le repérage des doublons, les champs obligatoires, la validation
par Julien. Exemple : refuser un business déjà en test, c'est déclarer en
base que le statut d'un business ne peut passer à `POC_SELECTED` que
depuis `CANDIDATE`.

Les chiffres d'une invocation sont des **réglages** rangés avec elle. Un
réglage sert partout à la fois : dans le prompt (« Propose
{nombre_idees} idées »), dans le format de la réponse (une liste
d'exactement ce nombre d'éléments, vérifiée), dans l'écriture (« au plus
N lignes ») et dans les paramètres des outils et des liens. Une table
peut aussi avoir un **quota** : « au plus 3 business choisis pour un
POC », refusé par le code d'écriture quelle que soit l'invocation. Les
réglages et les quotas marqués « policy » se changent en direct sur la
page Policy de Mission Control.

Exemple de ce que ça permet : si Julien change dans Mission Control le
modèle de « Trier les pages », ou ajoute une invocation entre « Trier les
pages » et « Formuler des business », le cycle suivant en tient compte,
sans redéploiement. À terme, une page de Mission Control permettra de
modifier tout le pipeline sans écrire de code, et de créer une invocation
de toutes pièces : son rôle, son modèle, ce qu'elle reçoit, où elle écrit,
ce qui la lance.

**Où on en est (lot 6)** : les tables qui décrivent le pipeline existent,
et un seul programme, l'interpréteur (`serge/interpreter/`), exécute
n'importe quelle invocation décrite en base. Tout le code écrit en dur pour
un enchaînement (le cycle d'écoute, la relève du mail, le circuit des
réponses, la consolidation) a été rangé dans `pas_encore_branche/`. Le
pipeline de départ (`config/pipeline.yaml`) contient les files, les
modèles, la présentation de Serge, les outils, les protections des
tables, et l'étape 1 entière (voir
[`etapes/1-pre-prospection.md`](etapes/1-pre-prospection.md) et
[`LOT7_CONCEPTION.md`](LOT7_CONCEPTION.md)). Les étapes suivantes sont
l'objet des lots suivants. Serge ne peut
donc pas encore être allumé pour de vrai, et il est arrêté par défaut.

### Ce que le code met dans la base

Le fichier `config/pipeline.yaml` contient le pipeline de départ. Il sert
à remplir la base d'une nouvelle instance, et à ajouter sur une instance
existante les objets nouveaux. Il ne modifie jamais un objet qui existe
déjà. Exemple : Julien modifie le prompt d'une invocation dans Mission
Control ; un développeur modifie ensuite le prompt de départ dans le
fichier ; au déploiement, l'instance de Julien garde son prompt, et une
nouvelle instance reçoit celui du fichier.

Le code, lui, déclare au démarrage ses capacités (`serge/capabilities.py`)
et calcule l'empreinte de leurs fichiers. Quand un fichier change, Mission
Control peut afficher « code modifié le … ».

Rien n'est effacé au démarrage : une invocation supprimée dans Mission
Control ne revient pas. Seule une capacité retirée du code est marquée
absente, et la fiche des outils qui s'en servaient le signale.

---

## Qui décide quoi

Serge agit seul par défaut. Julien valide dans un ticket Discord, où l'on
peut discuter, les décisions suivantes :

- le plan d'un POC et sa fiche produit, à l'étape 2 ; sans réponse sous
  48 heures, le plan s'applique ;
- le choix du business principal, à l'étape 4 ; sans réponse sous
  48 heures, le choix proposé s'applique ;
- le prix définitif, le plan et la fiche du vrai produit, à l'étape 5 ;
- pivoter ou arrêter le business principal, une nouvelle fonctionnalité
  importante ou un changement de prix, à l'étape 6 ;
- chaque message et chaque publication sur LinkedIn ;
- un connecteur vers un nouveau service, écrit par Serge ;
- un remboursement au-dessus du seuil, à l'étape 8 ;
- les leçons proposées par la consolidation, à l'étape 7 ; sans réponse
  sous 48 heures, elles sont acceptées.

Après le lot 8, Serge ouvrira aussi un ticket quand il ne saura pas
répondre à un prospect (lot « Julien dans la conversation » ; d'ici là,
les réponses partent seules, décision Q79).
Ce ticket doit être compréhensible par quelqu'un qui ne suit pas Serge : il
contient le business en trois lignes, le prospect, le fil de la
conversation, le brouillon de Serge et la question précise posée.

**La seule limite de Serge est la légalité.** Il ne trompe personne et
assume d'être un agent IA.

---

## Parler aux prospects et aux clients

Chaque prospect a un fil de discussion unique, tous canaux confondus, qui
garde les messages envoyés par Serge et les réponses reçues. Une seule
invocation, « Traiter une réponse », lit ce fil avec la fiche du prospect,
la fiche du business et la fiche produit, puis rend la réaction du
prospect (question, refus, désinscription…), la réponse à envoyer (ou
rien) et les demandes sur le produit. La règle la plus importante : Serge
ne relance jamais quelqu'un qui a déjà répondu, et il le vérifie au moment
même de l'envoi.

Le circuit est décrit en base (lot 8, décision Q79) :

- toutes les 2 minutes, chaque canal qui se relève (l'e-mail) est relevé ;
  un message reçu est rattaché à son contact par le fil, sinon par son
  adresse. Le message d'un inconnu n'est pas traité : il apparaît dans
  Mission Control (page Système) ;
- un message rattaché lance « Traiter une réponse », une seule tâche en
  attente par contact ;
- la réponse part entre 5 et 20 minutes plus tard, à toute heure et tous
  les jours (réglé par canal sur la page Policy, 0 pour les tests) ;
- toutes les 15 minutes, « Préparer les relances » cherche qui n'a pas
  répondu : une relance 3 jours après le premier message, une autre
  7 jours après, sur le même canal ;
- une désinscription bloque la personne partout, sur tous les canaux et
  pour tous les business, et un ticket prévient Julien et Clem.

Le canal e-mail est branché : Gmail par l'outil `gog`, ou une boîte
SMTP/IMAP, selon le fichier d'instance ; au plus 40 e-mails par jour (page
Policy). Le canal appel est branché aussi : un appel part dans les heures
d'appel de la page Policy (sinon il attend le prochain créneau), l'agent
vocal sait à qui il parle, et la transcription entre dans le fil ; la
suite d'un appel part par e-mail si Serge a l'adresse, sinon il rappelle
(décision Q83). Pour essayer les deux canaux, le bouton « Lancer un essai »
(page Système) crée un business bidon, puis Serge écrit et appelle la
personne indiquée. Le détail est dans
[`LOT8_CONCEPTION.md`](LOT8_CONCEPTION.md).

---

## Mesurer un test : la grille de points

Chaque message reçu (un e-mail, la transcription d'un appel) est classé
par « Traiter une réponse » parmi huit réactions : rendez-vous, intéressé,
question, objection, refus, absence, hors sujet, désinscription. La grille
de points donne à chaque réaction de 0 à 10 points, selon un barème par
canal, réglé sur la page Policy (famille « Grille de points », un réglage
par canal et par réaction). Le barème de départ est le même pour l'e-mail
et l'appel : rendez-vous 10, intéressé 8, question 4, objection 3, refus 1
(un refus poli montre quand même que le besoin intéresse), 0 pour le
reste. Un nouveau canal arrive avec son barème de départ.

Un prospect compte une fois, pour sa meilleure réaction dans son business,
tous canaux confondus : on mesure jusqu'où chacun est allé, et un prospect
qui écrit cinq fois ne gonfle pas le total (décision Q84). Les points se
recalculent avec le barème du moment : le changer recompte tous les
business de la même façon. Seules les réponses comptent : Serge ne suit
ni les ouvertures ni les clics de ses e-mails.

On compare deux business avec deux chiffres : le total de leurs points
(fiche du business, page Économie, bandeau d'En direct), et leurs points
par euro dépensé (à venir : le coût des modèles de leurs tâches et leurs
minutes d'appel). Chaque message, avec sa réaction, reste dans le fil du
contact.

---

## Où lire la suite

- Les étapes une par une : [`docs/etapes/`](etapes/)
- La mémoire et ce que voit chaque invocation : [`MEMOIRE.md`](MEMOIRE.md)
- La base de données : [`DB.md`](DB.md)
- La console : [`MISSION_CONTROL.md`](MISSION_CONTROL.md)
- Les règles pour écrire du code : [`CHARTE.md`](CHARTE.md)
- L'installation : [`installation/`](installation/)
