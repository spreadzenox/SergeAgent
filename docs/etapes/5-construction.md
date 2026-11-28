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
s'appuie sur « Appeler une API » pour Stripe et Cloudflare. Le lot 11
(décisions Q96 et Q97) y a ajouté les e-mails du produit, la boîte du
relecteur, les arrêts d'une tâche, et le vrai Chrome du paiement test.

**Essayée de bout en bout sur le serveur le 16 novembre 2026** : une
calculatrice, du plan au paiement test de 1 € (payé dans le vrai Chrome,
vérifié dans Stripe, remboursé), puis essayée à la main, inscription et
paiement compris.

Elle part du choix du business principal (étape 4, lot 12) : « Appliquer
le choix du principal » fait passer le business choisi « en construction
de son produit » (`PRODUCT_BUILDING`) et lance « Concevoir le produit ».

1. **Concevoir le produit** (niveau intelligent) reçoit la fiche du
   business, le plan de son POC, la fiche produit, toutes les demandes de
   ses clients (`customer_requests`) et ce qu'ont répondu ses prospects.
   Elle écrit le plan du produit (`product_plans`, `kind` = `product`) :
   le prix définitif, le plan de A à Z (inscription, abonnement Stripe, ce
   que le compte débloque), les scénarios de test (l'un va jusqu'au
   paiement) et un nom de domaine libre (elle le vérifie chez Cloudflare).
   Elle écrit aussi les offres du produit (`product_offers`, décision
   Q119) : une par abonnement que le client peut choisir, avec son code,
   son prix en centimes, sa période (par mois ou par an) et ce qu'elle
   comprend ; une seule est l'offre principale. Exemple : `standard`,
   19 € par mois, et `pro`, 49 € par mois. Elle réécrit la fiche produit
   et ses questions fréquentes, et marque chaque demande des clients
   retenue ou refusée, avec sa raison.
2. **Challenger le produit** (niveau intelligent), 3 tours au plus.
3. **Le ticket « Plan »** (`PLAN_PRODUIT`) montre le plan, son prix, ses
   offres, son domaine, la critique, la fiche produit et les demandes des
   clients. Il n'expire jamais.
4. **Vendre en mode test** (niveau moyen) : le produit et un prix par
   offre dans Stripe en mode test. Chaque prix porte l'identifiant du
   business (`metadata[venture_id]`) et une clé de recherche
   (`lookup_key`) : le numéro du business pour l'offre principale, et
   `<numéro du business>_<code>` pour une autre (exemple : `ven_12_pro`).
   Le produit retrouve ses prix par ces clés, en mode test comme en vrai
   mode, sans rien changer à son code. La clé d'une autre offre est
   choisie par le modèle : « Appeler une API » refuse celle qui ne
   commence pas par le numéro du business, figé en base.
   Avant de créer quoi que ce soit, l'invocation regarde si le business a
   déjà un prix, par la clé du business, puis un produit sans prix, par
   la recherche de Stripe. Elle garde un prix déjà au bon montant, crée
   ceux qui manquent, et archive ceux qui ne correspondent plus à une
   offre ; les clients déjà abonnés à un prix archivé le gardent.
5. **Construire le produit** (niveau « code ») : comptes, e-mails,
   abonnement par une page de paiement Stripe, le service. Son chantier
   reçoit la clé du mode test (`STRIPE_SECRET_KEY`). Le constructeur
   vérifie par des commandes, sans navigateur (Q96). Puis **publier en
   staging** (même clé), **relire** (niveau « web », un modèle moins cher
   qui navigue) jusqu'au paiement avec la carte de test 4242 4242 4242
   4242, comme à l'étape 2 : 3 reprises et 3 passages au plus. Le
   relecteur s'inscrit avec sa propre adresse (« Ma boîte e-mail ») et y
   lit les e-mails du produit (un lien de validation) ; pour un scénario
   qui demande la fin d'un abonnement, il l'annule dans Stripe en mode
   test, comme si le temps avait passé.
6. **Le ticket « Tester le produit »** (`TEST_PRODUIT`) : un humain essaie
   le staging, paiement compris. Il n'expire jamais. « À corriger »
   relance la construction (un bug) ; « Revoir le plan » renvoie à la
   conception, puis au critique et au ticket « Plan » (une fonctionnalité
   à changer, décision Q116). Entre la relecture et ce ticket, un
   aiguillage sans LLM (« Suite d'une relecture réussie du produit »)
   regarde si le business reçoit la correction d'un produit déjà en
   vente : elle part alors en prod sans ce ticket (voir « Une nouvelle
   version », plus bas).
7. **Choisir le domaine** (sans LLM), une fois le produit essayé et
   validé, pour une première mise en vente (un second aiguillage,
   « Suite d'un essai validé du produit », envoie ailleurs la nouvelle
   version d'un produit déjà en vente) : avec un domaine commun des produits finis (réglage, page
   Policy), rien n'est acheté : Serge fait pointer
   `<produit>.<domaine commun>` vers le serveur (un enregistrement DNS chez
   Cloudflare, pour ce seul nom) et passe à l'étape 8. Sinon,
   **acheter le domaine** (niveau intelligent) : chez Cloudflare, avec la carte de Serge enregistrée
   sur son compte, s'il est libre et sous le prix maximum (30 € par an, la
   première année comme le renouvellement, page Policy), pour un an sans
   renouvellement automatique, puis un enregistrement DNS vers le
   serveur. Sinon, le ticket
   « Domaine » (`DOMAINE_PRODUIT`) dit pourquoi et propose des noms libres
   ; « À corriger » avec un nom achète ce nom.
8. **Mettre en vente** (niveau moyen) : le produit et son prix dans
   Stripe en vrai mode, avec la même clé de recherche. Puis **publier en
   prod** sur le domaine, avec une clé Stripe restreinte du vrai mode
   (`stripe-produits-live.key`) : le produit n'a jamais la clé complète de
   Serge.
9. **Le paiement test de 1 €** (niveau « web ») : il retrouve le produit
   par la clé de recherche de son prix, à jour tout de suite (la
   recherche de Stripe ne voit un produit qu'une minute environ après sa
   création : le 19 novembre 2026, 9 secondes après la mise en vente,
   elle ne le trouvait pas). Puis un prix de 1 € (100 centimes, en
   euros : le montant et la monnaie sont figés en base, le modèle ne les
   choisit pas) et un
   lien de paiement, payé dans le **vrai Chrome** (un Chromium normal, sur
   un écran virtuel : le captcha de Stripe ne se chargeait pas dans le
   navigateur sans écran, décision Q97) avec la carte de Serge et
   l'adresse de la boîte du relecteur,
   déchiffrée de `payment-card.enc` au moment de taper (« taper un
   secret » : le modèle ne voit jamais ses numéros, et la carte ne se
   tape que sur une page de paiement de Stripe), vérifié
   dans Stripe (la session du lien est payée), remboursé ; le lien est
   désactivé et le prix archivé. Le paiement est noté dans `transactions`
   (`kind` = `canary`). Si un captcha bloque, le modèle appelle « Appeler
   un humain » : la tâche s'arrête, et un ticket « Un humain, prêt ? »
   (`GUICHET_PRET`) mentionne les administrateurs. « Je suis prêt » la
   fait repartir du début ; au même captcha, un second ticket (`GUICHET`)
   envoie le lien de l'écran du vrai Chrome, dans Mission Control
   (`/owner/vrai-chrome`, derrière la connexion), et la tâche attend
   « C'est fait » 10 minutes (page Policy, « Bac à sable »). Sans réponse,
   elle s'arrête et redemande ; « Abandonner » la fait continuer sans
   humain. Pour faire passer une autre invocation au vrai Chrome, on
   remplace ses outils « Agir dans une page », « Lire la page » et
   « Prendre une capture » par « Agir dans le vrai Chrome », « Lire la page
   du vrai Chrome » et « Capture du vrai Chrome » (page Pipeline), et on
   lui donne « Appeler un humain ».
10. **Produit en vente** : le business passe à `PRODUCT_READY`, d'où
    part la prospection lourde (étape 6, lot 12), et un ticket
    d'information le dit. Une étape ratée
    (Stripe, la prod, le paiement test) ouvre un ticket d'information
    avec la raison.

La fiche du business, dans Mission Control, montre le plan du produit
avec son domaine, les demandes des clients et ce que le plan en a fait,
les passages, les captures, les publications et les versions.

**Dans l'essai total.** L'essai total de la page Système (décision Q99)
passe par cette étape comme un vrai business, dans le couloir d'essai :
plan du produit, Stripe en mode test puis en vrai mode, la prod sur un
sous-domaine, le paiement test de 1 €, remboursé. Deux différences : il
n'achète jamais de domaine (sans domaine commun des produits, un ticket
demande de le régler), et, après le paiement test, il essaie le captcha
avec un humain avant « Produit en vente ». Avec l'étape de départ 5,
l'essai commence ici, avec une calculatrice dont le POC est fait et trois
demandes de clients (un historique des calculs, le pourcentage et la
racine carrée, un résultat qui dépasse de l'écran). Il faut, sur le
serveur, les secrets décrits dans
[`installation/STRIPE.md`](../installation/STRIPE.md) et
[`installation/DOMAINES.md`](../installation/DOMAINES.md).

**Les e-mails du produit** (lot 11, Q96). Le produit envoie ses e-mails
(valider une inscription, changer un mot de passe oublié, un reçu) par
SMTP, avec les variables `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASS` et `MAIL_FROM` : le même code marche partout.

- Dans le chantier et en staging, la boîte d'essai (un Mailpit sur le
  serveur, `serge-boite`) garde tous les e-mails, quel que soit le
  destinataire : rien ne part. Le relecteur y lit les siens ; Julien et
  Clem les lisent sur la fiche du business (« E-mails d'essai »), pour
  essayer le produit eux-mêmes avec n'importe quelle adresse.
- En prod, ils partent par Resend, avec une clé par produit qui ne sait
  qu'envoyer : Serge la crée la première fois avec la clé maîtresse et la
  range dans `resend-<business>.key` ; aucun modèle ne la voit.
  L'expéditeur est `<nom court>@<domaine d'envoi>`, toujours un
  sous-domaine de Serge (page Policy, « E-mails des produits »). Sans
  domaine d'envoi, la mise en prod rate et le dit.
- L'adresse de contact (décision Q119) : un produit fini publié reçoit
  `CONTACT_EMAIL`, l'adresse de la boîte de Serge avec son nom court
  après un « + » (exemple : `serge+calcudevis@exemple.fr`), et la montre
  en pied de page et dans les mentions légales. C'est la publication qui
  la demande (son paramètre `contact`, réglé sur les invocations du
  produit fini) : un POC n'en reçoit pas. Un e-mail qu'un inconnu y
  écrit est rattaché au business (étape 6). Pas de formulaire de contact.
  L'éditeur des mentions légales est Julien Pesquet ; le service est tenu
  par Serge, un agent IA.

Mise en place : [`installation/DOMAINES.md`](../installation/DOMAINES.md).

**Une nouvelle version** (lot 16, décision Q119). Un produit déjà en
vente change par ces mêmes invocations, lancées par le point de la
semaine ou par un bug signalé (étape 6) :

- **une correction** reprend à « Construire le produit », avec ses
  consignes. Dès que le relecteur la juge bonne, elle part en prod, sans
  essai d'un humain ;
- **une évolution** (une fonctionnalité, une offre, un prix) reprend à
  « Concevoir le produit », qui part du plan déjà construit, puis passe
  par le critique, le ticket « Plan », Stripe en mode test, la
  construction, la relecture et le ticket « Tester le produit ».

La fin est plus courte qu'une première mise en vente : pour une
évolution, « Mettre à jour les offres dans Stripe » (le vrai mode), puis
« Publier la nouvelle version en prod », à l'adresse où le produit est
déjà en ligne (`same_address`) ; un produit qui n'est pas en ligne en
prod est refusé. Rien n'est racheté, il n'y a pas de second
paiement test de 1 €, et la prospection lourde n'est pas relancée. Les
clients gardent leur compte et leurs données : le dossier de données du
produit est gardé d'une version à l'autre, et le constructeur doit le
faire évoluer sans rien perdre. Puis le point qui a lancé la version
passe à « en ligne », les demandes des clients retenues passent à
« livrée » avec le numéro de la version, et un ticket d'information le
dit. Un humain qui renvoie une correction en conception (« Revoir le
plan ») en fait une évolution.

**Pas encore fait** : prévenir chaque client que sa demande est livrée.

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
4. **Construire** avec un duo de deux invocations (Q91) : le
   constructeur (niveau « code ») écrit et lance le produit dans un
   chantier (un conteneur), et le vérifie par des commandes ; le
   relecteur (niveau « web », moins cher, Q96) est le seul à naviguer. Il
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
