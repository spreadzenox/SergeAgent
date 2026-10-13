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

**Rien n'est branché.** L'invocation « Écrire l'idée de business »
(hypothèse, taille de 30 à 50 prospects, canaux, seuil de succès, durée
de 10 jours au plus, prix indicatif), jamais appelée, est rangée dans
`pas_encore_branche/` (`serge/points/hypotheses.py`). Le code qui crée une
campagne de test (`serge/funnels/essai.py`) existe, mais rien ne l'appelle.

---

## Décidé

Seulement des produits web, et le POC est gratuit pour les prospects
(Q91). Le détail technique (le chantier, l'interface web, la mise en
ligne, les tables) est dans
[`LOT10_CONCEPTION.md`](../LOT10_CONCEPTION.md).

1. **Concevoir le POC** (invocation LLM). Elle écrit :
   - l'hypothèse, la cible, le ou les canaux, le nombre de prospects, la
     durée, le prix indicatif ;
   - le rythme des relances (exemple : « relance à J+3 puis J+7 sans
     réponse, 3 messages maximum ») ;
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
