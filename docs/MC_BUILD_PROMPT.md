# MISSION CONTROL v2 — Prompt de réécriture complète (Serge en kit)

> **Destinataire** : agent WSL (repo `serge-v2`, base tag `v0` + patchs `v0.1`/`v0.2`).
> **Auteur du prompt** : agent VPS, après exploration exhaustive du legacy (`/home/serge/serge-system`,
> ~12 000 lignes de monitoring) + du kit + de la charte + capture « avant ».
> **Langue de travail** : français, dense. Toda la UI owner en français (voir §8.5).

---

## §0. Mode d'emploi de ce prompt + règles de travail

1. **Le legacy n'est PAS accessible depuis WSL.** Tout ce qu'il faut en savoir est **inliné
   ci-dessous** (§2-§4 + annexes). Les pointeurs `fichier:ligne` legacy servent à demander un
   extrait exact via Julien (VPS vivant, lecture seule) si un point bloque. Ne jamais deviner
   un comportement legacy : demander l'extrait.
2. **Remplacer, pas migrer** (`docs/INTERACTION_ARCHITECTURE.md` §11, `docs/LEGACY_REUSE.md`
   option C) : le code v2 est **neuf sous charte**. Rien du legacy n'entre sans choix explicite
   de Julien, tracé dans `docs/LEGACY_REUSE.md` (source, quoi, pourquoi, ce qu'on a laissé).
   Les seuls cherry-picks pré-autorisés sont listés au §8.7 (données tarifaires + concepts).
3. **Charte non négociable** : P1 (1 fichier = 1 responsabilité, < 500 lignes de logique),
   P2 (frontière LLM/déterministe ; le MC est 100 % déterministe — 0 point LLM dans le MC,
   pas même pour formuler : les textes FR sont des templates/gabarits), P3 (structures typées ;
   la prose owner/agent n'est jamais parsée pour décider), P4 (SQLite = autorité, tools partagés,
   pas de JSON d'état intermédiaire), P5 (E2E comportement passant + refusé), R1 (commits < 300
   lignes de code prod — **JS + CSS + Python comptent tous**), R2 (docstrings Google, `ruff`,
   `ty`, pre-commit), R3 (phase rework : **aucune nouvelle dépendance** — ni pip ni npm —
   sans discussion avec Julien ; donc **stdlib Python + vanilla JS**, pas de framework),
   R4 (policy unique + fenêtre MC), R5 (bloc P1-P5 review dans chaque message de commit).
4. **Gates** : `ruff check`, `ruff format --check`, `ty check`, `scan-repo-secrets.py`,
   `python3 -m unittest discover -s tests` — verts avant chaque commit.
5. Les numéros de ligne kit ci-dessous réfèrent le VPS (`v0` + 1 commit) : **dérive possible**
   après `v0.1`/`v0.2` — retrouver par symbole, ne pas faire confiance aveuglément.
6. **Livrables** : code + tests + `docs/MISSION_CONTROL.md` (le doc manquant — spec + guide
   utilisateur FR) + MAJ `docs/INSTALL.md` / `docs/INSTANCE_CONTRACT.md` si le câblage change.

---

## §1. Objectif & vision (1 page)

**Contexte.** Le live legacy est éteint (2026-09-09, units down + KILL_SWITCH). Son Mission
Control (2 serveurs, 1 page scrollable, ~2 350 lignes de `ui.py` monolithique) était la référence
fonctionnelle : vue live, graphe/îlots, KPIs, introspection agents, voix, funnel économique.
Le kit `serge-v2` (scheduler SQL, tickets 13 types, funnels déterministes, matrice ~29 points LLM,
mémoire 5 couches, voix S2S, bot Discord, collect Stripe) **ne contient aujourd'hui aucun code
Mission Control** : seulement des exigences dispersées dans les docs (§1.2) + un template systemd
qui pointe encore vers le legacy. Le bot Discord est le seul « miroir » existant.

**Objectif.** Construire le Mission Control v2 **neuf sous charte** : multi-pages, temps réel,
FR-first, parité totale avec Discord, et une identité visuelle enfin originale — **« Jarvis-like »** :
HUD sombre animé (canvas découplé des ticks de données), îlots lumineux, transitions, zéro platitude
générique. Et surtout : **le bug qui tue l'animation à chaque heartbeat ne doit jamais revenir**
(§4.2 : cause racine + contrat + tests).

**Principes produit (rappels constitutionnels).**
- H §1 : **DB = vérité, UI = projections temps réel.** Jamais l'inverse. Thread/post supprimé →
  re-projection. Le MC ne stocke aucun fait métier hors SQLite (+ `runtime_flags`, §8.1).
- H §8 : **parité Discord ⇄ /owner** — tout acte faisable d'un côté l'est de l'autre, mêmes outils,
  mêmes événements. Discord = rapide/mobile ; /owner = confortable/complet.
- H §1.6 : **FR + contexte + belle UI.** Jamais de pavé brut, jamais d'ID opaque visible, remise
  en contexte systématique (où on en est, pourquoi on me parle, ce qu'on attend de moi).
  Serge raisonne en anglais en interne ; le FR est une **couche de présentation**.
- **Entonnoir général → spécifique** : chaque page part du général et fore jusqu'au détail
  (pensées agents, décisions fines, historique complet). **Tout chiffre est cliquable** vers sa
  source. Aucun cul-de-sac, aucun JSON brut visible (§10).

### §1.2 Exigences constitutionnelles explicites (à toutes satisfaire)

| # | Exigence | Source |
|---|---|---|
| E1 | Page `/owner/tickets` : même liste/états/actes que Discord + vue diff (policy, R1) + historique + recherche/filtres + fenêtre `requested` P3 + fenêtre `config/policy.yaml` | H §8 |
| E2 | Fenêtre « Policy » R4 : voir/modifier, même schéma de validation, historique (qui/quand/avant→après), rollback 1 clic. Julien applique ; Serge/Meta-Grok proposent (diff + raison) | Charte R4, `config/policy.yaml:3` |
| E3 | Topologie `[testing]` TOML modifiable via MC **uniquement à froid** (0 campagne RUNNING), lock ailleurs | `INSTANCE_CONTRACT` §testing, `kit/instance_file.py:223-224` |
| E4 | Fenêtre `requested` P3 : « demandes d'évolution » + contexte, lecture owner | Charte P3, H §8 |
| E5 | Métriques tickets : temps médian de réponse par type, taux approbation, expirations/semaine, tickets/semaine (+ §12 : rejets, auto-approbations, bypass, GUICHET résolus/expirés, backlog) | H §9, §12 |
| E6 | Métriques charte : LOC total, plus gros fichier, appels/tokens LLM par cycle (médiane + dérives), **tokens/€ de revenu**, `requested` non traités, recalls JSON, E2E passant/refusé par capacité | Charte §Métriques |
| E7 | Liens signés expirables pour écrans sensibles (ex. stream CAPTCHA GUICHET) — jamais de contenu brut/PII | H §10 + §15 |
| E8 | Auth MC = token existant (`owner_dashboard_token`, sidecar) ; feature `owner_ui` | H §10, `instance-inventory.yaml:243`, `kit/units.py` |
| E9 | Dette builder visible MC, candidate v2, jamais oubliée silencieusement | `FUNNEL_ARCHITECTURE:297` |
| E10 | Traçabilité totale des réponses full-auto : DB + MC, audit post-hoc | `FUNNEL_ARCHITECTURE:365` |
| E11 | Voix : CDR + transcriptions + métadonnées par appel (`state/voice/`), **écoute owner post-hoc via MC**, providers temps réel alignés MC (xAI primary, OpenAI rollback), kill manuel P5 | `PHONE_VOICE_SMS:156-179`, `LLM_MATRIX` P5 |
| E12 | Digest MEMORY Discord qui déborde → « +N leçon(s) sur Mission Control » : le MC pagine/rend TOUTES les leçons | `serge/discord/render.py:247` |
| E13 | Surface publique derrière ingress (8790 loopback), projection fail-closed | `instance-inventory.yaml:390`, template systemd |
| E14 | Tools partagés scheduler/workers/MC : une seule implémentation, un seul comportement | Charte P4 |
| E15 | Champ `note` (1 phrase) : logs humains et MC **uniquement** | Charte P3 |

**Gaps connus à combler** (n'existent pas dans `v0`, à créer) : app HTTP MC, writer
`policy_snapshots` (table prête, `serge/db/schema.py:172-176`), liens signés, éditeur testing à
froid, template systemd dashboard (l'actuel pointe `orchestrator/public_dashboard.py` legacy —
à réécrire), runtime trust zones (doc-only → MC affiche métriques + candidates, activation via
ticket POLICY en attendant le runtime).

---

## §2. Le legacy, en résumé utile (connaissance inline — WSL n'y a pas accès)

### §2.1 Architecture legacy (à NE PAS reproduire telle quelle)

- **2 serveurs** (confusion à tuer, §4) : MC V2 `monitoring/app.py` (796 l., port **8790**,
  `PublicHandler`, routes `/` + `/owner/*`) et diagnostic Tailscale
  `orchestrator/owner_dashboard.py` (932 l., port **8788**, mini-HTML « Private diagnostics »).
  V2 = un seul serveur 8790 loopback + ingress.
- **UI monolithique** `monitoring/ui.py` (2 354 l.) : HTML + ~400 l. de CSS + vanilla JS en
  template literals Python, `innerHTML` massif. À tuer (§4).
- **Snapshot** `monitoring/snapshot.py` (3 091 l.) : agrégation owner snapshot (graph, stats,
  meta-grok, KPIs, market tests...), cache TTL **1,5 s** opaque (`snapshot.py:139-140`).
- **Présentation** `monitoring/present.py` (1 601 l.) : géométrie du graphe, cartes
  venture/candidate, activité. Concepts graphe à reprendre, code non.
- **Voix** `monitoring/voice.py` (2 386 l.) + `voice_bus.py` (550) + `voice_providers.py`
  (332) : dock vocal owner → Meta-Grok, 20 outils (liste en annexe C).
- **Contrat de tests** `tests/test_mission_control.py` (2 413 l.) : ordre DOM imposé
  (safety → meta-grok → prompts → thoughts → controls → graph), auth, CSP voix.
- Captures « avant » : `state/web-ingress/visual-qa-owner/<timestamp>/desktop-1440x900.png`
  (demander via Julien pour comparaison avant/après).

### §2.2 Routes legacy (référence fonctionnelle)

| Path | Auth | Rôle | Devenir v2 |
|---|---|---|---|
| `/`, `/api/state`, `/api/stream` (SSE 2 s) | non | Page + snapshot + stream publics | Gardé (fail-closed, §8.4) |
| `/healthz`, `/robots.txt`, `/favicon.*` | non | Sondes/robots | Gardé |
| `/owner/login` (GET/POST) | token form → cookie 12 h | Login | Gardé, + rate-limit (§8.4) |
| `/owner`, `/owner/api/state`, `/owner/api/stream` | owner | Shell + snapshot + SSE owner | Gardé, resegmenté par page (§6, §8.3) |
| `/owner/api/task-trace?task_id=` | owner | **JSON brut** (tâche, events, reviews, context packets) | → renderer timeline §10 |
| `/owner/api/meta-grok-run?run_id=` | owner | **JSON brut** (artefacts run) | Non-objectif v1 (pas de Meta-Grok) |
| `/owner/api/voice/*` (status, prefs, events, jobs, session, tools, end, presence, ack, memory) | owner | Statut/providers/prefs/bus/sessions temps réel | Page Voix v1 = CDR/écoute/qualité/kill ; dock conversationnel = v2 (question Q1, §15) |
| `/owner/api/runtime-controls` (POST) | owner | Mutations limiters/approvals | Concept gardé : POST d'actions typées → §9 |
| `/owner/challenge/{token}` + `/owner/api/challenge/{token}` + `/frame.png` | owner | Page CAPTCHA humain + ops click/type/done + capture | → liens signés §15 (GUICHET) + renderer, plus de JSON nu |
| `/meta-grok/discord-interactions` | proxy loopback | Forward Discord | Sans objet (bot Discord neuf `serge/discord/`) |

### §2.3 Sections du dashboard owner legacy (le « quoi » à reprendre, mieux organisé)

Ordre legacy : safety → meta-grok → prompts → thoughts → controls → graph → ingress/tokens →
portfolio/candidates → stats → activity → voice-dock. Contenu par section :
- **Hero live** (`#now`) : rôle actif, headline, scheduler, chips (role/tool events, cycles),
  pastille connexion. → page Live §6.
- **Safety/finance/approvals** : KV bruts (`kill_switch`, `autonomous_loop`, `policy_max_eur`
  + boutons `Yes/No` EN). → pages Santé/Économie/Tickets, labellisés FR, actes typés.
- **Meta-Grok live** : run state, crédit, inbox, wake, historique runs, alerte analyse.
  → non-objectif v1 (hooks seulement).
- **Introspection agents** (`#owner-prompts`, `#owner-thoughts`) : prompts workspace + thought
  stream sanitizé, fail-soft. → page Cerveau §6, pensée = texte d'origine + contexte FR.
- **Runtime controls** : rate limits (lecture/édition), approvals. → pages Politique/Santé §9.
- **Graphe/îlots** (`#graph`, SVG recréé à chaque tick — **le bug**, §4.2) : spine sémantique,
  rework lane, arêtes live animées `dash`. → page Système, canvas rAF découplé §8.2.
- **Ingress/tokens** : hostnames publiés, tokens lifetime/today + USD estimé. → Santé/Économie.
- **Portfolio/candidates** : cartes venture/candidate + statuts. → Système/Économie (ventures kit).
- **Stats groupés + chips** (~40 KPIs, §2.4) : groupes Activité/Portefeuille/Marché/Économie/
  Funnel/Fiabilité + chips avancés. → reventilés par page §7.
- **Activity feed** (`#feed`, lien « trace » → JSON brut). → Live + renderer timeline §10.
- **Voice dock** (`#voice-dock`, bas de page fixe) : parler/stop/muet/transcription/téléchargement,
  sélecteur provider, voix, proactive. → v2 (Q1).
- **Mailbox observation** : injecté dans sched-detail/activity (pas de panneau). → Cerveau/Live
  (signaux `inbound_events`).

### §2.4 Catalogue KPI legacy → équivalent kit (table de reprise — prescriptive)

Chaque ligne : KPI legacy → définition v2 → source kit exacte → page v2 → fraîcheur.

| KPI legacy | Définition v2 | Source kit | Page | Fraîcheur |
|---|---|---|---|---|
| Cycles aujourd'hui | Cycles `run_once` terminés (succès/échecs) + en cours | **À créer** : `events` kind=`cycle` (résumé par run, §8.7) | Live | live |
| Activité today (durées agents) | Durée cumulée calls LLM/jour par point | `llm_usage` (`schema.py:177-185`) | Cerveau | live |
| Tokens today/lifetime + USD | Tokens in/out + coût estimé (tarifs) | `llm_usage` + **tarifs portés** (données `pricing.json` legacy, §8.7) | Économie | live |
| Rôle courant | « Ce qui se passe maintenant » : work_item RUNNING (kind, venture, depuis) + file READY | `work_items` + `scheduler.py` | Live (hero) | live |
| Ventures by lifecycle | Comptes par état (CANDIDATE→SMOKE→FULL→SCALE/PIVOT/KILL...) | `ventures` + `funnels/lifecycle.py:124-212` | Système | live |
| Candidats WAITING | Ventures CANDIDATE + campagnes DRAFT | `ventures`, `campaigns` | Système | live |
| Comms PREPARED/SENT/BLOCKED | Touches par statut/conclusion + refus guards | `touches` + `events` kind=`guard` (**à créer**, §8.7) | Système | live |
| Prospects | Contacts par statut (NEW→...→CUSTOMER), régime IN/OUTBOUND | `contacts` + `funnels/contacts.py:79-239` | Système | lent |
| Actions externes SUCCEEDED | Envois/appels/pubs aboutis | `touches`, `ticket_events` (PUBLICATION), CDR voix | Économie | lent |
| Outbox pending | `email.send`/`voice.send` READY + campagnes RUNNING | `work_items`, `campaigns` | Live | live |
| Dépenses réglées/mois, revenus, récurrent, marge | Depuis intents/transactions + abonnements + coûts LLM | `transactions`, `subscriptions`, `accounts_standing`, `llm_usage`, `policy.budget` | Économie | lent |
| Funnel éco 17 étapes | **Ne pas porter** les 17 étapes. V2 : entonnoir kit = lifecycle venture × U1-U5 (`funnels/metrics.py:21`) × intents collect (`collect/intents.py:68-197`) — avec la règle evidence-strict legacy (pas d'upgrade sans receipt) | `ventures`, `funnels/metrics`, `transactions` | Économie | lent |
| Succès/échecs work | DONE/FAILED par kind, retries, `fail()` avec `retry_at` | `work_items` + `scheduler.py:148-214` | Système | live |
| Blocages humains | Tickets OPEN par type + urgents (GUICHET TTL < 15 min, veto < 1 h) + ALERT | `tickets`, `ticket_events` | Live + Tickets | live |
| Classes action exécutables | Matrice capacités × garde-fous (E2E passant/refusé par capacité, P5) | Tests + `guards/check.py`, verdicts `reasons.py` | Santé | statique+CI |
| human_block_count | = Blocages humains (ci-dessus) | `tickets` | Live | live |
| market_test pending/cooling | Campagnes DRAFT/RUNNING/PAUSED + cooldowns | `campaigns`, `campaigns.py:69-209` | Système | live |
| tool_calls | Calls LLM par point (volume, latence, verdict) | `llm_usage` | Cerveau | live |
| compute_reservations | **Non-objectif v1** (lié Meta-Grok) — hook | — | — | — |
| email_actions_by_status | Workers `email.send`/`email.poll` : volumes, erreurs, dernier poll | `work_items`, `workers/send.py:84`, `workers/poll.py:87` | Système | live |
| Ingress/hostnames | Units actives, ports, tunnels/ingress, dernier déploiement | `kit/units.py`, systemd (sonde lente), instance TOML | Santé | lent |
| Approvals pending | Tickets OPEN + expiries proches + défauts annoncés | `tickets` + `ticket-types.yaml` | Tickets | live |
| Rate limits | Quotas policy vs consommation (email/j, voix/j, LLM €/j) + jauges burn-down | `policy.quotas/budget` + `llm_usage` + `touches`/CDR | Politique | live |
| Tokens/€ de revenu | Coût cognitif par euro gagné → tend vers 0 (E6) | `llm_usage` + `transactions` | Économie | lent |
| Recalls JSON, malformés | % recalls par point, `LLM_OUTPUT_MALFORMED` | `llm_usage` (verdicts) | Cerveau | lent |
| `requested` non traités | Demandes d'évolution P3 en attente | `events`/`tickets` REQUESTED (selon stockage — vérifier `tickets/shared.py`) | Mémoire | live |
| Consolidation due | Prochaine consolidation 3 j, dernier run, ticket MEMORY en cours | `memory/consolidate.py`, `summaries`, `tickets` | Mémoire | lent |
| Clusters d'écoute hot | Clusters Jaccard chauds (J1) | `listen_docs`, `listen/cluster.py:125` | Cerveau ou Live | lent |
| Trust candidates | Types avec approbation > 95 % sur ≥ 20 tickets → candidates auto | `ticket_events` (calcul dét, E5/H §9) | Politique | lent |
| Drift versions | gog, modèles LLM, schéma DB, tag déployé | Sondes lentes + `schema.py:14` | Santé | lent |
| Quiet hours actives | Fenêtre courante + prochain digest | `policy.windows/quiet_hours`, `tickets.digest_hour` | Tickets | live |
| Bypass utilisés | Ordres `--force` + FYI post-hoc | `ticket_events` OWNER_ORDER | Tickets | lent |
| Backups/disk/certs | Dernier backup, espace disque, expiry TLS | Sondes lentes (optionnel mais recommandé) | Santé | lent |

### §2.5 Temps réel legacy (garder le pattern, tuer les défauts)

- SSE `GET /api/stream` tick **2,0 s** (`app.py:322-326`), fetch initial + bootstrap HTML
  `window.__SERGE_BOOT_STATE` (premier paint sans attendre), `?snapshot=1` désactive le stream
  (QA visuelle), polling voix séparé 2,5 s, cache serveur TTL 1,5 s **opaque** (à rendre transparent).
- Client : `EventSource` → `render(json)` global. **C'est ce render global + `innerHTML` qui tue
  les animations** (§4.2).

### §2.6 Auth legacy (reprendre le pattern, adapté sidecar)

Token fichier (`~/.config/serge/secrets/owner-dashboard.token`) → V2 : `owner_dashboard_token`
du sidecar age (`schemas/serge.secrets.manifest.yaml:17-20`). Bearer OU header
`X-Serge-Owner-Token` (`hmac.compare_digest`) OU cookie session 12 h (SQLite). Login POST → cookie
`HttpOnly`, path `/owner`. Legacy 8788 (cookie `serge_owner_dash`) : **supprimé** (1 seul serveur).

### §2.7 Voix legacy (référence pour la page Voix + hooks v2)

Providers : **xAI** défaut (`wss://api.x.ai/v1/realtime`, `grok-voice-think-fast-2.0`) /
**OpenAI** rollback (WebRTC, `gpt-realtime-2.1-mini`) — mêmes providers que la cible kit P5
(`PHONE_VOICE_SMS:156-160`, `serge/voice/realtime.py:4`). Prefs (voix, provider, proactive, seuil,
kiosk), bus jobs/events/présence, session (1 concurrente, 40 tool calls, TTL 15 min), 20 outils
(annexe C). V1 : CDR/écoute/qualité/kill (§6 page Voix). Dock conversationnel : v2 (Q1).

### §2.8 Projection publique fail-closed (garder + tester)

`public_projection.assert_public_safe()` : toute fuite suspecte → document minimal. V2 : même
contrat, tests d'assertion dédiés (aucun secret/PII/ID opaque/token dans le JSON public).

---

## §3. Bonnes idées legacy à garder (10)

1. **Projection publique fail-closed** (§2.8) — sécurité par défaut, testée.
2. **SSE simple + bootstrap HTML** (§2.5) — premier paint immédiat, complexité minimale (pas de WS).
3. **Registre KPI avec source canonique + fraîcheur** (`snapshot._kpi_registry`) — V2 : chaque KPI
   affiche sa source et son âge (« à jour il y a 4 s ») ; âge > seuil → grisé + tooltip.
4. **Funnel evidence-strict** (pas d'upgrade sans receipt) — repris dans l'entonnoir kit (§2.4).
5. **Graphe sémantique** (spine, lanes, arêtes typées — `present.py`) — repris en canvas interactif.
6. **Introspection fail-soft** (`owner_introspection.py`) — si les pensées/prompts manquent, la page
   dégrade gracieusement, jamais d'erreur bloquante. Généraliser : **tout widget dégrade**.
7. **Préservation de l'état UI local** (`OWNER_UI.touched`, drawer ouvert) à travers les ticks —
   généraliser : scroll, drawers, formulaires, Naga? non — formulaires, onglets, graphe (viewport).
8. **Mutations = POST d'actions typées** (`runtime-controls`) — repris : toute mutation MC est un
   POST typé, idempotent, audité (§9).
9. **`?snapshot=1` + QA visuelle scriptée** (legacy `visual-qa-*.py` + PNGs `state/web-ingress/`) —
   reprendre le pattern pour la non-régression visuelle (desktop + mobile).
10. **Ordre DOM safety-first** (sécurité/approbations avant le reste) — repris : Live = urgents
    d'abord,ß jamais de vanity metrics avant les décisions dues.

---

## §4. Anti-patterns à tuer (10 + le bug) — chacun avec règle + test anti-récurrence

| # | Anti-pattern legacy | Cause racine | Règle v2 | Test anti-récurrence |
|---|---|---|---|---|
| A1 | `ui.py` 2 354 l. (HTML+CSS+JS en strings Python) | Pas de frontière front/back | P1 strict : Python ≤ 500 l./fichier, **assets statiques sur disque** (`serge/mc/static/…`), HTML généré ≤ shell bootstrap | Test taille + test « aucun `.py` ne contient `innerHTML` ni `<div` au-delà du shell » |
| A2 | **Le bug heartbeat** (§4.2) | `svg.innerHTML` à chaque tick | Contrat §4.2 (patch par signature, anims rAF découplées) | Tests §4.2 |
| A3 | Double serveur 8788/8790, 2 cookies, 2 logins | Sédimentation | **Un seul serveur**, un seul cookie, une seule route login | Test : 1 seul `http.server` instancié ; grep anti-`8788` |
| A4 | `innerHTML` partout (feed, stats, approvals) | Render global naïf | Patch DOM ciblé par `data-sig` ; `innerHTML` interdit sur conteneurs animés/vivants (allowlist : conteneurs remplacés wholesale ET non animés, ex. page statique Santé) | Test statique JS : `innerHTML` uniquement dans `patch.js` (le module autorisé) |
| A5 | i18n par maps ad hoc (`FIELD_LABELS`, `frenchWaitCopy`) | Pas de source unique | **Module i18n central** (§8.5) : toute chaîne UI passe par lui | Test FR : crawl des clés + 0 chaîne EN hors allowlist (test + hook pre-commit léger) |
| A6 | Pages détail = JSON brut (`task-trace`, `meta-grok-run`) | Pas de renderer | **Tout endpoint détail a son renderer** (§10) ; JSON = export explicite via bouton | Test : chaque route `/owner/api/*` détail a une page/routeur front ; E2E « pas de `Content-Type: application/json` sur une navigation » |
| A7 | Cache snapshot 1,5 s opaque (désync SSE invisible) | Perf sans observabilité | TTL explicite + `X-Snapshot-Age` + âge affiché par widget (§2.4, règle R3) | Test : header présent ; E2E âge affiché |
| A8 | Styles inline + CSP `unsafe-inline` | CSS dans Python | **Design system CSS sur disque**, CSP stricte **sans** `unsafe-inline`/`unsafe-eval` | Test : headers CSP sur chaque page ; build qui échoue si `style=` dans le HTML servi |
| A9 | Mélange EN/FR (§7 legacy : `Yes/No`, `role events`, `Apply`...) | Pas de gate | Gate §8.5 + relecture FR des gabarits (exemples interdits en annexe D) | Test A5 + revue gabarits |
| A10 | `build_snapshot` dupliqué (2 chemins de données) | P4 violée | **Projecteurs uniques** : 1 fonction pure par section, partagée SSE/fetch/boot (§8.1) | Test P4 : `render_boot == fetch_state == premier_event_SSE` (même payload, même sig) |

### §4.2 Le bug heartbeat — autopsie et contrat de non-récurrence (CRITIQUE)

**Mécanisme legacy (6 étapes, vérifié dans le code).**
1. Tick SSE (2 s) → `es.onmessage` → `render(json)` global (`ui.py:1568`).
2. `render()` appelle **systématiquement** `renderGraph()` (`ui.py:1316`), même si le graphe n'a pas changé.
3. `renderGraph()` fait `svg.innerHTML = ...` : **remplacement intégral du DOM SVG** (`ui.py:939-948`).
4. Les arêtes « live » portent une animation CSS `@keyframes dash` (`ui.py:118,173`).
5. Recréer le DOM **réinitialise l'animation** à chaque tick → le flux ne « coule » plus (stroboscope / animation perçue comme désactivée).
6. Aggravant : le cache serveur 1,5 s renvoie souvent le **même JSON** deux ticks de suite → réécriture `innerHTML` identique mais animation quand même tuée.

**Contrat v2 (non négociable).**
- C1. Chaque section du payload SSE porte une **signature** (`sig` = hash stable du contenu canonique). Le client ne touche au DOM d'une section que si `sig` a changé.
- C2. **Anims découplées des données** : les animations (flux des arêtes, pulsation du noyau, compteurs) tournent en `requestAnimationFrame` continu ; les ticks de données ne font que mettre à jour des **attributs/classes**, jamais recréer les nœuds animés.
- C3. Tick identique ⇒ **zéro mutation DOM** (observable : MutationObserver compte 0 sur tick rejoué).
- C4. Graphe/îlots en **canvas** (pas de SVG recréé) OU SVG à nœuds persistants + update d'attributs. Canvas recommandé (performances + effets Jarvis).
- C5. Préservation : viewport graphe, scroll, drawers, formulaires en cours, état UI local survivent aux ticks (généralisation de `OWNER_UI.touched`).

**Tests exigés.**
- T1 (serveur) : projecteur pur — même DB ⇒ même `sig` ; DB changée ⇒ `sig` changée (par section, indépendantes).
- T2 (serveur) : rejouer 2 ticks identiques ⇒ payloads `sig`-égaux (précondition du skip client).
- T3 (client, Node si dispo sur WSL sinon QA scriptée) : harness qui rejoue 2 ticks identiques dans le `store`/`patch` et assert **0 mutation DOM** (compteur via MutationObserver). Si pas de Node : le faire dans le script QA visuelle (naviguer, geler le stream, comparer screenshots à 2 s d'intervalle hors zones animées volontaires).
- T4 (E2E visuel) : capture à T et T+6 s (3 ticks) — les zones de données stables sont pixel-identiques, les zones animées (flux, pulsation) ont bougé. C'est LE test du bug Julien (« heartbeat désactive l'affichage dynamique ») : il doit être **rouge sur le legacy, vert sur v2**.

---

## §5. Vision UI « Jarvis-like » — définition opposable

« Jarvis-like » n'est pas un adjectif, c'est cette spec. Tout écart = proposition à Julien.

**Ambiance.** HUD sombre, profondeur (pas plat) : fond radial très sombre bleu-nuit, panneaux verre
dépoli (blur + bordure lumineuse 1 px), accent cyan (#35e0ff familier) + orange signal (#ff9a3c)
pour le « live/chaud », vert/bleu sémantiques (succès/info), rouge réservé aux urgents. Typographie :
une fonte technique pour les chiffres/labels (monospace ou condensed système — **pas de webfont
externe**, offline-first, CSP stricte), une fonte lisible pour la prose FR.

**Mouvement (le cœur du brief).**
- Hero Live : **noyau d'état** (canvas) — pulsation dont le rythme/couleur = état système
  (calme = bleu lent, travail = cyan, urgent = orange rapide, erreur = rouge) + anneau d'activité
  (cycles récents) + waveform des dernières 24 h (touches/calls/tickets).
- Îlots Système : nœuds lumineux + **arêtes animées qui coulent** (débit ∝ activité réelle :
  work_items/h, calls LLM/h), survol = détail, clic = drill-down. Tout en canvas rAF continu.
- Compteurs qui **défilent** (pas de saut sec), barres qui **glissent**, sparklines partout où il y
  a une série (coûts, tokens, tickets/semaine, latences), transitions 150-250 ms, squelettes au
  chargement (jamais de page blanche), toasts FR pour chaque acte (« Ticket approuvé — exécution… »).
- **Règle d'or** : aucune animation n'est pilotée par un tick réseau (§4.2 C2). Les ticks mettent
  à jour des valeurs cibles ; le rAF interpole.

**Densité & langue.** Dense mais hiérarchisé (entonnoir, §6). Tout libellé/bouton/message en
**français** (voir §8.5). Chiffres `fr-FR` (espaces, virgules), dates relatives FR (« il y a 2 min »,
« dans 12 min »), fuseau Europe/Paris explicite. Pensées agents : texte d'origine (souvent EN) +
1 ligne de contexte FR systématique.

**Navigation.** Barre latérale (ou supérieure) : les 9 pages + recherche globale **Ctrl+K**
(palette : aller à un ticket/une venture/un KPI/une action — « approuver », « pause scheduler »…).
Breadcrumb + bouton retour sur chaque détail. Desktop-first, mobile utilisable (QA visuelle les deux,
comme le legacy).

**Interdictions UI.** Thème générique plat (Bootstrap-like) ; `innerHTML` wholesale (A4) ; styles
dans Python (A1) ; texte EN hors allowlist (A9) ; JSON brut (A6) ; chiffre sans drill-down (§1) ;
page blanche au chargement ; animation pilotée par tick réseau (§4.2).

---

## §6. Architecture en entonnoir — plan des pages (9 + 1)

Convention par page : `route` — but. **Widgets** (liste). **Sources** (tables/outils/fichiers exacts).
**Fore vers** (drill-down). **Mutations**. **Fraîcheur** (live ≈ 2 s / lent 30-60 s / statique + refresh ciblé).

### P0. `/owner` — Vue Live (le « maintenant »)
- But : en 5 secondes : état, urgents, activité. Safety-first (§3.10).
- Widgets : noyau d'état animé + headline FR (« Serge traite… / attend… / dort ») ; urgents
  (GUICHET TTL < 15 min, veto < 1 h, ALERT non lues → actes inline) ; file (RUNNING + READY) ;
  feed temps réel (tickets, touches, calls, cycles — chaque item fore vers sa trace) ; jauges
  budgets du jour (LLM €/j, email/j, voix/j).
- Sources : `work_items`, `tickets`, `ticket_events`, `events` (cycle/guard/note), `llm_usage`,
  `policy` (quotas/budgets), `touches`/CDR.
- Fore vers : trace tâche (timeline §10), ticket, pages Système/Cerveau/Économie.
- Mutations : actes urgents inline (mêmes actes que Tickets), « mettre en pause » (Q4).
- Fraîcheur : live (feed + file + urgents) ; lent (jauges).

### P1. `/owner/system` — Îlots & santé des sous-systèmes
- But : le graphe — où en est chaque partie de Serge, d'un coup d'œil.
- Widgets : canvas îlots (scheduler, workers ×11 kinds, guards, funnels, collect, listen,
  allocator, sms, email/gog, discord-gateway, voix/bridge) — taille/lumière = activité, couleur =
  santé, arêtes = flux ; panneau îlot (clic) : KPIs, derniers verdicts, erreurs ; scheduler
  (prochain READY, `next_ready()` en direct) ; campagnes (DRAFT/RUNNING/PAUSED + cooldowns) ;
  contacts/ventures par état ; workers email (volumes, erreurs, dernier poll).
- Sources : `work_items`, `scheduler.py`, `campaigns`, `contacts`, `ventures`, `touches`,
  `events` guard, `workers/*`, `funnels/*`, sonde gateway Discord, bridge voix.
- Fore vers : venture/campagne/contact (fiche), kind worker (runs récents + erreurs), trace.
- Mutations : aucune directe (lecture + forages ; les kills vivent en Politique/Santé).
- Fraîcheur : live (îlots, file, campagnes) ; lent (contacts/ventures).

### P2. `/owner/mind` — Cerveau (pensées, décisions, points LLM)
- But : l'introspection — ce que les agents pensent et décident, jusqu'au détail fin.
- Widgets : thought stream (pensées + `note` P3 + contexte FR, fail-soft) ; décisions récentes
  (qualify, score, juge allocator, QNA…) avec entrées/sorties résumées ; matrice des ~29 points
  LLM (registre `llm-points.yaml` : rôle, checklist, budget, repli) × usage réel (volume, latence,
  verdicts, recalls, dérives vs médiane 7 j — alertes P2 « 3× la médiane ») ; signaux entrants
  (`inbound_events` + classification O1) ; clusters d'écoute hot (J1).
- Sources : `llm_usage`, `llm-points.yaml`, `events`, `inbound_events`, `listen_docs`,
  `lessons`/`playbooks` (contexte), `tickets` QNA.
- Fore vers : trace tâche (timeline complète : pensées → décisions → actes), point LLM (fiche :
  checklist, prompts, repli, historique 7 j), cluster (docs sources).
- Mutations : kill-switch par point (proposition §9 — runtime_flags + ticket POLICY auto).
- Fraîcheur : live (stream, décisions, signaux) ; lent (matrice, dérives).

### P3. `/owner/tickets` — Décisions (parité Discord, E1)
- But : la même vérité que Discord, en confortable/complet. **Règle : tout acte Discord est
  faisable ici et inversement, mêmes outils, mêmes `decision_id`.**
- Widgets : liste (filtres type/état/urgence, recherche, tri expiry) ; carte §17 FR (contexte,
  blocage, recommandation, conséquences Yes/No, impact, expiry + défaut) ; actes (boutons déclarés
  `ticket-types.yaml`, idempotents) ; vue diff (POLICY, R1_OVERRIDE, MEMORY items) ; historique
  complet (`ticket_events`) ; MEMORY : TOUS les items paginés (E12) ; GUICHET : lien signé vers
  l'écran (E7) ; métriques E5/H §12 + quiet hours + prochain digest.
- Sources : `tickets`, `ticket_items`, `ticket_events`, `ticket-types.yaml`, `policy` (digest_hour,
  quiet_hours).
- Fore vers : venture/campagne liée, policy concernée (POLICY), trace d'exécution (EXECUTED).
- Mutations : tous les actes (approve/reject/edit/discuter/…), items MEMORY (garder/modifier/jeter),
  `discuter` (fil de discussion — persister en `ticket_events`, affiché aussi côté Discord comme
  message de suivi : parité à spécifier finement au lot).
- Fraîcheur : live.

### P4. `/owner/memory` — Mémoire (5 couches + évolution)
- But : voir et curer ce que Serge sait et apprend.
- Widgets : 5 couches (`MEMORY_ARCHITECTURE.md`) — registres (comptes + forages), épisodes
  (`events`/`touches`, recherche FTS + `memory_search()`), leçons/playbooks/pitfalls (CRUD via
  tickets MEMORY — pas d'édition directe : toute leçon naît/modifiée/meurt par acte traçé),
  résumés + SERGE.md (versions + rollback, D2), consolidation (prochaine due, dernier run, ticket
  MEMORY en cours) ; **demandes d'évolution** `requested` P3 (E4, lecture + contexte + statut
  batch) ; archives 30 j.
- Sources : `ventures/contacts/campaigns/consents/blocklist/accounts_standing`, `events`,
  `touches`, `inbound_events`, `transactions`, `ticket_events`, `lessons/playbooks/pitfalls`,
  `summaries`, SERGE.md, `episode_archives`, `memory/*`.
- Fore vers : ticket MEMORY d'origine, épisode source, ticket REQUESTED.
- Mutations : aucune directe (curation = actes MEMORY) ; rollback SERGE.md = acte typé + audité.
- Fraîcheur : lent + refresh ciblé (consolidation, ticket MEMORY en cours).

### P5. `/owner/policy` — Politique & garde-fous (E2, E3)
- But : la fenêtre R4 — voir/modifier les nombres, en confiance.
- Widgets : éditeur `policy.yaml` par section (budget, quotas, windows, calling_zones,
  cooldowns, voice, tickets, memory — libellés FR + bornes + aide) ; validation **même schéma**
  (`serge/policy.py`) avant application, refus expliqués FR ; historique (qui/quand/avant→après,
  `policy_snapshots`) + **rollback 1 clic** ; propositions Serge (tickets POLICY : diff + raison +
  impact) ; topologie `[testing]` (E3 : édition **à froid uniquement**, lock visible si ≥ 1
  campagne RUNNING + test du lock) ; trust zones (métriques + candidates H §9, activation = ticket
  POLICY — runtime absent) ; jauges quotas vs consommation (burn-down).
- Sources : `config/policy.yaml` (+ `policy.test.yaml` si `SERGE_ENV=test`), `policy_snapshots`
  (**writer à créer**), `tickets` POLICY, instance TOML `[testing]`, `campaigns`, `ticket_events`.
- Fore vers : ticket POLICY source, campagne bloquante (lock testing), consommation détaillée.
- Mutations : édition policy (Julien direct ; snapshot avant/après auto), rollback, édition testing
  à froid, création ticket POLICY depuis une candidate trust zone.
- Fraîcheur : statique + refresh ciblé (post-mutation) ; jauges live.

### P6. `/owner/economy` — Économie (funnel, collect, coûts)
- But : l'argent — gagné, dépensé, en cours. Evidence-strict (§3.4).
- Widgets : entonnoir kit (lifecycle venture × U1-U5 × intents collect — §2.4, jamais de
  « revenu » sans receipt `transactions`) ; intents (`PRICE_OWNED→PAID`, dunning J+7/J+14,
  readiness) ; transactions + abonnements R3 (renouvellements suivis) ; coûts LLM (tokens/€,
  burn-down €/j et €/mois, par point, dérives) ; dette builder visible (E9) ; traçabilité
  réponses full-auto (E10, audit post-hoc : réponse → template/contraintes → envoi → réception).
- Sources : `ventures`, `funnels/metrics.py`, `collect/*`, `transactions`, `subscriptions`,
  `accounts_standing`, `llm_usage` + tarifs (§8.7), `policy.budget`, artifacts builder,
  `touches` + `workers/respond.py`.
- Fore vers : venture, campagne (U1-U5 détaillés), intent (chronologie), facture/receipt, réponse
  (audit E10).
- Mutations : aucune financière directe (tout flux passe par tickets/intents — constitution).
  `COLLECT_READINESS` = acte ticket.
- Fraîcheur : lent.

### P7. `/owner/voice` — Voix (E11)
- But : chaque appel — preuve, coaching, litiges, écoute owner.
- Widgets : CDR (liste : date, direction, durée, tours, verdict, coût) ; fiche appel (métadonnées,
  transcription, **écoute** post-hoc, script P4 vs réel, dérive) ; qualité (F4c : score, pause auto
  + FYI) ; bridge (état, originate, consentements) ; temps réel P5 (état session, tours/durée,
  détecteur dérive, **bouton kill manuel**) ; repli tour-par-tour (état AGI).
- Sources : `state/voice/` (CDR, enregistrements, transcriptions), `serge/voice/*`
  (`ledger.py`, `quality.py`, `bridge.py`, `turn.py`, `realtime.py`), `policy.voice`
  (rétention — **faire respecter** : purge affichée/auditée), `consents`/`blocklist`.
- Fore vers : contact/fiche, ticket lié (DTMF1), script P4.
- Mutations : kill manuel P5 (confirm + audit + FYI), pause voix (KILL_SWITCH §9).
- Fraîcheur : live (session en cours) ; lent (CDR).

### P8. `/owner/health` — Santé, charte & système
- But : Serge va-t-il bien ? Le code va-t-il bien ? Preuves à l'appui.
- Widgets : métriques charte E6 (LOC, plus gros fichier, appels/tokens par cycle + dérives,
  recalls, E2E par capacité, `requested` en attente) ; units systemd (pipeline, timers, discord,
  ingress, sms, MC lui-même — état + derniers logs ciblés, sonde lente, lecture seule) ;
  versions & drift (schéma DB, tag, gog, modèles) ; sécurité (backups, disque, TLS — recommandé
  §2.4) ; kill-switches globaux (§9 : LLM par point, voix sortante, pipeline) ; audit trail
  (tous les actes owner/MC : qui, quoi, quand, avant→après).
- Sources : repo (LOC — calcul lent, caché), rapports CI/tests, `llm_usage`, `events` audit,
  sondes systemd (lentes, timeout court, jamais bloquant), `KILL_SWITCH`, instance TOML.
- Fore vers : fichier (plus gros), test (E2E refusé), acte (audit), unit (logs).
- Mutations : kills (§9), pause scheduler (Q4).
- Fraîcheur : lent/statique + refresh ciblé.

### P9. `/` — Public (E13)
- But : vitrine fail-closed derrière ingress. Contenu : statut grossier (« systèmes
  opérationnels »), zéro chiffre sensible. **Interdit** : secrets, PII, IDs opaques, tokens,
  détails ventures/contacts, pensées, coûts fins.
- Contrat : `assert_public_safe()` sur chaque payload (concept legacy §2.8), tests adversariaux
  (fuzz champs DB → projection). 1 seul serveur, mêmes assets (thème), routes `/`, `/api/state`,
  `/api/stream`, `/healthz`, `/robots.txt`.

**Fils transverses (toutes les pages).** Ctrl+K ; toasts d'actes ; âge/fraîcheur par widget ;
lien « source » (table/outil) sur chaque KPI (registre §3.3) ; breadcrumb ; `?snapshot=1` ;
dégradation gracieuse widget par widget (§3.6) ; responsive desktop-first + mobile QA.

---

## §7. Catalogue KPI v2 — voir §2.4 (prescriptive, 30+ lignes)

La table §2.4 **est** le catalogue : chaque ligne = un KPI à implémenter sur la page indiquée,
avec la source et la fraîcheur indiquées. Y ajouter : sparklines (coûts, tokens, tickets/sem.),
médianes 7 j + alertes de dérive P2, et les compteurs H §12 (tickets/sem. par type, approbation/
rejet/expiry, auto-approbations, bypass, GUICHET résolus/expirés, backlog).

---

## §8. Architecture technique

### §8.1 Backend — package `serge/mc/` (stdlib uniquement, P1 strict)

Découpage indicatif (< 500 l. logique/fichier, 1 responsabilité — à ajuster, jamais à gonfler) :

```text
serge/mc/
  __init__.py      # version + exports
  server.py        # http.server, routage, statiques, headers sécu (≤ ~250 l.)
  auth.py          # bearer/cookie/login/logout/rate-limit (≤ ~200 l.)
  sse.py           # EventSource framing + signatures + suscripteurs par page (≤ ~200 l.)
  projectors.py    # socle : cache TTL explicite, sig(), âge (≤ ~200 l.)
  proj_live.py     # projecteurs P0 (+ public P9 + fail-closed) (≤ ~350 l.)
  proj_system.py   # P1 (≤ ~300 l.)
  proj_mind.py     # P2 (≤ ~300 l.)
  proj_tickets.py  # P3 (+ cartes §17) (≤ ~350 l.)
  proj_memory.py   # P4 (≤ ~300 l.)
  proj_policy.py   # P5 (+ snapshots/rollback) (≤ ~300 l.)
  proj_economy.py  # P6 (≤ ~300 l.)
  proj_voice.py    # P7 (≤ ~300 l.)
  proj_health.py   # P8 (≤ ~300 l.)
  actions.py       # POST typés → tools partagés + audit (≤ ~350 l.)
  signedlinks.py   # liens HMAC expirables E7 (≤ ~150 l.)
  i18n.py          # labels FR centraux + formats (≤ ~250 l.)
  audit.py         # append-only actes (events kind=mc_act) (≤ ~120 l.)
  flags.py         # runtime_flags : kills à chaud (≤ ~150 l.)
  static/          # assets §8.2 (app.js, pages/, components/, style.css…)
  templates/       # shell.html bootstrap uniquement (pas de logique)
```

**Règles backend.**
- B1. Stdlib `http.server` (comme le legacy) — **0 nouvelle dépendance** (R3). Threading :
  `ThreadingHTTPServer` + SSE non bloquant (queue par abonné).
- B2. **Projecteurs = fonctions pures** `(conn, policy, now) -> dict` sans effet de bord, un par
  section, partagés boot/fetch/SSE (A10). Signature : `sig = sha256(canonical_json(payload))[:16]`.
- B3. **Mutations = tools partagés** (E14) : `decide_ticket`, `expire_due_tickets`, `render_card`
  (contenu — factoriser le builder depuis `serge/discord/render.py` si besoin, renderer séparé),
  `validate_policy` (`serge/policy.py`), `_validate_testing` (`kit/instance_file.py`). **Jamais de
  logique métier dans `serge/mc/`** (H §7 : adaptateur sans logique).
- B4. `policy_snapshots` : **écrire le writer manquant** (snapshot avant/après à chaque mutation
  policy/rollback — E2). Placer le writer près de `serge/policy.py`, pas dans `mc/` (P1 : l'invariant
  appartient à la policy).
- B5. `runtime_flags` (proposition — Q3 si refusée, justifier l'alternative) : table
  `runtime_flags(name, value, set_by, set_at, expires_at, reason)` ; `registry.llm_enabled()` la
  consulte **avant** le YAML (override à chaud + TTL + ticket POLICY auto-créé pour persister) ;
  kill voix = `KILL_SWITCH` fichier (cohérent `voice/policy.py`) avec confirm ; pause pipeline =
  `KILL_SWITCH` pipeline (Q4) avec double confirm + FYI auto. Tout flag = audité + visible Santé.
- B6. Audit : chaque POST (acte, édition, kill, rollback, login) → `events` kind=`mc_act`
  (actor=owner, quoi, avant→après, decision_id). L'audit trail Santé lit cette source.
- B7. Erreurs : JSON FR `{erreur, code, aide}` + HTTP idoine ; jamais de traceback au client ;
  toute mutation invalide = 4xx + raison actionnable (chemin refusé, P5).

### §8.2 Frontend — vanilla ES modules (pas de framework, R3)

```text
serge/mc/static/mc/
  app.js            # boot, routage pages, shell (≈150 l.)
  store.js          # état + abonnements par section (≈120 l.)
  sse.js            # EventSource + backoff + fallback poll + ?snapshot + visibility (≈150 l.)
  patch.js          # SEUL module autorisé à toucher innerHTML (conteneurs statiques) ;
                    # patch par data-sig pour le reste (≈150 l.)
  i18n.js           # labels + Intl fr-FR + dates relatives (≈120 l.)
  hud.js            # canvas rAF : noyau, îlots, waveform, compteurs interpolés (≈250 l.)
  components.js     # toast, drawer, modal-confirm, sparkline, gauge, kbd (≈200 l.)
  cmdk.js           # palette Ctrl+K (≈120 l.)
  pages/live.js system.js mind.js tickets.js memory.js policy.js economy.js voice.js health.js
                    # 1 routeur+rendu par page (≈150-250 l. chacun)
  style.css         # DESIGN SYSTEM (§5) — 1 seul fichier, variables CSS (≈400-500 l. — lot dédié)
```

**Règles frontend.**
- F1. ES modules natifs, **0 build step, 0 dépendance**. `type="module"`, CSP sans `unsafe-*` (A8).
- F2. **Contrat §4.2** : `store.apply(section, sig, payload)` → skip si `sig` inchangée ; anims dans
  `hud.js` (rAF continu, valeurs cibles) ; `patch.js` = seul `innerHTML` (test A4).
- F3. SSE : `EventSource(/owner/api/stream?page=...)` + backoff exp reconnect + fallback
  `fetch` poll 5 s si SSE HS + `document.visibilitychange` (pause en onglet caché) +
  `?snapshot=1` (1 seul fetch, pas de stream — QA).
- F4. Formulaires (policy, testing) : état local préservé aux ticks (§3.7), validation miroir
  immédiate + validation serveur faisant foi, confirm modale pour les destructeurs (rollback,
  kills, pause), undo quand possible (rollback policy = l'undo naturel).
- F5. Accessibilité minimale : focus visible, `aria-live` sur toasts/urgents, navigation clavier
  (Ctrl+K, `/` recherche tickets, `?` aide), contrastes HUD vérifiés.

### §8.3 Protocole temps réel

- `GET /owner/api/stream?page=<p0..p8>` : `event: section\ndata: {"sig":…, "age_ms":…, "payload":…}\n\n`
  tick 2 s (sections live) ; sections lentes multiplexées (1 tick sur 15-30) + `X-Snapshot-Age`.
- `GET /owner/api/state?page=…` : même payload (1 shot, fetch initial + fallback).
- Boot : `window.__SERGE_BOOT_STATE` (même projecteurs — test A10).
- POST `/owner/api/actions` : `{action, params, decision_id}` → `{ok, decision_id, affected_sections[]}`
  → le client rafraîchit les sections affectées (pas de reload).
- Public : `/api/state`, `/api/stream` (même framing, projection fail-closed).

### §8.4 Auth & sécurité

- Bearer `owner_dashboard_token` (sidecar age, E8) OU cookie `serge_mc` 12 h `HttpOnly; Path=/owner;
  SameSite=Lax` (+ `Secure` derrière ingress TLS). Comparaison `hmac.compare_digest`. Un seul login.
- Rate-limit login : 10 essais/min/IP (nouveau vs legacy — à implémenter, testé).
- Jamais de secret/PII : hashes (`privacy.subject_hash`) + liens signés E7
  (`signedlinks.py` : HMAC-SHA256, `exp` ≤ TTL externe, one-shot quand pertinent, scope restreint
  — ex. `guichet:<ticket>` ; rejets testés : expiré, forgé, rejoué si one-shot).
- Public : `assert_public_safe` + tests adversariaux (§6 P9).
- Audit B6. Sessions : révocation (logout + rotation token via kit — documenter).

### §8.5 FR-first / i18n (tuer A9)

- `serge/mc/i18n.py` (+ miroir `i18n.js` — **décider et documenter** ;
  recommandé : Python = source, JS embarque un export JSON servi en statique, test de parité) :
  toute chaîne UI (labels, boutons, erreurs, enums → labels FR, aide contextuelle) y vit.
- Formats : `Intl.NumberFormat('fr-FR')`, dates relatives FR maison (« il y a 2 min », « dans 12 min »),
  fuseau Europe/Paris.
- Pensées agents : texte d'origine **tel quel** + 1 ligne contexte FR (« Pourquoi tu lis ça : … »).
- Enums → FR : lifecycle tickets (brouillon/ouvert/en discussion/approuvé/rejeté/édité/exécuté/
  clôturé/expiré/annulé), work_items, ventures, campagnes, contacts, verdicts guards, signaux,
  états voice (annexe A à compléter au lot 0).
- Gate : test qui échoue sur toute chaîne EN hors allowlist courte et justifiée (IDs techniques,
  noms de modèles, « Serge »…). Exemples interdits : annexe D.

### §8.6 Units/systemd/ports/kit

- **Un seul serveur** : réécrire `systemd/templates/serge-public-dashboard.service.in`
  (supprimer la réf legacy, unit `serge-mission-control.service` + doc du renommage), 8790 loopback,
  `features.owner_ui` existant (`kit/units.py`), `SERGE_INSTANCE_FILE` requis.
- `/healthz` (liveness, sans auth) ; logs structurés ; `ConditionPathExists` pipeline inchangée.
- MAJ `docs/INSTALL.md` + `INSTANCE_CONTRACT.md` si câblage/flags changent.

### §8.7 Petits ajouts runtime nécessaires (justifiés, R1 — pas de refonte déguisée)

| # | Ajout | Où | Pourquoi | Lignes ≈ |
|---|---|---|---|---|
| R-a | `events` kind=`cycle` (résumé `run_once` : traités, succès, échecs, expirés, durée) | `serge/runner.py` + test | KPI cycles + feed + waveform (aucune source sinon) | ~30 + test |
| R-b | `events` kind=`guard` (verdict + code + canal, sujet hashé) | `serge/guards/check.py` + test | Comms BLOCKED + audit E10 + matrice capacités | ~25 + test |
| R-c | Writer `policy_snapshots` (avant/après, qui, raison) | près de `serge/policy.py` + test | E2 historique + rollback | ~60 + test |
| R-d | Table `runtime_flags` + lecture dans `llm_enabled()` (override avant YAML) | `serge/db/schema.py` (migration v4), `registry.py`, `mc/flags.py` | Kills à chaud §9 (Q3) | ~80 + tests |
| R-e | Données tarifs : porter `pricing.json` legacy en **données** + moteur maigre | `serge/mc/tariffs.json` + ~40 l. | Coûts USD legacy-parité (exception P1 données/code) — **tracer LEGACY_REUSE.md** | ~40 + test |
| R-f | Export i18n Python→JSON pour `i18n.js` + test de parité | `serge/mc/i18n.py` + static | §8.5 sans duplication P4 | ~40 + test |

Si un ajout déborde son lot : ticket R1_OVERRIDE (E1 — dogfooding assumé).

---

## §9. Surfaces MODIFIABLES — contrats (1 par 1)

Toutes : POST typé + `decision_id` (idempotence) + validation serveur + audit B6 + toast FR +
refresh ciblé. Refus = 4xx + raison FR actionnable (P5 : tester passant ET refusé).

| # | Mutation | UI | Validation | Audit/rollback |
|---|---|---|---|---|
| M1 | Actes tickets (boutons `ticket-types.yaml`) | Carte P3 + inline Live + Ctrl+K | Mêmes outils que Discord (`decide_ticket`), états légaux, expiry non passée | `ticket_events` + `decision_id` (double-clic = 1 acte) |
| M2 | Items MEMORY (garder/modifier/jeter, tout-approuver) | P3 paginé (E12) | Idem + item existant | Idem, par item |
| M3 | Discussion ticket (`discuter`) | Fil P3 → `ticket_events` + suivi Discord | Non vide, ticket non clôturé | Event horodaté |
| M4 | Édition policy (E2) | P5 par section, bornes + aide | `validate_policy` (même schéma) ; refus expliqué | Snapshot auto avant/après + rollback 1 clic (M5) |
| M5 | Rollback policy | P5 historique | Snapshot existant | Nouveau snapshot (jamais d'écrasement) |
| M6 | Édition testing à froid (E3) | P5, lock visible si RUNNING | `_validate_testing` + 0 campagne RUNNING (re-vérifié serveur au POST) | TOML versionné (git) + event |
| M7 | Quiet hours / digest_hour | P3/P5 (via policy) | Plages cohérentes | M4/M5 |
| M8 | Kill-switch point LLM | P2 fiche point + P8 | Point existant, raison requise | `runtime_flags` + TTL + **ticket POLICY auto** (persister) + event |
| M9 | Kill voix P5 (appel en cours) | P7 session live | Session active | Confirm + event + FYI auto |
| M10 | Pause/reprise pipeline (Q4) | P0/P8, double confirm | — | Fichier KILL_SWITCH + FYI auto + event |
| M11 | Pause/reprise voix sortante | P7/P8, confirm | Fichier `KILL_SWITCH` + ticket lié | Confirm + event |
| M12 | Proposer en POLICY (depuis candidate trust zone / dérive quota) | P5, pré-rempli (diff + raison) | Diff non vide | Ticket POLICY créé (proposition, pas application — R4) |
| M13 | Lier/délier ? **Non** : mandat = lecture seule (INSTANCE_CONTRACT). Venture/campagne manuelles ? **Non v1** (création = VETO_AMONT). |

**Jamais modifiable depuis le MC** : mandat, secrets/PII, code/prompts (P2 : dossier `prompts/`, revue), données financières brutes (intents uniquement), passé (append-only).

---

## §10. Renderers de détail — tuer le JSON (A6)

| Ex-endpoint JSON legacy | Renderer v2 | Contenu rendu |
|---|---|---|
| `task-trace` | **Timeline tâche** (drawer/page) | Pensées → décisions → actes → verdicts, horodatés, avec `note` P3 + liens (venture, ticket, leçon) |
| `meta-grok-run` | Sans objet v1 | — (hooks) |
| Ticket | **Carte §17** (H §5) | Contexte, blocage, recommandation, Yes/No, impact, expiry+défaut — gabarit FR, zéro ID visible |
| Policy (proposition) | **Vue diff** | Avant→après par clé + raison + impact + boutons |
| R1_OVERRIDE | **Vue diff + dossier** | Pourquoi indécoupable + risques + boutons |
| `requested` | **Carte évolution** | Demande + contexte (tâche, venture, tentatives) + statut batch |
| Leçons (MEMORY) | **Liste paginée + recherche** | Toutes les leçons (E12), actes par item |
| CDR appel | **Fiche appel + player** | Métadonnées, transcription, écoute, script vs réel |
| Historique policy | **Timeline + rollback** | Qui/quand/avant→après + bouton |
| Cycle/run | **Résumé run** | R-a : traités/succès/échecs/expirés/durée + forages |
| Réponse full-auto | **Audit E10** | Template+contraintes → envoi → réception → décision aval |

Règle : **0 page JSON nue**. Chaque renderer a un bouton « Exporter JSON » (debug) — c'est le seul JSON visible, derrière un geste explicite. Test A6.

---

## §11. Phasage R1 (lots ≤ 300 lignes prod — JS+CSS+Python+TOML/yaml comptent)

Ordre imposé (dépendances). Chaque lot : code + tests + doc du lot (paragraphe dans `docs/MISSION_CONTROL.md`) + critères DONE. Estimation : ~13-15 lots.

| Lot | Contenu | DONE quand |
|---|---|---|
| 0 | `docs/MISSION_CONTROL.md` (squelette + i18n annexe A) + `server.py` + `auth.py` + shell + login + `/healthz` + tests auth (passant/refusé/rate-limit) | Login/logout OK, gates verts |
| 1 | `sse.py` + `projectors.py` (sig, TTL, âge) + `store/sse/patch` front + `?snapshot=1` + tests T1/T2/A10 | Ticks signés, skip testé |
| 2 | Design system `style.css` + `components.js` + gabarits FR de base + test CSP A8 + gate FR A5 | Page blanche stylisée, CSP verte |
| 3 | P0 Live (hero + urgents + file + feed + jauges) + R-a/R-b (cycle/guard events) + renderer timeline (§10) | Live temps réel, forages OK |
| 4 | `hud.js` (noyau, waveform, compteurs) + toasts + tests T3/T4 (QA visuelle v1) | **T4 vert** (le bug ne revient pas) |
| 5 | P1 Système (canvas îlots + panneau + scheduler + campagnes) | Îlots animés + drill-down |
| 6 | P2 Cerveau (stream + décisions + matrice + signaux + clusters) + kills M8 (R-d) | Matrice + dérives + kill testé |
| 7 | P3 Tickets (liste + carte + actes + diff + MEMORY paginé + métriques E5) + test parité Discord | Acte MC ≡ acte Discord |
| 8 | P4 Mémoire (5 couches + FTS + consolidation + `requested`) + rollback SERGE.md | Curation traçée |
| 9 | P5 Politique (éditeur + R-c snapshots + rollback + testing E3 + trust + jauges) + tarifs R-e | E2/E3 vertes, lock testé |
| 10 | P6 Économie (entonnoir + intents + coûts + audit E10 + dette E9) | Funnel evidence-strict |
| 11 | P7 Voix (CDR + fiche + player + qualité + kill M9 + pause M11) + `signedlinks.py` + GUICHET E7 | Écoute + liens testés |
| 12 | P8 Santé (charte E6 + units + drift + kills + audit) + M10/M12 + Ctrl+K global | Audit complet |
| 13 | P9 Public (projection + `assert_public_safe` + tests adversariaux) + unit systemd §8.6 + INSTALL/CONTRACT | E13, déployable |
| 14 | Polish (transitions, responsive, perfs) + QA visuelle complète (desktop+mobile, avant/après) + guide utilisateur FR final | §12 vert |

Règle lots : un lot qui menace 300 lignes se découpe (front/back séparés) AVANT de coder ; si vraiment indécoupable : ticket R1_OVERRIDE (E1 — dogfooding).

---

## §12. Tests & gates (P5 — comportement, pas implémentation)

**E2E HTTP (mock DB, 0 token, à chaque changement).** Pour chaque capacité : passant + refusé.
- Auth : login OK / token faux / expiré / rate-limit dépassé / accès `/owner` sans session / logout.
- Tickets : acte valide → `ticket_events` + sections affectées / double POST même `decision_id` = 1 acte / acte sur ticket clôturé → 4xx / acte expiré → 4xx + défaut appliqué.
- Parité : scénario « approve via MC » produit les mêmes `ticket_events` que « approve via Discord » (rejouer via `interactions.py` sur fixture sœur).
- Policy : édition valide → snapshot + appliquée / valeur hors schéma → 4xx + raison FR / rollback → snapshot N+1 / proposition Serge → ticket POLICY (jamais d'application directe).
- Testing : édition à froid OK / édition avec 1 campagne RUNNING → 4xx + lock visible.
- Liens signés : valide OK / expiré → 4xx / forgé → 4xx / rejoué (one-shot) → 4xx.
- Kills : kill point → `runtime_flags` + ticket POLICY auto + `llm_enabled()` faux / unkill → rétabli ; pause pipeline → fichier + FYI.
- Guards/cycles : R-a/R-b écrivent (passant) ; payload malformé → 4xx (refusé).
- Public : projection de fixtures adversariales (PII, secrets, IDs) → `assert_public_safe` OK, champs absents.
- SSE : 2 ticks identiques → sig égales (T2) ; `?snapshot=1` → 1 payload, pas de stream ; headers `X-Snapshot-Age` + CSP (A7/A8).
**Projecteurs purs** : fixtures DB → payloads golden (1 par page) + T1 (sig stables).
**i18n** : parité Python/JS (R-f), 0 EN hors allowlist (A5/A9 — aussi en pre-commit sur `mc/`).
**Structure** : P1 tailles (étendre `test_charter.py`), A1 (pas de HTML/JS dans `.py` hors shell), A3 (pas de `8788`), A4 (`innerHTML` ∈ `patch.js` uniquement).
**QA visuelle** : script `scripts/qa-mc-visual.py` (desktop 1440×900 + mobile 390×844, `?snapshot=1` + stream 6 s) → T3/T4 + comparaison avant/après (captures legacy VPS).
**Gates** : ruff, format, ty, scan secrets, unittest — verts par lot.

---

## §13. Critères d'acceptation (checklist — tout coché = livré)

- [ ] E1-E15 toutes satisfaites, chacune avec ≥ 1 E2E.
- [ ] §4.2 : T1+T2+T3+T4 verts (le bug heartbeat est mort, prouvé).
- [ ] Parité Discord : acte MC ≡ acte Discord (mêmes outils, mêmes events, `decision_id`).
- [ ] 0 page JSON nue (A6) ; 0 chaîne EN hors allowlist (A5/A9) ; CSP sans `unsafe-*` (A8).
- [ ] Tout KPI affiche source + âge ; tout chiffre fore vers sa source (§1).
- [ ] Chaque widget dégrade gracieusement (données manquantes ⇒ état vide FR, jamais 500).
- [ ] Ticks : état UI local préservé (C5) ; tick identique ⇒ 0 mutation DOM (C3).
- [ ] Mutations M1-M13 : toutes idempotentes, auditées, avec chemin refusé testé.
- [ ] Policy : rollback 1 clic démontré ; testing : lock RUNNING démontré.
- [ ] `docs/MISSION_CONTROL.md` complet (spec + guide FR + captures) ; INSTALL/CONTRACT à jour.
- [ ] QA visuelle desktop+mobile verte ; comparaison « avant/après » fournie à Julien.
- [ ] Commits R1 (≤ 300 l. prod) + blocs R5 ; `LEGACY_REUSE.md` tracé (R-e) ; gates verts.
- [ ] Déployable : unit systemd + feature `owner_ui` + `verify` instance OK sur la bêta WSL.

---

## §14. Non-objectifs v1 (explicites — hooks seulement)

Meta-Grok UI (page/section — prévoir l'emplacement) ; framework JS (R3 — proposition séparée si
voulu) ; édition mandat (lecture seule) ; création manuelle venture/campagne (VETO_AMONT) ;
flux financiers directs (intents/tickets uniquement) ; données publiques élargies ; mobile-first ;
multi-owner ; dock voix conversationnel (Q1) ; édition prompts P2 (dossier `prompts/`, revue).

---

## §15. Questions pour Julien (trancher avant/après lot 0 — avec recommandation)

- **Q1. Dock voix conversationnel (façade outillée comme le legacy) en v1 ou v2 ?**
  Recommandation : **v2** — E11 (CDR/écoute/kill) suffit en v1 ; prévoir le hook (bus + providers).
- **Q2. Skin/thème : valider la direction §5 (HUD cyan/orange) ou autre ?**
  Recommandation : **valider vite** (une capture du lot 2) pour ne pas repeindre au lot 14.
- **Q3. `runtime_flags` DB vs fichiers pour les kills à chaud ?**
  Recommandation : **DB** (requêtable, TTL, audit — §8.1 B5) ; fichiers = repli.
- **Q4. Bouton « pause scheduler » (KILL_SWITCH pipeline) dans le MC ?**
  Recommandation : **oui** (M10, double confirm + FYI) — c'est l'acte d'urgence naturel.
- **Q5. QA visuelle : Playwright (ou équivalent) en dépendance DEV (R3) ?**
  Recommandation : **oui, dev-only** (jamais en prod) — sinon QA manuelle + T3 Node si dispo.

---

## §16. Ordre de lecture conseillé (agent WSL)

1. Ce prompt en entier. 2. `docs/CODEBASE_CHARTER.md` (charte). 3. `docs/INTERACTION_ARCHITECTURE.md`
   (H — tickets/parité). 4. `docs/LLM_MATRIX.md` + `config/llm-points.yaml` (matrice). 5. `docs/MEMORY_ARCHITECTURE.md`
   + `docs/FUNNEL_ARCHITECTURE.md` + `docs/PHONE_VOICE_SMS.md` (domaines). 6. `serge/tickets/*`,
   `serge/discord/{render,interactions,mirror}.py`, `serge/policy.py`, `serge/registry.py`,
   `serge/scheduler.py`, `serge/runner.py`, `serge/db/schema.py` (code à réutiliser). 7. Questions
   (§15) + extraits legacy si besoin → via Julien. 8. Lot 0.

---

## Annexes

### A. Glossaire FR des enums (à compléter au lot 0 — source : `i18n.py`)

Tickets : DRAFT=brouillon, OPEN=ouvert, DISCUSSING=en discussion, APPROVED=approuvé,
REJECTED=rejeté, EDITED=édité, EXECUTED=exécuté, CLOSED=clôturé, EXPIRED=expiré, CANCELLED=annulé.
Work : READY=prêt, RUNNING=en cours, DONE=terminé, FAILED=échoué (+retry=nouvel essai planifié).
Ventures/campagnes/contacts : reprendre les états `funnels/*.py` + `campaigns.py` + `contacts.py`.
Guards : codes `reasons.py` → libellés FR + aide (« Quota dépassé — voir Politique »).
Signaux : `observe/signals.py` (8 + OTHER). Voix : états bridge/session + verdicts qualité.

### B. Captures legacy « avant » (VPS, via Julien)

`serge-system/state/web-ingress/visual-qa-owner/<timestamp>/{desktop-1440x900,mobile-390x844}.png`
(+ `scroll-*.png` du 19/08 08:11 : ingress, safety, limits). Demander les PNGs pour la comparaison
avant/après du lot 14.

### C. Les 20 outils voix legacy (référence hooks v2 — `monitoring/voice.py:122-414`)

`get_metagrok_status`, `get_current_activity`, `ask_metagrok`, `delegate_metagrok_job`,
`get_mission_control_context`, `get_recent_activity`, `get_pending_owner_decisions`, `inspect_entity`,
`submit_owner_instruction`, `get_owner_conversation_history`, `get_system_metrics`, `get_compute_cost`,
`get_xai_voice_cost`, `wake_metagrok`, `interrupt_metagrok`, `get_venture_outlook`,
`get_agent_prompt_status`, `get_metagrok_work`, `get_thought_protocol`, `end_voice_session`,
`show_mission_control`. Limites : 1 session, 40 tool calls, TTL 15 min. V1 : hooks (bus + providers
alignés P5) ; dock conversationnel : Q1/v2.

### D. Exemples legacy INTERDITS (A9 — ne jamais reproduire)

`Yes/No`, `role events`, `tool events`, `cycles`, `Apply`, `Read-only`, `Persistent`, `Temporary 24h`,
`Current:`, `Owner action needed`, `No stats in this window`, `No venture hostname published yet`,
`SELECTED and WAITING first so starvation is visible`, `Hostnames served by the generic multi-venture
ingress`, fallback headline Meta-Grok EN, `Validating` à côté de `En exploitation`. Tout libellé de ce
type existe en FR dans `i18n.py`, testé (A5).

---

*Fin du prompt. Base : tag `v0` + `v0.1` + `v0.2`. Bon courage — et que le heartbeat ne tue plus jamais
une animation.* 🖖
...[truncated 21852 chars]