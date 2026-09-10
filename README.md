# SergeAgent — opérateur économique autonome (kit + runtime)

SergeAgent est un système complet pour faire tourner **un opérateur économique
autonome** : il prospecte, qualifie, relance, facture, encaisse, apprend de ses
erreurs et rend des comptes — sous mandat explicite, avec un humain qui tranche
les décisions propagatives. Le projet comprend le **kit d'installation**
(« serge depuis 0 » : questionnaire → instance vierge chiffrée) et le
**runtime** (prospection, LLM gouvernés, mémoire, voix, facturation, console
Discord).

> **Positionnement.** Ni framework agentique générique, ni chatbot : un
> opérateur métier opinionated, **déterministe par défaut**, où chaque recours
> au LLM est déclaré, mesuré et repliable. SQLite est la seule autorité, tout
> le reste est dérivé ou jetable.

## Philosophie (le contrat, en bref)

- **Déterministe par défaut.** Ordonnancement, guards, kill/scale, facturation :
  0 token. Le LLM ne juge que là où des règles coûteraient une combinatoire
  explosive — et chaque point de jugement est **déclaré** (registre versionné),
  avec repli déterministe obligatoire.
- **Fail-closed partout.** Pas de fichier d'instance → pas de boot. Pas de
  consentement → pas d'appel. Secret manquant → refus routable, jamais
  d'exception métier silencieuse.
- **Un fait = une source.** SQLite (`serge.db`) est l'autorité unique des faits
  métier. Zéro cache fichier, zéro JSON d'état, zéro constante dupliquée.
- **L'humain tranche, la machine propose.** Les décisions amont (venture, prix,
  hypothèse) passent en tickets avec expiry et défaut annoncé ; les boutons
  sont des actes typés idempotents, la prose ne tranche jamais.
- **Tests comportementaux.** ~470 tests prouvent le comportement (passant +
  refusé pour chaque capacité externe), plus des tests live-prudents bornés
  (allowlist owner-only, caps de session, jamais en CI).

Charte complète (P1-P5 / R1-R5) : [`docs/CODEBASE_CHARTER.md`](docs/CODEBASE_CHARTER.md).

## Capacités

### 1. Kit d'installation « serge depuis 0 »

`bin/serge-install` est le seul point d'entrée : il réutilise un couple
existant **ou** le génère (questionnaire guidé avec aide LLM intégrée, clé API
+ modèles d'abord), puis construit une instance vierge — arborescence depuis
`git archive` (jamais de copie de machine existante), canon vide, secrets
injectés en `0600`, units systemd, slots LLM, receipt JSON.

- Couple : `serge.instance.toml` (zéro secret) + `serge.secrets.age` (chiffré
  age, sidecar dotenv v2 avec support multiligne). Sans les deux, pas de boot.
- Mandat racine neutre généré (`policy-reference/` montre la forme sandbox).
- Gardes builder : refuse les chemins live sans confirmation, n'embarque
  jamais Meta-Grok aveuglément, scrub toute mémoire d'une autre instance.

Architecture : [`docs/INSTALL.md`](docs/INSTALL.md) ·
[`docs/INSTANCE_CONTRACT.md`](docs/INSTANCE_CONTRACT.md) · Code : [`kit/`](kit/)


### 2. Prospection : funnels déterministes

Campagnes (1 test sur 1 canal, N + seuils + fenêtre), contacts nommés
(états + régimes OUTBOUND/INBOUND), lifecycle ventures (gates, une seule
ACTIVE), séquenceur multi-canal versionné (ex. email → email → voix → email).
Les métriques U1-U5 sont des compteurs purs (le LLM classe, le code compte) et
les règles kill/scale sont des fonctions pures (métriques + seuils → verdict),
sans DB ni LLM.

Architecture : [`docs/FUNNEL_ARCHITECTURE.md`](docs/FUNNEL_ARCHITECTURE.md) ·
Code : [`serge/funnels/`](serge/funnels/)


### 3. 29 jugements LLM déclarés (matrice C)

Couche LLM [`serge/llm/`](serge/llm/) : client OpenRouter minimal (stdlib),
3 tiers modèles (rapide/défaut/stratège), kill-switch par point (registre
versionné `config/llm-points.yaml`), budget dur en €/jour avec dégradation
gracieuse, metering + alertes sur dérives vs médiane. Chaque point
[`serge/points/`](serge/points/) a sa checklist du besoin, son repli
déterministe, ses recalls JSON bornés (jamais de retry aveugle) : qualification
prospects, rédaction/slots, scripts et dialogue voix, classification réponses,
brouillons de réponse, hypothèses/plans/pivots, prix borné, build d'artifacts +
revue, consolidation mémoire, rendus et intentions owner, labels d'écoute,
juge d'allocation, guide d'installation.

Architecture : [`docs/LLM_MATRIX.md`](docs/LLM_MATRIX.md)


### 4. Mémoire 5 couches

L1 registres (faits chauds), L2 épisodes (ce qui s'est passé), L3
leçons/playbooks (ce qu'on a appris, distillé et actionnable), L4 résumés
versionnés régénérables, L5 recherche libre budgetée en lecture seule (soupape
anti-prison). Consolidation en batch semi-interactive (jamais d'écriture
directe), oubli par archive froide **réversible**.

Architecture : [`docs/MEMORY_ARCHITECTURE.md`](docs/MEMORY_ARCHITECTURE.md) ·
Code : [`serge/memory/`](serge/memory/)


### 5. Console owner Discord + tickets universels

Le bot [`serge/discord/`](serge/discord/) est un **miroir temps réel** des
tickets (gateway v10, forum + canal urgent + digest) : cartes de décision en
français, boutons = actes typés idempotents, mentions → tickets dans le sens
inverse. CLI : `serve` (service), `verify` (token + droits), `mirror-once`.
Les tickets [`serge/tickets/`](serge/tickets/) suivent un lifecycle générique
avec expiry et défaut annoncé ; les types sont des données YAML
(`config/ticket-types.yaml` : hypothèses, vetos amont, guichet humain,
publications…), pas du code.

Guides : [`docs/DISCORD_SETUP.md`](docs/DISCORD_SETUP.md) ·
[`docs/INTERACTION_ARCHITECTURE.md`](docs/INTERACTION_ARCHITECTURE.md)


### 6. Facturation stricte (collect, 0 LLM)

Ledger déterministe [`serge/collect/`](serge/collect/) : le prix n'est jamais
inventé (proposition → bornes → validation). Rail Stripe test-first
(PaymentIntents, refunds, vérification HMAC des webhooks) et relances bornées
(J+7 polie → J+14 ferme → STOP + ticket). La boucle retour événements Stripe
vers le ledger est en cours de branchement.

Code : [`serge/collect/`](serge/collect/) (doc d'architecture à venir)


### 7. Voix commerciale bornée

[`serge/voice/`](serge/voice/) : voix temps réel speech-to-speech + repli
tour-par-tour sur Asterisk user-space (AGI), policy gate fail-closed (heures
légales, bits de mandat, état runtime), consentements/blocklist dans le canon,
journal d'appels (CDR), gate qualité (2 mauvaises notes sur 10 → pause),
daemon de pont avec contrôle de santé du trunk.

Guides : [`docs/PHONE_OPTIONS.md`](docs/PHONE_OPTIONS.md) ·
[`docs/PHONE_VOICE_SMS.md`](docs/PHONE_VOICE_SMS.md)


### 8. SMS inbound vérifié (+ receveur Android)

[`serge/sms/`](serge/sms/) : inbox OTP vérifiée et idempotente + receveur
webhook loopback pour la passerelle Android. L'envoi SMS est volontairement
absent (pas d'OTP sortant, pas de spam).

Guide : [`docs/PHONE_SMS_ONLY.md`](docs/PHONE_SMS_ONLY.md)


### 9. Écoute signaux + routeur universel

Écoute [`serge/listen/`](serge/listen/) : collecte déterministe (RSS/API,
rate-limits respectés, dédup), clustering (Jaccard + union-find), filtre
« opportunité chaude » → FYI. Observation [`serge/observe/`](serge/observe/) :
8 signaux universels + OTHER (enum fermé), normaliseurs « physique du canal →
signal » en tables, routeur déterministe aveugle au canal. Canaux
[`serge/channels/`](serge/channels/) : contrat `can_send`/`send`/`poll`,
email via CLI `gog` (Gmail API, binaire externe requis). Guide Gmail :
[`docs/GMAIL_SETUP.md`](docs/GMAIL_SETUP.md). Boîte de confiance SMTP/IMAP
(sans OAuth, clé en main) : [`docs/MAILBOX_SETUP.md`](docs/MAILBOX_SETUP.md).

Code : [`serge/listen/`](serge/listen/) · [`serge/observe/`](serge/observe/) ·
[`serge/channels/`](serge/channels/) (écoute/routeur : doc à venir)


### 10. Allocation de budget inter-familles (A/B/C)

[`serge/allocator/`](serge/allocator/) : couche A = gardes déterministes non
négociables (0 token), couche B = bandit Thompson Sampling continu (0 token),
couche C = juge LLM borné par A (justifications tracées).

Code : [`serge/allocator/`](serge/allocator/) (doc d'architecture à venir)


### 11. Cœur d'exécution : scheduler SQL, guards, workers

- Ordonnanceur 100 % SQL (premier READY gagne, 0 LLM) + runner de cycle
  (expiry tickets, file READY, consolidation due).
- 9 workers [`serge/workers/`](serge/workers/) : classification inbound,
  réponses, envois email, poll Gmail, écoute, mémoire, appels voix, scoring
  vocal, dispatch.
- `check()` : point de passage unique avant toute exposition sortante,
  fail-closed, 0 LLM, codes routables (jamais de prose).
- SQLite = autorité unique (fichier `0600`, événements append-only, horloge
  UTC), un seul fichier de policy versionné (`config/policy.yaml`, chargement
  fail-closed), un seul lecteur de secrets, empreintes PII centralisées.

Code : [`serge/scheduler.py`](serge/scheduler.py) ·
[`serge/guards/`](serge/guards/) · [`serge/workers/`](serge/workers/) ·
[`serge/db/`](serge/db/)


### 12. Ops : units systemd, scans, tests live-prudents

Templates d'units paramétrés [`systemd/templates/`](systemd/templates/)
(pipeline + timer, bot Discord, receveur SMS, pont voix, Asterisk, rapports,
dashboards, ingress), scan secrets pre-commit (zéro secret versionné, vérifié
par test), harnais live-prudent (`SERGE_LIVE_TESTS=1` + présence owner :
canary Stripe 1 € + refund, smoke Discord sans persistance).

Outillage : [`docs/DEV_TOOLING.md`](docs/DEV_TOOLING.md)

## Architecture (layout)

```text
kit/            installeur (TOML+age, wizards, builder, guide, slots LLM)
serge/          runtime (scheduler, guards, tickets, funnels, mémoire, voix)
serge/discord/  bot Discord (miroir tickets + actes owner, gateway temps réel)
serge/collect/  facturation (intents, relances, rail Stripe test-first)
serge/observe/  signaux inbound + routeur universel
serge/listen/   écoute signaux (collecteurs + clustering + opportunités)
serge/memory/   mémoire 5 couches (registres → recherche libre)
serge/llm/      couche LLM (client metered, budget dur, kill-switchs)
serge/points/   29 points LLM déclarés (matrice C, replis dét)
serge/workers/  exécutants des files (inbound, mémoire, écoute, envois, voix)
serge/voice/    voix bornée (S2S + repli tour-par-tour, policy, CDR)
serge/sms/      SMS inbound vérifié (inbox OTP + receveur loopback)
serge/allocator/ allocation A/B/C (gardes + bandit + juge)
config/         policy.yaml, llm-points.yaml, ticket-types.yaml, séquences
schemas/        contrats instance + secrets + exclusions
policy-reference/ exemple de mandat sandbox neutre
systemd/        templates d'units paramétrés
scripts/        serge-install (+ outils), scan secrets
bin/            shims CLI
tests/          unitaires + live-prudents (skippés par défaut)
docs/           design (charte, funnels, mémoire, matrice, interactivité)
```

## Démarrage rapide

```sh
bin/serge-install            # interactif guidé (clé API + modèles d'abord)
bin/serge-install --instance-file X --mandate Y --source-repo Z  # couple prêt
```

Détail : [docs/INSTALL.md](docs/INSTALL.md). Contrat :
[docs/INSTANCE_CONTRACT.md](docs/INSTANCE_CONTRACT.md). Discord :
[docs/DISCORD_SETUP.md](docs/DISCORD_SETUP.md). Téléphonie :
[docs/PHONE_OPTIONS.md](docs/PHONE_OPTIONS.md).

## Développer

```sh
curl -LsSf astral.sh/uv/install.sh | sh
uv sync --group dev
uv tool install pre-commit && pre-commit install
pre-commit run --all-files
python3 -m unittest discover -s tests            # unitaires
SERGE_ENV=test python3 -m unittest discover -s tests  # + live-prudents (.env.test)
```

Règles : charte P1-P5 + R1-R5 (review dans chaque message de commit),
jamais de secret commité, jamais d'écriture live sans
`--confirm-live-instance-id`. Outillage : [docs/DEV_TOOLING.md](docs/DEV_TOOLING.md).

## État

Tag `v0.2` = kit installable (sidecar v2 multiligne) + runtime complet
(funnels dét, 29 points LLM, mémoire 5 couches, voix S2S + repli, collect
sandbox, bot Discord). Bêta en cours : installation vierge depuis le tag sur
machine dédiée, puis activation progressive (verify → tests live → miroir →
services).

## Licence

MIT — voir [LICENSE](LICENSE). La plus permissive possible : utilisez, modifiez,
redistribuez, y compris commercialement, en gardant la notice de copyright.
