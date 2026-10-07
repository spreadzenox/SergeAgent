# Lot 8 — Conception : les canaux de conversation

Ce document décrit comment Serge parle aux contacts des business qu'il
teste : un fil par contact, un message reçu qui réveille le pipeline, une
réponse écrite par une seule invocation, des relances, une désinscription
qui vaut partout. Il suit les réponses de Clem du 7 octobre 2026 (décision
Q79 de [`DECISIONS_REVUE.md`](DECISIONS_REVUE.md)) et la règle de tous les
lots : le code n'est qu'un interpréteur de la base, jamais de code propre à
une invocation ni à un canal.

Le lot se livre en quatre PR :

1. **L'architecture des canaux, sans canal réel** (ce document, parties 1
   à 9), testée avec un faux canal.
2. **Le canal e-mail** (partie 10).
3. **Le canal appel**, et un agent vocal qui sait à qui il parle
   (partie 11).
4. **Le kit de test** : une demi-fiche produit, un business bidon, des
   invocations temporaires, un bouton pour lancer l'essai (partie 12).

---

## 1. Un canal : une ligne en base et un adaptateur

Un canal est une façon de joindre une personne : l'e-mail, le téléphone,
plus tard LinkedIn. Il y a deux parties.

**Dans le code, un adaptateur par canal**, avec trois fonctions, toujours
les mêmes :

- `send(message)` envoie un message à une adresse et rend une référence
  (l'identifiant du mail chez le fournisseur, celui de l'appel) ;
- `poll(depuis)` rend les messages reçus depuis une date, chacun avec son
  expéditeur, son texte, et à quel message il répond (pour l'e-mail, les
  en-têtes `In-Reply-To` et `References`). Un canal qui reçoit en direct
  (le téléphone) n'en a pas : son programme écrit lui-même chaque appel
  reçu (partie 4) ;
- `confirm(message)` dit si un envoi est vraiment parti : l'e-mail est
  cherché dans les messages envoyés, l'appel dans son journal.

Les adaptateurs sont rangés dans `serge/channels/`, un fichier par canal,
et déclarés dans une seule liste. Ils ne savent rien d'une invocation ni
d'un business : ils transportent un message.

**En base, une ligne de `canaux`** par canal : son titre, sa description,
et en plus, au lot 8 :

- `address_channel` : la sorte d'adresse qu'il utilise dans
  `contact_addresses` (`email` pour l'e-mail, `phone` pour l'appel) ;
- `connected` : 1 si son adaptateur existe dans le code (rempli au
  démarrage, comme les capacités) ;
- `polled_at` : la dernière relève réussie (vide pour un canal qui reçoit
  en direct).

**Ses réglages sont dans la policy** (famille « Canaux » de la page
Policy), un groupe par canal. Exemple pour l'e-mail :
`channels.email.reply_delay_min_minutes` (5), `reply_delay_max_minutes`
(20) et `max_poll_age_minutes` (60).

**Ajouter un canal**, c'est donc écrire son adaptateur, ajouter sa ligne et
ses réglages : le pipeline ne change pas. Un canal par machine virtuelle
(LinkedIn, lot 12) aura un adaptateur qui confie l'envoi à l'agent web.

---

## 2. Le fil d'un contact

Le fil, c'est tout ce qui s'est dit avec un contact, tous canaux
confondus, par date (décision Q37). Il est fait de deux tables qui
existent déjà, auxquelles on ajoute des colonnes :

**`touches` : ce que Serge envoie.** Une ligne par message, écrite *avant*
l'envoi :

| Colonne | Exemple | Sens |
|---|---|---|
| `contact_id`, `venture_id` | `c_12`, `v_3` | à qui, pour quel business |
| `channel`, `address` | `email`, `marc@exemple.fr` | par où, vers quelle adresse |
| `kind` | `first`, `reply`, `followup` | premier message, réponse, relance |
| `subject`, `body` | « Votre devis » | le texte |
| `status` | `to_write`, `pending`, `sending`, `sent`, `failed`, `cancelled` | voir partie 6 |
| `reply_to` | `ie_45` | le message reçu auquel il répond |
| `followup_of` | `t_7` | l'envoi qu'il relance |
| `thread_ref` | `<abc@serge>` | le fil d'e-mail (l'identifiant du message) |
| `external_ref` | `18c2f…` | la référence rendue par l'adaptateur |
| `sent_at` | | quand il est parti |

**`inbound_events` : ce que Serge reçoit.** Une ligne par message reçu
(un e-mail, un appel avec son résumé), avec en plus : `address`
(l'expéditeur), `subject`, `body`, `thread_ref` (à quel message il
répond), `external_ref` (sa référence chez le fournisseur : un même
message n'est jamais écrit deux fois), `status` (`attached` ou
`unattached`), `reaction` (remplie par « Traiter une réponse ») et
`venture_id`.

**Le rattachement** d'un message reçu à son contact se fait au moment de
la relève, dans le code de la capacité, dans cet ordre :

1. par le fil : il répond à un message que Serge a envoyé (son
   `thread_ref` désigne un envoi connu) ;
2. par l'adresse : l'expéditeur est une adresse connue sur ce canal. Si
   plusieurs fiches ont cette adresse (une personne contactée pour deux
   business), on prend celle à qui Serge a écrit le plus récemment.

Sinon le message est écrit `unattached` : il n'est pas traité, et il
apparaît dans Mission Control, dans « Messages non rattachés » (Q37, Q79).

Exemple : Marc répond à « Votre devis » depuis l'adresse d'un collègue. Le
message est rattaché à Marc par le fil, pas par l'adresse.

---

## 3. Des réglages de plus pour le pipeline en base

Pour que le circuit des conversations soit décrit en base, l'interpréteur
apprend cinq réglages, utiles à n'importe quelle invocation :

1. **Une condition sur un lien ou une écriture** : `condition_field`,
   `condition_op` (`=`, `!=`, `non_vide`) et `condition_value` sur `links`
   et `invocation_writes`. Exemple : le lien vers « Désinscrire » ne passe
   que si `reaction` = `désinscription` ; l'écriture de la réponse ne se
   fait que si `reply` est non vide. Le champ est lu dans la réponse de
   l'invocation (lien `on_finish`, écriture simple) ou dans la ligne écrite
   (lien `per_row`, écriture par élément).
2. **Un délai sur un lien** : `delay_min_setting` et `delay_max_setting`,
   deux réglages de la policy, entre lesquels un délai est tiré au hasard
   pour la tâche suivante (« pas avant »). Le nom peut contenir le canal de
   la ligne : `channels.{channel}.reply_delay_min_minutes`. Un délai de 0
   fait partir tout de suite.
3. **Une seule tâche en attente par contact** :
   `invocations.single_pending_param` (`contact_id`). Si une tâche de cette
   invocation attend déjà pour ce contact, aucune autre n'est créée : deux
   messages coup sur coup ne créent qu'une réponse, qui lit tout le fil.
4. **Annuler des tâches selon une autre colonne** : la règle d'annulation
   du lot 7 (`task_cancel_rules`) compare un paramètre des tâches au numéro
   de la ligne ; elle apprend `row_column`, la colonne de la ligne à
   comparer. Exemple : un message reçu (`inbound_events` passé à
   `attached`) annule les tâches en attente dont `contact_id` est le sien :
   une relance prévue ne part pas.
5. **Une capacité qui agit hors de Serge** : `capabilities.acts_outside`
   (1 pour envoyer). C'est ce qui l'autorise à enregistrer en cours de tâche
   (partie 6). Mission Control l'affiche sur la fiche de la capacité.

---

## 4. Un message reçu réveille le pipeline

Deux façons de recevoir, un seul résultat : une ligne écrite dans
`inbound_events`, qui lance les déclencheurs « une ligne est écrite ».

- **Par relève** (l'e-mail) : l'invocation « Relever les messages » (sans
  LLM) tourne toutes les 2 minutes pour chaque canal qui a une fonction
  `poll`. Elle écrit les nouveaux messages par ses règles d'écriture,
  comme n'importe quelle invocation : les déclencheurs partent tout seuls.
- **En direct** (un appel reçu, plus tard un SMS) : le programme qui reçoit
  écrit la ligne, puis appelle `notify_rows_written`, la même fonction que
  l'interpréteur utilise après une écriture.

Le déclencheur « un message rattaché est écrit » lance « Traiter une
réponse » avec le contact et le message.

---

## 5. Les invocations du circuit

Elles sont transverses (sans étape), dans la file des conversations.

| Invocation | Sorte | Ce qui la lance | Ce qu'elle fait |
|---|---|---|---|
| Relever les messages | sans LLM | toutes les 2 min, une tâche par canal qui relève | écrit les messages reçus, rattachés ou non |
| Traiter une réponse | LLM, niveau moyen | un message rattaché écrit ; une seule tâche en attente par contact | rend la réaction, la réponse, les demandes sur le produit |
| Envoyer un message | sans LLM, agit hors de Serge | un envoi `pending` écrit (délai du canal pour une réponse) | envoie par l'adaptateur du canal, confirme |
| Préparer les relances | sans LLM | toutes les 15 min | écrit une relance à rédiger pour chaque contact dû (partie 7) |
| Écrire une relance | LLM, niveau moyen | une relance à rédiger écrite | rédige son texte |
| Désinscrire | sans LLM | lien « réaction = désinscription » | bloque partout (partie 8) |
| Prévenir Julien et Clem | sans LLM | lien depuis « Désinscrire » | ouvre un ticket d'information |

**« Traiter une réponse »** reçoit d'office le fil du contact, sa fiche,
la fiche du business et la fiche produit. Sa réponse :

- `reaction`, dans une liste fermée : `intéressé`, `question`,
  `objection`, `rendez-vous`, `refus`, `désinscription`, `absence`,
  `hors sujet` ;
- `reply` : le texte à envoyer, ou vide pour ne rien répondre
  (désinscription, absence, hors sujet) ;
- `requests` : les demandes sur le produit (`bug`, `insatisfaction`,
  `idée`), rangées dans `customer_requests`.

Ses écritures : la réaction sur le message reçu ; un envoi `pending` de
sorte `reply` si `reply` est non vide ; l'état du contact (`intéressé`,
`refus`) ; les demandes. Son prompt contient les consignes de prudence :
ne jamais promettre une date ou une fonctionnalité absente de la fiche
produit (une fonctionnalité manquante devient une demande `idée`) ; en cas
de doute, répondre sans s'engager.

Exemple : Marc écrit « Ça marche avec Excel ? ». « Traiter une réponse »
rend `question`, une réponse tirée de la fiche produit, et rien d'autre.
L'envoi est écrit `pending` ; « Envoyer un message » part entre 5 et
20 minutes plus tard (0 pour les tests).

---

## 6. Ne jamais agir deux fois

Un envoi est écrit dans `touches` avant de partir. « Envoyer un message »
fait ensuite, pour cet envoi :

1. déjà `sent` : rien ;
2. `sending` (le programme s'est arrêté pendant un envoi) : il demande à
   l'adaptateur `confirm`. Parti : il le marque `sent`. Pas parti : il
   l'envoie ;
3. sinon : les garde-fous (adresse bloquée, accord exigé pour l'appel,
   plafond de 4 contacts en 30 jours), puis `sending` **enregistré en
   base**, l'envoi, puis `sent` et sa référence **enregistrés**.

C'est la seule capacité qui enregistre en cours de tâche
(`acts_outside`). Il n'y a pas de bouton dans Mission Control : on fait
confiance à la confirmation du canal (Q79).

---

## 7. Les relances

Les relances ne dépendent d'aucun canal ; elles partent sur le canal du
premier message. Leurs réglages sont dans la policy (famille « Relances ») :
`followups.delays_minutes` (4320, 10080 : 3 jours après le premier message,
puis 7 jours après la première relance), dont la longueur donne le nombre
maximum de relances.

« Préparer les relances » cherche les contacts dont :

- le dernier événement du fil est un envoi `first` ou `followup` parti ;
- aucun message n'est arrivé depuis ;
- le délai de la prochaine relance est passé ;
- le nombre de relances déjà faites est sous le maximum ;
- le contact n'a ni refusé, ni demandé à ne plus être contacté ;
- les messages de ce canal ont été relevés depuis moins de
  `max_poll_age_minutes` (60) : on ne relance jamais à l'aveugle (Q37).

Pour chacun, elle écrit un envoi `followup` au statut `to_write`.
« Écrire une relance » en rédige le texte et le passe `pending`.
« Envoyer un message » refait le contrôle au moment de partir : si un
message est arrivé depuis, la relance est annulée (Q37). Un message reçu
annule aussi les relances en attente (partie 3, réglage 4).

---

## 8. La désinscription vaut partout

Quand « Traiter une réponse » rend `désinscription` (« ne me contactez
plus », « STOP ») :

1. Serge ne répond rien ;
2. « Désinscrire » met toutes les adresses de la personne dans la liste de
   blocage, pour tous les canaux ; toutes ses fiches, dans tous les
   business, passent `désinscrit` ; ses envois en attente sont annulés ;
3. « Prévenir Julien et Clem » ouvre un ticket d'information, visible dans
   Mission Control (Décisions) et sur Discord, pour qu'ils voient ce qui se
   passe et débloquent un cas rare.

Chaque e-mail finit par une phrase réglable dans les textes de la page
Pipeline : « Répondez STOP pour ne plus être contacté ».

---

## 9. La fiche produit et les demandes

- `product_sheets` : une fiche par business. Ce que fait le produit et
  pour qui, ce qu'il ne fait pas, le prix, les délais habituels, comment on
  l'utilise.
- `product_faq` : les questions fréquentes et leurs réponses.
- `customer_requests` : les demandes sur le produit (`bug`,
  `insatisfaction`, `idée`), avec le contact et le message d'où elles
  viennent.

Elles ont leur vue (`table_views`), comme les contacts, leurs adresses,
les envois et les messages reçus. La fiche produit est écrite par
l'invocation qui conçoit le produit (lot 10) ; la PR 4 en met une
demi-fiche pour les tests.

Les événements de ces tables nomment la ligne concernée : « Lire
l'historique » d'un contact montre tout son fil.

---

## 10. PR 2 — Le canal e-mail

L'adaptateur e-mail utilise Gmail par l'outil `gog`, comme sur le serveur
de Julien, ou une boîte SMTP/IMAP (`serge/channels/email_gog.py`,
`email_smtp.py`). Il ajoute à chaque envoi un `Message-ID` choisi par
Serge, qui sert à rattacher les réponses et à confirmer un envoi. La
réponse garde l'objet (« Re: … ») et les en-têtes du fil. La relève
(`poll`) lit les messages reçus depuis la dernière relève.

## 11. PR 3 — Le canal appel

L'adaptateur appel passe par le pont téléphonique existant
(`serge/voice/bridge.py`). Un appel sortant a pour « message » le but de
l'appel ; l'agent vocal reçoit au décrochage la fiche du contact, son fil,
la fiche du business et la fiche produit, avec son prompt, son modèle et
ses outils réglés en base comme une invocation. Après l'appel, son résultat
(joint ou non, durée, résumé) est écrit dans le fil, ce qui réveille
« Traiter une réponse ». Un appel reçu cherche le numéro en base (TODO,
lot 8, PR 3). Un appel de test vers un numéro qui a donné son accord part
à toute heure ; un appel de prospection reste dans les heures légales.

## 12. PR 4 — Le kit de test

Une demi-fiche produit et un business bidon, des invocations temporaires
« Écrire le premier message » et « Faire le premier appel », et un bouton
« Lancer un essai » dans Mission Control : Clem y tape ses coordonnées, qui
restent en base (le dépôt est public). Le bouton enregistre son accord pour
l'appel de test. Les délais de réponse se mettent à 0 dans la policy pour
une réponse immédiate.
