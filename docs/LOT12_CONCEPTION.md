# Lot 12 — Conception : du business imaginé à la vente du produit fini

Ce document décrit la suite du pipeline après le lot 10 : comment Serge
trouve des prospects, mène le test léger d'un business, le juge, choisit le
business principal, puis vend en masse le produit fini, tel qu'il sort de
la construction : la liste des invocations, des tables, des liens, des
déclencheurs et des réglages en base. Le lot est codé depuis le
16 novembre 2026 ; il reste à l'essayer sur le serveur, avec l'essai
total (partie 18).

Ce lot s'appelait le lot 11 jusqu'au 15 novembre 2026 : un lot 11 pour les
e-mails des produits s'est placé avant lui, et les lots suivants ont pris
un cran (décision Q95). Les décisions Q92 et Q93 gardent les numéros
d'alors : leur lot 11 est ce lot 12, et leur lot 15 est le lot 16.

Il suit les réponses de Clem du 13 octobre 2026 (décisions Q92 et Q93 de
[`DECISIONS_REVUE.md`](DECISIONS_REVUE.md)) et les décisions déjà prises :
les places de test (Q14, Q14 bis), les business mis de côté (Q15, Q44), la
grille de points (Q16, Q84), trouver les prospects (Q36), les envois et
relances (Q37, Q79), le circuit des réponses (Q38, Q50), le choix du
principal (Q16 bis), la caisse (Q47), le web (Q48) et le lot 10 (Q91). Et
la règle de tous les lots : le code n'est qu'un interpréteur de la base,
jamais de code propre à une invocation.

**Ce que le lot 12 couvre** : d'un business dont le POC est en ligne (fin
de l'étape 2, lot 10) jusqu'à la vente en masse du produit fini (étape 6),
en passant par le choix du principal (étape 4) et la construction du vrai
produit (étape 5, lot 10). La prospection lourde, c'est seulement vendre
en masse ce qui existe déjà.

**Ce qu'il ne couvre pas** : le suivi et le raffinement d'un produit
pendant qu'il se vend. Le point de la semaine (continuer, accélérer,
pivoter, arrêter), les retours des clients et les nouvelles versions, les
livraisons, les impayés, les remboursements, la maintenance et la
fermeture d'un business partent au lot 16, « Faire vivre les produits »,
placé tout à la fin (partie 15). Pour l'instant, le pipeline a un début et
une fin.

**Ce qui ne change pas** : l'étape 1 (écouter le web, formuler et choisir
les business) reste telle quelle. Le circuit des conversations (lot 8),
Julien dans la conversation (lot 8 bis) et la grille de points (lot 9)
sont réutilisés sans changement de fond. Les réponses automatiques, qui
peuvent faire répondre Serge sans fin, sont traitées à part, au lot 10 bis
(TODO).

**Une première version qu'on pourrait lancer** (décision Q98, 16 novembre
2026) : le pipeline entier, de l'écoute du web à la vente, avec deux
canaux, l'e-mail et l'appel. Deux exigences s'y ajoutent : **un canal se
branche sans toucher au reste** (partie 17), et **un seul essai, de bout
en bout, à part de ce qui tourne** (décision Q99, partie 18). La recherche
de prospects se fait avec la recherche web d'aujourd'hui ; le moteur de
recherche et la navigation sur des sites qui bloquent restent au lot 13.

Le lot se livre en deux PR (Q99 : la CI est longue). La première, déjà
fusionnée, marque les business d'essai et les sort des places de test. La
seconde apporte tout le reste : les étapes 3, 4 et 6, le couloir d'essai,
l'essai total, « repartir d'une tâche », et le retrait des anciens essais.

**Tous les chiffres sont des réglages en base**, comme d'habitude (Q68) :
les réglages d'une invocation, marqués « policy » pour se changer sur la
page Policy, ou la policy générale pour ce qui ne concerne aucune
invocation (les plafonds d'envoi par canal, par exemple). Aucun n'est écrit
dans le code. Les valeurs de ce document sont des valeurs de départ ; la
partie 9 les rassemble.

---

## 0. Le parcours d'un business, en une page

```text
CANDIDATE          trouvé par l'étape 1
   ↓  « Choisir les business »  (étape 1, existe)
POC_SELECTED       prend une place de test léger
   ↓  concevoir, construire, essayer le POC  (étape 2, lot 10)
SMOKE_READY        POC en ligne, campagne de test prête
   ↓  « Démarrer une campagne »
SMOKE_RUNNING      Serge trouve ses prospects (40 par e-mail, par exemple),
   ↓               écrit, appelle, relance, répond
   ↓  « Suivre une campagne » clôt chaque campagne finie ; puis « Mesurer
   ↓  le test », « Faire le bilan » et « Conclure le test »
SMOKE_DONE         test fini et retenu ; sous les seuils ──→ KILLED
   ↓  quand plus aucun test léger ne tourne et que la place lourde est libre
   ↓  « Choisir le business principal »  → ticket à Julien (48 h)
PRODUCT_BUILDING   le principal ; les autres retenus  ──→ PARKED
   ↓  concevoir, construire, essayer, mettre en vente  (étape 5, lot 10)
PRODUCT_READY      produit en vente sur son domaine, Stripe branché
   ↓  « Préparer la prospection lourde », puis « Démarrer une campagne »
FULL_RUNNING       vente en masse du produit fini, tel quel
   ↓  la suite (le point de la semaine, la maintenance…) : lot 16
```

Un business `PARKED` testé il y a plus de 60 jours redevient `CANDIDATE`
(Q44). Un business `KILLED` produit toujours une leçon (Q46). Une place de
test qui se libère relance l'étape 1, sans clic (Q92).

---

## 1. Ce que le lot 12 réutilise

- **L'étape 1** : « Choisir les business » écrit des business
  `POC_SELECTED`, au plus autant que de places libres (Q65).
- **L'étape 2 (lot 10)** : « Concevoir le POC » écrit le plan (cible,
  canal, durée), la fiche produit et une campagne au statut `DRAFT`.
  « POC prêt pour le test léger » passe la campagne à `READY` et le
  business à `SMOKE_READY`. Le nombre de prospects et le rythme des
  relances ne viennent plus du plan, mais de réglages (parties 3 et 4) :
  ces deux champs du plan sont à retirer.
- **L'étape 5 (lots 10 et 11)** : « Concevoir le produit », le ticket du
  plan, la construction, le ticket de test et la mise en vente amènent le
  business à `PRODUCT_READY`. Elle a été essayée de bout en bout sur le
  serveur le 16 novembre 2026. Elle se lance encore par un bouton de la
  fiche du business ; le lot 12 la lance par un lien depuis le choix du
  principal.
- **Ce que le lot 11 a ajouté** (décisions Q96 et Q97), utile aux
  invocations de ce lot : une tâche a un plafond de dépense et s'arrête
  avec le bouton rouge ; une demande à Julien la gèle jusqu'à sa
  réponse ; un produit envoie de vrais e-mails ; une invocation peut
  naviguer dans un vrai Chrome et passer la main à un humain pour un
  captcha (« Appeler un humain »).
- **Les conversations (lots 8 et 8 bis)** : « Envoyer un message » (garde-
  fous, plafonds du jour, heures d'appel), « Préparer les relances » et
  « Écrire une relance » (3 jours, puis 7 jours, 2 au plus), « Traiter une
  réponse » (réaction, réponse, demandes sur le produit), les tickets
  « Conversation », la désinscription.
- **La grille de points (lot 9)** : chaque contact compte pour sa
  meilleure réaction ; points et points par euro dépensé, par business.

---

## 2. Les statuts et les places

Les statuts d'un business (`ventures.lifecycle`), avec leurs passages
permis en base (`status_transitions`) :

| De | Vers | Qui |
|---|---|---|
| `SMOKE_READY` | `SMOKE_RUNNING` | « Démarrer une campagne » |
| `SMOKE_RUNNING` | `SMOKE_DONE` | « Conclure le test » (test retenu) |
| `SMOKE_RUNNING` | `KILLED` | « Conclure le test » (sous les seuils) |
| `SMOKE_DONE` | `PRODUCT_BUILDING` | « Appliquer le choix du principal » |
| `SMOKE_DONE` | `PARKED` | idem, pour les autres retenus |
| `PARKED` | `PRODUCT_BUILDING` | idem, un business mis de côté repris |
| `PARKED` | `CANDIDATE` | « Oublier les vieux tests » (60 jours) |
| `PRODUCT_READY` | `FULL_RUNNING` | « Démarrer une campagne » |

Un business reste `SMOKE_RUNNING` pendant qu'on mesure son test, quelques
minutes : `SMOKE_DONE` veut donc toujours dire « test fini et retenu ».
Ainsi, le choix du principal ne part jamais pendant qu'un test est encore
en train d'être mesuré.

`PRODUCT_BUILDING` et `PRODUCT_READY` viennent du lot 10. Il n'y a pas de
statut « choisi comme principal » à part : le choix lance tout de suite
la conception du vrai produit. Ce qui suit `FULL_RUNNING` (`MAINTENANCE`,
`CLOSED`, un arrêt décidé par Julien) est au lot 16. Les anciens statuts
jamais utilisés (`FULL_READY`, `SCALE`, `PIVOT`, `EXTEND`, `INVALID_RETRY`)
disparaissent.

**Les places** (Q14) sont deux quotas de la table des business, réglés sur
la page Policy :

- **places de test** (existe) : au plus 3 business `POC_SELECTED`,
  `SMOKE_READY`, `SMOKE_RUNNING` ou `SMOKE_DONE` ;
- **place de prospection lourde** (nouveau) : au plus 1 business
  `PRODUCT_BUILDING`, `PRODUCT_READY` ou `FULL_RUNNING`.

Un business `KILLED` ou `PARKED` libère sa place de test : l'étape 1 peut
en choisir un autre. Tant que la place lourde est prise, les tests finis
attendent en `SMOKE_DONE` et gardent leur place (Q14 : quand les places
sont prises, tout est figé). Au lot 12, rien ne libère la place lourde :
c'est le lot 16 qui dira quand un business principal laisse sa place.

---

## 3. Les campagnes

Une **campagne**, c'est un business, une phase (`smoke` pour le test
léger, `full` pour la prospection lourde) et un canal : « contacter
40 artisans du bâtiment par e-mail ». La table `campaigns` existe ; elle
reçoit sa phase, son plan, ses volumes et la raison de sa fin.

Sa vie : `DRAFT` (écrite par la conception) → `READY` (le produit est en
ligne) → `RUNNING` (Serge prospecte) → `FINISHED` (fin, avec sa raison).
Une campagne peut aussi être `PAUSED` (mise en pause dans Mission
Control) ou `CANCELLED` (le business est arrêté).

**Des volumes en chiffres absolus, par canal** (Q93). La « cible » d'un
business (tous les artisans de France, par exemple) ne se compte pas ;
le nombre de prospects à contacter, si. Chaque canal a ses réglages :

| Canal | Test léger | Prospection lourde |
|---|---|---|
| E-mail | 40 prospects | 200 par semaine, 1 000 au total |
| Appel | 20 prospects | 50 par semaine, 250 au total |

Exemple : un POC testé par e-mail et par appel a deux campagnes, l'une de
40 e-mails, l'autre de 20 appels. Un nouveau canal arrive avec ses
réglages. Les plafonds du jour de chaque canal (40 e-mails, 50 appels,
page Policy) bornent toujours ce qui part : 200 e-mails par semaine
tiennent dans 40 par jour.

**Quand une campagne de test se termine**, au plus tôt (Q92 ; les
chiffres sont des réglages de « Suivre une campagne ») :

1. elle a son compte de prospects (40 pour l'e-mail), plus aucun message
   n'attend de partir, et rien n'est parti depuis 8 jours : c'est un jour
   de plus que le plus long délai entre deux relances (7 jours), donc
   toutes les relances sont faites ;
2. **ou** elle a atteint la durée de son plan (30 jours au plus) ;
3. **ou** Serge n'a plus de prospects à contacter : « Trouver des
   prospects » est passé 3 fois de suite sans en trouver un nouveau.

Exemple : 40 artisans contactés en 4 jours, deux relances à J+3 et J+10,
la dernière part au 14e jour ; le test se termine au 22e jour, même si le
plan prévoyait 30 jours. Un test rapide ne garde pas sa place pour rien.

**Une campagne lourde** n'a pas de durée : elle contacte son volume de la
semaine, jusqu'à son total (1 000 e-mails), puis elle se termine. Le
business reste en `FULL_RUNNING` : Serge répond toujours et vend à ceux
qui écrivent. Ce qui vient ensuite (prolonger, arrêter, libérer la place)
est au lot 16.

**Après la fin d'une campagne**, Serge répond toujours aux contacts qui
écrivent : seuls les premiers messages et les relances s'arrêtent.

---

## 4. L'étape 3 dans le pipeline : le test léger

Toutes ces invocations sont en base, comme les autres. Celles qui servent
aussi à la prospection lourde sont marquées *(3 et 6)*.

1. **Démarrer une campagne** *(3 et 6)* — sans LLM. Déclencheur : une
   campagne passe à `READY`. Elle vérifie que le canal est branché, passe
   la campagne à `RUNNING`, note son volume (les réglages du canal), son
   début et sa fin prévue (début + durée du plan, pour un test), et passe
   le business à `SMOKE_RUNNING` (ou `FULL_RUNNING` pour une campagne
   lourde). Une campagne sur un canal qui n'est pas branché est annulée,
   avec la raison. **Le téléphone ne démarre pas pour des inconnus** : le
   canal « voice » demande l'accord de la personne avant tout appel (page
   Policy, « Accord des gens »), et un prospect jamais contacté ne l'a
   pas donné. Les 20 appels par test du tableau de la partie 3 restent
   donc sans effet tant que ce réglage ne change pas : c'est voulu, et
   la voix sera reprise dans un lot suivant (décision Q100). Lien :
   « Trouver des prospects ».

2. **Trouver des prospects** *(3 et 6)* — LLM, niveau intelligent, file
   des travaux. Elle reçoit d'office la campagne (son canal, sa cible), le
   plan, la fiche du business et la fiche produit. Outils : rechercher sur
   le web, lire une page, et **« Ajouter un prospect »**. Elle ajoute au
   plus 10 prospects par passage (réglage) : nom, entreprise, rôle,
   pourquoi il est visé, et son adresse professionnelle sur le canal de la
   campagne, avec la page où elle a été trouvée (Q36).

   **« Ajouter un prospect » vérifie tout de suite, et dit pourquoi il
   refuse** : une adresse générique (Q93), une adresse mal formée, un
   domaine qui ne reçoit pas d'e-mails, une personne déjà contactée pour
   ce business ou désinscrite, une campagne qui a son compte. Le modèle
   lit le refus et cherche quelqu'un d'autre. Un prospect accepté devient
   un contact, avec son adresse (et sa source) et un premier message « à
   rédiger » sur le canal de la campagne.

   **Jamais d'adresse générique** (Q93). Un contact précis paie toujours,
   et beaucoup se trouvent en ligne : le site de l'entreprise (sa page
   équipe, ses mentions légales), les annuaires professionnels, les fiches
   Google Maps, les articles et publications. Elle cherche une personne
   nommée, avec son rôle (« Marie Dupont, gérante »), et son adresse
   directe (`marie.dupont@…`), pas `contact@`, `info@` ou `accueil@`. Une
   entreprise dont elle ne trouve qu'une adresse générique est laissée de
   côté. La liste des débuts d'adresse refusés est un réglage (page
   Policy, « Contacts »).

3. **Suivre une campagne** *(3 et 6)* — sans LLM, toutes les heures, une
   tâche par campagne `RUNNING`. Elle fait l'une de ces trois choses :
   - **clore** la campagne (`FINISHED`, avec sa raison) si elle remplit
     une condition de fin (partie 3) ; quand toutes les campagnes de test
     d'un business sont finies, lien vers « Mesurer le test » ;
   - **relancer « Trouver des prospects »** si la campagne n'a pas encore
     son compte (40 au total pour un test, 200 cette semaine pour une
     campagne lourde) et que Serge a moins d'un jour d'envois d'avance
     (réglage : avec 40 e-mails par jour, il garde au plus 40 premiers
     messages qui attendent). Ainsi, Serge ne cherche pas 1 000 prospects
     d'un coup, et ne dépense pas pour des contacts qu'il n'aura pas le
     temps d'écrire ;
   - **attendre**.

   C'est une seule invocation, et non « Réapprovisionner » et « Clore »
   séparées : les deux regardent la même campagne, à la même heure.

4. **Rédiger un premier message** *(3 et 6)* — sans LLM. Déclencheur : un
   premier message « à rédiger » est écrit. Elle ne fait qu'aiguiller,
   par un lien conditionné sur le canal : « Écrire le premier message »
   pour l'e-mail, « Préparer le premier appel » pour l'appel. Un nouveau
   canal ajoute ici son lien (partie 17).

5. **Écrire le premier message** *(3 et 6)* — LLM, niveau moyen, file des
   conversations. La vraie version de l'invocation temporaire du lot 8.
   Elle reçoit le contact, la source de son adresse, le plan (l'angle,
   l'offre), la fiche produit, et l'adresse du produit en ligne : le POC
   pendant le test, le produit fini et son prix ensuite. Elle écrit
   l'objet et le texte. Lien : « Envoyer un message » (existe).

6. **Préparer le premier appel** *(3 et 6)* — LLM, niveau moyen. La vraie
   version de l'invocation temporaire : le but de l'appel, que l'agent
   vocal suit. Lien : « Envoyer un message ».

7. **Les relances et les réponses** existent (lots 8 et 8 bis) : rien à
   ajouter. Le rythme des relances est le même pour tous les business :
   les réglages de « Préparer les relances » (3 jours, puis 7 jours, deux
   au plus), sur la page Policy (Q92). **Un rebond** (l'e-mail n'a pas pu
   être remis) est reconnu à la relève : l'adresse est désactivée, et le
   contact passe à « injoignable » s'il n'en a pas d'autre.

---

## 5. La fin d'un test léger : mesurer et juger

8. **Mesurer le test** — sans LLM. Lien depuis « Suivre une campagne »,
   quand la dernière campagne de test d'un business est finie. Elle écrit
   le compte rendu chiffré du test (`test_reports`) : prospects contactés
   par canal, réponses par réaction, points, dépense, points par euro.
   Puis elle **juge le test avec des seuils en chiffres absolus**, réglés
   sur la page Policy (Q93) :
   - **assez de prospects contactés** : au moins 30, tous canaux
     confondus ; sinon le test ne dit rien, faute de prospects ;
   - **assez de points** : au moins 10 (par exemple un « intéressé » et
     un « refus », ou un « rendez-vous ») ;
   - **assez de points par euro** : au moins 0 au départ (pas de seuil).

   Un test qui passe les trois seuils est **retenu**. Le code juge, pas un
   modèle : il lit des chiffres et des seuils (charte, partie 4).

9. **Faire le bilan du test** — LLM, niveau intelligent, file des
   travaux. Lien depuis « Mesurer le test », retenu ou non. Elle lit le
   compte rendu chiffré, les fils des contacts qui ont répondu, leurs
   objections et leurs demandes sur le produit, et écrit sur le compte
   rendu un bilan en quelques lignes : ce qui a plu, ce qui a bloqué, les
   prospects qui ont le mieux répondu. Ce bilan sert au choix du
   principal, à la conception du vrai produit et à la prospection lourde.
   Lien : **« Conclure le test »**, sans LLM : le business retenu passe à
   `SMOKE_DONE`, avec la date de fin de son test ; l'autre passe à
   `KILLED`, avec la raison (« 4 points, moins que les 10 demandés »),
   libère sa place et produit une leçon (Q92).

10. **Tirer la leçon d'un business arrêté** — LLM, niveau moyen.
    Déclencheur : un business passe à `KILLED`, quelle que soit l'étape
    (Q46 : chaque business arrêté produit une leçon). Elle écrit une ou
    deux leçons au statut « proposée », rattachées à l'étape ou à
    l'invocation qu'elles concernent. Julien les garde ou les jette dans
    Mission Control (page Mémoire).

---

## 6. L'étape 4 : choisir le business principal

11. **Choisir le business principal** — LLM, niveau intelligent, file des
    travaux. Deux déclencheurs : un test est conclu et retenu (son
    business passe à `SMOKE_DONE`), ou un business est arrêté (il passe à
    `KILLED`). **Trois conditions** : aucun test léger ne tourne encore
    (aucun business `POC_SELECTED`, `SMOKE_READY` ou `SMOKE_RUNNING`), au
    moins un business retenu attend (`SMOKE_DONE`, ou `PARKED` : un
    business mis de côté depuis plus de 60 jours ne l'est plus), et la
    place lourde est libre (Q14 bis). Elle reçoit, pour chacun : ses
    chiffres, son bilan et les réponses de ses prospects. Elle propose un
    business, ou aucun, avec une phrase par business. Critère de départ,
    donné dans le prompt : d'abord les points par euro, puis les points,
    puis la facilité de vendre le produit fini. Elle écrit sa proposition
    (`principal_choices`).

12. **Faire valider le choix** — sans LLM (capacité « Demander à Julien »).
    Un ticket « Choix du principal » : la proposition, et pour chaque
    business ses chiffres et son bilan. Boutons : « Valider », « Choisir
    un autre » (on écrit le nom du business voulu, parmi ceux du ticket),
    « Aucun ». Sans réponse sous 48 heures, la proposition s'applique
    (Q16 bis).

13. **Appliquer le choix du principal** — sans LLM. Déclencheur : la
    réponse au ticket. Le business choisi passe à `PRODUCT_BUILDING` ;
    les autres business retenus passent à `PARKED`. Avec « Aucun », tous
    passent à `PARKED`. Un nom qui ne désigne aucun business du ticket
    rouvre le ticket, avec la raison. Lien : « Concevoir le produit »
    (étape 5, lot 10), qui remplace le bouton de la fiche du business.

14. **Oublier les vieux tests** — sans LLM, une fois par jour. Un business
    `PARKED` dont le test a fini il y a plus de 60 jours (réglage)
    redevient `CANDIDATE` : l'étape 1 peut le choisir de nouveau (Q44).

15. **L'étape 1 repart toute seule** (Q92) : un déclencheur lance « Ouvrir
    un cycle d'écoute » dès qu'une place de test se libère (un business
    passe à `KILLED`, `PARKED` ou `PRODUCT_BUILDING`), si Serge est
    démarré, si aucun cycle n'est ouvert et si une place est libre. Le
    bouton « Lancer un cycle » reste. « Choisir les business » peut ne rien
    choisir : le cycle se ferme, et le suivant attend qu'une autre place se
    libère. La coupure automatique d'un flux qui ne ramène que du bruit
    reste pour plus tard.

---

## 7. L'étape 6 : vendre en masse le produit fini

L'étape 5 (lot 10) amène le business à `PRODUCT_READY` : le produit est en
ligne sur son domaine, payant, et Stripe est branché. La prospection
lourde vend ce produit **tel qu'il est sorti de la construction** : pas de
nouvelle version, pas de changement de prix ni de cible en cours de route
(Q93). Le suivi et le raffinement pendant la vente viendront au lot 16.

16. **Préparer la prospection lourde** — LLM, niveau intelligent.
    Déclencheur : un business passe à `PRODUCT_READY`. Elle lit le plan du
    produit, le bilan du test et ses chiffres par canal, et écrit une
    campagne lourde par canal, au statut `READY` : la cible précise
    (affinée par ce que le test a appris : les métiers, les tailles
    d'entreprise et les régions qui ont le mieux répondu) et l'angle des
    messages. Les volumes ne sont pas les siens : ce sont les réglages de
    chaque canal (partie 3). Lien : **« Prévenir les intéressés du
    test »**, sans LLM : un premier message « à rédiger » pour **chaque
    contact du test qui avait dit « intéressé » ou « rendez-vous »** ; ils
    apprennent les premiers que le produit existe, avec son lien. Un
    ticket d'information prévient Julien (Q42 : la prospection lourde est
    automatique).

17. La campagne passe à `RUNNING` par **Démarrer une campagne**, et le
    business à `FULL_RUNNING`. **Trouver des prospects**, **Suivre une
    campagne**, **Écrire le premier message**, les relances et **Traiter
    une réponse** servent comme au test léger, au volume de la semaine.
    Différence : la fiche produit donne le prix et le lien d'inscription
    du produit, et « Traiter une réponse » l'envoie à un contact
    « intéressé ».

18. **Enregistrer une vente** — sans LLM. Déclencheur : Stripe annonce un
    paiement (une transaction payée, écrite par le webhook, avec l'e-mail
    du payeur). Elle retrouve le contact par son e-mail dans ce business
    et le passe à « client » (`CUSTOMER`) : il ne reçoit plus de relance
    de prospection. Un acheteur inconnu devient un contact « entrant » et
    client. La **première vente** d'un business ouvre un ticket
    d'information.

19. **Suivre une campagne** termine une campagne lourde quand son total
    est atteint (partie 3). Le business reste en `FULL_RUNNING`, et le
    lot 12 s'arrête là.

---

## 8. Les tables

Chaque table a sa vue, ses colonnes inscriptibles, ses statuts permis et
ses quotas en base (règle de tous les lots).

- **`campaigns`** (existe) : reçoit `phase` (`smoke` ou `full`), sa cible
  et son angle (pour une campagne lourde), ses volumes (au total, et par
  semaine pour une campagne lourde), son début, la date de fin prévue
  d'un test, la raison de sa fin, et le compte des recherches de
  prospects restées vides. Sa colonne `family` devient `phase`. Les
  colonnes que le pipeline n'écrit pas (`budget_cap_eur`,
  `thresholds_json`, `window_start`, `window_end`) restent pour l'ancien
  code de la page Policy, à retirer avec lui (partie 13).
- **`contact_addresses`** (existe) : reçoit la page où l'adresse a été
  trouvée (Q36). Les prospects d'une campagne sont ceux qui ont un
  premier message dans cette campagne : la table des contacts ne change
  pas.
- **`test_reports`** (nouvelle) : une ligne par test léger : le business,
  ses chiffres par canal, le verdict (retenu ou non, avec la raison) et le
  bilan.
- **`principal_choices`** (nouvelle) : une ligne par proposition de
  principal : le business proposé (ou aucun), une phrase par business
  comparé, et ce que Julien a décidé.
- **`ventures`** : les statuts de la partie 2 ; la date de fin du test
  léger existe (`smoke_ended_at`) et sert à la règle des 60 jours.
- **L'essai et les redémarrages** (parties 18 et 19) : `trial` sur les
  cycles d'écoute, les pages, les tickets et leurs réponses ; sur une
  tâche, l'essai dont elle fait partie, la tâche qui l'a créée et la
  marque d'un redémarrage ; la valeur d'essai d'un réglage ; le couloir
  d'un lien ou d'un déclencheur.

Les ventes restent dans `transactions` et `subscriptions` (étape 8,
lot 10) : on ne recopie rien.

---

## 9. Les réglages : les critères chiffrés

Tous en base, et modifiables dans Mission Control (Q68). Valeurs de
départ :

| Réglage | Départ | Où |
|---|---|---|
| Prospects d'un test léger, par canal | e-mail 40, appel 20 | « Démarrer une campagne » |
| Prospects par semaine, prospection lourde, par canal | e-mail 200, appel 50 | idem |
| Prospects au total, prospection lourde, par canal | e-mail 1 000, appel 250 | idem |
| Durée maximale d'un test léger | celle du plan, 30 jours au plus | idem |
| Jours sans envoi avant de clore une campagne | 8 | « Suivre une campagne » |
| Recherches sans nouveau prospect avant de clore | 3 | idem |
| Envois d'avance gardés en réserve | 1 jour | idem |
| Prospects par passage de « Trouver des prospects » | 10 | son réglage |
| Adresses génériques refusées | `contact`, `info`, `hello`, `accueil`, `bonjour`, `admin`, `support`, `commercial`… | Policy, « Contacts » |
| Prospects contactés pour qu'un test compte | 30 | « Mesurer le test » |
| Points pour qu'un test soit retenu | 10 | idem |
| Points par euro pour qu'un test soit retenu | 0 | idem |
| Âge maximum d'un business mis de côté | 60 jours | « Oublier les vieux tests » |

Ce sont des réglages d'invocation marqués « policy » : ils se changent
sur la page Policy, sous leur invocation. Un réglage peut avoir une
**valeur d'essai**, qui ne vaut que dans l'essai total (partie 18).

Les places (3 et 1) sont des quotas de la page Policy. Les anciens
réglages de « Taille des essais » sont remplacés : « Petit essai,
personnes touchées » et « Grand essai, personnes touchées » par les
volumes par canal, et les seuils qui comptaient des réponses positives
(« Arrêt, réponses positives au plus », « Élargir, réponses positives au
moins », « Élargir, rendez-vous au moins », « Prolongations au plus ») sont
retirés : les points les remplacent, et prolonger est au lot 16 (Q78,
Q84).

---

## 10. Les tickets

Un nouveau type, en base comme les autres (Q85), réglable sur la page
Décisions : **« Choix du principal »**, la proposition et la comparaison.
Boutons « Valider », « Choisir un autre », « Aucun ». Sans réponse sous
48 heures, la proposition s'applique.

Les tickets d'information (FYI) existent : prospection lourde lancée,
première vente.

---

## 11. Mission Control

Ce qui est fait :

- **Page Système, « L'essai total »** : son seul bouton, où en est le
  dernier essai, ses tickets qui attendent, ses tâches dans l'ordre avec
  « Repartir d'ici », « Arrêter l'essai », et le fil de son contact
  (parties 18 et 19).
- **Fiche d'une tâche** : « Repartir d'ici », la tâche qui l'a créée et
  celles qu'elle a créées.
- **Fiche d'un business** : son compte rendu de test (chiffres, verdict,
  bilan), ses campagnes, et s'il est un business d'essai.
- **Fiche d'une campagne** : sa phase, son canal, son état, combien de
  prospects trouvés et contactés sur son volume, sa cible, son angle, sa
  fin prévue ou la raison de sa fin.
- **Pages Policy et Pipeline** : les réglages du lot (les volumes par
  canal, les seuils, les délais) sous leur invocation, et la place lourde.

Ce qui reste, à part (TODO) : les campagnes en une liste sur la page
Système, les places sur la page En direct, et mettre une campagne en
pause.

---

## 12. Ce que le code apprend

Ce sont des capacités générales, réglées en base ; aucune ne connaît une
invocation.

1. **Une condition de déclencheur « nombre de lignes »** : « au plus
   0 business `SMOKE_RUNNING` », « au moins 1 business `SMOKE_DONE` ».
   Les quotas d'aujourd'hui servent à la fois de limite d'écriture et de
   condition ; celle-ci ne limite pas l'écriture.
2. **Le domaine des campagnes** (`serge/campaigns/`) : démarrer une
   campagne, la suivre (la clore, ou dire qu'il lui faut des prospects),
   ajouter un prospect (avec ses refus : adresse générique, domaine sans
   e-mail, doublon), mesurer un test, appliquer le choix du principal,
   enregistrer une vente.
3. **Vérifier une adresse e-mail** : le domaine a-t-il un serveur de
   courrier (gratuit, sans service payant, Q48) ?
4. **Les rebonds** : la relève de l'e-mail reconnaît un message de rebond,
   marque l'adresse inactive, et le contact injoignable s'il n'a pas
   d'autre adresse.
5. **La condition d'un lien lue dans les paramètres de la tâche**, quand
   la réponse n'a pas ce champ.
6. **Le couloir d'essai** (partie 18) et **repartir d'une tâche**
   (partie 19).

---

## 13. Ce que le lot 12 retire

- Les versions temporaires de « Écrire le premier message » et de
  « Préparer le premier appel » : les vraies les remplacent.
- **Tous les essais de la page Système** (Q99) : « Lancer un essai »,
  « Essayer le chantier », « Essayer l'interface web », « Essayer le
  captcha avec un humain », « Publier le chantier d'essai », « Essayer
  l'étape 2 », les deux « Bout en bout », et, sur la fiche d'un business,
  « Essayer Stripe ». L'essai total (partie 18) les remplace. Les boutons
  « Supprimer de Stripe » restent : ils servent à nettoyer.
- Le bouton « Construire le vrai produit » de la fiche d'un business,
  remplacé par le lien depuis le choix du principal.
- Les champs « nombre de prospects » et « relances » du plan du POC
  (lot 10), remplacés par des réglages.
- Les modules `serge/funnels/lifecycle.py` et `contact_tool.py`, que plus
  rien n'appelait : le premier imposait en dur « un seul business actif »
  et d'anciens statuts. Les statuts et les places sont en base.
- **Pas encore retirés**, à faire à part (TODO) : la famille « Taille des
  essais » de la page Policy et l'ancien code qui la lit
  (`serge/funnels/campaigns.py`, `essai.py`, `rules.py`), que plus rien
  n'appelle dans le pipeline, avec les colonnes des campagnes qu'il est
  seul à écrire (partie 8).
- Les invocations écrites mais jamais appelées que ce lot remplace (TODO,
  « Brancher ou supprimer les invocations jamais appelées ») : la
  découverte de contacts (→ « Trouver des prospects »), le résumé d'un
  test (→ « Faire le bilan du test »), le départage de deux prospects
  (→ « Choisir le business principal »), l'hypothèse de test lourd
  (→ « Préparer la prospection lourde ») et le résumé d'un fil
  (« Traiter une réponse » lit déjà le fil entier). Leur code propre est
  supprimé. Les options de pivot, le plan de passage à l'échelle et
  l'arbitre du budget attendent le point de la semaine, au lot 16.

---

## 14. Le lot 10 bis : les réponses automatiques

Fait avant le lot 12 (Q93). Une réponse automatique (« je suis absent
jusqu'au 20 », « votre demande n° 1234 est bien reçue ») ne fait jamais
répondre Serge sans fin : reconnue à ses en-têtes, elle est rangée dans le
fil sans appeler le modèle ; « Traiter une réponse » peut décider
d'arrêter avec un contact (« Arrêté ») ; et un garde-fou annule tout
message au-delà de 10 en 24 heures au même contact, arrête avec lui et
prévient Julien et Clem. Le détail est dans
[`PIPELINE.md`](PIPELINE.md), « Parler aux prospects et aux clients ».

---

## 15. Le lot 16 : faire vivre les produits

Un produit qui a des clients doit être entretenu : ce n'est plus un
pipeline avec un début et une fin. Le lot 16, placé tout à la fin,
servira à clarifier et à imaginer ce système. Il part des décisions déjà
prises, à revoir :

- **le point de la semaine** sur le business principal (Q42) : continuer,
  accélérer, prolonger, pivoter ou arrêter, et ce que fait chaque
  décision ; quand le business laisse sa place lourde ;
- **les retours des clients et les nouvelles versions** (Q43) ;
- **un service sur mesure** : proposer à un client d'ajouter à un produit
  existant les fonctionnalités qu'il demande, en rappelant le
  constructeur du lot 10 sur ce produit (Q93) ;
- **les livraisons** (Q44), **la maintenance et la fermeture** d'un
  business (Q44–Q45), **les impayés et les remboursements** (Q47), **les
  leçons de la consolidation** (Q46).

Au lot 12, un business en `FULL_RUNNING` garde sa place : Serge continue
de répondre aux messages (le circuit des conversations ne dépend pas du
statut), et Stripe continue d'encaisser les abonnements.

---

## 16. Les questions ouvertes

Tranchées par Clem le 13 octobre 2026 : la fin d'un test léger (au plus
tôt), un test sous les seuils (arrêté, avec une leçon), l'étape 1 en
automatique (dans ce lot), le rythme des relances (un réglage commun)
(Q92) ; des volumes en chiffres absolus par canal, jamais d'adresse
générique, la prospection lourde qui vend le produit tel quel, le point de
la semaine au lot 16 (Q93).

Validés par Clem le 16 novembre 2026 (Q98), comme valeurs de départ,
toutes réglables dans Mission Control :

1. **Les volumes** : 40 e-mails et 20 appels pour un test ; 200 e-mails
   et 50 appels par semaine en prospection lourde, jusqu'à 1 000 et 250.
2. **Les seuils d'un test retenu** : 30 prospects contactés et 10 points
   au moins.
3. **Les intéressés du test** : prévenus en premier quand le produit fini
   sort, avec son lien.

---

## 17. Le contrat d'un canal

Clem veut pouvoir ajouter un canal (LinkedIn, un formulaire de contact,
un réseau où il faut naviguer) **sans toucher au reste ni tout retester**
(Q98). Le reste du pipeline ne doit donc rien savoir d'un canal en
particulier : il ne connaît que ce contrat.

**Ce qu'un canal apporte, et rien d'autre :**

1. **Son adaptateur** (`serge/channels/`) : envoyer un message à une
   adresse, et relever ce qui arrive. C'est le seul code d'un canal. Le
   catalogue `canaux` dit s'il est branché sur ce serveur. Un canal qui
   passe par un navigateur (LinkedIn, lot 13) aura le même adaptateur,
   qui pilotera le vrai Chrome.
2. **Sa sorte d'adresse** (`canaux.address_channel`) : une adresse
   e-mail, un numéro de téléphone, un profil. « Trouver des prospects »
   cherche cette sorte d'adresse pour la campagne du canal.
3. **Son invocation de premier message**, en base : « Écrire le premier
   message » pour l'e-mail, « Préparer le premier appel » pour l'appel.
   Un lien conditionné sur le canal la lance.
4. **Ses réglages**, en base : prospects d'un test, prospects par semaine
   et au total en prospection lourde, plafond du jour.

**Ce qui ne change jamais, quel que soit le canal :**

- une **campagne** est un business, une phase et un canal
  (`campaigns`) ;
- un prospect est un **contact** (`contacts`), avec ses **adresses**
  (`contact_addresses` : le canal, l'adresse, la page où elle a été
  trouvée) ;
- un message est un **envoi** (`touches` : le canal, l'adresse, son
  état), et ce qui arrive est un **message reçu** (`inbound_events`) ;
- « Démarrer une campagne », « Trouver des prospects »,
  « Réapprovisionner », « Clore », « Envoyer un message », les relances,
  « Traiter une réponse », la grille de points, « Mesurer le test » : une
  seule version de chacune, qui lit le canal dans la ligne qu'elle
  traite.

Ajouter un canal, c'est donc : un adaptateur, ses réglages de volume, une
invocation de premier message et son lien depuis « Rédiger un premier
message ». Aucune autre invocation ne change. **Un test le garantit** : un
canal factice, ajouté seulement de cette façon, traverse la chaîne
(campagne, prospect, premier message, envoi, réponse, points) sans
qu'aucune autre ligne du pipeline ne soit modifiée.

**Trouver des prospects autrement** (un annuaire, un site où il faut
naviguer) suit la même idée : c'est un outil de plus donné à « Trouver
des prospects ». Quel que soit l'outil, elle écrit au même endroit : des
contacts, leurs adresses avec leur source, et un premier message à
rédiger.

---

## 18. L'essai total

Un seul essai remplace tous ceux de la page Système (Q99). Il suit le
même chemin que le vrai pipeline, de l'écoute du web à la vente, avec les
mêmes invocations et les mêmes tables, **sans jamais toucher à ce qui
tourne**.

### Le couloir d'essai

Une tâche est soit du vrai pipeline, soit d'un essai : elle porte le
numéro de son essai (`tasks.trial_run`). Tout en découle, dans
l'interpréteur, sans rien savoir d'une invocation :

1. **Ce qu'une tâche d'essai écrit est marqué.** Une table qui a une
   colonne `trial` (les business, les cycles d'écoute, les pages, les
   tickets) reçoit 1. Les autres lignes (campagnes, contacts, envois,
   plans…) suivent leur business, par leur `venture_id`.
2. **Chacun ne voit que son couloir.** Une vraie tâche ne lit, ne
   modifie, ne compare et ne compte que les vraies lignes ; une tâche
   d'essai, que celles des essais. Exemples : « Choisir les business » ne
   voit jamais la calculatrice d'essai ; une page lue par l'essai n'est
   pas « déjà gardée » pour la vraie écoute ; « Abandonner le cycle » ne
   ferme pas le cycle de l'essai.
3. **Les places ne comptent que le vrai.** Un essai ne prend ni place de
   test, ni place lourde, ni le cycle d'écoute ouvert ; et des places
   prises ne l'arrêtent pas.
4. **La suite hérite du couloir.** Une tâche créée par un lien ou par une
   ligne écrite est du couloir de cette ligne (sinon de la tâche qui l'a
   créée). Une réponse à un ticket d'essai, un e-mail reçu d'un contact
   d'essai, un paiement sur un business d'essai lancent donc des tâches
   d'essai. Les déclencheurs à heure fixe sont du vrai pipeline : un
   essai n'a ni relance, ni veille, ni oubli.
5. **Un réglage peut avoir une valeur d'essai**, qui remplace la sienne
   dans une tâche d'essai. C'est ce qui rend l'essai petit et rapide,
   sans une ligne de code :

   | Réglage | Vrai | Essai |
   |---|---|---|
   | Recherches de « Explorer le web » | 10 | 2 |
   | Pages retenues, flux ajoutés | 30, 2 | 5, 0 |
   | Idées de « Formuler des business » | 3 | 0 |
   | Business à choisir, au moins | 0 | 1 |
   | Prospects d'un test, e-mail et appel | 40, 20 | 1, 1 |
   | Jours sans envoi avant de clore | 8 | 0 |
   | Prospects contactés et points pour retenir un test | 30, 10 | 0, 0 |

6. **Un lien ou un déclencheur peut n'exister que dans un couloir.**
   C'est là, et seulement là, que l'essai quitte le vrai chemin :

   | Dans le vrai pipeline | Dans l'essai |
   |---|---|
   | « Choisir les business » → « Concevoir le POC » | → le plan tout fait de la calculatrice, puis le ticket « Plan » |
   | « Démarrer une campagne » → « Trouver des prospects » | → un premier message pour le contact tapé au lancement |
   | « Suivre une campagne », toutes les heures | après chaque envoi |
   | le paiement test → « Produit en vente » | → le captcha avec un humain, puis « Produit en vente » |
   | un domaine à acheter | jamais : sans domaine commun des produits, un ticket le demande |
   | une place se libère → un cycle d'écoute ; un business arrêté → une leçon | rien |

### Ce que fait l'essai

Sur la page Système, un seul bouton : **« Lancer l'essai total »**. On
tape un nom, une adresse e-mail, un numéro, et l'étape de départ (1 si on
ne met rien). Serge arrête l'essai précédent, s'il y en a un, puis :

1. **Étape 1** : il crée le business d'essai « Calculatrice » et son
   contact (les coordonnées tapées), ouvre un cycle d'écoute d'essai,
   explore le web pour de vrai (2 recherches, 5 pages au plus, marquées
   « essai »), trie ces pages, puis « Choisir les business » choisit la
   calculatrice, seule candidate de l'essai.
2. **Étape 2** : le plan du POC est tout fait ; le ticket « Plan » arrive
   (mention « Essai »). Après « Valider » : construction, relecture,
   ticket « Tester le produit », mise en ligne.
3. **Étape 3** : les deux campagnes démarrent. Serge écrit un e-mail et
   prépare un appel pour le contact de l'essai, les envoie, et les
   campagnes se terminent aussitôt. Le test est mesuré, retenu quoi qu'il
   arrive, et son bilan écrit.
4. **Étape 4** : « Choisir le business principal », puis son ticket.
5. **Étape 5** : le plan du produit (écrit par le modèle), son ticket,
   Stripe en mode test, la construction, le ticket « Tester le produit »,
   le sous-domaine, la mise en vente dans Stripe, le paiement test de
   1 €, remboursé, puis le captcha avec un humain (les deux tickets).
6. **Étape 6** : la prospection lourde est préparée, ses campagnes
   démarrent, et le contact de l'essai reçoit un e-mail et un appel pour
   le produit fini. Une vente n'est enregistrée que si quelqu'un paie
   vraiment : le paiement test de 1 € de Serge n'en est pas une.

**Partir du milieu** : avec l'étape de départ 2, 3, 5 ou 6, Serge met
d'abord en base l'état d'où part cette étape (la calculatrice choisie ;
son POC « en ligne » et ses campagnes prêtes ; trois demandes de clients
et un test retenu ; un produit « en vente »), puis lance la suite. Ce qui
précède n'est pas rejoué : à partir de 3 ou de 6, les messages n'ont donc
pas de vrai site à montrer.

**Arrêter un essai** (le relancer, ou le bouton « Arrêter l'essai ») :
ses tâches en attente sont annulées, ses tickets ouverts fermés, son
cycle d'écoute abandonné, ses campagnes annulées, et son business, s'il
n'était pas arrivé au bout, passe à « arrêté ». Une tâche d'essai en
cours finit, mais sa suite ne part pas. Ce qui est en ligne (le site, les
produits Stripe) reste : « Supprimer de Stripe » sert à nettoyer.

**Un test le garantit** : avec un vrai cycle ouvert, trois vrais business
en test et un vrai principal, l'essai total va de l'écoute à la vente ;
aucune vraie ligne n'a changé, aucune vraie tâche n'a été créée, et les
vraies invocations ne voient à aucun moment une ligne de l'essai.

---

## 19. Repartir d'une tâche

Une chaîne qui a bloqué (une tâche en échec, annulée, ou finie sur un
mauvais résultat) doit pouvoir repartir d'une tâche précise, depuis
Mission Control (Q99). Avant, seule une tâche en échec se relançait ; et
rejouer une tâche finie ne faisait pas repartir sa suite, parce qu'un
même résultat n'est jamais transmis deux fois.

**« Repartir d'ici »**, sur la fiche de toute tâche qui n'est pas en
cours :

1. **Ce qui restait de l'ancienne chaîne est arrêté** : les tâches en
   attente que cette tâche avait créées (et celles qu'elles avaient
   créées), et leurs tickets ouverts. Chaque tâche note pour cela la tâche
   qui l'a créée (`tasks.parent_id`).
2. **Une tâche neuve part**, copie de l'ancienne : même invocation, mêmes
   paramètres, même couloir.
3. **Toute sa suite est neuve aussi** : la tâche neuve porte une marque
   de redémarrage (`tasks.rerun`), que ses suivantes héritent, et qui
   entre dans la clé de chaque tâche et de chaque passage. Un lien déjà
   passé pour l'ancienne chaîne passe donc de nouveau.

Exemple : le paiement test a fini sur « pas payé », et un ticket l'a dit.
« Repartir d'ici » sur cette tâche refait le paiement, puis « Produit en
vente », sans toucher au reste.

Sur la page Système, **l'essai en cours** montre ses tâches dans l'ordre,
avec leur état, ce qui attend (un ticket, une heure) et le bouton
« Repartir d'ici » : on voit où l'essai a bloqué, et on le fait repartir
de là.
