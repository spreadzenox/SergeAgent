# Étape 5 — Construction

Identifiant : `build_venture`.

**Rôle.** Transformer le livrable d'essai du business principal en vrai
produit, le mettre en ligne sur un domaine dédié et brancher le paiement.

**Entrée.** Le business principal choisi à l'étape 4, avec son livrable
d'essai, son plan de POC et les retours des prospects.

**Sortie.** Un produit en ligne, vendable, avec un paiement vérifié.

---

## Aujourd'hui

**Écrit mais pas branché.** Aucune de ces invocations n'est appelée :

- **« Construire un livrable »** (`build_artifact`,
  `serge/points/build.py`) : à partir d'une description, elle produit des
  fichiers (page d'atterrissage, document, script, modèle). Le code vérifie
  ensuite qu'il n'y a ni secret, ni traceur non déclaré, ni prix inventé.
- **« Relire un livrable »** (`review_build`, `serge/points/review.py`) :
  une invocation distincte, qui regarde des captures d'écran du rendu sur
  ordinateur et sur mobile. Elle répond « on publie », « à corriger
  (5 points maximum) » ou « à refaire ». 3 passages au maximum.
- **« Résumer la dette builder »** (`summarize_build_debt`) : liste ce qui
  a été publié avec des défauts connus.

La table `artifacts` existe pour ranger les livrables, mais rien ne
l'utilise. Aucune mise en ligne, aucune capture d'écran n'est codée.

---

## Décidé

### Le déroulé

1. **Concevoir le produit** (invocation LLM). Elle part du livrable
   d'essai, du plan du POC et de ce que les prospects ont dit. Elle écrit
   le plan du vrai produit : ce qu'on ajoute, ce qu'on corrige, le prix
   définitif, la page de vente.
2. **Challenger le produit** : même boucle qu'à l'étape 2 (3 tours,
   remarques « à corriger » ou « nouvelle capacité nécessaire »).
3. **Ticket Discord pour Julien** avant de construire. Julien valide
   notamment **le prix définitif**.
4. **Construire** avec le couple builder / reviewer ci-dessus. Les réponses
   du reviewer sont alignées sur la critique : « bon », « à corriger » ou
   « nouvelle capacité nécessaire ». La même mécanique sert aux étapes 2
   et 5.
5. **Mettre en ligne** sur un nom de domaine dédié, acheté avec la carte
   de Serge (exemple : `devisvocal.fr`).
6. **Brancher l'encaissement** : produit et prix créés dans Stripe, puis un
   paiement test de 1 € fait et remboursé automatiquement.
7. **Ticket d'information** (« produit en ligne, paiement vérifié »), puis
   passage à l'étape 6.

Les **versions suivantes** (corrections, améliorations) sont publiées
automatiquement dès que la relecture est bonne, avec un ticket
d'information.

### Mise en ligne

- Par défaut sur le VPS de Serge, via **Caddy**, qui publie déjà Mission
  Control. Le POC utilise un sous-domaine du domaine de Serge ; le
  business principal, son propre domaine.
- Une plateforme externe seulement quand le type de business l'exige
  (exemples : Chrome Web Store pour une extension, Telegram pour un bot).

### Stockage des fichiers

- Les fichiers sont rangés sur le disque du VPS, dans un seul dossier, par
  business, livrable et version. Exemple :
  `files/devis-artisan/generateur/v2/`.
- Une version publiée n'est jamais modifiée : une correction crée la
  version suivante.
- La table `artifacts` garde la fiche de chaque fichier : business, type,
  version, chemin, empreinte, taille, date, adresse publique.
- Pas de sauvegarde hors du VPS pour le moment.
