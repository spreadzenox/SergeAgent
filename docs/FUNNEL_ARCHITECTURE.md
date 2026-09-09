# Architecture des funnels Serge (B)

Version : 1.0 (2026-09-09)
Statut : VALIDÉ avec Julien le 2026-09-09 (discussion B, § par §).
S'applique à : le rework kit (nouveaux modules, nouvelles tables).
Références : charte ([CODEBASE_CHARTER.md](CODEBASE_CHARTER.md)), market tests (A),
interactivité ([INTERACTION_ARCHITECTURE.md](INTERACTION_ARCHITECTURE.md)).

Principe : le LLM ne décide qu'aux points de jugement déclarés (P2).
Tout le reste (scheduling, transitions, guards, compteurs) est déterministe.
Les points LLM repérés ici auront leur checklist P2 remplie en chantier C
(matrice état par état) — ils sont marqués `«C»` ci-dessous.

---

## §0 — Socle : scheduler SQL-first, 0 LLM (validé)

Le choix du prochain travail est une requête, pas une délibération.
Fini le Director qui "planifie" en langage naturel (68 % de cycles idle).

```sql
SELECT * FROM work_items
WHERE status = 'READY'
  AND blocked_until < now()
  AND venture_id IN (SELECT id FROM ventures WHERE status = 'ACTIVE')
  AND guard_pass(task)  -- quotas, cooldowns, fenêtres : booléens
ORDER BY priority DESC, created_at ASC
LIMIT 1;
```

- Premier READY gagne. Rien de READY → idle légitime (constitution §7 :
  pas de travail manufacturé).
- Work-conserving mécanique : si la venture A attend (fenêtre, cooldown,
  réponse), le scheduler prend le READY de B. L'attente locale reste locale.
- Le scheduler ne sait pas ce qu'est un email ou une facture — il ordonnance
  des `work_items` ("appeler X", "augmenter budget Y", "publier Z").

---

## §1 — Méta-funnel : vie d'une venture (validé)

Un seul funnel maître. **Une seule venture ACTIVE à la fois** (enforced ici,
pas par convention).

```text
CANDIDATE (écoute J : demande observée)
  │ [ticket HYPOTHESIS validé pour les full ; smokes auto]
  ▼
SMOKE (N=30-50, ~1 semaine, jamais de KILL)
  │ [seuils A : ≥3 positifs → SCALE précoce | sinon → FULL]
  ▼
FULL (N=150-200, 2-3 sem., pré-enregistré, seuils kill/scale)
  │ [compteurs sur seuils : SCALE | PIVOT | EXTEND(1×) | KILL | INVALID]
  ├─→ SCALE : industrialiser (volume + canaux + builder)
  ├─→ PIVOT : variation ciblée → nouveau test pré-enregistré
  ├─→ EXTEND : 1×, variation imposée
  ├─→ KILL : archiver + leçon obligatoire
  └─→ INVALID : fixer infra, refaire (ne compte pas comme test)
```

**Gate collect à deux vitesses (validé).**
- SMOKE : exige un **prix draft** (fourchette écrite dans l'hypothèse, pas
  encore owné) — on teste le message, pas l'encaissement.
- FULL : exige **collect READY** (prix owné + catalogue live + capacités
  AVAILABLE + canary 1 € passé). Pas de full sans caisse.

Rationnel : interdire le smoke avant la caisse retarderait l'apprentissage
message ; autoriser le full sans caisse reproduit le fiasco actuel
(ventures en pause qui attendent l'encaissement).

**États DB** : `CANDIDATE → SMOKE_READY → SMOKE_RUNNING → SMOKE_DONE →
FULL_READY → FULL_RUNNING → SCALE | PIVOT | EXTEND | KILLED | INVALID_RETRY`.
Chaque transition = événement append-only + garde-fou déterministe + ticket
H quand requis (HYPOTHESIS, VETO_AMONT).

---

## §2 — Prospection multicanal (validé)

### §2.0 Modèle : campaign/audience, pas contact (validé)

L'unité de travail universelle est la `campaign`, pas le contact
(le contact ne marche pas pour la pub, le contenu, les marketplaces).

```text
venture
  └── campaign (1 test sur 1 canal : N, seuils, fenêtre — cf. A)
        ├── AUDIENCE (liste de contacts OU audience pub OU lieu public)
        ├── TOUCHES (chaque exposition : email, appel, impression, post)
        ├── ENGAGEMENTS (chaque réaction : réponse, clic, upvote, brief)
        └── INTENTS (chaque signal d'achat : meeting, devis, objection, trial)
```

Trois familles d'audiences, même funnel de mesure (U1-U5) :

| Famille | Exemples | U1 (toucher) | Particularité |
|---|---|---|---|
| **Nommée** | Email, voix, LinkedIn 1:1, SMS | Délivrés/connects/accepts | Séquences, cooldowns OUTBOUND, consentement individuel |
| **Ciblée anonyme** | Meta/Google/LinkedIn/Reddit Ads | Impressions viewables, clics | Budget, enchères, créas ; opt-in à la conversion |
| **Lieu** | SEO, Reddit orga, PH, marketplaces, contenu | Vues, visites, briefs reçus | Pas de quota d'envoi — gate = qualité + standing |

Le **contact** est un cas particulier : audience nommée de N individus.

### §2.1 Régimes OUTBOUND / INBOUND (validé)

Deux régimes distincts — un cooldown mécanique ne doit jamais bloquer une
réponse urgente.

- **OUTBOUND** (Serge initie) : cooldowns stricts, 1 touch à la fois,
  quotas, séquences. Protections anti-harcèlement.
- **INBOUND** (le prospect a parlé en premier ou répondu) : **pas de
  cooldown mécanique**. SLA à la place (1h ouvrée, §4). Le prospect qui
  engage a ouvert la porte — la ralentir artificiellement, c'est perdre
  la vente (speed-to-lead).

Transition : un contact passe en INBOUND au premier signal entrant et y
reste tant que la conversation est active (silence < X jours, X en policy,
défaut 7). Retour en OUTBOUND si silence prolongé — cooldowns réappliqués.
En INBOUND, quotas/fenêtres/consentement restent (pas d'appel à 3h), mais
cooldowns inter-touches et "1 touch à la fois" sautent.

### §2.2 Adaptateurs canal : un contrat unique (validé)

Un module par canal (P1, < 500 lignes). Contrat :

```python
def can_send(target, message) -> GuardVerdict:
    """Quotas, fenêtres, consentement, cooldown, standing. Idempotent."""

def send(target, message) -> Receipt:
    """Idempotent (idempotency_key) + coût logué."""

def poll(since) -> list[NativeEvent]:
    """Boîte mail, CDR voix, DM LinkedIn, webhooks... dédup idempotente."""
```

`send` prend une cible polymorphe (contact OU audience OU lieu).
Guards communs : venture ACTIVE, fenêtre de test ouverte, N/budget non
atteint, idempotence. Consentement individuel et cooldowns : famille nommée
uniquement. Détail par canal :

| Canal | `can_send` spécifique | `poll` remonte |
|---|---|---|
| Email | Quota 30-50/j/mailbox, warmup OK, bounce < 2 %, opt-out | Réponses, bounces (codes SMTP), plaintes FBL |
| Voix | NPV, heures Paris, consentement/contrat, ≤ 4/30j (`serge/voice/policy.py`) | CDR, transcriptions, DTMF, répondeurs |
| LinkedIn | Compte chauffé, plafonds connect/InMail, cooldown thread | Réponses, accepts, standing compte |
| SMS/WhatsApp | Opt-in documenté, template approuvé (WA), STOP | Réponses, opt-out, block rate |
| Reddit/commu | Ticket PUBLICATION approuvé, karma/standing, ratio 90/10 | Réponses, upvotes, suppressions modo |

### §2.3 State machine famille nommée (validé)

```text
NEW → QUALIFIED → CONTACTING → ENGAGED → INTENT → MEETING|CUSTOMER
  │        │            │            │         │
  │        └─→ REJECTED (non-ICP, logué + raison)
  │                     └─→ UNREACHABLE (N tentatives, canaux épuisés)
  │                                  └─→ OPTED_OUT / BLOCKED (définitif)
  └─→ INVALID (bounce, faux numéro → ne compte pas dans N)
```

Transitions par événements (`email.replied`, `call.connected`,
`optout.received`...), code enum fermé + `requested` libre (P3).

### §2.4 State machine famille pub (validé)

```text
DRAFT (créas + ciblage + budget plancher ; VETO si nouveau canal)
  → REVIEW (créas conformes ? tracking OK ? budget enveloppe ?)
  → LEARNING (dépense le plancher, PAS de décision avant significativité :
     ~50 clics ou 7 jours — validé Q4a)
  → OPTIMIZING (U4 connu → ajustements bornés, 1 variable à la fois)
  → SCALING (U4 < seuil rentable → paliers +50 % max — validé Q4b)
  → PAUSED (budget épuisé, garde-fou, décision alloueur — réversible 1 clic)
  → KILLED (plancher dépensé + 0 intent + U5 pauvre → archiver + leçon)
  → INVALID (tracking cassé, compte restreint, créa rejetée → fixer, ne compte pas)
```

**Créas : 3 paliers de confiance (validé Q4c).**
- Palier 1 (démarrage ~1 mois) : batch hebdo en 1 ticket (5-10 créas,
  veto par créa), défaut 48h = tout part sauf veto.
- Palier 2 (0 veto sur 20 créas) : auto si templates approuvés + banque
  d'images + checkers déterministes verts (pas de promesse non sourcée,
  pas de marque tierce, mots interdits, mentions légales, landing
  cohérente) + échantillonnage 1/5 en ticket FYI avec screenshot.
- Palier 3 (palier 2 propre 2 mois) : full auto dans les bornes, batch
  mensuel récap, kill-switch par campagne. Bornes modifiables via POLICY
  uniquement. 1 veto sérieux en palier 2 → retour palier 1 (2 semaines).
- Filets permanents : rejet plateforme → pause variante + leçon + ALERT si
  pattern (3/semaine) ; plainte → pause + ticket ; CTR < 10 % benchmark
  7 jours → pause auto + candidat-leçon.

### §2.5 State machine famille lieu (validé)

```text
SCOUTED (lieu identifié via écoute J)
  → WARMING (compte/profil en chauffe : contributions, pas de lien — 3+ sem.)
  → ACTIVE (publication selon playbook + tickets PUBLICATION validés)
  → COMPOUNDING (rapporte en passif : SEO, thread, briefs entrants)
  → COOLDOWN (standing dégradé, saturation, pause volontaire — veille maintenue)
  → ABANDONED (lieu mort/banni/inadapté → archiver + leçon)
```

- **Capital standing (validé Q4d)** : chaque lieu/compte a un capital
  (karma, ancienneté, avertissements, taux suppression). Publier coûte,
  être bien reçu recharge. `can_publish` vérifie le capital, pas un quota.
  **Perte importante → leçon obligatoire** (prioritaire consolidation).
- **Surveillance COMPOUNDING (validé Q4e)** : job déterministe quotidien +
  ALERT si anomalie (thread qui tourne mal, SEO qui chute, avis négatif).
- **Voie rapide (validé Q4f)** : juge LLM automatique («C») choisit voie
  lente (chauffe 3 sem.) vs rapide (profil pro direct : marketplaces,
  annuaires, PH) selon lieu bien décrit. Déclaration P2 obligatoire.

### §2.6 Séquenceur + alloueur (validé)

**Séquenceur contact** (familles nommées) : lit contact + état + historique +
séquence YAML → prochain `work_item` READY. Règles : 1 touch à la fois par
contact (OUTBOUND), amplification voix (appel même non connecté → re-priorise
follow-up email, ×2), attribution multi-touch (intent → touche déclenchante +
précédentes, pour U4 par canal). Séquence de départ : email → voix →
LinkedIn (modifiable par venture). Follow-ups : *quand* déterministe,
*quoi* en LLM avec contexte mémoire complet (validé en A).

**Alloueur inter-familles : mix A+B+C (validé Q3, sans hystérésis).**

- **Couche A — garde-fous déterministes (0 token, non négociables)** :
  planchers de significativité garantis ; plafonds (30 % max sur campagne
  non prouvée, 60 % max sur un canal — en policy) ; réserve opportunité
  20 % ; ordres irréversibles → tickets H ; budget lu en policy chaque
  cycle. Proposition hors bornes → **clampée** + loguée ("proposé X,
  clampé Y, règle Z"). Pas d'hystérésis (trop complexe, exceptions
  ingérables) — remplacée par : **le juge justifie tout revirement**
  (> 10 points contre le sens précédent → 1 phrase obligatoire) ;
  3 oscillations sans raison → candidat-leçon auto.
- **Couche B — bandit Thompson Sampling (0 token, continu)** : bras =
  campagnes, récompense = intent pondéré (barème A) moins coût. Mise à
  jour à chaque événement. Exploration/exploitation mathématique.
  Limites assumées : pas de *pourquoi*, pas d'interactions, inexplicable.
- **Couche C — juge LLM (quotidien + déclenché)** : reçoit état complet +
  proposition B. Valide/ajuste (interactions voix→email, leçons, contexte
  trunk/maintenance...), décide les mouvements discrets (lancer, pauser,
  proposer KILL → ticket, allouer réserve), **explique en français**
  (1 phrase/décision). Écart > 15 points vs B → justification étendue
  loguée (= leçon candidate : juge vs maths, qui avait raison ?).
- Déclencheurs en plus du quotidien : budget à 80 %, seuil kill/scale,
  ALERT, signal d'écoute chaude, oscillation bandit.

### §2.7 Budget dynamique (principe transverse validé)

Le budget mensuel (et tous plafonds/seuils/fenêtres/quotas/pourcentages)
est lu depuis `config/policy.yaml` à chaque cycle, **jamais codé en dur**.
Passer de 50 € à 200 € = 1 changement policy (ticket POLICY si proposé par
Serge, direct si Julien) + propagation automatique. Test R4 : aucun montant
codé en dur hors policy. **Tout le décisionnel est paramétrique** — le code
ne contient que de la logique.

---

## §3 — Funnel builder (validé)

Pipeline à gates. Chaque gate peut rejeter avec un code ; rejets bornés.

```text
SPEC (quoi, pour qui, critères d'acceptation — typée, obligatoire)
  │ [VETO_AMONT si nouveau produit ; auto si déclinaison]
  ▼
BUILD (génération : code, copy, assets)
  ▼
GATE 1 — checks déterministes (0 token, millisecondes)
  │ HTML valide · viewport mobile · pas de lorem ipsum · CTA présent
  │ mentions légales · perf (poids, temps) · liens morts · secrets absents
  │ → REJECT avec codes enum (MISSING_CTA, LOREM_IPSUM, BROKEN_LINK...)
  ▼
GATE 2 — review LLM multimodale (jugé unique «C», déclaration P2)
  │ Entrées : code/HTML + SCREENSHOTS rendus (desktop + mobile, Chromium
  │ headless) + SESSION D'INTERACTION pour produits interactifs (clics,
  │ formulaires, navigation — sandboxée, jamais de mutation externe).
  │ Verdict enum : SHIP | FIX (liste bornée, max 5 items) | REBUILD.
  │ Juge DISTINCT du builder (pas d'auto-complaisance : prompts/sessions
  │ séparés, idéalement modèles différents). Verdict sur le RENDU RÉEL.
  ▼
STAGE (déployé en staging, URL privée)
  ▼
GATE 3 — validation humaine progressive
  │ Builds 1-5 : spot-check Julien (ticket + screenshots). Puis trust zone :
  │ auto si gates 1+2 verts + métriques OK.
  ▼
PUBLISH → artifact versionné immuable (v1, v2...) + URL canonique + log
```

- **Boucle bornée à 3 passes** : BUILD → G1 → G2 → BUILD, 3× max par
  livrable. **Passe 3 (dernière)** : warning injecté dans les deux prompts
  (builder : "plus de réécriture globale, corrige la liste FIX par impact" ;
  reviewer : "binaire SHIP ou REBUILD-abandon, plus de FIX ; réserves =
  dette explicite"). Échec passe 3 → ticket QNA (historique complet, 3
  verdicts, screenshots, recommandation) — toi seul débloques une passe 4.
- **Dette visuelle explicite** : SHIP avec réserves → dette rattachée à la
  version (v1-dette-hero), visible Mission Control, candidate v2, jamais
  oubliée silencieusement.
- **Versioning immuable** : jamais de modif en place — v1, v2... = A/B
  naturel + U5 ("v2 avec prix affiché convertit 2×").
- **Scope** : landings, pages, packs digitaux, templates, docs, scripts
  automation client, configs (n8n, agendas). Pas d'infra lourde sans
  VETO_AMONT.

---

## §4 — Funnel observation (validé, repris multicanal)

**3 couches.** Chaque canal a sa physique ; l'unification se fait au niveau
des intentions, pas des messages.

### Couche 1 — Collecteurs natifs (1 module/canal, déterministes)

| Canal | Événements natifs |
|---|---|
| Email | RECEIVED (headers), BOUNCED (codes SMTP), COMPLAINED (FBL), OPENED, CLICKED |
| Voix | MISSED, CONNECTED (durée), VOICEMAIL_LEFT, DTMF_1, CALLBACK_REQUESTED, NUMBER_INVALID, TRANSCRIPT |
| LinkedIn | INVITE_ACCEPTED, REPLIED, PROFILE_VIEWED, POST_ENGAGED, RESTRICTED |
| SMS/WhatsApp | DELIVERED, READ, REPLIED, OPTED_OUT, BLOCKED, FAILED (codes opérateur) |
| Reddit/commu | REPLIED, UPVOTED (agrégé), AWARDED, REMOVED (modo), DM_RECEIVED |
| Pub | CLICKED, CONVERTED, LEAD_FORM, DISAPPROVED, SPENT |
| Marketplaces | BRIEF_RECEIVED, MESSAGE, MISSION_AWARDED, REVIEW_LEFT |
| SEO/contenu | VISIT (source/page/durée), SIGNUP, TRIAL, DOWNLOAD |

Chaque événement : canal, type natif, timestamp, acteur (ou anonyme), payload,
coût, receipt/preuve.

### Couche 2 — Normaliseurs (physique du canal → 8 signaux + OTHER)

| Signal | Sens |
|---|---|
| TECH_OK / TECH_FAIL | Infra saine/cassée (délivrabilité, trunk, standing, tracking) |
| SEEN / ENGAGED | Exposé passif / réaction sans intent clair |
| REPLIED | Réponse avec contenu → CLASSIFY |
| INTENT | Signal d'achat (meeting, devis, objection, trial, achat) |
| NEGATIVE | Refus explicite (+1 : preuve de lecture) |
| OPT_OUT | Ne plus contacter (immédiat, global) |
| OTHER | Non classable → file d'examen (juge LLM «C» en batch → reclasser ou proposer nouvelle catégorie → ticket Discord) |

- **Pas de filtre temporel global** : détection par headers/codes/preuves
  (SMTP, opérateur, provider), pas par "répondu en < 3 min". Le temps est
  un **modificateur de score** (réponse en 2 min = chaleur, pas robot).
- **Règle de sur-classement (validée)** : en cas de doute, vers le haut
  (REPLIED plutôt que AUTO). Faux positif = centimes de LLM ; faux négatif
  = vente perdue. Asymétrie totale.

### Couche 3 — Routeur universel (aveugle au canal)

| Signal | Routage déterministe |
|---|---|
| TECH_FAIL | Santé canal + pattern (3×/sem) → ALERT + leçon. Hors compteurs business. |
| SEEN/ENGAGED | Compteurs U1/U2, pas d'action (sauf nurture programmée). |
| REPLIED | CLASSIFY (LLM «C», enum P3 + requested) → SCORE (barème A) → intent ? file réponse : nurture/close. |
| INTENT | File réponse prioritaire (SLA 1h ouvrée 8h-20h Paris) + U3 + attribution multi-touch. |
| NEGATIVE | SCORE + close polie auto + candidat-leçon. |
| OPT_OUT | Blocage immédiat + accusé. < 1 cycle, P0 si raté. |

- **U1-U5 calculés ici**, depuis signaux universels. LLM classe, code compte.
  Définitions (implémentées dans `serge/funnels/metrics.py`) : U1 = touches
  envoyées ; U2 = signaux ENGAGED+REPLIED ; U3 = signaux INTENT (seul
  "positif" des seuils) ; U4 = coût EUR / U3 (dépense brute si U3=0) ;
  U5 = classes distinctes non vides (+ verbatims bruts). N valide = U1
  hors contacts INVALID.
- **Réponses full auto dès jour 1** (pas de spot-check) — exigence : traçabilité
  totale après coup (DB + Mission Control, audit post-hoc).

---

## §5 — Funnel collect (validé : strict, boring, fiable)

```text
PRICE_OWNED (prix + offre + identité légale, ticket VETO_AMONT)
  ▼
CATALOG_READY (produit/prix Stripe live OU template facture ; check déterministe)
  ▼
CANARY_1EUR (owner→owner 1 € bout en bout, webhook rapproché ; 1×/rail → capacités AVAILABLE)
  ▼
READY (= gate collect-first pour les tests full)
  ════════════════════════════════════════════
  Par transaction :
  INTENT_TO_CHARGE
    → QUOTE_DRAFT → QUOTE_SENT → QUOTE_SIGNED (si requires_quote — B2B pro ; sinon direct)
    → INVOICE_DRAFT (montant catalogue/offre, JAMAIS inventé)
    → ISSUED (facture numérotée sans trou, mentions légales — FR — OU PaymentLink ; idempotent)
    → SENT → PAID (webhook signé OU virement rapproché) | OVERDUE | CANCELLED
    → RECEIPT (reçu stocké, ledger DB, rapprochement ; factures conservées 10 ans)
```

- **Pas de prix → pas de facture** → ticket QNA, jamais de contournement ni
  de prix par défaut. L'owning du prix est une étape obligatoire.
- **Relances bornées (validé)** : OVERDUE → J+7 (polie) → J+14 (ferme,
  conséquences annoncées) → STOP + ticket. 2 max, opt-out respecté.
- **Remboursements (validé)** : < 5 € auto + FYI ; ≥ 5 € ticket systématique.
- **Sandbox/live séparés** : tests = rail sandbox uniquement ; live = vraies
  transactions + canary 1 €. Canary marqué comme tel dans le ledger.
- **Rapprochement** : écart (montant, intent inconnu, double paiement) →
  ALERT + ticket, jamais silencieux.
- Offres avec `requires_quote: true` (missions 990 €) vs direct (abo 29 €).

---

## §6 — Gardes transverses (validé)

Un seul module `guards/`, une seule interface, appelé avant toute mutation
externe. Toutes déterministes, en DB, loguées.

1. **Consentement/blocklist** : store unique (qui, base, preuve, date,
   révocation). Effet immédiat global (< 1 cycle). Bloctel : import
   **mensuel** (validé) + check pré-appel voix. Violation = bug P0.
2. **Quotas** : par canal/jour, par contact/30j (≤ 4, légal FR), par
   venture (N smoke/full), global €/jour. Fenêtres glissantes en DB.
   Dépassement = refus + code + **report auto au lendemain** ; atteint
   **2 jours d'affilée → ticket FYI** (signal "augmenter ?").
3. **Fenêtres** : voix 10h-13h/14h-20h Paris ouvrés, quiet hours notifs
   (23h-8h, paramétrable), prospection lun-ven hors fériés FR (réutiliser
   le calcul du kit). Hors fenêtre = replanifié, pas annulé.
4. **Cooldowns** : contact (OUTBOUND uniquement), thread (X jours/lieu),
   compte (standing). Ne bloquent jamais une réponse INBOUND (SLA).
5. **Idempotence** : `idempotency_key` sur toute mutation (email :
   message_id ; appel : request_id ; paiement : intent_id ; post : hash
   contenu+lieu+fenêtre). E2E systématique P5 (passe 1× + retry no-op).
6. **Expiry universelle (invariant absolu validé)** : tout état d'attente a
   un TTL + un défaut (pause propre, replanification, escalade). Aucune
   attente infinie nulle part.

Interface unique :

```python
def check(action: OutboundAction) -> GuardVerdict:
    """Point de passage unique avant toute mutation externe.

    Returns:
        ALLOWED ou DENIED avec code enum fermé (QUOTA_EXCEEDED,
        OUTSIDE_WINDOW, NO_CONSENT, COOLDOWN_ACTIVE, DUPLICATE_IDEMPOTENT,
        BUDGET_EXCEEDED, STANDING_LOW...) + next_retry_at + requested (P3).
    """
```

Verdicts logués (qui, quoi, décision, code, timestamp) → métriques santé
(taux de refus par code → alerte si anomalie).

---

## Débordements assumés vers C et D (à trancher, pas ici)

**→ C (matrice LLM/déterministe).** Points LLM candidats repérés, checklist
P2 à remplir : qualifier prospect, classifier réponse, rédiger slots et
follow-ups, review builder gate 2, résumer test, router ordres owner, juger
"grosse conséquence", clustering écoute, juge alloueur (quotidien +
déclenché), juge OTHER (batch), juge voie WARMING rapide/lente,
scoring intent ambigu.

**→ D (mémoire).** Chaque transition écrit un événement épisodique ; chaque
sortie SCALE/PIVOT/KILL/EXTEND produit un candidat-leçon ; objections →
playbooks ; échecs typés → pitfalls ; pertes standing/bans → leçons
obligatoires. Consolidation 3j lit ces candidats, Julien dispose.

**→ H (tickets).** Gates ouvrant des tickets : HYPOTHESIS (full),
VETO_AMONT (venture/produit/prix), GUICHET (CAPTCHA marketplace, OAuth
client...), PUBLICATION, QNA (rejets builder ×3, cas limites),
ALERT (trunk down, ban, anomalie financière).
