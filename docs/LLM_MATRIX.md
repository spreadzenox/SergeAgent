# Matrice LLM / déterministe (C) + contrats de contexte

Version : 1.0 (2026-09-09)
Statut : VALIDÉ avec Julien le 2026-09-09 (discussion C, funnel par funnel).
S'applique à : le rework kit (registre `config/llm-points.yaml`, implémentation).
Références : charte P2/P3 ([CODEBASE_CHARTER.md](CODEBASE_CHARTER.md)),
funnels ([FUNNEL_ARCHITECTURE.md](FUNNEL_ARCHITECTURE.md)),
mémoire ([MEMORY_ARCHITECTURE.md](MEMORY_ARCHITECTURE.md)),
interactivité ([INTERACTION_ARCHITECTURE.md](INTERACTION_ARCHITECTURE.md)).

Principe : chaque point LLM a verdict + checklist P2 + contrat de contexte
(fixed / retrieved / couche-5 / forbidden / enveloppe) + garde-fou + repli +
kill-switch. Les enveloppes tokens sont des dimensionnements initiaux,
ajustés empiriquement — jamais des caps (alertes sur dérive vs médiane,
seul budget dur = plafond financier global).

---

## 0. Légende et règles transverses

| Verdict | Sens |
|---|---|
| **DET** | 100 % déterministe, 0 LLM. LLM **interdit** (test/grep anti-import) |
| **LLM-1** | Jugé unique : 1 call, output enum fermé + `requested`, mesuré |
| **LLM-B** | Borné : template + slots, output contraint, checkers dét autour |
| **LLM-L** | Libre en sandbox : génération créative, gates aval obligatoires |
| **LLM-R** | Lecture seule : résume/explique, ne change aucun état |
| **HYB** | Hybride algo + LLM (bandit + juge, embeddings + labeling...) |

**Règles transverses (tous points LLM).**
- Checklist P2 à 4 cases + risque de propagation → registre versionné
  `config/llm-points.yaml`. Ajouter un point = ajouter un bloc, jamais du
  code caché.
- Output vers déterministe = structuré (P3 : enum fermé + `requested`).
- Repli déterministe obligatoire. Retry = changer quelque chose, puis code
  routable. Jamais de retry aveugle.
- Mesure systématique (tokens, latence, verdicts) + alertes sur dérives vs
  médiane 7j. Enveloppes = dimensionnement, pas caps.
- **Kill-switch par point** : `llm_points.<nom>.enabled: false` en policy →
  fallback 100 % dét immédiat, sans déployer. Chaque point survit à sa
  propre extinction (mode dégradé, pas crash).
- Tiers modèles : **T1** reflexe (rapide/cheap, volume), **T2** rédacteur
  (qualité, contexte long), **T3** stratège (jugement rare et amont).
  Modèles exacts via OpenRouter à choisir avec bench + coût réel.

**Invariants 0 LLM (absolus, testés) :** scheduler, guards `check()`,
compteurs U1-U5, transitions d'états, expiry, idempotence, routage,
lifecycle tickets, collect (sauf draft prix), OPT_OUT, textes financiers
(factures/devis/relances : templates purs).

---

## 1. Méta-funnel venture

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| M0 | Scheduler | **DET** | — | Requête SQL uniquement | Invariant absolu | — |
| M1 | `draft_hypothesis_smoke` | LLM-B | T2 | fixed: template smoke, SERGE.md, seuils A, policy. retrieved: signaux écoute top-5 (1200t), leçons hypothesis top-3 (800t), benchmarks canal (400t). C5: oui (1500t). forbidden: secrets, PII tiers, autres ventures, montants non-catalogue. Env ~5000t. Checklist: entrée±/sortie template/info externe oui/dérive oui. | Schéma validé dét (N 30-50, seuils A, fenêtre ≤ 10j, prix draft non-owné). Smokes auto + FYI complet. | Template min + ticket QNA. Kill: tout en QNA. |
| M2 | `draft_hypothesis_full` | LLM-B | T2 | fixed: + template full, gate collect READY. retrieved: résultats smoke complets U1-U5 + objections + verbatims (2000t), leçons full_test top-3 (800t), état collect (300t). C5: oui (1500t). forbidden: idem M1 + pas de montants inventés. Env ~6000t. Checklist: entrée oui/sortie template+jugement seuils/info externe oui/dérive ±. | Schéma + **ticket HYPOTHESIS bloquant** (version précise). Gate collect vérifié dét avant ticket. | Idem M1. Kill: idem M1. |
| M3 | `plan_scale` | LLM-L | **T3** | fixed: template plan (volumes/canaux/budget/builder/risques/jalons), résultats full, budget restant + policy. retrieved: playbooks scale top-3 (1000t), pitfalls scale top-3 (800t), standing (500t). C5: oui large (3000t). forbidden: engagements contractuels (propositions, pas actes). Env ~12000t. Checklist 4/4. Risque propagation maximal. | Dans bornes → auto + FYI détaillé. Hors bornes (nouveau canal, gros budget, recrutement, engagement) → VETO_AMONT bloquant. Justification/section obligatoire. | Rejouer le test gagnant à l'identique + FYI. Kill: SCALE = ticket (données brutes fournies). |
| M4 | `options_pivot` | LLM-L | **T3** | fixed: template option ×2-3 (changement/rationnel/risque/nouveau pré-enregistrement). retrieved: objections top-10 verbatims (1500t), leçons pivot top-3 (800t), playbooks domaine (600t). C5: oui (2500t). forbidden: "refaire pareil" (diff non vide vérifiée dét sur ≥ 1 dimension clé). Env ~10000t. Checklist 4/4. | Chaque option = pré-enregistrement → ticket HYPOTHESIS (choix + validation). Jamais d'auto-pivot. | PIVOT → EXTEND (variation min imposée) + FYI + QNA optionnel. Kill: ticket QNA avec données brutes. |
| M5 | `resume_test` | LLM-R | T1 | fixed: template (verdict/chiffres/apprentissages/suites). retrieved: compteurs + verdict + preuves (800t), top objections/réponses (800t), leçons candidates (400t). **C5 interdite.** forbidden: PII non anonymisée, autres ventures. Env ~3000t. Checklist: entrée structurée/sortie template/pas info externe/pas dérive. | **Lecture seule mécanique** (pas d'outil d'écriture). Chiffres = DB ou rien. | Chiffres bruts sans résumé. Kill: digest chiffres bruts. |

Pas de juge de priorisation CANDIDATEs (FIFO + score écoute dét — validé).

---

## 2. Prospection

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| P0 | Séquenceur/guards/attribution | **DET** | — | Invariants. Le LLM ne choisit jamais qui/quand à grande échelle. | — | — |
| P1 | `qualify_prospect` | LLM-1 | T1 | fixed: ICP + exemples ± (600t), SERGE.md. retrieved: fiche prospect (800t), 2 exemples historiques proches (600t). **C5 interdite** (hot path, pré-chargé suffit ; log de manque). forbidden: PII inutile (minimisation), autres ventures. Env ~2500t. Checklist 2,5/4. | Binaire strict + confiance ; < 0,6 → REJECT conservateur + log + candidat-leçon. | Règles ICP de base. Kill: 100 % règles + FYI quotidien. |
| P2 | `fill_slots` | LLM-B | T1 | fixed: template + contraintes (longueur, ton, mots interdits, pas de promesse non sourcée). retrieved: fiche (600t), 2 slots convertis (600t), objection à éviter (200t). **C5: 1 recherche** (800t, timeout 2 s). forbidden: secrets, prix non-catalogue, allégations non sourcées, autres prospects. Env ~3000t. Checklist 3/4. | Checkers dét post-génération (longueur, interdits, chiffres sourcés, URL, PJ). Échec → regen 1× puis template brut. | Template brut (envoyé quand même). Kill: templates bruts. |
| P3 | `write_followup` | LLM-B | T2 | fixed: template + contraintes (jamais agressif, patterns interdits). retrieved: historique complet ou résumé+K (2000t), objections + réponses playbook (800t), leçons followup top-3 (600t). **C5 autorisée** (préparé à l'avance, 1500t). forbidden: idem P2 + jamais révéler d'autres prospects. Env ~5000t. Checklist **4/4** (le plus justifié). | Checkers P2 + détecteur agressivité + N follow-ups (séquence dét). | Template générique. Kill: templates génériques. |
| P4 | `voice_script` | LLM-B | T2 | fixed: template script (durées, disclosure tête, DTMF, mentions), patterns interdits, SERGE.md. retrieved: fiche (600t), objections segment + réponses (1000t), pitfalls voix (400t). **C5 autorisée** (préparation, 1500t). forbidden: se faire passer pour humain (disclosure obligatoire), engagements, prix non-catalogue. Env ~4500t. Checklist 3,5/4. | Checkers dét (durée, disclosure, interdites, prix) + ticket initial par type, puis trust zone (échantillonnage). | Script validé précédent (pinné). Kill: scripts pinnés uniquement. |
| P5 | `voice_dialog` temps réel | LLM-B | T2 | fixed: script P4, règles dures (durée/tours max, interdites, DTMF, raccrochage propre), SERGE.md min. retrieved: **pré-chargé avant décroché** (fiche 600t, historique 400t, objections 600t). **C5 INTERDITE** (voix = option A stricte). Tools: agenda, catalogue, fiches (dét). forbidden: engagements, prix non-catalogue, autres prospects, hors-sujet (→ "revenons à..."). Env ~4000 + tours. Checklist 4/4. **Point LLM temps réel comptant le speech-to-speech** (providers xAI/OpenAI Realtime comme Mission Control — cible rework ; tour-par-tour = repli). | Tours/durée max (coupure gracieuse) ; détecteur dérive temps réel (recentrage 1× puis raccrochage propre) ; enregistrement systématique ; DTMF1 → ticket ; kill manuel (bouton). Écoute owner post-hoc via Mission Control (pas de spot-check initial — validé). | Échec mid-call → message secours pré-enregistré + répondeur + ticket + rappel planifié. Jamais silence/sec. Kill: entrants → message + répondeur, plus de sortant. |
| P6 | `summarize_thread` (= O5, fusionné) | LLM-R | T1 | fixed: template (statut/derniers échanges/objections/next step). retrieved: historique borné 5000t (récursif au-delà). **C5 interdite.** forbidden: PII en clair (anonymiser). Env ~6000 in / 800 out. | Lecture seule. Régénérable. | Brut tronqué (derniers K). Kill: brut tronqué partout. |
| P7 | `score_lead` | **DET + départage LLM-1** (hybride validé) | T1 si appelé | DET: score = f(compteurs barème A, formule en policy). LLM-1 si zone grise ET décision coûteuse : fixed = historique résumé + options (allouer appel vs abandonner) ; C5 interdite ; env ~2000t. | Seuil zone grise en policy. | Score DET seul. Kill: DET seul. |

**Anti-attracteur clé prospection** : LLM à l'unité (rédige, qualifie), jamais
à l'échelle (qui/quand = séquenceur DET + N bornés).

---

## 3. Builder

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| B0 | Spec validée, gate 1, stage/publish | **DET** | — | Schéma, checks, déploiement, versioning. | — | — |
| B1 | `build_artifact` | LLM-L | **T3** (validé : cœur opérationnel, pas d'économie) | fixed: spec complète (~1500t), contraintes (stack, interdictions, perf), SERGE.md léger. retrieved: playbooks builder top-2 (800t), pitfalls (400t), version précédente si itération (1000t). **C5 autorisée** (2000t : benchmarks, docs). forbidden: secrets/credentials, PII réelle (démo), prix non-spec, code réseau non-allowlisté, trackers non déclarés. Env ~6000 in / sortie mesurée. Checklist 4/4 (partiel info externe). | Sandbox (pas secret/mutation externe, réseau allowlist) ; sortie = artifact versionné (jamais prod directe) ; 3 passes max partagées avec B2. | Pas de repli dét pour créer → ticket QNA (spec + tentatives + recommandation). Kill: builds = tickets, plus d'auto. |
| B2 | `review_build` gate 2 (multimodal) | LLM-1 | T2 multimodal obligatoire | fixed: spec + critères (1500t), rubric review + poids (800t), n° passe (1/2/3 + warning si 3), SERGE.md min. retrieved: verdicts passes précédentes (anti-contradiction non justifiée, 800t), pitfalls review (faux positifs connus, 300t). Entrées: code/HTML + **screenshots desktop+mobile** + **session d'interaction sandboxée** (clics/formulaires, jamais mutation externe). **C5 interdite** (jugement sur pièces). Env ~4000t + 2-6 images. Checklist: entrée très variable/sortie enum/derrière visuelle. | **Juge DISTINCT du builder** (sessions/prompts séparés, idéalement modèles ≠). Verdict enum strict (malformé → 2 recalls puis code). FIX ≤ 5 items localisés. Passe 3 = binaire SHIP/REBUILD + dette explicite. Contradiction non justifiée entre passes = candidat-leçon (pas bloquant — validé). **Fail-closed (validé) : pas de review = pas de publish** (échec B2 → ALERT + file, jamais PASS silencieux). | — (fail-closed : pas de repli qui publie). Kill: builds en attente + ALERT (mode dégradé = humain). |
| B3 | `summarize_build_debt` | LLM-R | T1 | fixed: template dette (titre/localisation/gravité/suggestion v2). retrieved: verdict passe 3 + réserves (500t), dettes existantes (anti-doublon, 300t). **C5 interdite.** forbidden: PII, autres ventures. Env ~1500t. | Lecture seule (écriture DB dét depuis sortie structurée). Dédupliqué dét. | Réserves brutes copiées. Kill: idem repli. |

**Boucle 3 passes (validé)** : BUILD → G1 → G2 → BUILD, 3× max/livrable.
Passe 3 = warning injecté (builder : corriger liste FIX par impact, plus de
réécriture ; reviewer : binaire + dette). Échec passe 3 → ticket QNA
(historique + 3 verdicts + screenshots + recommandation) — toi seul
débloques une passe 4.

---

## 4. Observation

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| O0 | Collecte, normalisation, routage, scoring | **DET** | — | Poll, headers/codes/standing, routeur signaux, barème A. **OPT_OUT = DET pur, 0 LLM sur le chemin** (P0). | — | — |
| O1 | `classify_reply` | LLM-1 | T1 | fixed: taxonomie + 2 exemples/classe (~1200t), SERGE.md min. retrieved: message (tronqué 2000t si énorme + signalé), contexte micro (canal + 3 derniers échanges résumés 1 ligne, 300t). **C5: 1 recherche** (800t, timeout 2 s). forbidden: PII inutile, autres prospects/ventures, secrets. Env ~3500t. Checklist: entrée variable/sortie enum/pas info externe/dérive. | Enum strict P3 + `requested` ; confiance < 0,6 → file review humaine groupée quotidienne. **UNSUBSCRIBE/SPAM : double-check dét par patterns** ; doute → traiter comme opt-out (P0). | Règles mots-clés + confiance basse forcée → review. Kill: 100 % règles + review élargie. |
| O2 | `extract_meeting` | LLM-1 | T1 | fixed: schéma sortie (datetime ISO + durée + moyen + confiance), fuseau Europe/Paris, date/heure actuelles (ancrage), SERGE.md min. retrieved: message (800t), historique micro (200t). **C5 interdite.** forbidden: PII inutile, autres ventures. Env ~2000t. | **Vérif agenda déterministe** (libre ? chevauchement ? horaires ?) ; confiance < 0,8 OU ambiguïté → clarification, jamais de booking deviné. Booking = écriture + confirmation + rappel (3 actes dét, idempotents). | Clarification générique ("2-3 créneaux ?"). Kill: suspicion RDV → clarification manuelle (template + ticket si insiste 2×). |
| O3 | `reply_intent` | LLM-B | T2 | fixed: contraintes (ton, longueur, disclosure 1er contact, jamais engagement/prix-délai hors catalogue/promesse non sourcée), SERGE.md. retrieved: historique complet ou résumé+K (2000t), classe + confiance + verbatim (400t), playbook objection (600t), fiche offre/prix catalogue (400t). **C5 autorisée** (SLA 1h confortable, 1200t). forbidden: autres prospects (pas de name-drop non public), prix/délais inventés, engagements, hors scope. Env ~5000t. Checklist 4/4. | **Détecteur d'engagement contractuel** (patterns dét : garanti/promis/montants/délais/contrat...) → doute = **ticket au lieu d'envoi** (+ accusé "je reviens sous Xh" au prospect). Prix/délai = catalogue ou rien (vérifié dét : tout nombre match une source). **Full auto dès jour 1** (validé) + traçabilité totale post-hoc. | Accusé + "je reviens sous Xh" + ticket QNA. Kill: accusés auto + tous intents en ticket. |
| O4 | `review_other` (juge OTHER, batch) | LLM-1 | T1 | fixed: taxonomie 8 signaux + critères OTHER, template proposition (nom/définition/exemples/fréquence/routage). retrieved: batch OTHER du jour (≤ 20 items + contexte, 3000t). **C5 autorisée** (batch, 1500t). forbidden: PII, secrets, autres ventures. Env ~5000t. | Batch quotidien, jamais bloquant. Proposition catégorie = ticket (tu valides la taxonomie). Reclassements logués + confiance (basse → reste OTHER, revu demain). | Pas de batch → OTHER s'accumule (compteur + alerte si > 50) + traités REPLIED conservateur. Kill: file review manuelle groupée. |
| O5 | = P6 (`summarize_thread`, fusionné — validé) | LLM-R | T1 | Voir P6. Un seul point paramétré par usage. | — | — |

---

## 5. Collect (le plus déterministe — par design)

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| C0 | Catalogue→reçu (tout sauf prix) | **DET** | — | Catalog, canary, devis, facture (templates purs), relances (templates purs), rapprochement, reçu, numérotation, mentions. **0 slot LLM sur documents financiers.** Test anti-import LLM dans `collect/`. | — | — |
| C1 | `draft_price` | LLM-L | T2 | fixed: template proposition (prix + 2 alternatives + justif/risque + conditions de révision), SERGE.md, bornes policy (min/max par offre — rejet dét avant ticket si hors bornes). retrieved: benchmarks segment (1000t), coûts unitaires (300t), objections prix passées (800t), offre (600t). **C5 autorisée** (batch, décision rare, 2500t). forbidden: prix autres clients (confidentiel), PII, engagements ("garantit X ventes" — proposition avec incertitude assumée). Env ~5000t. Checklist 4/4, amont propagatif. | **Ticket VETO_AMONT bloquant** (prix owné = toi qui tranches, toujours). Proposition inclut conditions de révision (jamais définitif). | Ticket QNA avec données brutes (benchmarks + coûts), tu fixes. Kill: prix 100 % manuels. |

---

## 6. Alloueur

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| — | Couche A (garde-fous) | **DET** | — | Planchers, plafonds (30/60 %), réserve 20 %, tickets irréversible, budget policy. Proposition hors bornes → clampée + loguée. | — | — |
| — | Couche B (bandit Thompson) | **Algo** | — | Bras = campagnes, récompense = intent pondéré − coût. Continu, 0 token. | Borné par A. | Équi-répartition si pas de données. |
| A1 | `judge_allocator` (couche C) | LLM-1 | **T3** (validé : quotidien + amont, coût assumé — cf. B1) | fixed: bornes A + template décision, SERGE.md. retrieved: U1-U5 toutes campagnes + coûts + contraintes (4000t) + leçons + opportunités + proposition B. **C5 autorisée** (2000t). forbidden: ordres irréversibles directs (→ tickets), engagements. Env ~8000t. Quotidien + déclenché (budget 80 %, seuils, ALERT, signal chaud, oscillation). | Bornes A + justification revirements (> 10 pts contre sens précédent → 1 phrase) + écart > 15 pts vs B justifié + tickets irréversible. | Proposition B brute. Kill: bandit seul (+ FYI). |

---

## 7. Mémoire

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| D1 | `consolidate` (batch 3j) | LLM-B | T2 | fixed: templates (leçon + confiance + sources, playbook, pitfall), K max, policy. retrieved: épisodes période + OTHER + `requested` + recherches récurrentes + pertes standing (6000t, plus gros batch). **C5 large** (3000t). forbidden: PII en clair dans les leçons (anonymiser), secrets, autres ventures (sauf scope global explicite). Env ~12000t. | K max, budget mesuré, **ticket MEMORY** (tu disposes par leçon). Jamais d'écriture directe sans validation. | Pas de nouvelles leçons ce cycle (+ FYI). Kill: pas de consolidation (épisodes s'accumulent, compteur + alerte). |
| D2 | `edit_serge_md` | LLM-B | T1 | fixed: template sections + constitution + version actuelle + < 100 lignes. retrieved: changements depuis dernière version (diff épisodes clés, 1000t). **C5 interdite.** forbidden: PII, secrets. Env ~3000t. | Diff visible, rollback 1 clic, constitution injectée. | Version précédente (pas d'édit). Kill: SERGE.md figé (MAJ manuelle). |

Écriture épisodique, retrieval SQL/FTS, oubli (archive 30j, deprecated 3×) : **DET**.

---

## 8. Interactivité H

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| H1 | `render_context_fr` | LLM-R | T1 | fixed: template (où/enjeu/attente). retrieved: ticket + thread résumé + état venture (1500t). **C5 interdite.** forbidden: IDs opaques affichés (backend only), PII, secrets. Env ~2500t. | Lecture seule mécanique. | Champs bruts (titre + état + lien). Kill: idem repli. |
| H2 | `classify_owner_intent` | LLM-1 | T1 | fixed: taxonomie intents + exemples. retrieved: message + thread courant (1000t). **C5 interdite.** forbidden: — (message owner, mais pas de PII tierce inutile). Env ~2000t. | Ambigu + irréversible → clarification, jamais d'exécution devinée. | Ticket QNA "précise ta demande". Kill: tout en QNA manuel. |
| H3 | `judge_consequence` | LLM-1 | T2 | fixed: 5 critères (irréversible/financier/visible/N/juridique) + exemples + seuils. retrieved: ordre + contexte cible/montants/portée (1500t). **C5: 1 recherche** (800t, "historique cible ?"). forbidden: —. Env ~3000t. | Doute → confirmation (conservateur). Bypass respecté. **§14.1a jamais bypassé** (check dét après le juge). | Confirmation systématique. Kill: confirmation systématique. |

Lifecycle tickets, actes (boutons), expiry : **DET**.

---

## 9. Écoute J

| ID | Point | Verdict | Tier | Contrat de contexte (résumé) | Garde-fou | Repli |
|---|---|---|---|---|---|---|
| J0 | Crawl/collecte | **DET** | — | RSS/API/forums, rate-limits, dédup. Respect ToS lecture. | — | — |
| J1 | `cluster_demand` (batch hebdo) | HYB + LLM-1 | T2 | Embeddings = outil dét ; labeling/scoring = LLM-1. fixed: rubric (volume/intensité/récurrence/willingness) + template cluster. retrieved: verbatims échantillonnés/cluster (3000t). **C5 large** (recherche = le job, 2500t). forbidden: PII (verbatims anonymisés), secrets. Env ~7000t. | Batch hebdo, jamais bloquant. Opportunité chaude (seuils policy) → ALERT/FYI dét. | Clusters bruts sans labels. Kill: signaux bruts + FYI. |

---

## 10. Synthèse : ~29 points LLM + squelette DET

| Couche | Nature | Points |
|---|---|---|
| **Squelette** (DET pur, 0 LLM, invariants testés) | Scheduler, guards, compteurs, transitions, expiry, idempotence, collect (C0), routage, lifecycle tickets, OPT_OUT | Si tout le LLM tombe, arrêt propre — jamais n'importe quoi |
| **Muscles** (algo, 0 LLM) | Bandit, scoring, attribution, clustering embeddings, rapprochement | Optimisation continue sans token |
| **Cerveau** (~29 points déclarés) | M1-M5, P1-P6, B1-B3, O1-O5, C1, A1, D1-D2, H1-H3, J1 | Chacun : checklist + contrat + garde-fou + repli + kill-switch |
| **Conscience** (humain) | Veto amont, guichet, validation full, consolidation, bypass | L'irréversible et le stratégique |

**Tiers modèles (validé).** T1 reflexe (volume, borné, cheap), T2 rédacteur
(qualité, contexte long), T3 stratège (B1 builder, M3/M4 plans, A1 alloueur —
jugement rare et amont, coût assumé). Modèles exacts via OpenRouter : bench +
coût réel à choisir ensemble.

**Révision de frontière (validé).** LLM→règle auto après preuve (E2E
d'équivalence + FYI + rollback auto si régression) ; règle→LLM sur ticket
obligatoire (double standard assumé : resserrer = sûr, élargir = décision).

**Registre.** Chaque point vit dans `config/llm-points.yaml` (versionné) :
verdict, checklist, contrat (fixed/retrieved/C5/forbidden/enveloppe),
garde-fou, repli, kill-switch. Nouveau point en phase autonome = ticket
obligatoire.
