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

- **La consolidation tourne tous les 3 jours**
  (`serge/memory/consolidate.py`). L'invocation « Consolider la mémoire »
  (`consolidate`) lit le journal de la période et propose des leçons, des
  procédures et des pièges. Julien reçoit un ticket « Mémoire » pour
  garder, modifier ou jeter chaque proposition. Sans réponse sous 48 h,
  tout est accepté.
- Jusqu'à fin septembre 2026, la consolidation ne s'exécutait jamais : la
  tâche n'était rattachée à aucune venture et l'ordonnanceur l'ignorait.
  C'est corrigé.
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
