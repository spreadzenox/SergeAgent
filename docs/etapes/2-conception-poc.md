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

**Rien n'est branché.** Le code contient :

- l'invocation **« Écrire l'idée de business »** (`draft_hypothesis_smoke`,
  `serge/points/hypotheses.py`) : hypothèse, taille (30 à 50 prospects),
  canaux, seuil de succès, durée (10 jours maximum), prix indicatif. Elle
  n'est jamais appelée ;
- de quoi créer une campagne de test (`serge/funnels/essai.py`), jamais
  appelé non plus.

---

## Décidé

1. **Concevoir le POC** (invocation LLM). Elle écrit :
   - l'hypothèse, la cible, le ou les canaux, le nombre de prospects, la
     durée, le prix indicatif ;
   - le rythme des relances (exemple : « relance à J+3 puis J+7 sans
     réponse, 3 messages maximum ») ;
   - la description du livrable d'essai (exemple : « un générateur de devis
     en ligne, 3 devis gratuits, puis 39 €/mois ») ;
   - **un plan de A à Z** : de quoi le produit a besoin, ce que le builder
     doit faire, pourquoi et comment ça va marcher.
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
   plan final, la critique, ce qui a été corrigé et ce qui reste. Julien
   valide, refuse ou discute. Sans réponse sous 48 h, le plan s'applique.
   S'il reste une « nouvelle capacité nécessaire » après 3 tours, le ticket
   arrive dans cet état : c'est à Julien de créer la capacité.
5. **Construire le livrable** avec le même couple builder / reviewer que
   l'étape 5 (voir [`5-construction.md`](5-construction.md)).
6. **Mettre en ligne** sur un sous-domaine du domaine de Serge, via Caddy
   sur le VPS.
7. **Créer la campagne** de test léger, puis ticket d'information à
   Julien avec le lien. Le business passe à l'étape 3.

Les types de business possibles, et ce qu'on construit pour chacun, sont
dans [`DECISIONS_REVUE.md`](../DECISIONS_REVUE.md) (question 32).
