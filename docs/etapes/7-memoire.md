# Étape 7 — Mémoire

Identifiant : `collect_feedback`.

**Rôle.** Tirer des leçons de ce qui s'est passé, pour que Serge ne refasse
pas deux fois la même erreur.

**Entrée.** Le journal (`events`) depuis la dernière consolidation.

**Sortie.** Des leçons, des procédures qui marchent et des pièges à éviter,
validés par Julien.

Le fonctionnement général de la mémoire est dans
[`MEMOIRE.md`](../MEMOIRE.md).

---

## Aujourd'hui

- **La consolidation est débranchée** depuis le lot 6. Son code
  (l'invocation « Consolider la mémoire », qui lisait le journal tous les
  3 jours et proposait des leçons, des procédures et des pièges dans un
  ticket « Mémoire ») est rangé dans `pas_encore_branche/`. Elle reviendra
  décrite en base : un déclencheur régulier, une invocation qui lit le
  journal, et une règle d'écriture qui ajoute des leçons « proposées »,
  que Julien garde ou jette (voir « Plus tard » dans le
  [`TODO.md`](../../TODO.md)).
- La page Mémoire de Mission Control montre toujours les leçons existantes
  et les derniers événements de consolidation.
- `SERGE.md` (un résumé de Serge réécrit à chaque consolidation) a été
  supprimé.

---

## Décidé

- Une **leçon obligatoire** chaque fois qu'un business passe en `KILLED`
  ou en `CLOSED` : pourquoi il a échoué, ou pourquoi il s'est arrêté.
- Chaque leçon est rattachée **au niveau le plus précis possible** :
  - une invocation (exemple : « Trouver des prospects : les annuaires de la
    CCI donnent des adresses qui rebondissent 3 fois moins que les pages
    contact ») ;
  - sinon une étape (exemple : « Étape 3 : les artisans répondent surtout
    entre 7 h et 8 h ») ;
  - sinon tout Serge.
- Une invocation reçoit **d'office ses propres leçons**, les plus fiables
  d'abord. Les leçons de son étape et de tout Serge sont disponibles sur
  demande.
