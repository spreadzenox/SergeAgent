# Stripe — webhook d’instance (tuto installateur)

Objectif : après `serge-install`, un paiement Stripe (test ou live)
passe la transaction Serge en `paid`. Le domaine n’est **pas** figé :
c’est le même `identity.public_hostname` que Mission Control.

## Principe

```
Dashboard Stripe  POST  https://<domaine>/hooks/stripe
                         ↕ Caddy (handle /hooks/stripe*)
VPS loopback 127.0.0.1:8788  serge-stripe-receiver
                         ↕ HMAC whsec (live puis test)
canon  transactions.intent_id = pi_…  → mark_paid
```

Même hôte que le MC (`https://<domaine>/`). Pas de sous-domaine `pay.`.
Le kit refuse `stripe` / `payments_live` sans `ingress` ni hostname.

## Ordre dans le kit (ne pas inverser)

1. Features : allumer `stripe` (sandbox) et/ou `payments_live`.
   L’installeur force `ingress` si besoin.
2. **Domaine public** (MC, `sms.<domaine>`, webhook Stripe).
3. L’installeur affiche l’URL exacte à coller, **avant** les secrets.
4. Dashboard Stripe → Developers → Webhooks → Add endpoint :
   - URL : `https://<domaine>/hooks/stripe` (la même en test et en live)
   - événements : `payment_intent.succeeded`, `checkout.session.completed`
5. Copier les deux signing secrets (`whsec_…` test et, si live, live)
   dans l’installeur (saisie masquée).
6. Finir le kit. Le builder pose la unit, sème la route Caddy, écrit
   les fichiers 0600 `stripe-*-key` / `stripe-webhook-*-key`.

Sans l’étape 4 **avant** les `whsec`, le secret existe mais Stripe
poste ailleurs : rien n’est payé.

## Après install

Le receipt affiche `stripe_route` (`https://<domaine>/hooks/stripe`).
Unit : `serge-stripe-receiver.service` (loopback `:8788`).
Santé locale : `GET http://127.0.0.1:8788/healthz`.

`sk_test_` / `sk_live_` encaissent. `whsec_` ne prouve que que le POST
vient de Stripe. Un `whsec` n’est pas lié à un hostname : c’est
**l’URL de l’endpoint** dans le Dashboard qui doit matcher l’instance.

## Vérifier

1. Créer un PaymentIntent test dont l’id (`pi_…`) est déjà
   `transactions.intent_id` (facture `issued` ou `sent`).
2. Déclencher le paiement test (Dashboard ou `StripeRail`).
3. Stripe POST → receiver 200 `{ "status": "ok" }` → ligne `paid`.
4. Replay du même événement : `{ "status": "ok", "already": true }`.

Événement sans `pi_` connu : `unmatched` (200, pas de crash). Signature
fausse : 401. Webhook trop vieux : 400.

## Pièges

| Symptôme | Cause typique |
| --- | --- |
| Stripe 404 / timeout | Caddy ou unit down ; URL ≠ `public_hostname` |
| 401 unauthorized | `whsec` test collé sur l’endpoint live (ou l’inverse) |
| `unmatched` | `intent_id` ledger ≠ `pi_` Stripe |
| Payé dans Stripe, draft chez Serge | webhook jamais reçu (mauvaise URL) |

Détail contrat : [`INSTANCE_CONTRACT.md`](INSTANCE_CONTRACT.md).
Install : [`INSTALL.md`](INSTALL.md).
