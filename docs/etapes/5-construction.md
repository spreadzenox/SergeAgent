# Étape 5 — Construction

Identifiant : `build_venture`.

**Rôle.** Transformer le livrable d'essai du business principal en vrai
produit, le mettre en ligne sur un domaine dédié et brancher le paiement.

**Entrée.** Le business principal choisi à l'étape 4, avec son livrable
d'essai, son plan de POC et les retours des prospects.

**Sortie.** Un produit en ligne, vendable, avec un paiement vérifié.

---

## Aujourd'hui

**Écrit mais pas branché**, et rangé dans `pas_encore_branche/` depuis le
lot 6 (`serge/points/build.py`, `serge/points/review.py`) :

- « Construire un livrable » : à partir d'une description, elle produit des
  fichiers (page d'atterrissage, document, script, modèle). Le code
  vérifiait ensuite qu'il n'y a ni secret, ni traceur non déclaré, ni prix
  inventé.
- « Relire un livrable » : une invocation distincte, qui regarde des
  captures d'écran du rendu sur ordinateur et sur mobile. Elle répond « on
  publie », « à corriger (5 points maximum) » ou « à refaire ». 3 passages
  au maximum.
- « Résumer la dette builder » : liste ce qui a été publié avec des
  défauts connus.

La table `artifacts` existe pour ranger les livrables, mais rien ne
l'utilise. Aucune mise en ligne, aucune capture d'écran n'est codée.

---

## Décidé

Seulement des produits web, payants : on paie pour avoir un compte et
utiliser le service (Q91). Le détail technique (le chantier, l'interface
web, la mise en ligne, Stripe, les tables) est dans
[`LOT10_CONCEPTION.md`](../LOT10_CONCEPTION.md).

### Le déroulé

1. **Concevoir le produit** (invocation LLM). Elle part du livrable
   d'essai, du plan du POC et de ce que les prospects ont dit : toutes les
   demandes des clients du business (`customer_requests`), qu'elle marque
   retenues ou refusées avec leur raison, leurs objections et leurs
   questions. Elle écrit
   le plan du vrai produit : ce qu'on ajoute, ce qu'on corrige, le prix
   définitif, la page de vente. Elle écrit aussi la **fiche produit** :
   ce que fait le produit et pour qui, ce qu'il ne fait pas, le prix, les
   délais habituels de livraison, comment on l'utilise, et les questions
   fréquentes. C'est cette fiche que lira l'invocation qui répond aux
   clients.
2. **Challenger le produit** : même boucle qu'à l'étape 2 (3 tours,
   remarques « à corriger » ou « nouvelle capacité nécessaire »).
3. **Ticket Discord pour Julien** avant de construire. Julien valide
   notamment **le prix définitif**, la fiche produit et le nom de domaine ;
   il y en aura peu, donc c'est une relecture rapide. Ce ticket n'expire
   jamais (Q91).
4. **Construire** avec un duo de deux invocations du niveau de modèle
   « code » (Q91). Le constructeur écrit et lance le produit dans un
   chantier (un conteneur), et l'essaie dans un navigateur. Le relecteur
   ne voit jamais le code : il suit les scénarios de test comme un
   prospect ordinaire, sur ordinateur et sur mobile, garde ses captures
   comme preuves, et répond « bon », « à corriger » ou « nouvelle capacité
   nécessaire ». Trois passages au plus. Chaque version est mise en ligne
   en staging, avec Stripe en mode test. La même mécanique sert aux
   étapes 2 et 5.
5. **Ticket de test** (Q91) : un humain essaie le produit fini depuis le
   lien du staging, avant la prospection lourde. Le ticket n'expire
   jamais.
6. **Mettre en ligne** sur un nom de domaine dédié (exemple :
   `devisvocal.fr`), acheté par Serge seul une fois son nom validé dans le
   ticket du plan (Q91), avec le produit et son prix créés dans Stripe par
   l'outil « Créer un prix Stripe », qui inscrit l'identifiant du business
   sur le prix (Q76).
7. **Vérifier l'encaissement** : Serge fait seul, avec sa carte, un
   paiement test de 1 €, vérifie qu'il est rattaché au business, puis se
   rembourse (Q91). Le business passe ensuite à l'étape 6.

Les **versions suivantes** (corrections, améliorations) passent par la
même boucle en staging, et sont publiées en prod automatiquement dès que
la relecture est bonne, avec un ticket d'information. À chaque nouvelle
version, la fiche produit est mise à jour, pour que Serge ne réponde
jamais aux clients sur une ancienne version.

### Mise en ligne

- Par défaut sur le VPS de Serge, via **Caddy**, qui publie déjà Mission
  Control. Chaque produit tourne dans son propre conteneur, avec ses
  propres données, sans accès à la base de Serge (Q91). Le staging est
  sur `staging-<business>.<domaine de Serge>` ; en prod, le POC utilise
  un sous-domaine du domaine de Serge, le business principal son propre
  domaine.
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
