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
| 1b | Front store/sse/patch + E2E navigateur + A4 | ✅ (ce commit) |
| 2-14 | Voir prompt §11 (design → 9 pages → public → polish) | ⏳ |

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
