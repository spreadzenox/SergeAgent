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

### Ce qui marche

- **Envoyer un e-mail** (`email.send`, `serge/workers/send.py`). Serge
  remplit le modèle avec l'invocation « Remplir les créneaux »
  (`fill_slots`), ou écrit une relance avec « Écrire une relance »
  (`write_followup`). Avant l'envoi, il vérifie les garde-fous
  (`serge/guards/check.py`) et le quota du jour, puis enregistre l'envoi
  dans `touches`.
- **Passer un appel** (`voice.send`, `serge/workers/call.py`). Seulement
  dans les heures légales, avec un consentement ou un contrat enregistré,
  et si le mandat l'autorise (`serge/voice/`).
- **Relever la boîte mail** toutes les 5 minutes. Les réponses sont
  traduites en signaux et traitées (voir l'étape 6, dont le circuit des
  réponses dépend encore aujourd'hui).

### Ce qui manque

- **Trouver des prospects.** L'invocation `discover_contacts` enregistre
  seulement des contacts qu'on lui donne ; elle ne cherche rien. Elle n'est
  appelée par personne.
- **Lancer une campagne.** Aucun code ne prend les prospects d'une
  campagne pour programmer les premiers envois. Un ancien « séquenceur »
  existait sur `main` sans être branché ; il a été supprimé.
- **Relancer au bon moment.** Rien ne programme les relances.
- « Départager deux pistes » (`score_lead_departage`) n'est appelée par
  personne.

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

Le circuit des réponses sert les étapes 3 et 6. Il est décrit dans
[`6-prospection-lourde.md`](6-prospection-lourde.md).

### LinkedIn

Serge utilise LinkedIn avec son propre compte, à un volume modéré. **Chaque
message et chaque publication est validé par Julien.**
