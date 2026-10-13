# Étape 5 — Construction

Identifiant : `build_venture`.

**Rôle.** Transformer le livrable d'essai du business principal en vrai
produit, le mettre en ligne sur un domaine dédié et brancher le paiement.

**Entrée.** Le business principal choisi à l'étape 4, avec son livrable
d'essai, son plan de POC et les retours des prospects.

**Sortie.** Un produit en ligne, vendable, avec un paiement vérifié.

---

## Aujourd'hui

**L'étape est en base depuis le lot 10 (PR 7, décision Q91).** Aucune
ligne de code ne lui est propre : ses invocations, ses liens et ses
tickets sont dans `config/pipeline.yaml` et `config/ticket-types.yaml`.
Elle reprend la mécanique de l'étape 2 (« Compter les tours », les
paramètres de lien tirés de la réponse, les trois boutons de ticket), et
s'appuie sur « Appeler une API » pour Stripe et Hostinger.

En attendant l'étape 4 (lot 11), elle part du bouton « Construire le vrai
produit » de la fiche d'un business au test léger (`SMOKE_READY` ou
`SMOKE_DONE`), qui le fait passer « en construction de son produit »
(`PRODUCT_BUILDING`), ou du bouton « Bout en bout : le produit fini d'une
calculatrice » de la page Système (plus bas).

1. **Concevoir le produit** (niveau intelligent) reçoit la fiche du
   business, le plan de son POC, la fiche produit, toutes les demandes de
   ses clients (`customer_requests`) et ce qu'ont répondu ses prospects.
   Elle écrit le plan du produit (`product_plans`, `kind` = `product`) :
   le prix définitif, le plan de A à Z (inscription, abonnement Stripe, ce
   que le compte débloque), les scénarios de test (l'un va jusqu'au
   paiement) et un nom de domaine libre (elle le vérifie chez Hostinger).
   Elle réécrit la fiche produit et ses questions fréquentes, et marque
   chaque demande des clients retenue ou refusée, avec sa raison.
2. **Challenger le produit** (niveau intelligent), 3 tours au plus.
3. **Le ticket « Plan »** (`PLAN_PRODUIT`) montre le plan, son prix, son
   domaine, la critique, la fiche produit et les demandes des clients. Il
   n'expire jamais.
4. **Vendre en mode test** (niveau moyen) : le produit et son prix dans
   Stripe en mode test. Le prix porte l'identifiant du business
   (`metadata[venture_id]`) et une clé de recherche (`lookup_key`) égale
   au numéro du business : le produit retrouve son prix par cette clé, en
   mode test comme en vrai mode, sans rien changer à son code.
5. **Construire le produit** (niveau « code ») : comptes, abonnement par
   une page de paiement Stripe, le service. Son chantier reçoit la clé du
   mode test (`STRIPE_SECRET_KEY`). Puis **publier en staging** (même
   clé), **relire** (niveau « code ») jusqu'au paiement avec la carte de
   test 4242 4242 4242 4242, comme à l'étape 2 : 3 reprises et
   3 passages au plus.
6. **Le ticket « Tester le produit »** (`TEST_PRODUIT`) : un humain essaie
   le staging, paiement compris. Il n'expire jamais.
7. **Acheter le domaine** (niveau intelligent), une fois le produit
   essayé et validé : chez Hostinger, s'il est libre et sous le prix
   maximum (30 € par an, la première année comme le renouvellement, page
   Policy), puis un enregistrement DNS vers le serveur. Sinon, le ticket
   « Domaine » (`DOMAINE_PRODUIT`) dit pourquoi et propose des noms libres
   ; « À corriger » avec un nom achète ce nom.
8. **Mettre en vente** (niveau moyen) : le produit et son prix dans
   Stripe en vrai mode, avec la même clé de recherche. Puis **publier en
   prod** sur le domaine, avec une clé Stripe restreinte du vrai mode
   (`stripe-produits-live.key`) : le produit n'a jamais la clé complète de
   Serge.
9. **Le paiement test de 1 €** (niveau « code ») : un prix de 1 € et un
   lien de paiement, payé dans le navigateur avec la carte de Serge
   (« taper un secret » : le modèle ne voit jamais ses numéros), vérifié
   dans Stripe (la session du lien est payée), remboursé ; le lien est
   désactivé et le prix archivé. Le paiement est noté dans `transactions`
   (`kind` = `canary`).
10. **Produit en vente** : le business passe à `PRODUCT_READY`, d'où
    part la prospection lourde (étape 6, lot 11), et un ticket
    d'information le dit. Une étape ratée
    (Stripe, la prod, le paiement test) ouvre un ticket d'information
    avec la raison.

La fiche du business, dans Mission Control, montre le plan du produit
avec son domaine, les demandes des clients et ce que le plan en a fait,
les passages, les captures, les publications et les versions.

**Le bout en bout du produit fini.** Le bouton « Bout en bout : le
produit fini d'une calculatrice » de la page Système met en base, d'un
clic, une calculatrice dont le POC est fait (sa fiche produit et son plan
validé) et trois demandes de clients (un historique des calculs, le
pourcentage et la racine carrée, un résultat qui dépasse de l'écran). La
conception du produit commence aussitôt ; tout le reste est l'étape 5
réelle : Stripe en mode test puis en vrai mode, l'achat du domaine
(validé dans le ticket « Plan »), la prod, le paiement test de 1 €
remboursé. Il faut, sur le serveur, les secrets décrits dans
[`installation/STRIPE.md`](../installation/STRIPE.md) et
[`installation/DOMAINES.md`](../installation/DOMAINES.md).

**Pas encore fait** : les versions suivantes, publiées en prod quand la
relecture est bonne (elles viennent avec l'étape 6, au lot 11), et le
passage d'une demande des clients à « livrée ».

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
   sur le prix (Q76). Le domaine n'est acheté qu'après l'essai du ticket
   de test : rien n'est dépensé pour un produit qu'un humain arrête.
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
