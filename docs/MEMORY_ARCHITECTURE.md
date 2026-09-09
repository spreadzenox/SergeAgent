# Architecture mémoire Serge (D-spec)

Version : 1.0 (2026-09-09)
Statut : VALIDÉ avec Julien le 2026-09-09 (discussion D).
S'applique à : le rework kit (tables, tools, consolidateur, SERGE.md, index).
Références : charte ([CODEBASE_CHARTER.md](CODEBASE_CHARTER.md) P2/P4),
funnels ([FUNNEL_ARCHITECTURE.md](FUNNEL_ARCHITECTURE.md)),
interactivité ([INTERACTION_ARCHITECTURE.md](INTERACTION_ARCHITECTURE.md)).

Principe : la mémoire est l'infrastructure qui sert les points LLM (C).
Un point LLM sans contrat de contexte est une spec incomplète.
Réciproquement, on ne construit que ce que la matrice C exige.

---

## 0. Vue d'ensemble : 5 couches

| # | Couche | Question | Latence | Écrivain | Lecteurs |
|---|---|---|---|---|---|
| 1 | **Registres** | "Quel est l'état actuel ?" | ms (SQL direct) | Dét + tickets | Tous (fixed) |
| 2 | **Épisodes** | "Que s'est-il passé ?" | ms (SQL append-only) | Dét (transitions) | Consolidation, audit, calculs |
| 3 | **Leçons** | "Qu'a-t-on appris ?" | ms (SQL top-k) | Consolidateur + Julien | Points LLM (retrieved) |
| 4 | **Résumés** | "L'essentiel de ce gros truc ?" | ms (cache + TTL) | LLM-R + Julien | Points à gros contexte |
| 5 | **À la demande** | "De quoi ai-je besoin ?" | 100ms-1s (hybride) | Auto (indexation) | Tous LLM non simplistes |

Couches 1-4 : **prédéfinies** (le système décide le contenu).
Couche 5 : **libre** (le LLM décide ce qu'il cherche). Soupape anti-prison.

---

## 1. Couche 1 — Registres (faits chauds)

**Contenu.** État courant, structuré, SQL pur. Tables : `ventures` (1 ACTIVE
+ historique), `contacts` (+ consentement, régime, cooldowns), `campaigns`
(+ N, seuils, fenêtres, budgets), `quotas_counters`, `accounts_standing`
(karma, âge, avertissements, capital), `policy_snapshot` (valeurs actives
versionnées), `artifacts` (versions, URLs, hashes), `subscriptions`,
`ledger_entries`.

**Règles.**
- Écriture déterministe ou ticket uniquement. Jamais d'écriture LLM directe.
- Lecture illimitée, gratuite, synchrone.
- Toute valeur : `updated_at` + `updated_by` (scheduler, ticket #X...).
- Pas de texte libre décisionnel (P3).
- Filtre `venture_id` partout dès le jour 1 ; colonne `owner_id`
  (1 seul aujourd'hui) ; `registre_snapshots` quotidiens (time-travel debug).

**Consommateurs.** Scheduler, guards, normaliseurs, compteurs U1-U5,
dashboards, contexte `fixed` de tous les points LLM.

---

## 2. Couche 2 — Épisodes (ce qui s'est passé)

**Contenu.** Tout événement significatif, append-only, immuable, horodaté :
transitions funnel, touches (+ coût), inbound (+ classification), décisions
(+ codes), dépenses, approbations/rejets tickets, bans/warnings,
déploiements, canary, erreurs typées. Tables : `events` (générique : ts,
acteur, venture, type, payload JSON validé, liens), `touches`,
`inbound_events`, `transactions`, `ticket_events`.

**Règles.**
- **Jamais modifié, jamais supprimé.** Corriger = nouvel événement
  `CORRECTION` référençant l'ancien. Traçabilité totale.
- Jamais lu en brut par un LLM temps réel (trop gros, trop bruité).
- Indexé (venture, type, période, contact, campagne).
- Rétention : chaud 90 jours en DB live, puis archive (fichiers compressés
  + index, toujours requêtable, plus lent).
- Preuve légale/commerciale : qui, quoi, quand, avec quel consentement.

**Consommateurs.** Consolidation (matière première), attribution multi-touch,
audit post-hoc Julien, debug, calcul U1-U5, export comptable/légal.
Futur : replay ("et si on avait fait X ?"), détection d'anomalies.

---

## 3. Couche 3 — Leçons (ce qu'on a appris)

**Contenu.** Connaissance distillée, structurée, actionnable.
Tables : `lessons` (énoncé, confiance 0-1, épisodes sources, scope
venture/canal/global, statut candidate/active/deprecated, `created_by`,
historique confirmations/infirmations), `playbooks` (procédures qui
marchent + conditions d'application), `pitfalls` (échecs typés + coût
observé).

**Règles.**
- Écriture par **consolidateur + Julien uniquement** (ticket MEMORY :
  garder/modifier/jeter par leçon).
- Confiance bayésienne simplifiée : confirmations +, infirmations −,
  3 infirmations → `deprecated` (jamais effacé).
- Toute leçon référence ses épisodes sources ("pourquoi on croit ça ?").
- Retrieved top-k par tags + scope (venture > canal > global).
- Leçons à expiry possible ("valable jusqu'à fin 2026" : lois, prix,
  plateformes). Jamais de re-test d'une leçon négative forte sans ticket.

**Consommateurs.** Points LLM (retrieved top-k), PIVOT (objections →
variation), anti-répétition (pitfalls checkés avant action), onboarding
nouvelle campagne (playbooks applicables).

---

## 4. Couche 4 — Résumés (l'essentiel des gros trucs)

**Contenu.** Condensats régénérés, TTL ou trigger. Objets : `SERGE.md`
(< 100 lignes : qui, venture active, 5 leçons chaudes, 3 pièges, état
chiffré du jour), résumés de conversations longues (résumé + derniers K
bruts), résumés de ventures (état + métriques + décisions), résumés de
tickets longs, snapshots digest (quotidien/hebdo).

**Règles.**
- Générés par **LLM-R** (lecture seule, template fixe par type).
- **Toujours régénérables** : supprimer = reconstruit (cf. vues P4).
- TTL explicite (conversation : au-delà du seuil ; venture : quotidien ;
  SERGE.md : chaque consolidation + événement majeur).
- Versionnés (garder N-1 : diff "qu'est-ce qui a changé ?" → détecte les
  dérives silencieuses).
- `SERGE.md` : diff visible, rollback 1 clic, **constitution injectée
  avec** (exigence Julien), auto-édité par Serge sous ces garde-fous.

**Consommateurs.** Contexte `fixed` universel (SERGE.md partout), points à
gros contexte, supervision Julien (digest, cartes H), prompts longs sans
explosion tokens. Futur : multi-niveaux (1 ligne → 1 page), comparatifs,
projections (calcul dét + formulation LLM-R).

---

## 5. Couche 5 — À la demande (tool libre, validé)

**Contenu.** Index unifié sur (presque) tout : épisodes, leçons, artifacts
(docs, landings, copy), tickets + threads, signaux d'écoute, prompts,
codebase (docs + code commenté). **Hybride structuré + sémantique** :
filtres d'abord (rapide, précis), vecteurs ensuite (rappel), fusion.

**Interface : tool unique `memory_search`.**

```yaml
memory_search:
  query: "objections prix artisans email"     # libre, langage naturel
  filters:                                    # structuré, optionnel
    types: [lesson, episode, ticket]
    venture: current
    since: "2026-08-01"
    tags: [pricing, artisans]
  top_k: 5
  budget_tokens: 2000                         # garanti : tronque + "affine ta requête"
  # → [{type, id, score, extrait, lien}, ...] + tokens_used
```

**Règles.**
- **Lecture seule, toujours.** Informe une décision, ne l'exécute jamais.
- **Budget imposé par l'appelant** (contrat de contexte du point) ; garanti.
- **Traçabilité** : chaque recherche loguée (qui, quoi, filtres, résultats,
  tokens). Source U5 ("toujours la même recherche → promouvoir en 1/3") et
  détecteur d'abus ("200 recherches/cycle" → attracteur).
- **Interdictions héritées** : applique les `forbidden` du contrat appelant
  (secrets, PII inutile, autres ventures sauf scope global) — filtrage côté
  tool, pas espoir côté prompt.
- **Index incrémental** : indexation à l'écriture (job dét léger), pas de
  re-index globale. Embeddings versionnés, modèle pinné par hash.
- **Pur vectoriel sans filtres interdit par design** (bruit + tokens).
- **Rate limit** : 3 recherches/cycle/point (policy). Au-delà → log + on
  continue sans (dégradation, pas blocage).
- **Hot path** : voir §6 (hybride par criticité, validé).
- **Audit** : requêtes récurrentes (même pattern 10×/sem) → candidates à la
  promotion en couche 1/3/4. La couche 5 reste une soupape longue traîne.

**Garde-fous.** Interdiction d'indexer secrets/PII (filtrage à l'écriture).
Jamais de PII/secrets dans les extraits retournés (redaction + `forbidden`).

---

## 6. Hot path : hybride par criticité (validé)

- **Voix temps réel** (tours de parole) : **0 recherche couche 5.**
  Contexte pré-chargé + résumé uniquement. Latence critique.
- **Async temps réel** (classifier, qualifier, router — SLA 1h) :
  **1 recherche max** (budget 1000 tokens, timeout 2 s). Échec/timeout →
  on juge sans (dégradation). Logué.
- **Batch et préparation** (consolidation, drafts, juge alloueur,
  builder) : **couche 5 libre** (rate limit 3/cycle/point, budgets larges).

Dans tous les cas : log de manque quand le contexte pré-chargé est
insuffisant ("j'aurais voulu X") → alimente la promotion. Métrique :
taux de manques par point, doit décroître (sinon le pré-chargé est
mal dimensionné).

---

## 7. Embeddings : local dès jour 1 (validé)

- Modèle type `bge-small` / `e5-small` multilingue (384 dim, ~130 Mo).
  Small suffit pour verbatims courts FR/EN (à confirmer par un mini-bench
  sur nos données).
- Runtime : ~300-500 Mo RAM résident, ~20-50 ms/embedding sur 1 vCPU,
  ~2 Ko/vecteur → 100 k souvenirs ≈ 200 Mo. Négligeable à notre échelle.
- Store : `sqlite-vec` (extension SQLite, **même fichier** — P4 respecté,
  pas de nouveau store).
- Modèle **pinné par hash**, versionné ; changement = re-index documenté.
- Coût marginal **0 €**, données ne sortent pas, pas de dépendance metered
  sur le chemin critique mémoire. Latence ~30 ms (vs +100-500 ms en API).
- Interdiction d'indexer secrets/PII quelle que soit l'option (ici :
  filtrage à l'écriture + redaction à la lecture).

Rationnel vs API : le prix API est dérisoire au début mais c'est un impôt
permanent sur chaque lecture mémoire + une dépendance outage + une fuite
de données (verbatims clients, décisions). Le local coûte ~1 jour
d'intégration, payé une fois.

---

## 8. Consolidation (rythme validé : 3 jours, semi-interactif)

- Job batch : épisodes de la période → candidats-leçons (K max, template
  leçon + confiance + sources) + candidats-playbooks/pitfalls +
  promotions pré-chargé + révisions `SERGE.md`.
- Ticket MEMORY : Julien dispose par leçon (garder/modifier/jeter) +
  "tout approuver". Défaut 48h : auto-accepté sauf veto.
- Budget tokens mesuré (pas de cap arbitraire, alerte sur dérive).
- Entrées : épisodes, `requested` P3, OTHER §4, recherches récurrentes
  couche 5, revirements juge, pertes standing/bans (leçons obligatoires).

## 9. Oubli explicite (validé)

- Épisode non référencé par aucune leçon depuis 30 jours → archive froide
  (réversible, requêtable lent). Jamais effacé (couche 2 éternelle).
- Leçon contredite 3 fois → `deprecated` (pas effacée, exclue du retrieved
  sauf demande explicite).
- Acte de gouvernance logué (qui/quoi/quand/pourquoi), visible FYI.
  Pas d'oubli silencieux.

## 10. Invariants mémoire

1. Aucune écriture LLM directe en couches 1/2/3 (consolidateur validé ou
   ticket uniquement).
2. Tout est traçable (qui a écrit/lu quoi, quand). Couche 5 loguée.
3. Tout est supprimable sauf couche 2 (append-only) ; leçons = deprecated,
   jamais effacées.
4. Aucun secret/PII non nécessaire en 3/4/5 (filtrage à l'écriture).
5. Tout résumé est régénérable (supprimer = reconstruit).
6. Budgets de contexte par point, mesurés (cf. matrice C étendue).
7. Kill-switch par point LLM : `enabled: false` → fallback dét immédiat.
