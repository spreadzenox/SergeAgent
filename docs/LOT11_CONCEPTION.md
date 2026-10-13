# Lot 11 — Conception : du business imaginé à la vente du produit fini

Ce document décrit la suite du pipeline après le lot 10 : comment Serge
trouve des prospects, mène le test léger d'un business, le juge, choisit le
business principal, puis vend en masse le produit fini, tel qu'il sort de
la construction. **Rien n'est codé ici** : c'est la liste des invocations,
des tables, des liens, des déclencheurs et des réglages à mettre en base,
pour que Clem et Julien les valident avant le code.

Il suit les réponses de Clem du 13 octobre 2026 (décisions Q92 et Q93 de
[`DECISIONS_REVUE.md`](DECISIONS_REVUE.md)) et les décisions déjà prises :
les places de test (Q14, Q14 bis), les business mis de côté (Q15, Q44), la
grille de points (Q16, Q84), trouver les prospects (Q36), les envois et
relances (Q37, Q79), le circuit des réponses (Q38, Q50), le choix du
principal (Q16 bis), la caisse (Q47), le web (Q48) et le lot 10 (Q91). Et
la règle de tous les lots : le code n'est qu'un interpréteur de la base,
jamais de code propre à une invocation.

**Ce que le lot 11 couvre** : d'un business dont le POC est en ligne (fin
de l'étape 2, lot 10) jusqu'à la vente en masse du produit fini (étape 6),
en passant par le choix du principal (étape 4) et la construction du vrai
produit (étape 5, lot 10). La prospection lourde, c'est seulement vendre
en masse ce qui existe déjà.

**Ce qu'il ne couvre pas** : le suivi et le raffinement d'un produit
pendant qu'il se vend. Le point de la semaine (continuer, accélérer,
pivoter, arrêter), les retours des clients et les nouvelles versions, les
livraisons, les impayés, les remboursements, la maintenance et la
fermeture d'un business partent au lot 15, « Faire vivre les produits »,
placé tout à la fin (partie 15). Pour l'instant, le pipeline a un début et
une fin.

**Ce qui ne change pas** : l'étape 1 (écouter le web, formuler et choisir
les business) reste telle quelle. Le circuit des conversations (lot 8),
Julien dans la conversation (lot 8 bis) et la grille de points (lot 9)
sont réutilisés sans changement de fond. Les réponses automatiques, qui
peuvent faire répondre Serge sans fin, sont traitées à part, au lot 10 bis
(TODO).

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
   ↓  « Clore les campagnes finies »  (relances finies, ou durée écoulée)
SMOKE_DONE         « Mesurer le test » : retenu, ou ──→ KILLED (sous les seuils)
   ↓  quand plus aucun test léger ne tourne et que la place lourde est libre
   ↓  « Choisir le business principal »  → ticket à Julien (48 h)
PRODUCT_BUILDING   le principal ; les autres retenus  ──→ PARKED
   ↓  concevoir, construire, essayer, mettre en vente  (étape 5, lot 10)
PRODUCT_READY      produit en vente sur son domaine, Stripe branché
   ↓  « Préparer la prospection lourde », puis « Démarrer une campagne »
FULL_RUNNING       vente en masse du produit fini, tel quel
   ↓  la suite (le point de la semaine, la maintenance…) : lot 15
```

Un business `PARKED` testé il y a plus de 60 jours redevient `CANDIDATE`
(Q44). Un business `KILLED` produit toujours une leçon (Q46). Une place de
test qui se libère relance l'étape 1, sans clic (Q92).

---

## 1. Ce que le lot 11 réutilise

- **L'étape 1** : « Choisir les business » écrit des business
  `POC_SELECTED`, au plus autant que de places libres (Q65).
- **L'étape 2 (lot 10)** : « Concevoir le POC » écrit le plan (cible,
  canal, durée), la fiche produit et une campagne au statut `DRAFT`.
  « POC prêt pour le test léger » passe la campagne à `READY` et le
  business à `SMOKE_READY`. Le nombre de prospects et le rythme des
  relances ne viennent plus du plan, mais de réglages (parties 3 et 4) :
  ces deux champs du plan sont à retirer.
- **L'étape 5 (lot 10)** : « Concevoir le produit », le ticket du plan, la
  construction, le ticket de test et la mise en vente amènent le business
  à `PRODUCT_READY`. Au lot 10, elle se lance par un bouton d'essai ; le
  lot 11 la lance par un lien depuis le choix du principal.
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
| `SMOKE_RUNNING` | `SMOKE_DONE` | « Clore les campagnes finies » |
| `SMOKE_DONE` | `KILLED` | « Mesurer le test » (sous les seuils) |
| `SMOKE_DONE` | `PRODUCT_BUILDING` | « Appliquer le choix du principal » |
| `SMOKE_DONE` | `PARKED` | idem, pour les autres retenus |
| `PARKED` | `PRODUCT_BUILDING` | idem, un business mis de côté repris |
| `PARKED` | `CANDIDATE` | « Oublier les vieux tests » (60 jours) |
| `PRODUCT_READY` | `FULL_RUNNING` | « Démarrer une campagne » |

`PRODUCT_BUILDING` et `PRODUCT_READY` viennent du lot 10. Il n'y a pas de
statut « choisi comme principal » à part : le choix lance tout de suite
la conception du vrai produit. Ce qui suit `FULL_RUNNING` (`MAINTENANCE`,
`CLOSED`, un arrêt décidé par Julien) est au lot 15. Les anciens statuts
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
sont prises, tout est figé). Au lot 11, rien ne libère la place lourde :
c'est le lot 15 qui dira quand un business principal laisse sa place.

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
chiffres sont des réglages de « Clore les campagnes finies ») :

1. ses prospects (40 pour l'e-mail) ont reçu leur premier message et
   leurs relances, et la dernière relance date de plus de 7 jours ;
2. **ou** elle a atteint la durée de son plan (30 jours au plus) ;
3. **ou** Serge n'a plus de prospects à contacter : « Trouver des
   prospects » est passé 3 fois de suite sans en trouver un nouveau.

Exemple : 40 artisans contactés en 4 jours, deux relances à J+3 et J+10,
la dernière part au 14e jour ; le test se termine au 21e jour, même si le
plan prévoyait 30 jours. Un test rapide ne garde pas sa place pour rien.

**Une campagne lourde** n'a pas de durée : elle contacte son volume de la
semaine, jusqu'à son total (1 000 e-mails), puis elle se termine. Le
business reste en `FULL_RUNNING` : Serge répond toujours et vend à ceux
qui écrivent. Ce qui vient ensuite (prolonger, arrêter, libérer la place)
est au lot 15.

**Après la fin d'une campagne**, Serge répond toujours aux contacts qui
écrivent : seuls les premiers messages et les relances s'arrêtent.

---

## 4. L'étape 3 dans le pipeline : le test léger

Toutes ces invocations sont en base, comme les autres. Celles qui servent
aussi à la prospection lourde sont marquées *(3 et 6)*.

1. **Démarrer une campagne** *(3 et 6)* — sans LLM. Déclencheur : une
   campagne passe à `READY`. Elle passe la campagne à `RUNNING`, note son
   début et sa fin prévue (début + durée du plan, pour un test), et passe
   le business à `SMOKE_RUNNING` (ou `FULL_RUNNING` pour une campagne
   lourde). Lien : « Trouver des prospects ».

2. **Trouver des prospects** *(3 et 6)* — LLM, niveau intelligent, file
   des travaux. Elle reçoit d'office le plan (la cible), la fiche du
   business et la fiche produit, et la version courte des contacts déjà
   trouvés pour ce business (pour ne pas les reprendre). Outils :
   rechercher sur le web, lire une page, l'interface web du lot 10 (pour
   un annuaire ou une fiche Google Maps qui demande un navigateur),
   chercher un contact en base, et **vérifier une adresse e-mail** (une
   nouvelle capacité gratuite : le domaine reçoit-il des e-mails ?). Elle
   rend au plus 10 prospects par passage (réglage) : nom, entreprise,
   rôle, pourquoi il est visé, et ses adresses professionnelles (e-mail
   ou téléphone), chacune avec la page où elle a été trouvée (Q36).

   **Jamais d'adresse générique** (Q93). Un contact précis paie toujours,
   et beaucoup se trouvent en ligne : le site de l'entreprise (sa page
   équipe, ses mentions légales), les annuaires professionnels, les fiches
   Google Maps, les articles et publications. Elle cherche une personne
   nommée, avec son rôle (« Marie Dupont, gérante »), et son adresse
   directe (`marie.dupont@…`), pas `contact@`, `info@` ou `accueil@`. Une
   entreprise dont elle ne trouve qu'une adresse générique est laissée de
   côté. Le prompt le dit, et le code d'écriture le garantit : une
   adresse dont le début est dans la liste des adresses génériques
   (réglage en base : `contact`, `info`, `hello`, `accueil`, `bonjour`,
   `admin`, `support`, `commercial`…) est refusée.

   Elle écrit les contacts, leurs adresses (avec leur source), et un
   premier message « à rédiger » pour chacun, sur le canal de la campagne.
   Lien, une tâche par premier message : « Écrire le premier message » ou
   « Préparer le premier appel ».

3. **Réapprovisionner les campagnes** *(3 et 6)* — sans LLM, toutes les
   heures. Pour chaque campagne `RUNNING` qui n'a pas encore son volume
   (40 au total pour un test, 200 cette semaine pour une campagne
   lourde), elle relance « Trouver des prospects » si Serge a moins d'un
   jour d'envois d'avance (réglage : avec 40 e-mails par jour, il garde au
   plus 40 premiers messages qui attendent). Ainsi, Serge ne cherche pas
   1 000 prospects d'un coup, et ne dépense pas pour des contacts qu'il
   n'aura pas le temps d'écrire.

4. **Écrire le premier message** *(3 et 6)* — LLM, niveau moyen, file des
   conversations. La vraie version de l'invocation temporaire du lot 8.
   Elle reçoit le contact, la source de son adresse, le plan (l'angle,
   l'offre), la fiche produit, et le lien du POC (phase `smoke`) ou le
   lien du produit et son prix (phase `full`). Elle écrit l'objet et le
   texte. Lien : « Envoyer un message » (existe).

5. **Préparer le premier appel** *(3 et 6)* — LLM, niveau moyen. La vraie
   version de l'invocation temporaire : le but de l'appel, que l'agent
   vocal suit. Lien : « Envoyer un message ».

6. **Les relances et les réponses** existent (lots 8 et 8 bis) : rien à
   ajouter. Le rythme des relances est le même pour tous les business :
   les réglages de « Préparer les relances » (3 jours, puis 7 jours, deux
   au plus), sur la page Policy (Q92).

7. **Clore les campagnes finies** *(3 et 6)* — sans LLM, toutes les
   heures. Elle passe à `FINISHED` chaque campagne qui remplit une
   condition de fin (partie 3), avec sa raison. Quand toutes les
   campagnes de test d'un business sont finies, le business passe à
   `SMOKE_DONE` et la date de fin du test est notée sur sa fiche.

---

## 5. La fin d'un test léger : mesurer et juger

8. **Mesurer le test** — sans LLM. Déclencheur : un business passe à
   `SMOKE_DONE`. Elle écrit le compte rendu chiffré du test
   (`test_reports`) : prospects trouvés et contactés par canal, réponses
   par réaction, points, dépense, points par euro. Puis elle **juge le
   test avec des seuils en chiffres absolus**, réglés sur la page Policy
   (Q93) :
   - **assez de prospects contactés** : au moins 30, tous canaux
     confondus ; sinon le test ne dit rien, faute de prospects ;
   - **assez de points** : au moins 10 (par exemple un « intéressé » et
     un « refus », ou un « rendez-vous ») ;
   - **assez de points par euro** : au moins 0 au départ (pas de seuil).

   Un test qui passe les trois seuils est **retenu**. Sinon, le business
   passe à `KILLED`, avec la raison (« 4 points, moins que les 10
   demandés »), libère sa place et produit une leçon (Q92) ; il n'est pas
   comparé pour le choix du principal. Le code juge, pas un modèle : il
   lit des chiffres et des seuils (charte, partie 4).

9. **Faire le bilan du test** — LLM, niveau intelligent, file des
   travaux. Lien depuis « Mesurer le test », retenu ou non. Elle lit le
   compte rendu chiffré, les fils des contacts qui ont répondu, leurs
   objections et leurs demandes sur le produit, et écrit sur le compte
   rendu un bilan en quelques lignes : ce qui a plu, ce qui a bloqué, les
   prospects qui ont le mieux répondu. Ce bilan sert au choix du
   principal, à la conception du vrai produit et à la prospection lourde.

10. **Tirer la leçon d'un business arrêté** — LLM, niveau moyen.
    Déclencheur : un business passe à `KILLED`, quelle que soit l'étape
    (Q46 : chaque business arrêté produit une leçon). Elle écrit une ou
    deux leçons au statut « proposée », rattachées à l'étape ou à
    l'invocation qu'elles concernent. Julien les garde ou les jette dans
    Mission Control (page Mémoire).

---

## 6. L'étape 4 : choisir le business principal

11. **Choisir le business principal** — LLM, niveau intelligent, file des
    travaux. Deux déclencheurs : un bilan de test est écrit, ou la place
    lourde se libère (au lot 15). **Trois conditions** : aucun test léger
    ne tourne encore (aucun business `POC_SELECTED`, `SMOKE_READY` ou
    `SMOKE_RUNNING`), au moins un business retenu attend (`SMOKE_DONE`
    retenu, ou `PARKED` testé il y a moins de 60 jours), et la place
    lourde est libre (Q14 bis). Elle reçoit, pour chacun : ses chiffres,
    son bilan et les réponses de ses prospects. Elle propose un business,
    ou aucun, avec une phrase par business. Critère de départ, donné dans
    le prompt : d'abord les points par euro, puis les points, puis la
    facilité de vendre le produit fini. Elle écrit sa proposition
    (`principal_choices`).

12. **Faire valider le choix** — sans LLM (capacité « Demander à Julien »).
    Un ticket « Choix du principal » : la proposition, et pour chaque
    business ses chiffres et son bilan. Boutons : « Valider », « Choisir
    un autre » (un choix parmi les autres business), « Aucun ». Sans
    réponse sous 48 heures, la proposition s'applique (Q16 bis).

13. **Appliquer le choix du principal** — sans LLM. Déclencheur : la
    réponse au ticket. Le business choisi passe à `PRODUCT_BUILDING` ;
    les autres business retenus passent à `PARKED`, avec la date. Avec
    « Aucun », tous passent à `PARKED`. Lien : « Concevoir le produit »
    (étape 5, lot 10), qui remplace le bouton d'essai du lot 10.

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
(Q93). Le suivi et le raffinement pendant la vente viendront au lot 15.

16. **Préparer la prospection lourde** — LLM, niveau intelligent.
    Déclencheur : un business passe à `PRODUCT_READY`. Elle lit le plan du
    produit, le bilan du test et ses chiffres par canal, et écrit une
    campagne lourde par canal, au statut `READY` : la cible précise
    (affinée par ce que le test a appris : les métiers, les tailles
    d'entreprise et les régions qui ont le mieux répondu) et l'angle des
    messages. Les volumes ne sont pas les siens : ce sont les réglages de
    chaque canal (partie 3). Elle écrit aussi un premier message « à
    rédiger » pour **chaque contact du test qui avait dit « intéressé » ou
    « rendez-vous »** : ils apprennent les premiers que le produit existe,
    avec son lien. Un ticket d'information prévient Julien (Q42 : la
    prospection lourde est automatique).

17. La campagne passe à `RUNNING` par **Démarrer une campagne**, et le
    business à `FULL_RUNNING`. **Trouver des prospects**, **Réapprovisionner
    les campagnes**, **Écrire le premier message**, les relances et
    **Traiter une réponse** servent comme au test léger, au volume de la
    semaine. Différence : la fiche produit donne le prix et le lien
    d'inscription du produit, et « Traiter une réponse » l'envoie à un
    contact « intéressé ».

18. **Enregistrer une vente** — sans LLM. Déclencheur : Stripe annonce un
    paiement ou un abonnement (tables `transactions` et `subscriptions`,
    remplies par le webhook). Elle retrouve le contact par son e-mail dans
    ce business et le passe à « client » (`CUSTOMER`) : il ne reçoit plus
    de relance de prospection. Un acheteur inconnu devient un contact
    « entrant » et client. La **première vente** d'un business ouvre un
    ticket d'information.

19. **Clore les campagnes finies** termine une campagne lourde quand son
    total est atteint (partie 3). Le business reste en `FULL_RUNNING`, et
    le lot 11 s'arrête là.

---

## 8. Les tables

Chaque table a sa vue, ses colonnes inscriptibles, ses statuts permis et
ses quotas en base (règle de tous les lots).

- **`campaigns`** (existe) : reçoit `phase` (`smoke` ou `full`), le plan
  dont elle vient, ses volumes (au total, et par semaine pour une
  campagne lourde), la date de fin prévue d'un test et la raison de sa
  fin. Les colonnes que rien n'écrit (`budget_cap_eur`,
  `thresholds_json`) sont retirées.
- **`contacts`** (existe) : reçoit la campagne qui l'a trouvé.
- **`contact_addresses`** (existe) : reçoit la page où l'adresse a été
  trouvée (Q36) et le résultat de sa vérification (le domaine reçoit des
  e-mails, ou un rebond).
- **`test_reports`** (nouvelle) : une ligne par test léger : le business,
  ses chiffres par canal, le verdict (retenu ou non, avec la raison) et le
  bilan.
- **`principal_choices`** (nouvelle) : une ligne par proposition de
  principal : le business proposé (ou aucun), une phrase par business
  comparé, et ce que Julien a décidé.
- **`ventures`** : les statuts de la partie 2 ; la date de fin du test
  léger existe (`smoke_ended_at`) et sert à la règle des 60 jours.

Les ventes restent dans `transactions` et `subscriptions` (étape 8,
lot 10) : on ne recopie rien.

---

## 9. Les réglages : les critères chiffrés

Tous en base, et modifiables dans Mission Control (Q68). Valeurs de
départ :

| Réglage | Départ | Où |
|---|---|---|
| Prospects d'un test léger, par canal | e-mail 40, appel 20 | Policy, « Taille des essais » |
| Prospects par semaine, prospection lourde, par canal | e-mail 200, appel 50 | idem |
| Prospects au total, prospection lourde, par canal | e-mail 1 000, appel 250 | idem |
| Durée maximale d'un test léger | celle du plan, 30 jours au plus | idem |
| Fin d'un test léger après la dernière relance | 7 jours | « Clore les campagnes finies » |
| Passages sans nouveau prospect avant de clore | 3 | idem |
| Prospects par passage de « Trouver des prospects » | 10 | son réglage |
| Adresses génériques refusées | `contact`, `info`, `hello`, `accueil`, `bonjour`, `admin`, `support`, `commercial`… | Policy, « Contacts » |
| Envois d'avance gardés en réserve | 1 jour | « Réapprovisionner les campagnes » |
| Prospects contactés pour qu'un test compte | 30 | « Mesurer le test » |
| Points pour qu'un test soit retenu | 10 | idem |
| Points par euro pour qu'un test soit retenu | 0 | idem |
| Âge maximum d'un business mis de côté | 60 jours | « Choisir le business principal » |

Les places (3 et 1) sont des quotas de la page Policy. Les anciens
réglages de « Taille des essais » sont remplacés : « Petit essai,
personnes touchées » et « Grand essai, personnes touchées » par les
volumes par canal, et les seuils qui comptaient des réponses positives
(« Arrêt, réponses positives au plus », « Élargir, réponses positives au
moins », « Élargir, rendez-vous au moins », « Prolongations au plus ») sont
retirés : les points les remplacent, et prolonger est au lot 15 (Q78,
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

- **Page Système, « Campagnes »** : la section retirée parce que rien ne
  créait de campagne revient, branchée. Pour chaque campagne : son
  business, sa phase, son canal, son état, combien de prospects trouvés
  et contactés sur son volume, les réponses, les points, sa fin prévue
  ou la raison de sa fin. Un bouton met une campagne en pause ou la
  relance.
- **Page En direct** : les places, « 3 places de test sur 3 occupées » et
  « place lourde : libre », à côté du bouton du cycle d'écoute.
- **Fiche d'un business** : son compte rendu de test (chiffres, verdict,
  bilan) et le choix du principal qui le concerne.
- **Page Économie** : les ventes et l'argent encaissé par business
  existent déjà ; s'y ajoutent les campagnes lourdes et leur rythme.

---

## 12. Ce que le code doit apprendre (plus tard)

Ce sont des capacités générales, réglées en base ; aucune ne connaît une
invocation.

1. **Une condition de déclencheur « nombre de lignes »** : « au plus
   0 business `SMOKE_RUNNING` », « au moins 1 test retenu ». Les quotas
   d'aujourd'hui servent à la fois de limite d'écriture et de condition ;
   il faut une condition qui ne limite pas l'écriture.
2. **Une valeur d'écriture « maintenant plus N jours »**, N lu dans une
   colonne ou un réglage (la fin prévue d'un test).
3. **Une règle d'écriture « valeur refusée »** : une colonne refuse les
   valeurs qui commencent par un mot d'une liste en base (les adresses
   génériques).
4. **Les chiffres d'un business**, une capacité et un outil : prospects,
   réactions, points, dépense, points par euro, ventes et argent, sur une
   période. Mission Control les calcule déjà (lot 9) ; le pipeline doit
   pouvoir les lire.
5. **Vérifier une adresse e-mail** : le domaine a-t-il un serveur de
   courrier (gratuit, sans service payant, Q48) ?
6. **Les rebonds** : la relève de l'e-mail reconnaît un message de rebond,
   marque l'adresse inactive, et le contact injoignable s'il n'a pas
   d'autre adresse. Aujourd'hui, rien ne lit les rebonds.
7. **Réapprovisionner** et **clore** des campagnes : deux capacités du
   domaine des campagnes, comme « Préparer les relances » l'est des envois.
8. **Enregistrer une vente** : relier un paiement Stripe à un contact par
   son e-mail.
9. **Un choix parmi des lignes dans un ticket** : le bouton « Choisir un
   autre » liste les business comparés.

---

## 13. Ce que le lot 11 retire

- Les invocations temporaires du kit d'essai des canaux (« Lancer un
  essai », « Créer le contact d'essai », « Écrire le premier message
  (temporaire) », « Préparer le premier appel (temporaire) ») et le bouton
  « Lancer un essai », une fois les vraies invocations essayées en
  production (TODO, « Plus tard »).
- Le bouton d'essai « Construire le vrai produit » du lot 10, remplacé par
  le lien depuis le choix du principal.
- Les champs « nombre de prospects » et « relances » du plan du POC
  (lot 10), remplacés par des réglages.
- Le module `serge/funnels/lifecycle.py`, qui impose en dur « un seul
  business actif » et d'anciens statuts : les statuts et les places sont
  en base.
- Les anciens réglages de « Taille des essais » (partie 9) et les
  colonnes inutiles des campagnes (partie 8).
- Les invocations écrites mais jamais appelées que ce lot remplace (TODO,
  « Brancher ou supprimer les invocations jamais appelées ») : la
  découverte de contacts (→ « Trouver des prospects »), le résumé d'un
  test (→ « Faire le bilan du test »), le départage de deux prospects
  (→ « Choisir le business principal »), l'hypothèse de test lourd
  (→ « Préparer la prospection lourde ») et le résumé d'un fil
  (« Traiter une réponse » lit déjà le fil entier). Leur code propre est
  supprimé. Les options de pivot, le plan de passage à l'échelle et
  l'arbitre du budget attendent le point de la semaine, au lot 15.

---

## 14. Le lot 10 bis : les réponses automatiques

Fait avant le lot 11 (Q93). Une réponse automatique (« je suis absent
jusqu'au 20 », « votre demande n° 1234 est bien reçue ») ne fait jamais
répondre Serge sans fin : reconnue à ses en-têtes, elle est rangée dans le
fil sans appeler le modèle ; « Traiter une réponse » peut décider
d'arrêter avec un contact (« Arrêté ») ; et un garde-fou annule tout
message au-delà de 10 en 24 heures au même contact, arrête avec lui et
prévient Julien et Clem. Le détail est dans
[`PIPELINE.md`](PIPELINE.md), « Parler aux prospects et aux clients ».

---

## 15. Le lot 15 : faire vivre les produits

Un produit qui a des clients doit être entretenu : ce n'est plus un
pipeline avec un début et une fin. Le lot 15, placé tout à la fin,
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

Au lot 11, un business en `FULL_RUNNING` garde sa place : Serge continue
de répondre aux messages (le circuit des conversations ne dépend pas du
statut), et Stripe continue d'encaisser les abonnements.

---

## 16. Les questions ouvertes

Tranchées par Clem le 13 octobre 2026 : la fin d'un test léger (au plus
tôt), un test sous les seuils (arrêté, avec une leçon), l'étape 1 en
automatique (dans ce lot), le rythme des relances (un réglage commun)
(Q92) ; des volumes en chiffres absolus par canal, jamais d'adresse
générique, la prospection lourde qui vend le produit tel quel, le point de
la semaine au lot 15 (Q93).

Encore à valider, avec les valeurs de départ proposées (toutes
réglables) :

1. **Les volumes** : 40 e-mails et 20 appels pour un test ; 200 e-mails
   et 50 appels par semaine en prospection lourde, jusqu'à 1 000 et 250.
2. **Les seuils d'un test retenu** : 30 prospects contactés et 10 points
   au moins.
3. **Les intéressés du test** : prévenus en premier quand le produit fini
   sort, avec son lien.
