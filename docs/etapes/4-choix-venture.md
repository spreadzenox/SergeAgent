# Étape 4 — Choix du business principal

Identifiant : `choix_venture`.

**Rôle.** Quand les 3 tests légers sont finis, choisir le meilleur business
pour en faire le business principal de Serge.

**Entrée.** 3 business au statut `SMOKE_DONE`, avec leurs points, leurs
points par euro et le détail des réponses des prospects. Plus, s'il y en a,
les business `PARKED` testés il y a moins de 60 jours.

**Sortie.** Un business principal, qui passe à l'étape 5. Les autres
passent en `PARKED`.

---

## Aujourd'hui

**Rien n'est branché.**

- Trois invocations sont écrites mais jamais appelées : « Raconter
  l'essai » (`resume_test`), « Écrire l'idée (après essai) »
  (`draft_hypothesis_full`) et « Trois autres idées » (`options_pivot`).
- L'invocation technique « Choisir une pré-venture »
  (`select_pre_venture`) est décrite au catalogue, sans code.
- Le code impose une seule venture active à la fois
  (`serge/funnels/lifecycle.py`).

---

## Décidé

1. **Déclenchement** : seulement quand les 3 business en prospection
   légère ont tous fini leur test, et que la place de prospection lourde
   est libre.
2. **Une invocation LLM propose un choix motivé.** Elle reçoit, pour chaque
   business : le total de points, les points par euro, et le détail des
   signaux et des réponses.
3. **Julien valide ou change** dans un ticket Discord où l'on peut
   discuter. Sans réponse sous 48 h, le choix proposé s'applique.
4. **Les autres passent en `PARKED`.** Ils libèrent leur place : l'étape 1
   peut repartir. Les dates de début et de fin de leur test léger restent
   sur leur fiche.
5. **Quand le business principal passe en `MAINTENANCE`**, la place se
   libère. Le choix suivant compare aussi les business `PARKED` testés il
   y a moins de 60 jours (réglage de la policy). Un business `PARKED` plus
   ancien repasse en `CANDIDATE`.
6. Si les tests légers ne sont pas tous finis, la place reste vide jusqu'à
   ce qu'ils le soient.
