# Mission Control v2 — miroir web owner

> Spec de construction : [`MC_BUILD_PROMPT.md`](MC_BUILD_PROMPT.md) (15 lots,
> contrats, tests). Ce document = vision + état + glossaire + décisions.
> Entonnoir : cette page résume, le prompt détaille, le code tranche.

## Vision (1 page)

Mission Control est le **miroir web temps réel** de Serge pour Julien :
9 pages owner + 1 publique, **parité totale avec Discord** (mêmes outils,
mêmes actes, mêmes `decision_id`), DB = vérité, UI = projections.
**FR-first** (Serge raisonne en anglais, le FR est une couche de présentation),
**Jarvis-like** (HUD sombre, canvas animé découplé des ticks, îlots lumineux),
**entonnoir général → spécifique** (tout chiffre fore vers sa source, 0 JSON nu,
0 cul-de-sac). Détail : prompt §1 + §5 + §6.

## État : lot 1b ✅ (temps réel complet)

| Lot | Contenu | État |
|---|---|---|
| 0a | Sessions + auth token/cookie + rate-limit + tests | ✅ |
| 0b | Serveur + shell/login + E2E HTTP + doc + prompt versionné | ✅ |
| 1a | Projecteurs + SSE + boot (T1/T2/A10) | ✅ |
| 1b | Front store/sse/patch + E2E navigateur + A4 | ✅ |
| 2a | Design system CSS base + validation skin Q2 (10/09) | ✅ |
| 2b | CSS HUD + sidebar + routeur hash + tests nav | ✅ |
| 2c | Composants + gate FR + CSP systématisée | ✅ |
| 3a | Events cycle + guard (R-a/R-b) + tests | ✅ |
| 3b | Projecteur P0 (hero/urgents/file/feed/jauges) + goldens | ✅ |
| 3c | Page live.js + routeur + E2E navigateur | ✅ |
| 3d | Endpoint trace + drawer timeline + tests | ✅ (ce commit) |
| 4-14 | HUD canvas, puis 8 pages → polish | ⏳ |

### Routes lot 0

| Route | Auth | Rôle |
|---|---|---|
| `GET /healthz` | non | Liveness JSON `{"status":"ok"}` |
| `GET /robots.txt` | non | `Disallow: /owner/` |
| `GET /favicon.ico` | non | 204 (pas d'erreur console) |
| `GET /owner/login` | non | Formulaire jeton |
| `POST /owner/login` | rate-limit 10/min/IP | Jeton → 302 + cookie 12 h, sinon 401 |
| `POST /owner/logout` | cookie | Révoque + clear + 302 login |
| `GET /owner` | owner (302 sinon) | Shell (santé live, routeur au lot 2) |
| `GET /static/mc/*` | non (assets génériques) | CSS/JS (whitelist ext, anti-traversal) |

### Auth (E8)

Token `owner_dashboard_token` (sidecar) : Bearer OU `X-Serge-Owner-Token`
OU cookie `serge_mc` 12 h `HttpOnly; Path=/owner; SameSite=Lax`
(sans `Secure` : loopback direct — voir §Décisions).
Sessions en `mc_sessions` (**hash SHA256, jamais brut**), `compare_digest`
partout, rate-limit login 10/min/IP (mémoire, fenêtre glissante).
Erreurs : HTML FR (navigations) / JSON FR (API), jamais de traceback.

### Décisions lot 0 (rappels opposables)

- D1. Sessions **hashées** en DB (défense en profondeur si fuite DB).
- D2. Rate-limit **en mémoire** (éphémère, pas un fait métier — redémarrage = reset).
- D3. Cookie **sans `Secure`** (loopback ; le flag viendra avec l'ingress TLS).
- D4. Templates **validés au boot** (`ValueError` si manquant — fail-fast, pas de 500).
- D5. **Zéro HTML dans `serge/mc/*.py`** (test A1) : erreurs login = blocs cachés
  révélés (`data-error`), pas de markup injecté.
- D6. Statiques **sans auth** (assets génériques, pas de données).

### Décisions lot 3 (rappels opposables)

- D7. Events cycle/guard **dans les commits existants** (pas de commit séparé) ;
  `check()` journalise (docstring « lecture seule » corrigée), `ValueError`
  appelant non loggée (bug, déjà visible).
- D8. Urgents = GUICHET <15 min + VETO <1 h + ALERT OPENISH ; `message_id`
  renommé (plus `gmail_id`) ; dédup compatible historique (OR).
- D9. Feed = events + ticket_events + touches (calls voix au lot 7, ledger
  séparé) ; jauges = LLM (estimation garde) + email (CDR voix au lot 7).
- D10. **Croissance `events` sans purge documentée** : point de vigilance
  (pas de code lot 3 — à trancher : rétention/archivage).
- D11. Actes urgents inline → **lot 7** (avec l'endpoint actions + parité
  Discord) ; la page Live v1 est lecture + navigation.
- D12. Timeline lot 3d = fiche + contexte (pas de chaînage causal fin :
  `llm_usage` sans `task_id` — noté, pas perdu).
- D13. Libellés FR + dates relatives en dur côté front → `i18n.js` lot 8.
- D14. Hero sans canvas (→ `hud.js` lot 4) ; milliers non formatés (→ lot 8).
- D15. Timeline = drawer générique réutilisé ; erreurs fetch = toast,
  jamais de page (cohérence lot 2c).

## Glossaire FR des enums (annexe A — source pour `i18n.py`)

Tickets : brouillon (DRAFT), ouvert (OPEN), en discussion (DISCUSSING),
approuvé (APPROVED), rejeté (REJECTED), édité (EDITED), exécuté (EXECUTED),
clôturé (CLOSED), expiré (EXPIRED), annulé (CANCELLED).
Travail : prêt (READY), en cours (RUNNING), terminé (DONE), échoué (FAILED),
nouvel essai planifié (`retry_at`).
Ventures : candidat (CANDIDATE), test à froid prêt/en cours/terminé
(SMOKE_READY/RUNNING/DONE), test complet prêt/en cours (FULL_READY/RUNNING),
mise à l'échelle (SCALE), pivot (PIVOT), prolongation (EXTEND), tué (KILLED),
réessai invalide (INVALID_RETRY).
Campagnes : brouillon (DRAFT), prête (READY), en cours (RUNNING ⇄ PAUSED
en pause), terminée (DONE), annulée (CANCELLED).
Contacts : nouveau (NEW), qualifié (QUALIFIED), contacté (CONTACTING),
engagé (ENGAGED), intention (INTENT), rendez-vous (MEETING), client (CUSTOMER),
rejeté (REJECTED), injoignable (UNREACHABLE), désinscrit (OPTED_OUT),
bloqué (BLOCKED), invalide (INVALID) ; régimes sortant (OUTBOUND) / entrant
(INBOUND).
Guards : autorisé (OK), doublon idempotent (DUPLICATE_IDEMPOTENT), bloqué
(BLOCKLISTED), sans consentement (NO_CONSENT), quota contact 30 j
(QUOTA_CONTACT_30D), hors fenêtre (OUTSIDE_WINDOW), canal inconnu
(UNKNOWN_CHANNEL).
Signaux : technique OK/échec (TECH_OK/TECH_FAIL), vu (SEEN), engagé (ENGAGED),
répondu (REPLIED), intention (INTENT), négatif (NEGATIVE), désinscription
(OPT_OUT), autre (OTHER).
Voix (partiel — détaillé au lot 11) : appel, journal d'appels (CDR),
transcription, écoute, score (1-5), pause automatique, kill manuel,
consentements, liste noire.

## Différé v2 (registre — rien ne se perd)

- Dock voix conversationnel (Q1 : E11 suffit en v1, hooks bus + providers).
- Meta-Grok UI (page/section — prévoir l'emplacement).
- Framework JS (R3 : vanilla imposé ; proposition séparée si voulu).
- Mandat éditable (lecture seule — contrat).
- Création manuelle venture/campagne (VETO_AMONT).
- Flux financiers directs (intents/tickets uniquement).
- Mobile-first (desktop-first + mobile utilisable).
- Multi-owner (un seul owner).
- Édition prompts P2 (dossier `prompts/`, revue).
- Trust runtime (v1 = métriques + candidates, activation via ticket POLICY).
- `?snapshot=1` + QA visuelle (lot 1+), design system (lot 2), streaming SSE (lot 1).

## Lots suivants

Voir prompt §11 (phasage), §12 (tests), §13 (acceptation). Prochain : lot 2
(design system + routeur + gabarits FR).

## Temps réel (lot 1a/1b)

- Enveloppe SSE : `event: section` + `{section, sig, age_ms, payload}`.
  Le nom voyage dans l'enveloppe (type unique, prompt §8.3).
- `sig` = SHA256 du JSON canonique (16 hex) ; **jamais de temps dans un
  payload signé** (l'âge voyage dans l'enveloppe, hors signature).
- Client : `store.apply` skip si sig égale (C3) → `patch` remplit les
  `[data-field]` (notation pointée) ; `?snapshot=1` = 1 fetch sans stream ;
  `window.__MC.stats` (applied/skipped/mode) pour debug et tests.
- Reconnect : backoff 1→30 s, fallback poll 5 s après 3 échecs, pause en
  onglet caché. DB rouverte par tick (vue fraîche, coût négligeable).
- Tests navigateur : skip gracieux si Chromium indisponible ; `wait_for_*`
  string interdit (eval bloqué par notre propre CSP — polling `evaluate`).

## Composants (lot 2c)

`components.js` : toast (auto 4 s), drawer, modale de confirmation (Promise,
Échap/clic-fond = non), sparkline SVG, jauge (create/update). DOM via
`createElement` uniquement (jamais `innerHTML` — A4, testé). Libellés FR
en dur (centralisation `i18n.js` au lot 8). Gate A5/A9 (`test_charter`) :
34 mots EN interdits dans le texte visible des templates + littéraux JS
(hors contextes techniques) — prouvé rouge→vert.

## HUD (lot 4)

`hud.js` : `etatSysteme` (calme/travail/urgent/erreur depuis hero +
urgents + tête de feed, `work.failed` en premier = erreur), noyau canvas
rAF piloté par valeurs cibles (jamais par tick — T1), `densite24h` +
waveform 24 h, `tweenNumber` (WeakMap, 1 tween/élément), `hudActives`
(testabilité). `data-etat` sur `.hero` (bordure orange/rouge si
urgent/erreur). T3 : tick rejoué sur DB figée = 0 mutation DOM
(MutationObserver, 2 ticks) ; T4 : zones stables pixel-identiques,
canvas animé diffère. Anti-fuite : `stop()` au unmount, navigations
p0→p1→p0 → compteur 1→0→1. Socle : `McBrowserCase` (Chromium partagé +
helpers — `McFrontTests` migre dessus, −57 lignes).

## Système P1 — îlots (lot 5a)

`proj_ilots.py` (299 lignes, R1) : 11 îlots {id, label, sante, activite,
resume} + scheduler (`next_ready` + compteurs). Santé : scheduler erreur
si READY débloqué non servi (ventures non schedulables, B5) ; workers
erreur si FAILED 24 h, degrade si RUNNING > 30 min ; collect erreur si
overdue ; email erreur si FAILED email.* 24 h. Allocator/discord/voix =
'inconnu' (fail-soft — câblages lots 6/12/11). 4 goldens (dont file
coincée et RUNNING suspect).

## Système P1 — campagnes (lot 5b)

`proj_campagnes.py` (125 lignes, style inline) : campagnes (état +
envoyés/touches par campagne) + cooldowns (`accounts_standing`), population
(contacts par funnel_state, ventures par lifecycle), email (volumes par
statut + dernière activité). Fixtures partagées via `ProjSystemFixtures`
(héritage, 0 duplication). 2 goldens.

## Système P1 — page îlots (lot 5c)

Route p1 : `system.js` (canvas 11 îlots + panneau + liste accessible).
`hud.js` : `startIlots` (1 boucle rAF, halo pulsé, taille = activité,
couleur = santé) + `dispositionIlots` pure (grille 4 colonnes, hit-test
clic) — boucle `boucle()` partagée avec le noyau (refactor, compteur
`hudActives` commun). Panneau : label + santé FR + résumé + détails
ordonnanceur (next/kind brut — libellés lot 8). Stream : sections p1
câblées (`population` lente 30 s). 5 tests (registre, rendu, clic bouton,
anti-fuite, clic canvas réel).

## Système P1 — sections (lot 5d)

`system.js` : rendus ordonnanceur (phrase next + compteurs data-field),
campagnes (états FR + cooldowns relatifs), population (contacts/ventures
triés), email (volumes + dernière activité). Mutualisation P4 : `li`,
`fillList`, `rel` déménagent dans `components.js` (live.js migre, −42
lignes nettes). 2 E2E (données + vides gracieux). P1 DONE : îlots animés
+ drill-down (fores externes aux lots fiches).

## Cerveau P2 — projecteurs lecture (lot 6a)

`proj_cerveau.py` : signaux (30 derniers inbound classés), clusters (hot
24 h, hors-cluster exclus), décisions (30 derniers appels LLM + verdicts),
pensées (stub fail-soft — aucun émetteur dans le kit), usage par point 7 j
(appels/tokens/latence/verdicts — base de la matrice). `proj_outils.py` :
`avant_iso` partagé (3e usage — `proj_ilots` migre, goldens verts).
Registre llm-points.yaml + dérives + kills M8 = lot 6b.

## Cerveau P2 — matrice (lot 6b)

`project_matrice` : registre `llm-points.yaml` (29 points réels) × usage
7 j complets (appels/tokens/latence/verdicts) + dérives J-1 vs médiane
J-8..J-2 (ratio > 3, volume puis tokens ; médiane nulle = activation,
pas dérive). Fail-soft registre illisible (`erreur`, prouvé). Fixtures
registre tmp via `SERGE_CONFIG_DIR`. 2 goldens (dont dérive volume).
Kills M8 + page Cerveau = lots 6c/6d.

## Cerveau P2 — kills M8 (lot 6c)

`runtime_flags` (table B5) + `registry.py` : `runtime_allows`,
`poser_kill` (flag + ticket POLICY auto + event `mc_act`,
idempotent `decision_id`), `retirer_kill`, `llm_enabled`
override runtime AVANT YAML. `run_point` court-circuite
(verdict `killed`, les 2 chemins). Endpoints `POST
/owner/api/kill|unkill` (401/400/404 FR via `_refus`, B7 ;
1 méthode fusionnée). Dette : `server.py` à 500 pile —
extraction `actions.py` (§8) au prochain endpoint.
Écart §8 documenté : logique dans `registry.py` (B3 — jamais
de métier dans `mc/`), pas de `mc/flags.py`. 10 tests.
Page Cerveau = lot 6d.
