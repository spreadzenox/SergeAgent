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

- `send(message)` envoie un message à une adresse et rend sa référence :
  pour l'e-mail, son `Message-ID`, qu'une réponse cite ;
- `poll(depuis)` rend les messages reçus depuis une date, chacun avec son
  expéditeur, son texte, et à quel message il répond (pour l'e-mail, les
  en-têtes `In-Reply-To` et `References`). Un canal qui reçoit en direct
  (le téléphone) n'en a pas : son programme écrit lui-même chaque appel
  reçu (partie 4) ;
- `confirm(message)` dit si un envoi est vraiment parti (sa référence, ou
  rien) : l'e-mail est cherché dans les messages envoyés, l'appel dans son
  journal.

Les adaptateurs sont rangés dans `serge/channels/`, un fichier par canal,
et déclarés dans une seule liste (`ADAPTERS`, `serge/channels/adapters.py`).
Ils ne savent rien d'une invocation ni d'un business : ils transportent un
message.

**En base, une ligne de `canaux`** par canal : son titre, sa description,
et en plus, au lot 8 :

- `address_channel` : la sorte d'adresse qu'il utilise dans
  `contact_addresses` (`email` pour l'e-mail, `phone` pour l'appel) ;
- `connected` : 1 si son adaptateur existe dans le code et que le canal
  est configuré sur ce serveur (rempli au démarrage, comme les
  capacités). Exemple : sans boîte Gmail ni SMTP/IMAP dans le fichier
  d'instance, l'e-mail n'est pas branché ;
- `polls` : 1 s'il se relève (son adaptateur a une fonction `poll`) ;
- `polled_at` : la dernière relève réussie (vide pour un canal qui reçoit
  en direct).

**Ses réglages sont dans la policy** (famille « Canaux » de la page
Policy), un groupe par canal. Exemple pour l'e-mail :
`channels.email.reply_delay_min_minutes` (5), `reply_delay_max_minutes`
(20), `max_poll_age_minutes` (60) et `max_per_day` (40 e-mails au plus par
jour ; au-delà, ils attendent le lendemain).

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
| `external_ref` | `<s1@mail.gmail.com>` | la référence rendue par l'adaptateur (pour l'e-mail, son Message-ID) |
| `sent_at` | | quand il est parti |
| `last_error` | `BLOCKLISTED` | pourquoi il a été annulé, ou n'est pas parti |

**`inbound_events` : ce que Serge reçoit.** Une ligne par message reçu
(un e-mail, un appel avec son résumé), avec en plus : `address`
(l'expéditeur), `subject`, `body`, `message_ref` (sa référence, pour lui
répondre dans le même fil), `external_ref` (sa référence chez le
fournisseur : un même message n'est jamais écrit deux fois), `status`
(`attached`, `unattached`, ou `ignored` pour une réponse automatique
d'absence, qui n'arrête pas les relances), `reaction` (remplie par
« Traiter une réponse ») et `venture_id`.

**Le rattachement** d'un message reçu à son contact se fait au moment de
la relève, dans le code de la capacité, dans cet ordre :

1. par le fil : il répond à un message que Serge a envoyé (une des
   références qu'il cite est l'`external_ref` d'un envoi) ;
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
apprend quatre réglages, utiles à n'importe quelle invocation :

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
4. **Une capacité qui agit hors de Serge** : `capabilities.acts_outside`
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

Ses écritures, chacune avec sa condition : la réaction sur le message
reçu ; `ignored` sur le message si c'est une absence ; un envoi `pending`
de sorte `reply` si `reply` est non vide ; l'étape du contact (question ou
objection : `ENGAGED` ; intéressé : `INTENT` ; rendez-vous : `MEETING` ;
refus : `REJECTED` ; elle n'avance que dans un sens) ; les demandes. Son
prompt contient les consignes de prudence :
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

1. déjà `sent` ou `cancelled` : rien ;
2. `sending` (le programme s'est arrêté pendant un envoi) : il demande à
   l'adaptateur `confirm`. Parti : il le marque `sent`. Pas parti : il
   l'envoie ;
3. un envoi devenu inutile est annulé (`cancelled`, avec sa raison) : le
   contact s'est désinscrit ; un premier message ou une relance à un
   contact à une étape où Serge n'écrit plus de lui-même (une liste
   réglable sur la page Policy, famille « Contacts » : refus, client,
   injoignable… ; décision Q82) ; une réponse ou une
   relance alors que le contact a écrit depuis qu'elle a été écrite
   (« Traiter une réponse » répond alors à tout le fil ; une absence ne
   compte pas) ; une réponse alors qu'une réponse plus récente est écrite
   (deux messages coup sur coup pendant qu'elle s'écrivait) ;
4. sinon : les garde-fous (canal connu, adresse bloquée, accord exigé
   pour l'appel, plafond de 4 prises de contact en 30 jours, qui ne compte
   que les premiers messages et les relances, pas les réponses) ; un envoi
   refusé est annulé avec sa raison. Puis `sending` **enregistré en
   base**, l'envoi, puis `sent` et sa référence **enregistrés**. Un canal
   qui refuse le message le passe `failed`.

C'est la seule capacité qui enregistre en cours de tâche
(`acts_outside`). Il n'y a pas de bouton dans Mission Control : on fait
confiance à la confirmation du canal (Q79).

---

## 7. Les relances

Les relances ne dépendent d'aucun canal ; elles partent sur le canal du
premier message, dans le même fil. Leurs réglages sont ceux de
l'invocation « Préparer les relances », sur la page Policy : 4320 minutes
(3 jours) avant la première, 10080 (7 jours) entre deux relances, deux au
plus.

« Préparer les relances » cherche les contacts dont :

- le dernier événement du fil est un envoi `first` ou `followup` parti ;
- aucun message n'est arrivé depuis (une absence ne compte pas) ;
- le délai de la prochaine relance est passé ;
- le nombre de relances déjà faites est sous le maximum ;
- le contact n'est pas à une étape où Serge n'écrit plus de lui-même
  (la même liste, page Policy) ;
- les messages de ce canal ont été relevés depuis moins de
  `max_poll_age_minutes` (60) : on ne relance jamais à l'aveugle (Q37).

Pour chacun, elle écrit un envoi `followup` au statut `to_write`.
« Écrire une relance » en rédige le texte et le passe `pending`.
« Envoyer un message » refait le contrôle au moment de partir : si un
message est arrivé depuis, la relance est annulée (Q37, partie 6).

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

Chaque e-mail finira par une phrase réglable dans les textes de la page
Pipeline : « Répondez STOP pour ne plus être contacté » (PR 2).

---

## 9. La fiche produit et les demandes

- `product_sheets` : une fiche par business. Ce que fait le produit et
  pour qui, ce qu'il ne fait pas, le prix, les délais habituels, comment on
  l'utilise.
- `product_faq` : les questions fréquentes et leurs réponses.
- `customer_requests` : les demandes sur le produit (`bug`,
  `insatisfaction`, `idée`), avec le contact et le message d'où elles
  viennent.

Elles ont leur vue (`table_views`), comme les contacts, les envois et les
messages reçus. La fiche produit est écrite par l'invocation qui conçoit
le produit (lot 10) ; la PR 4 en met une demi-fiche pour les tests.

Le fil d'un contact se lit avec la capacité « Lire le fil d'un contact »,
donnée d'office à « Traiter une réponse » et « Écrire une relance ».

---

## 10. PR 2 — Le canal e-mail

L'adaptateur e-mail (`serge/channels/mail.py`) passe par Gmail avec
l'outil `gog`, comme sur le serveur de Julien (`email_gog.py`), ou par une
boîte SMTP/IMAP (`email_smtp.py`). Le fichier d'instance dit laquelle :
`features.mailbox` (choisie d'abord) ou `features.gmail` ; sans l'une ni
l'autre, le canal n'est pas branché.

- **Envoyer.** Une réponse ou une relance reste dans le fil : Gmail par
  `--reply-to-message-id`, SMTP par les en-têtes `In-Reply-To` et
  `References`. L'adaptateur rend le `Message-ID` du message parti :
  Gmail le choisit lui-même, il est relu après l'envoi ; en SMTP, Serge le
  tire du numéro de l'envoi (`<serge.tou_3f2a@exemple.fr>`).
- **Confirmer un envoi interrompu.** Gmail : un message envoyé au même
  destinataire depuis moins de 2 jours, qui commence par le même texte.
  SMTP : le `Message-ID` cherché dans le dossier des envoyés, où Serge
  range une copie de chaque message (le serveur SMTP ne le fait pas).
- **Relever.** Les messages reçus depuis la dernière relève (Gmail relit
  les 10 dernières minutes, IMAP la veille : un message déjà relevé est
  écarté). Un message est rendu sans la citation du message auquel il
  répond.
- **Refus et pannes.** Un destinataire refusé : l'envoi passe en échec.
  Une panne (réseau, accès) : l'envoi reste « en cours », et la tâche
  relancée demandera à la boîte s'il est parti.
- **La phrase de fin.** Chaque e-mail finit par un texte de la page
  Pipeline (« Pour ne plus recevoir de message de Serge, répondez
  STOP. »), qui n'entre pas dans le fil.

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
