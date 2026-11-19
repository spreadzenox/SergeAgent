# Étape 3 — Prospection légère

Identifiant : `prospection_light`.

**Rôle.** Tester un business auprès d'une quarantaine de vrais prospects :
les trouver, leur écrire ou les appeler, relancer, répondre, et noter leurs
réactions.

**Entrée.** Une campagne de test créée à l'étape 2, avec son plan.

**Sortie.** Les réactions des prospects, notées en points (voir la grille
de points dans [`PIPELINE.md`](../PIPELINE.md)). Un test retenu se termine
au statut `SMOKE_DONE` ; un test sous les seuils, à `KILLED`.

---

## Aujourd'hui

**L'étape est en base depuis le lot 12** (16 novembre 2026), par e-mail et
par appel, et depuis le lot 13 par LinkedIn, Instagram et X, avec le
compte de Serge sur chaque réseau (décision Q104). Le détail est dans
[`LOT12_CONCEPTION.md`](../LOT12_CONCEPTION.md), parties 3 à 5, et 17
pour les canaux du navigateur.

1. **Démarrer une campagne**, dès qu'elle est prête (le POC est en
   ligne) : son volume vient des réglages de son canal (40 prospects par
   e-mail), sa fin prévue du plan (30 jours au plus). Une campagne sur un
   canal qui n'est pas branché ne démarre pas. **Le téléphone ne sert pas
   à prospecter des inconnus** : ce canal demande l'accord de la personne
   avant tout appel (page Policy, « Accord des gens »).
2. **Trouver des prospects** : une personne nommée, son rôle, son adresse
   directe et la page où elle a été trouvée. Son outil « Ajouter un
   prospect » vérifie tout de suite et dit pourquoi il refuse : adresse
   générique (`contact@`, `info@`…), domaine qui ne reçoit pas d'e-mails,
   adresse qui n'est pas un profil du réseau de la campagne, personne
   déjà contactée ou désinscrite. Au plus 10 prospects par passage. Pour
   LinkedIn, Instagram ou X, elle peut fouiller le réseau lui-même, au
   plus 2 fois par réseau (« Fouiller LinkedIn »…).
3. **Rédiger un premier message**, par le canal de la campagne : « Écrire
   le premier e-mail », « Préparer le premier appel » ou « Écrire le
   premier message d'un réseau » (280 caractères pour une note LinkedIn),
   puis « Envoyer un message ». Sur un réseau, le message attend d'abord
   la validation d'un humain (réglage du canal), puis part par le
   navigateur. Les relances et les réponses sont celles des lots 8 et
   8 bis.
4. **Suivre une campagne**, toutes les heures : la clore (elle a son
   compte et rien n'est parti depuis 8 jours, ou sa durée est atteinte, ou
   elle ne trouve plus de prospects), lui chercher des prospects s'il lui
   en manque, ou attendre.
5. **Mesurer le test**, quand sa dernière campagne est close : le compte
   rendu chiffré, et le verdict avec des seuils en chiffres absolus
   (30 prospects contactés, 10 points). **Faire le bilan**, puis
   **conclure** : le business retenu passe à `SMOKE_DONE` ; l'autre est
   arrêté (`KILLED`), libère sa place et donne une leçon (« Tirer la leçon
   d'un business arrêté »).

**Ranger les prospects** (`serge/funnels/contacts.py`) : une fiche par
personne dans un business, une ligne par adresse ; une nouvelle adresse
s'ajoute à côté des anciennes, rien n'est écrasé, et Serge ne fusionne
jamais deux personnes tout seul.

---

## Décidé

### Trouver les prospects

**« Trouver des prospects »** est une seule invocation LLM avec recherche
web. Elle cherche **et** qualifie. Exemple de sources : sites
d'entreprises, annuaires professionnels, fiches Google Maps.

- Elle vise des prospects **pertinents** et des adresses qui **ne
  rebondissent pas**. **Jamais d'adresse générique** (`contact@`,
  `info@`…) : une personne nommée, avec son rôle et son adresse directe.
  Un contact précis paie toujours, et beaucoup se trouvent en ligne (Q93).
- Elle enregistre pour chaque adresse la page où elle l'a trouvée.
- Sa sortie exacte (champs, format) reste à définir.
- Elle ne sert qu'aux canaux qui ont besoin d'une liste de personnes
  (e-mail, appel, LinkedIn). Une campagne de pub a besoin d'un **profil de
  cible**, pas de prospects.

**Règle légale.** E-mails et appels à froid seulement vers des
**professionnels** (adresse professionnelle, offre liée à leur métier, lien
de désinscription). Vers un particulier, il faut son accord préalable : on
passe alors par la pub, le contenu ou les réseaux sociaux.

### Envois et relances : un système réactif

Le but numéro un : **ne jamais relancer quelqu'un qui a déjà répondu.**

1. **Un fil de discussion par prospect**, tous canaux confondus : ce que
   Serge a envoyé (avec le texte) et ce que la personne a répondu, par
   date. On le voit sur la fiche du prospect dans Mission Control.
2. **Chaque réponse est rattachée au bon prospect** : par son adresse
   e-mail ou son téléphone, et, pour l'e-mail, par le fil de messages. Une
   réponse impossible à rattacher part dans une file d'examen visible,
   jamais ignorée.
3. **Une relance ne part que si le dernier événement du fil est un envoi
   de Serge sans réponse depuis.** C'est vérifié au moment même de l'envoi.
   Sinon elle est annulée, et l'annulation est écrite dans le journal.
4. **Jamais de relance à l'aveugle.** Si les réponses d'un canal n'ont pas
   été relevées récemment (exemple : boîte mail non lue depuis plus d'une
   heure), aucune relance ne part sur ce canal, et Mission Control affiche
   une alerte.
5. **Le rythme** est un réglage commun à tous les business, sur la page
   Policy (Q92) : la première relance 3 jours après le premier message, la
   seconde 7 jours après, deux au plus.

### Les campagnes, du début à la fin

Le détail est dans [`LOT12_CONCEPTION.md`](../LOT12_CONCEPTION.md) : une
campagne démarre quand le POC est en ligne ; son nombre de prospects est
un réglage par canal (40 e-mails, 20 appels au départ, Q93) ; « Trouver
des prospects » cherche par paquets de 10, au rythme des envois ; le test
se termine au
plus tôt (relances parties depuis 7 jours, ou durée du plan, 30 jours au
plus) ; « Mesurer le test » le juge avec des seuils chiffrés, et un test
sous les seuils est arrêté, avec une leçon (Q92).

### Répondre aux prospects

Le circuit des réponses sert les étapes 3 et 6 : une seule invocation,
« Traiter une réponse », lit le fil du prospect avec la fiche du business
et la fiche produit, et répond après le délai réglé pour le canal. Les
appels entrants sont pris par un agent vocal qui cherche d'abord à qui il
parle. Tout est décrit dans
[`6-prospection-lourde.md`](6-prospection-lourde.md).

### LinkedIn

Serge utilise LinkedIn avec son propre compte, à un volume modéré (10
messages par jour au départ, et les actions du jour du compte). **Chaque
message est validé par un humain**, tant que le réglage du canal le
demande (page Policy, « Canaux » ; décision Q104). Serge n'y publie rien
pour le moment.
