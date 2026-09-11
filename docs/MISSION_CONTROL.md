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

## Cerveau P2 — page lecture (lot 6d)

Route p2 : `mind.js` (pensées, décisions, matrice 29 points,
signaux, clusters + 3 titres). Matrice : table dense (tier,
7 j, verdicts, dérive, état runtime/registre) + fail-soft
registre. Stream p2 (`matrice`/`clusters` lentes 30 s).
`project_clusters` enrichi (titres) ; `project_matrice` expose
`tue_runtime`. Fiche point + kills UI = lot 6e. 3 tests E2E.

## Cerveau P2 — fiche + kills UI (lot 6e)

`promptModal` (champs + requis) ; matrice cliquable → drawer
fiche (registre + usage 7 j + checklist) ; boutons Tuer
(modale raison + ttl) / Relancer (confirm) → POST kill|unkill
+ toast FR + refresh ciblé (`/owner/api/state?p2`, drawer
rouvert frais). Bouton désactivé pendant le flow. 2 E2E
(kill complet + unkill, DB vérifiée). P2 DONE.

## Tickets P3 — actions + M1 (lot 7a)

`actions.py` : mixin `ActionsMixin` (handlers API extraits de
`server.py` : 500 → 393 ; `MAX_FORM_BYTES` suit ; `Protocol`
ty-safe). `already_applied` déménage dans `tickets/shared.py`
(E14 — tool partagé Discord ↔ MC, table `ticket_events`
commune). M1 : `POST /owner/api/ticket/acte`
(approuver/rejeter/editer + note + `decision_id`, 401/400/404/
409 FR, stamp `mc.*` + audit `mc_act`). Socle tests :
`_auth_cookie` + `_api_post` (`test_mc_kill` migre). 4 tests
(dont parité E1 : même état Discord ≡ MC + garde 409 croisée).

## Tickets P3 — M2/M3 (lot 7b)

`tout_approuver` → `tickets/items.py` (E14) ; `POST
ticket/item` (garder/modifier/jeter + valeur, tout-approuver,
`mc.item`, 404/400/401) et `POST ticket/discuter` (DISCUSSING
+ `mc.fil`, 409 si déjà en discussion). `_refus_ticket`
partagé (M1 migre). Parité Discord exacte : pas de vérif
d'état ticket pour M2 (Discord n'en fait pas) ; `set_item`
écrase le payload dans les 2 canaux (comportement partagé).
M3 : pas de POST Discord (MC ne poste jamais — le mirror
reflète les états ; décision actée). 7 tests (+ parité item).

## Tickets P3 — liste + carte (lot 7c)

`champs_carte` → `tickets/shared.py` (E14/B3 — `render.py`
migre à rendu identique, 15/15 Discord verts). `proj_outils` :
`apres_iso` (migre `proj_live`) + `charge_json` (3 usages).
`proj_tickets.py` : liste (ouverts d'abord, cap 50, flag
urgent miroir P0, boutons registre) + carte §17 (champs,
boutons, `items_actes`, items, historique, versions, strip
IDs). Endpoint `GET ticket/carte` (401/400/404). 5 tests.
Analyse (diffs/mesures/digest) = lot 7d.

## Tickets P3 — analyse (lot 7d)

`proj_analyse.py` : diffs (POLICY + versions EDITED + items
edit avant/après), MEMORY paginé serveur (E12 — page, clamp
100, hors bornes = vide), métriques E5+§12 (volumes, backlog,
approbation globale/par type, rejets, auto, bypass = expirés
avec défaut, GUICHET, réponse médiane/délais draft→décidé),
digest (config pure — prochain calculé front, C2). Endpoint
`GET memory/items` (401/400 + clamp). 5 tests. Page = lot 7e.

## Tickets P3 — liste et filtres (lot 7e)

Route p3 : `tickets.js` (liste des tickets avec tri, état urgent
miroir P0, et filtres dynamiques par type, état 'à traiter' /
'terminés', urgents seuls, recherche textuelle, et tri date
d'échéance vs récents). Stream p3 câblé (`tickets`, `diffs`,
`metriques`, `digest`). `fetchState` exporté depuis `sse.js`
(refactor partagé avec `mind.js`). `llm_enabled` accepte
`now_iso` (robustesse temporelle testée). 3 tests E2E.
Carte détaillée et actes interactifs = lot 7f.

## Tickets P3 — carte interactive et actes (lot 7f)

`tickets.js` : ouverture et rendu de la carte §17 (méta, champs
dynamiques, boutons d'actes, items, historique). Câblage des
actes interactifs M1 (approuver/rejeter avec modale de confirmation,
éditer/discuter avec promptModal), M2 (items garder/modifier/jeter
+ tout-approuver), et rafraîchissement ciblé via `fetchState('p3')`
avec rechargement en place de la carte. 3 tests E2E interactifs
(actes complets vérifiés en DOM et en DB). 605 tests verts.

## Tickets P3 — extraction tickets_actes (lot 7f1 / refactor)

Extraction de la logique d'actes (modales, requêtes POST `agirTicket`,
`agirItem`, `toutApprouver`, `chargerCarte`, `renderCarte`) dans
`tickets_actes.js` (270 lignes). `tickets.js` allégé à 135 lignes
(charter < 500 et R1 < 300 par commit strictement respectés).

## Tickets P3 — diffs, MEMORY paginé, métriques et digest (lot 7g)

`tickets.js` :
- Panneau diffs : propositions POLICY ouvertes (diff, justification,
  impact), historique des versions EDITED, et modifications d'items
  MEMORY (avant/après).
- Panneau MEMORY : navigation paginée serveur (E12) via
  `/owner/api/memory/items?page=X&size=10` avec boutons Précédent /
  Suivant et compteur de page.
- Panneau métriques E5 : semaine (tickets, expirations), backlog,
  taux d'approbation global, délais médians de réponse par type,
  actes automatiques, guichet résolus/expirés.
- Panneau digest : heure du digest quotidien et plages silencieuses.
- 2 tests E2E supplémentaires (diffs/métriques et pagination mémoire).
Page P3 DONE (607 tests verts).

## Mémoire P4 — projecteurs et recherche (lot 8a)

`proj_memory.py` :
- `project_couches` : synthèse des 5 couches de mémoire de Serge
  (C1 épisodes & archives, C2 playbooks, C3 pièges / pitfalls,
  C4 leçons / lessons, C5 SERGE.md + previous pour diff/rollback).
- `project_consolidation` : cadence et état du moteur de consolidation
  (`last_run`, `due_for_consolidation`, derniers événements d'audit).
- `project_requested` : demandes d'évolution P3 des agents (tickets
  `type='REQUESTED'`).
- `GET /owner/api/memory/search?q=...` : recherche plein-texte FTS
  câblée sur `memory_search` (fail-soft, 401/400).
- Actions mémoire (curation leçons, rollback SERGE.md) = lot 8b.
- 4 tests (goldens C1-C5, consolidation, requested, search endpoint). 611 verts.

## Mémoire P4 — actions et curation (lot 8b)

- `lessons.py` : `update_lesson` (modifier l'énoncé) + `delete_lesson`
  (suppression), audité et validé.
- `POST /owner/api/memory/lesson` : curation de leçons (actions
  `modifier` et `supprimer`, 401/400/404, audit `mc_act`).
- `POST /owner/api/memory/rollback` : rollback SERGE.md à sa version
  précédente via `rollback_summary` (401/404, audit `mc_act`).
- Architecture : extraction des vues GET dans `api_views.py` (98 l.)
  et typage des mixins via `TYPE_CHECKING Protocol` pour immunité MRO.
  Tous les fichiers sous 480 lignes.
- 3 tests unitaires et d'API (+24 assertions, 614 tests verts).

## Mémoire P4 — page memory (lot 8c)

`memory.js` :
- Navigation interactive entre les 5 couches (C1 Épisodes, C2 Playbooks,
  C3 Pièges, C4 Leçons, C5 SERGE.md + previous).
- Recherche plein-texte FTS en direct via input et touche Entrée / bouton
  sur `/owner/api/memory/search?q=...`.
- Panneau consolidation (`last_run`, statut due / à jour, événements récents).
- Panneau requested (demandes d'évolution P3 des LLM).
- Câblage stream p4 (`couches`, `consolidation`, `requested`) et routeur p4.
- 3 tests E2E navigateur (rendu 5 couches, FTS UI).
- Page P4 Mémoire DONE (617 tests verts).

## Politique P5 — projecteurs et snapshots (lot 9a)

- `policy_snapshots.py` (invariant B4) : `snapshot_policy` (validation
  `validate_policy` + hash SHA256 16 hex + append-only dans `policy_snapshots`),
  `list_snapshots`, `get_snapshot`.
- `proj_policy.py` :
  - `project_politique_active` : politique runtime en vigueur.
  - `project_policy_snapshots` : historique 20 derniers snapshots.
  - `project_testing_froid` : état testing et détection de campagnes en cours (lock).
  - `project_trust_candidates` : détection des types candidats (>95% sur >=20 tickets).
- 4 tests unitaires et goldens (621 tests verts).

## Politique P5 — actions et mutations (lot 9b)

`policy_actions.py` :
- `POST /owner/api/policy/edit` (M4) : validation `validate_policy`,
  enregistrement d'un snapshot append-only, événement `mc_act`.
- `POST /owner/api/policy/rollback` (M5) : récupération du snapshot
  antérieur et écriture d'un nouveau snapshot (jamais d'écrasement).
- `POST /owner/api/policy/testing` (M6, E3) : validation `_validate_testing`,
  verrouillage strict à froid (409 si au moins une campagne `RUNNING`),
  événement `mc_act`.
- `POST /owner/api/policy/propose` (M12) : création d'un ticket `POLICY`
  en `DRAFT` depuis la zone de confiance ou une dérive constatée.
- 3 tests d'actes complets (passant, erreurs, verrouillage froid, 624 verts).

## Politique P5 — page policy (lot 9c)

`policy.js` :
- Affichage de la politique active par section YAML en blocs lisibles.
- Formulaire testing à froid E3 avec verrouillage dynamique (bouton désactivé
  et message d'alerte orange si campagnes RUNNING en cours).
- Historique des snapshots avec bouton de rollback immédiat (confirmModal).
- Tableau des candidats à la zone de confiance (Trust Candidates).
- Bouton "Proposer en POLICY" (M12) ouvrant une modale de saisie de diff/justification
  et créant un ticket POLICY DRAFT en base.
- Stream p5 câblé (`politique_active`, `policy_snapshots`, `testing_froid`, `trust_candidates`).
- 4 tests E2E navigateur (rendu, édition testing UI, proposition ticket POLICY UI).
- Page P5 Politique DONE (628 tests verts).

## Économie P6 — projecteurs (lot 10a)

`proj_economy.py` :
- `project_entonnoir` : agrégat evidence-strict (ventures x U1-U5 via
  `campaign_metrics` x transactions réglées/paid sans jamais inventer de revenu).
- `project_transactions_subscriptions` : 30 dernières transactions et 20
  derniers abonnements récurrents, calcul du MRR mensuel en EUR.
- `project_couts_cognitifs` : total tokens LLM, total dépensé en EUR
  selon `policy.budget`, total encaissé, ratio cognitif `tokens/€ de revenu` (E6).
- `project_audit_reponses` : traçabilité des réponses générées (E10) et
  dette technique builder (artifacts en attente E9).
- 4 tests unitaires et goldens (632 tests verts).

## Économie P6 — page economy (lot 10b)

`economy.js` :
- Entonnoir unifié evidence-strict (U1-U5 par venture et totalisateurs).
- Tableau des transactions et abonnements avec calcul dynamique du MRR.
- Panneau coûts cognitifs : tokens totaux, dépenses EUR, ratio `tokens/€ de revenu` (E6).
- Audit des réponses automatiques (E10) et de la dette technique builder (E9).
- Stream p6 câblé (`entonnoir`, `transactions_subscriptions`, `couts_cognitifs`, `audit_reponses`).
- 2 tests E2E navigateur.
- Page P6 Économie DONE (634 tests verts).

## Voix P7 — infrastructure (lot 11a)

- `signedlinks.py` (E7, §8.1) : génération (`signer_url`) et vérification
  (`verifier_url`) de liens signés HMAC-SHA256 avec date d'expiration pour
  l'accès sécurisé et temporaire aux flux audio et écrans sensibles.
- `voice_retention.py` : purge RGPD et rétention (`purger_audio_voix`)
  avec mise à jour des CDR, suppression physique des fichiers et événement
  d'audit `voice.purged`.
- 2 tests unitaires complets (+ robustesse test UI policy, 636 tests verts).

## Voix P7 — projecteurs (lot 11b)

`proj_voice.py` :
- `project_cdr_appels` : lecture des 30 derniers CDR d'appels depuis
  le ledger voix `state/voice/voice.db` (fail-soft si inexistant),
  avec injection d'une URL d'audio signée HMAC via `signer_url`
  lorsqu'un enregistrement `.wav` est présent.
- `project_qualite_voix` : récupération des 20 derniers scores d'appels
  via `recent_scores`, calcul de la note moyenne et détection des alertes qualité.
- `project_bridge_statut` : lecture de l'état du bridge voix,
  du trunk Asterisk et de l'activation du fichier `KILL_SWITCH`.
- 3 tests unitaires et goldens (639 tests verts).

## Voix P7 — page voice et actions (lot 11c)

`voice.js` :
- `bridge_statut` : affichage de l'état du bridge et bouton d'action
  `toggle-kill-voice` (confirmModal avant bascule, toast de succès, rafraîchissement).
- `cdr_appels` : liste des 30 derniers appels du ledger avec lien sécurisé
  `🔊 Écouter` vers l'audio signée HMAC (E7).
- `qualite_voix` : restitution des scores F4c et de la note moyenne.
- `GET /owner/api/voice/audio?cdr=...` (E7, E11) : vérification du lien
  signé HMAC ou session owner, streaming audio `.wav`.
- `POST /owner/api/voice/kill` (M9, M11) : activation / désactivation
  du fichier `KILL_SWITCH` (audité dans `events` type `mc_act`).
- Stream p7 câblé (`cdr_appels`, `qualite_voix`, `bridge_statut`).
- 3 tests E2E navigateur (rendu, toggle kill switch, écoute).
- Page P7 Voix DONE (642 tests verts).

## Santé & Audit P8 — projecteurs (lot 12a)

`proj_health.py` :
- `project_charte_metriques` : comptage des LOC (fichiers kit/ et serge/),
  identification du plus gros fichier du repo, demandes requested en attente,
  ratio tokens/€ de revenu (E6).
- `project_audit_trail` : liste ordonnée des 50 derniers actes owner/MC
  (events `type='mc_act'`).
- `project_versions_drift` : versions logicielles (MC, schéma SQLite attendu
  vs appliqué, version CLI `gog`).
- `project_units_systemd` : sonde lente des services systemd (`is-active`,
  fail-soft, timeout court).
- 4 tests unitaires et goldens (646 tests verts).

## Santé & Audit P8 — page health (lot 12b)

`health.js` :
- Métriques charte E6 (LOC total, nom et taille du plus gros fichier,
  requested en attente, coût cognitif par euro).
- Liste des units systemd avec coloration de statut (vert, orange, gris).
- Dérive versions : version MC, version schéma SQLite (alerte rouge si
  divergent), version du binaire CLI gog.
- Piste d'audit (audit trail) des 50 derniers actes owner/MC.
- Stream p8 câblé (`charte_metriques`, `units_systemd`, `versions_drift`, `audit_trail`).
- 2 tests E2E navigateur.
- Page P8 Santé & Audit DONE (648 tests verts).

## Surface publique P9 — fail-closed et assertions (lot 13a)

`proj_public.py` (E13, §2.8, §6 P9) :
- `assert_public_safe` : vérification récursive anti-fuite (détection de
  patterns de secrets, tokens `Bearer`, clés d'API, clés privées,
  emails/téléphones PII, identifiants opaques `t_`, `w_`, `e_`, `c_`).
- `project_public_statut` : projection publique ultra-minimaliste
  (statut opérationnel / travail en cours) soumise à `assert_public_safe`,
  avec repli fail-closed absolu en cas d'exception.
- Serveur HTTP : routes publiques `/` (template `public.html`),
  `/robots.txt` (interdisant `/owner/`) et `/api/state` accessible sans auth.
- 5 tests unitaires et d'API (tests adversariaux secrets & PII, 653 tests verts).
