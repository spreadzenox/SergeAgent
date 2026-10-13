# Étape 2 — Conception du POC

Identifiant : `conception_poc`.

**Rôle.** Pour chaque business choisi à l'étape 1, écrire un plan de test
complet, le faire critiquer, le faire valider par Julien, puis construire
et mettre en ligne un petit livrable d'essai.

**Entrée.** Un business au statut `POC_SELECTED`.

**Sortie.** Un plan validé, un livrable d'essai en ligne, et une campagne
de test léger prête pour l'étape 3.

---

## Aujourd'hui

**L'étape est en base depuis le lot 10 (PR 4, décision Q91).** Aucune
ligne de code ne lui est propre : ses invocations, ses liens et ses
tickets sont dans `config/pipeline.yaml` et `config/ticket-types.yaml`.

1. **Concevoir le POC** (niveau intelligent) part d'un business choisi
   pour un POC, par « Choisir les business » (étape 1) ou par le bouton
   « Essayer l'étape 2 » de la page Système. Elle écrit le plan
   (`product_plans`), la fiche produit et ses questions fréquentes, et la
   campagne de test, au brouillon (`campaigns`). Réglages : 30 à 50
   prospects, 10 jours au plus (page Policy). Le plan ne fixe pas le
   rythme des relances : il est commun à tous les business (Q37,
   corrigée par Q92).
2. **Challenger le POC** (niveau intelligent) rend « bon » ou
   « a_corriger » avec ses remarques (`plan_critiques`). « Compter les
   tours de critique » renvoie le plan à la conception, 3 tours au plus.
3. **Le ticket « Plan »** (`PLAN_POC`) : « Valider », « À corriger » (les
   consignes repartent à la conception), « Arrêter le business » (il
   libère sa place de test). Sans réponse sous 48 heures, le plan
   s'applique.
4. **Construire le POC** (niveau « code ») travaille dans le chantier du
   business et essaie son produit dans le navigateur. Son compte rendu va
   dans `builds`. Une construction pas finie (plafond du jour atteint)
   ou une publication ratée reprend, 3 reprises au plus.
5. **Publier le POC en staging** : `staging-<nom du business>.<domaine>`,
   non indexé.
6. **Relire le POC** (niveau « code ») l'essaie comme un prospect, sans
   voir le code, garde ses captures, et rend « bon » ou « a_corriger ».
   « Compter les passages » relance la construction, 3 passages au plus.
7. **Le ticket « Tester le produit »** (`TEST_POC`) n'expire jamais :
   « Valider » met le POC en prod sur `<nom du business>.<domaine>`, sa
   campagne passe à prête et le business au test léger (`SMOKE_READY`) ;
   « À corriger » relance la construction avec les consignes ; « Arrêter
   le business » l'arrête.

La fiche du business, dans Mission Control, montre le plan, les
remarques du critique, les passages avec le verdict du relecteur, les
captures, les publications et les versions.

**Le bout en bout du POC.** Le bouton « Bout en bout : le POC d'une
calculatrice » de la page Système met en base, d'un clic, un business
« Calculatrice » choisi pour un POC, avec sa fiche produit, ses questions
fréquentes, sa campagne et un plan déjà validé (huit scénarios de test :
12 + 7, 7 ÷ 2, la division par zéro, 0,1 + 0,2, le clavier, le
mobile…). La construction commence aussitôt ; tout le reste est le vrai
pipeline, à partir de l'étape 4 ci-dessus : construire, publier en
staging, relire dans le navigateur, le ticket « Tester le produit » (son
lien ouvre la calculatrice), puis la prod. Seules la conception du plan
et la création du business sont court-circuitées. Chaque essai crée un
business neuf (l'écriture passe outre la règle de doublon, `dedup:
false`) ; sa publication reprend l'adresse `staging-calculatrice.<domaine>`
et arrête le produit de l'essai d'avant.

## Décidé

Seulement des produits web, et le POC est gratuit pour les prospects
(Q91). Le détail technique (le chantier, l'interface web, la mise en
ligne, les tables) est dans
[`LOT10_CONCEPTION.md`](../LOT10_CONCEPTION.md).

1. **Concevoir le POC** (invocation LLM). Elle écrit :
   - l'hypothèse, la cible, le ou les canaux, le nombre de prospects, la
     durée, le prix indicatif ;
   - la description du livrable d'essai (exemple : « un générateur de devis
     en ligne, 3 devis gratuits, puis 39 €/mois ») ;
   - **un plan de A à Z** : de quoi le produit a besoin, ce que le builder
     doit faire, pourquoi et comment ça va marcher ;
   - **les scénarios de test** : ce que fait un prospect ordinaire, pas à
     pas (exemple : « créer un compte, faire un premier devis, le
     télécharger en PDF »). Le relecteur et l'humain du ticket de test les
     suivent ;
   - **la fiche produit du POC**, qui servira à répondre aux prospects :
     ce que fait le livrable et pour qui, ce qu'il ne fait pas, le prix,
     les délais, comment on l'utilise, et les questions fréquentes qu'on
     peut prévoir. Sans elle, l'invocation qui répond aux prospects
     inventerait ou se tromperait.
2. **Challenger le POC** (invocation LLM distincte). Elle critique la
   faisabilité technique, les limites du produit et le réalisme commercial.
   Chaque remarque est de l'un de ces deux types seulement :
   - **« à corriger »** : le plan est mal fait, mais faisable avec ce que
     Serge sait déjà faire ;
   - **« nouvelle capacité nécessaire »** : il manque un outil ou autre
     chose.

   Exemple de remarque attendue : « le plan commence par se connecter à
   l'ERP d'une grande entreprise contactée par e-mail : c'est irréaliste ».
3. **La conception reprend son plan** en tenant compte de la critique.
   **3 tours maximum.** Les prompts forcent à arriver à un plan qui marche.
4. **Ticket Discord pour Julien**, avant toute construction. Il contient le
   plan final, la fiche produit, la critique, ce qui a été corrigé et ce
   qui reste. Il commence par décrire le business en quelques lignes, pour
   que Julien le comprenne sans avoir suivi Serge. Julien
   valide, refuse ou discute. Sans réponse sous 48 h, le plan s'applique.
   S'il reste une « nouvelle capacité nécessaire » après 3 tours, le ticket
   arrive dans cet état : c'est à Julien de créer la capacité.
5. **Construire le livrable** avec le même duo que l'étape 5 (voir
   [`5-construction.md`](5-construction.md)) : un constructeur qui écrit
   et lance le POC dans un chantier, et un relecteur qui l'essaie comme un
   prospect, sans voir le code. Trois passages au plus. Chaque version
   est mise en ligne en staging, sur `staging-<business>.<domaine de
   Serge>`.
6. **Ticket de test** (Q91) : un humain essaie le POC depuis le lien du
   staging, avant qu'aucun prospect ne le voie. Le ticket n'expire jamais.
   « À corriger » renvoie ses consignes au constructeur ; « Arrêter le
   business » arrête tout.
7. **Mettre en ligne en prod** sur un sous-domaine du domaine de Serge,
   via Caddy sur le VPS. La campagne de test léger est prête, et le
   business passe à l'étape 3.

Les types de business possibles, et ce qu'on construit pour chacun, sont
dans [`DECISIONS_REVUE.md`](../DECISIONS_REVUE.md) (question 32).
