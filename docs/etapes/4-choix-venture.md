# Étape 4 — Choix du business principal

Identifiant : `choix_venture`.

**Rôle.** Quand plus aucun test léger ne tourne, choisir le meilleur
business pour en faire le business principal de Serge.

**Entrée.** Les business au statut `SMOKE_DONE` (leur test est retenu),
avec leurs points, leurs points par euro, leur bilan et le détail des
réponses des prospects. Plus, s'il y en a,
les business `PARKED` testés il y a moins de 60 jours.

**Sortie.** Un business principal, qui passe à l'étape 5. Les autres
passent en `PARKED`.

---

## Aujourd'hui

**L'étape est en base depuis le lot 12** (16 novembre 2026). Elle n'est
pas encore essayée sur le serveur : c'est le rôle de l'essai total (page
Système). Le détail est dans
[`LOT12_CONCEPTION.md`](../LOT12_CONCEPTION.md), partie 6.

1. **Choisir le business principal** part quand un test est retenu ou
   qu'un business est arrêté, si plus aucun test léger ne tourne, qu'un
   business retenu attend (`SMOKE_DONE`, ou `PARKED`) et que la place
   lourde est libre. Elle propose un business, ou aucun, avec une phrase
   par business.
2. **Le ticket « Choix du principal »** : « Valider », « Choisir un autre »
   (on écrit le nom du business voulu), « Aucun ». Sans réponse sous
   48 heures, la proposition s'applique.
3. **Appliquer le choix** : le business choisi passe à `PRODUCT_BUILDING`
   et son produit fini part en conception (étape 5) ; les autres tests
   retenus passent à `PARKED`.
4. **Oublier les vieux tests**, chaque jour : un business `PARKED` dont le
   test a fini il y a plus de 60 jours redevient `CANDIDATE`.

Trois invocations écrites mais jamais appelées restent rangées dans
`pas_encore_branche/` : « Raconter l'essai », « Écrire l'idée (après
essai) » et « Trois autres idées ».

---

## Décidé

1. **Déclenchement** : seulement quand aucun test léger ne tourne plus,
   et que la place de prospection lourde est libre. Un test sous les seuils
   chiffrés est arrêté (`KILLED`) et n'est pas comparé (Q92). Le détail
   est dans [`LOT12_CONCEPTION.md`](../LOT12_CONCEPTION.md), partie 6.
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
   y a moins de 60 jours (un réglage de l'invocation qui compare, modifiable
   sur la page Policy). Un business `PARKED` plus
   ancien repasse en `CANDIDATE`.
6. Si les tests légers ne sont pas tous finis, la place reste vide jusqu'à
   ce qu'ils le soient.
