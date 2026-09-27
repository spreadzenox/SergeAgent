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

### Le circuit des réponses (branché pour l'e-mail)

1. **Relever la boîte mail** (`email.poll`, toutes les 5 minutes). Chaque
   nouveau message est rattaché à un prospect et traduit en signal.
2. Selon le signal (`serge/observe/router.py`) :
   - **désinscription** : la personne est bloquée tout de suite ;
   - **refus** : réponse polie automatique ;
   - **réponse** : « Classer une réponse » (`classify_reply`) choisit une
     catégorie (demande de rendez-vous, objection de prix, question…), et
     « Extraire un rendez-vous » (`extract_meeting`) cherche une date ;
   - **intéressé** : « Répondre à une intention » (`reply_intent`) écrit
     une réponse, envoyée automatiquement. En cas de doute, ou si un
     garde-fou refuse l'envoi, Julien reçoit un ticket avec le brouillon ;
   - **inclassable** : « Relire un message autre » (`review_other`) traite
     ces cas en lot et propose de nouvelles catégories.

### La voix

- Appels sortants et entrants en temps réel (`serge/voice/`), avec un pont
  vers Asterisk.
- « Noter un appel » (`score_call`) note chaque appel. Deux mauvaises
  notes sur les dix derniers mettent la voix en pause.
- « Écrire un script d'appel » (`voice_script`) et « Dialoguer à l'oral »
  (`voice_dialog`) sont écrites mais pas appelées : la voix temps réel a
  son propre prompt.

### Écrit mais pas branché

« Comment grandir » (`plan_scale`), « Arbitrer l'allocation »
(`judge_allocator`) et « Résumer un fil » (`summarize_thread`).

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

### Les retours des clients

1. « Traiter une réponse » repère aussi les **demandes sur le produit** :
   bug, insatisfaction, demande (exemple : « est-ce que vous pouvez
   ajouter l'export Excel ? »). Chaque demande devient une ligne dans une
   nouvelle table `product_requests`.
2. **Urgent** (un bug qui touche un client qui a payé) : correction lancée
   tout de suite. **Le reste** : l'invocation hebdomadaire « Préparer la
   prochaine version » regroupe les doublons, choisit ce qui entre dans la
   version et refuse le reste avec une raison.
3. Construction avec le couple builder / reviewer de l'étape 5.
4. Corrections et petites améliorations : publication automatique.
   Nouvelle fonctionnalité importante, changement de prix ou nouvelle
   capacité nécessaire : ticket Discord.
5. Chaque personne dont la demande est livrée reçoit un message.

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
