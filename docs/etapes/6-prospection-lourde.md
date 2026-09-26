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

### Une seule invocation pour répondre

**« Traiter une réponse »** lit le fil complet du prospect et rend trois
choses :

- **le signal**, dans une liste fermée : intéressé, question, objection,
  refus, désinscription, hors sujet ;
- **la réponse à envoyer**, ou « pas de réponse » ;
- **« besoin de Julien : oui ou non »**, avec la raison. Exemple : le
  prospect demande un prix que le plan ne prévoit pas.

Elle remplace « Classer une réponse », « Répondre à une intention »,
« Relire un message autre » et « Extraire un rendez-vous ». La réponse part
automatiquement, sauf si elle dit « besoin de Julien » ou si un garde-fou
refuse : Julien reçoit alors un ticket avec le brouillon.

Ce circuit sert **les étapes 3 et 6**. Il a son propre interrupteur, pour
ne pas dépendre de l'étape 6.

**Délai** : entre 5 et 20 minutes après le message pendant les heures
ouvrées (exemple : 8 h à 20 h, du lundi au samedi), le lendemain matin
sinon.

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
