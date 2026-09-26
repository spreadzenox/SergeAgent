# Étape 8 — Caisse

Identifiant : `caisse`.

**Rôle.** Encaisser, relancer les impayés, rembourser. Sans LLM.

**Entrée.** Des ventes (paiements, abonnements) sur les produits de Serge.

**Sortie.** De l'argent encaissé, suivi par business.

---

## Aujourd'hui

- **Registre des paiements** (`serge/collect/intents.py`, table
  `transactions`) : devis, facture émise, envoyée, payée, en retard,
  annulée, remboursement. Un prix n'est jamais inventé.
- **Stripe** (`serge/collect/rails.py`, `receiver.py`, `webhook.py`) :
  création des paiements et remboursements, réception des confirmations
  sur `https://<domaine>/hooks/stripe`. La signature de Stripe est
  vérifiée. Un paiement confirmé passe en « payé » tout seul. Installation :
  [`installation/STRIPE.md`](../installation/STRIPE.md).
- **Abonnements** (`serge/collect/abonnements.py`, table `subscriptions`)
  : mis à jour par Stripe. **Défaut** : chaque abonnement est rattaché à un
  faux business unique, `serge-collect-stripe`, écrit en dur dans le code.
  On ne sait donc pas à quel business il appartient.
- **Relances d'impayés** (`serge/collect/dunning.py`) : polie à J+7, ferme
  à J+14, puis arrêt et ticket. **Codées mais jamais programmées.**

---

## Décidé

1. **Tout encaissement passe par Stripe** : liens de paiement, pages de
   paiement, abonnements. Stripe émet les factures conformes (numérotation,
   mentions obligatoires) avec l'identité de Serge. Serge ne fabrique pas
   ses propres factures.
2. **Les relances d'impayés sont programmées.** Elles passent par le fil du
   client et suivent les mêmes règles que les relances de prospection : pas
   de relance si le client a répondu entre-temps.
3. **Remboursements** : en dessous d'un seuil (exemple : 50 €, dans la
   policy), automatiques avec un ticket d'information. Au-dessus, ticket
   Discord pour Julien.
4. **Chaque abonnement est rattaché à son business** : Serge inscrit
   l'identifiant du business dans le produit Stripe.
5. **Mission Control montre, par business**, ce qui a été encaissé, ce qui
   est dû et ce qui est en retard.
6. **Le prix** vient du plan du POC (indicatif), puis du plan du produit
   validé par Julien (définitif). Il ne change que par un pivot validé.
   L'invocation « Proposer un prix » a été supprimée.
