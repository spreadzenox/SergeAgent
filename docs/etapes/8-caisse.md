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
  : mis à jour par Stripe. Chaque abonnement est rattaché à son business
  grâce au champ `metadata.venture_id` du prix (ou de l'abonnement) dans
  Stripe. Exemple : un prix Stripe avec `venture_id = v1` → l'abonnement et
  ses factures payées vont au business `v1`. Sans ce champ, l'abonnement est
  gardé sans business et le journal le signale
  (`collect.subscription_unattached`). Un business rattaché n'est jamais
  remplacé.
- **Ce qui manque** : Serge ne crée pas encore lui-même ses prix Stripe ;
  il faudra qu'il y inscrive `venture_id` en les créant.
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
   l'identifiant du business dans le prix Stripe. **Fait** pour la
   lecture ; reste l'écriture, avec la création des prix.
5. **Mission Control montre, par business**, ce qui a été encaissé, ce qui
   est dû et ce qui est en retard.
6. **Le prix** vient du plan du POC (indicatif), puis du plan du produit
   validé par Julien (définitif). Il ne change que par un pivot validé.
   L'invocation « Proposer un prix » a été supprimée.
