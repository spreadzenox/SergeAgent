# Étape 3 — Prospection légère

Identifiant : `prospection_light`.

**Rôle.** Tester un business auprès d'une quarantaine de vrais prospects :
les trouver, leur écrire ou les appeler, relancer, répondre, et noter leurs
réactions.

**Entrée.** Une campagne de test créée à l'étape 2, avec son plan.

**Sortie.** Les réactions des prospects, notées en points (voir la grille
de points dans [`PIPELINE.md`](../PIPELINE.md)). Le test se termine au
statut `SMOKE_DONE`.

---

## Aujourd'hui

### Ce qui existe

- **Ranger les prospects** (`serge/funnels/contacts.py`). Une fiche par
  personne dans `contacts`, une ligne par adresse dans `contact_addresses`.
  Dans un même business :
  1. une adresse déjà connue désigne la même personne. Exemple :
     `ada@acme.fr` puis `ADA@acme.fr` ajoute à la fiche d'Ada, sans en
     créer une autre ;
  2. une boîte partagée (`contact@`, `info@`…) ne regroupe jamais ;
  3. ni le nom, ni un même pseudo sur deux réseaux ne regroupent ;
  4. une nouvelle adresse s'ajoute à côté des anciennes, rien n'est écrasé ;
  5. si les adresses désignent deux fiches différentes, rien n'est écrit :
     Serge ne fusionne jamais deux personnes tout seul.

  Ce code n'est pas encore une capacité du pipeline.
- **Le code d'envoi** (e-mail par Gog ou SMTP, garde-fous
  `serge/guards/check.py`, quota) et **le pont téléphonique**
  (`serge/voice/`, heures légales, consentement, mandat) existent. Ils
  deviendront des capacités au lot 8.

### Ce qui ne marche plus depuis le lot 6

L'envoi d'e-mails, les appels sortants et la relève de la boîte mail
étaient lancés par l'ancien runner, avec du code propre à chaque
invocation (« Remplir les créneaux », « Écrire une relance »). Ce code est
rangé dans `pas_encore_branche/` (`serge/workers/send.py`,
`serge/workers/call.py`, `serge/workers/poll.py`).

### Ce qui manque

- **Trouver des prospects.** L'ancienne invocation de découverte de
  contacts n'enregistrait que les contacts qu'on lui donnait, et personne
  ne l'appelait.
- **Lancer une campagne** et **relancer au bon moment** : rien ne
  programme les premiers envois ni les relances.

---

## Décidé

### Trouver les prospects

**« Trouver des prospects »** est une seule invocation LLM avec recherche
web. Elle cherche **et** qualifie. Exemple de sources : sites
d'entreprises, annuaires professionnels, fiches Google Maps.

- Elle vise des prospects **pertinents** et des adresses qui **ne
  rebondissent pas**. Pas d'adresses de contact génériques de mauvaise
  qualité.
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
5. **Le rythme** vient du plan du POC validé par Julien.

### Répondre aux prospects

Le circuit des réponses sert les étapes 3 et 6 : une seule invocation,
« Traiter une réponse », lit le fil du prospect avec la fiche du business
et la fiche produit, et répond après le délai réglé pour le canal. Les
appels entrants sont pris par un agent vocal qui cherche d'abord à qui il
parle. Tout est décrit dans
[`6-prospection-lourde.md`](6-prospection-lourde.md).

### LinkedIn

Serge utilise LinkedIn avec son propre compte, à un volume modéré. **Chaque
message et chaque publication est validé par Julien.**
