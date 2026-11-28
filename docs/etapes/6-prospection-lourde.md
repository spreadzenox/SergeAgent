# Étape 6 — Prospection lourde

Identifiant : `prospection_lourde`.

**Rôle.** Faire vivre le business principal : prospecter à plus grande
échelle, répondre, vendre, livrer, améliorer le produit avec les retours
des clients.

**Entrée.** Le produit en ligne construit à l'étape 5.

**Sortie.** Des clients, de l'argent, et à terme le passage en
`MAINTENANCE`.

---

## Aujourd'hui

**Le début de l'étape est en base depuis le lot 12** (16 novembre 2026) :
vendre en masse le produit fini, tel qu'il sort de la construction. Elle
n'est pas encore essayée sur le serveur : c'est le rôle de l'essai total
(page Système). Le détail est dans
[`LOT12_CONCEPTION.md`](../LOT12_CONCEPTION.md), partie 7.

1. **Préparer la prospection lourde**, dès que le produit est en vente
   (`PRODUCT_READY`) : une campagne lourde par canal, avec sa cible,
   affinée par ce que le test a appris, et l'angle des messages. Un
   ticket d'information prévient Julien et Clem.
2. **Prévenir les intéressés du test** : chaque contact qui avait dit
   « intéressé » ou « rendez-vous » reçoit le premier le lien du produit.
3. Les campagnes démarrent (le business passe à `FULL_RUNNING`), et les
   invocations du test léger servent telles quelles : trouver des
   prospects (200 par semaine et 1 000 au total par e-mail), écrire le
   premier message, relancer, répondre, suivre la campagne.
4. **Enregistrer une vente** : quand Stripe annonce un paiement, le
   contact qui a l'e-mail du payeur passe à « client », et ne reçoit plus
   de relance ; la première vente d'un business ouvre un ticket
   d'information.

**Faire vivre le produit en vente est en base depuis le lot 16**
(28 novembre 2026, décision Q119). Aucun vrai produit fini n'était en
vente ce jour-là : la boucle n'a tourné que dans ses tests.

5. **Faire le point sur un produit** (niveau intelligent), chaque lundi à
   8 h 30 (un déclencheur à heure fixe, réglable sur la page Pipeline),
   pour chaque vrai business dont le produit fini est en vente
   (`PRODUCT_READY` ou `FULL_RUNNING`). Le business d'un essai n'est pas
   visité chaque lundi : le bouton « Faire le point sur ce produit
   maintenant », sur la fiche d'un business, le lance à la demande, pour
   un essai comme pour un vrai business. Ce bouton a un champ
   « consigne », facultatif : ce qu'un humain y écrit décide du point
   (exemple : « ajoute une offre Pro à 9 € par mois »). Elle reçoit la fiche du business, la fiche produit,
   le plan validé, les offres, ce qui est en ligne, les ventes et les
   abonnements, les campagnes, ce qu'ont répondu les prospects, les
   demandes des clients, la nouvelle version en cours et ses 8 derniers
   points. Elle rend deux choix, dans des listes fermées, avec leurs
   consignes :
   - pour le produit : `rien`, `corriger` (quelque chose ne marche pas
     comme le plan le prévoit) ou `faire_evoluer` (une fonctionnalité,
     une offre de plus, un prix à changer) ;
   - pour la prospection : `rien` ou `relancer`.
   Chaque point est gardé (`product_reviews`), et un ticket d'information
   donne son compte rendu à Julien et Clem.
6. **Une nouvelle version** repasse par les invocations de l'étape 5 :
   une correction reprend à la construction et part en prod dès que le
   relecteur la juge bonne ; une évolution reprend à la conception et
   garde les tickets « Plan » et « Tester le produit ». Le détail est
   dans [`5-construction.md`](5-construction.md), « Une nouvelle
   version ». **Une seule à la fois par produit** : le point qui en lance
   une porte son état (`open`, puis `online` ou `dropped`), et une règle
   de doublon en base écarte un second point qui voudrait en lancer une
   autre ; rien ne part alors. Le bouton « Abandonner la nouvelle version
   en cours d'un produit », sur la fiche du business, libère la place
   (une construction qui n'aboutit pas, une idée qu'on ne veut plus).
7. **Relancer la prospection d'un produit** (niveau intelligent), quand
   le point le décide : de nouvelles campagnes lourdes, une par canal
   branché qui n'en a pas déjà une en cours, avec la cible et l'angle que
   demandent les consignes du point. Elles démarrent comme les autres.
8. **Un bug signalé** : quand « Traiter une réponse » note une demande
   de sorte « bug » pour un business dont le produit est en vente,
   **« Trier un bug signalé »** (niveau intelligent) décide tout de
   suite : `corriger` ou `rien`. Elle n'a pas d'autre choix : un bug
   signalé ne lance jamais une fonctionnalité nouvelle. « Corriger »
   retient la demande et lance la construction avec ses consignes ; le
   bug d'un business en test léger ne lance rien. Un ticket d'information
   dit ce qui est décidé.
9. **L'adresse de contact d'un produit** : un e-mail écrit à l'adresse
   que montre un produit en ligne (`serge+<nom court>@…`, notée dans
   `deployments.contact_email`) par quelqu'un que Serge ne connaît pas
   devient le message d'un contact « entrant » de ce business ; « Traiter
   une réponse » y répond avec la fiche produit, et note ses demandes.
   Une réponse automatique ne crée pas de contact.

Ce qui reste (accélérer, pivoter, arrêter, les livraisons, les impayés,
la maintenance et la fermeture) est décrit plus bas, et n'est pas fait.
Le pont vers Asterisk et
l'agent vocal (`serge/voice/`) ne décrochent et n'appellent que si Serge a
été démarré dans Mission Control ; Serge est arrêté par défaut.

---

## Décidé

### Répondre aux prospects et aux clients

Les messages des prospects et des clients sont imprévisibles : questions
sur le produit, demandes de changement, questions de délais, sujets sans
rapport. On ne peut pas tout prévoir, mais on calibre les cas classiques,
et Serge demande de l'aide quand il ne sait pas. Ce circuit sert les
étapes 3 et 6, et il a son propre interrupteur, pour ne pas dépendre de
l'étape 6.

**Une seule invocation répond : « Traiter une réponse ».** Quand un
message arrive, elle est ajoutée à la file avec la priorité la plus haute.
Elle reçoit en entier le fil de discussion du prospect, sa fiche, la fiche
du business et la fiche produit. Elle rend trois choses : la réaction du
prospect, dans une liste fermée (intéressé, question, objection, refus,
désinscription, hors sujet) ; la réponse à envoyer, ou « pas de réponse » ;
et s'il faut Julien, avec la raison. Exemple : le prospect demande un prix
que le plan ne prévoit pas. Elle remplace quatre invocations actuelles :
« Classer une réponse », « Répondre à une intention », « Relire un message
autre » et « Extraire un rendez-vous ».

**Les questions sur le produit** trouvent leur réponse dans la fiche
produit. Quand Julien répond à un ticket sur une question produit, sa
réponse est ajoutée aux questions fréquentes de la fiche : la fois
suivante, Serge répond seul.

**Les questions de délais** sont les plus difficiles à prévoir. Le LLM
répond seul, avec trois consignes de prudence dans son prompt : ne jamais
promettre une date ou un délai qui n'est pas dans la fiche produit ; ne
jamais promettre une fonctionnalité qui n'existe pas (la demande devient
une demande client) ; en cas de doute, répondre sans s'engager, par
exemple « je vérifie et je reviens vers vous », et ouvrir un ticket.

**Les tickets doivent se comprendre sans suivre Serge.** Quand
l'invocation dit « besoin de Julien », ou qu'un garde-fou bloque l'envoi,
Julien reçoit un ticket qui contient, dans cet ordre : le business en trois
lignes (nom, ce qu'il vend, prix, où il en est) ; le prospect (nom,
entreprise, où il en est) ; le fil de la conversation, avec les derniers
messages en entier ; le brouillon de Serge ; pourquoi Serge a besoin
d'aide et la question précise ; un lien vers la fiche du prospect dans
Mission Control.

**Le délai de réponse se règle canal par canal** dans Mission Control, sur
la fiche du canal : délai minimum, délai maximum, heures et jours ouvrés.
Exemple : par e-mail entre 5 et 20 minutes pendant les heures de bureau et
le lendemain matin sinon, sur LinkedIn entre 1 et 4 heures, par SMS tout
de suite. Juste avant d'envoyer, Serge vérifie que le prospect n'a rien
écrit de nouveau ; s'il a réécrit, l'envoi est annulé et le fil complet est
retraité.

### Les appels entrants

Un appel ne passe pas par la file des tâches. Le standard téléphonique
décroche et confie l'appel à un agent vocal, un programme séparé qui parle
en direct et tourne en parallèle du reste de Serge. Quand un appel arrive
pendant une construction, il n'y a donc rien à interrompre.

Au décrochage, le numéro est cherché en base. S'il est connu, l'agent
reçoit la fiche du prospect, son fil, la fiche du business et la fiche
produit. S'il est inconnu, l'agent dit « Bonjour, je suis Serge, en quoi
puis-je vous aider ? », demande à qui il parle, et cherche la fiche avec un
tool, par nom, entreprise, e-mail ou numéro. Si l'appelant propose quelque
chose à Serge, comme un partenariat, l'agent répond poliment qu'il ne peut
pas traiter ce genre de demande pour l'instant ; le résumé est quand même
écrit au journal. Quand la personne est reconnue seulement parce qu'elle a
dit son nom, et pas par son numéro, l'agent se sert de sa fiche pour
comprendre, mais ne répète aucune information sensible (montants,
adresses, propos d'un collègue). Après l'appel, le résumé entre dans le fil
du prospect, et « Traiter une réponse » est lancée s'il y a une suite à
donner.

Aujourd'hui, l'agent vocal a le même prompt fixe pour tous les appels, ne
sait rien de celui qui appelle et n'a aucun tool.

### Le point hebdomadaire

Le point de la semaine existe (« Aujourd'hui », point 5) : il décide du
produit et de la prospection (décision Q119). Ce qui suit avait été
décidé avant (Q42), et n'est pas fait : accélérer, pivoter et arrêter.

Une fois par semaine, **« Faire le point sur le business principal »** lit
les chiffres de la semaine (points, points par euro, argent encaissé,
réponses, demandes des clients) et propose :

- **continuer** au même rythme ;
- **accélérer** : +50 % de volume maximum, ou un canal de plus ;
- **pivoter** : changer un seul élément (cible, prix, offre ou canal) ;
- **arrêter**.

« Continuer » et « accélérer » s'appliquent automatiquement, avec un
ticket d'information. « Pivoter » et « arrêter » passent par un ticket
Discord validé par Julien. Cette invocation remplace « Comment grandir »,
« Trois autres idées » et « Arbitrer l'allocation ».

La prospection lourde vend en masse le produit fini, tel qu'il sort de la
construction : elle est détaillée dans
[`LOT12_CONCEPTION.md`](../LOT12_CONCEPTION.md), partie 7 (décisions Q92
et Q93). La maintenance et la fermeture, ci-dessous, restent à faire.

### Les retours des clients

C'est fait (« Aujourd'hui », points 5 à 9, décision Q119), sauf le
dernier point :

1. « Traiter une réponse » repère les **demandes sur le produit** : bug,
   insatisfaction, idée (exemple : « est-ce que vous pouvez ajouter
   l'export Excel ? »). Chaque demande devient une ligne de
   `customer_requests`.
2. **Un bug signalé** sur un produit en vente : trié tout de suite, et
   corrigé s'il y a lieu. **Le reste** : le point de la semaine choisit
   ce qui change, et la conception retient ou refuse chaque demande, avec
   sa raison.
3. Construction avec le constructeur et le relecteur de l'étape 5.
4. Une correction part en ligne dès que le relecteur la juge bonne, avec
   un ticket d'information. Une évolution (une fonctionnalité, une offre,
   un prix) passe par les tickets « Plan » et « Tester le produit ».
5. Pas encore fait : chaque personne dont la demande est livrée reçoit un
   message.

### La fin de la prospection lourde

Arrêter de prospecter n'est pas fermer le business. Voir `MAINTENANCE` et
`CLOSED` dans [`PIPELINE.md`](../PIPELINE.md).

- **Entrée en `MAINTENANCE`** : quand les quotas de prospection lourde sont
  épuisés, ou quand Julien valide « arrêter » alors que le business a des
  clients (sans client, il passe en `KILLED`).
- En `MAINTENANCE`, Serge ne contacte plus de nouveaux prospects, mais il
  livre, répond, corrige et encaisse.
- **Passage en `CLOSED`**, automatique, quand il ne reste rien à faire :
  aucune livraison due, aucun abonnement actif, aucune demande client
  ouverte, aucun message client depuis 30 jours.
- **Nouvelle table `deliveries`** : une ligne par chose vendue à livrer
  (client, paiement, quoi livrer, date promise, état). Une livraison en
  retard passe en priorité haute.
