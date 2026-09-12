# Architecture d'interactivité Julien ↔ Serge (H)

Version : 1.0 (2026-09-09)
Statut : VALIDÉ avec Julien le 2026-09-09 (discussion H).
S'applique à : le rework kit (nouveau module `tickets/` + bot Discord + page Mission Control).
Principe : **tout échange décisionnel est un ticket**. Un seul objet, un seul lifecycle,
plusieurs projections (Discord, Mission Control). DB = vérité, UI = miroirs temps réel.

---

## 0. Cas couverts (12 types, extensible)

| # | Type | Rôle | Urgence |
|---|---|---|---|
| 1 | HYPOTHESIS | Co-rédaction + validation des hypothèses de market tests (niveau full) | Normale |
| 2 | VETO_AMONT | Création venture, verticale, prix, décisions propagatives | Normale |
| 3 | GUICHET | Étapes déléguées humaines (CAPTCHA stream, KYC, signature, 3DS) — A1 §14.1b | **Urgente (minutes)** |
| 4 | PUBLICATION | Drafts Reddit/LinkedIn/forums + contexte + risque | Normale |
| 5 | MEMORY | Consolidation 3 jours : N leçons à garder/modifier/jeter | Fenêtre 48h |
| 6 | POLICY | Propositions R4 (diff seuils/quotas + justification + impact) | Normale |
| 7 | R1_OVERRIDE | Dépassement 300 lignes (pourquoi indécoupable + risques) | Normale |
| 8 | FYI | Digest, résultats de tests, signaux d'écoute, rapports (pas de réponse) | Aucune |
| 9 | REQUESTED | Demandes d'évolution P3 des LLM (lecture seule owner, batch Meta-Grok) | Lecture seule |
| 10 | OWNER_ORDER | Ordres/questions/veto/infos owner → Serge (sens inverse) | Variable |
| 11 | QNA | Questions générales de Serge : QCM (2-4 options + "Autre") + texte libre + bouton "Discuter" (thread). Tool toujours accessible à tout agent. | Normale, jamais bloquant |
| 12 | ALERT | Incidents graves détectés (panne trunk, suspension compte, anomalie financière) : "voilà + voilà ce que j'ai fait". Pas de décision, juste tracé. | Haute (notifie, n'attend pas) |

**Ajouter un 13e, 20e type = ajouter un bloc YAML**, pas toucher au moteur (voir §7).

---

## 1. Principes directeurs (6)

1. **DB = vérité, UI = projections temps réel.** Le ticket vit dans SQLite (P4).
   Discord et Mission Control affichent la même source et se mettent à jour en
   temps réel (mêmes outils, mêmes événements). Thread supprimé → le ticket
   survit et se re-projette. Jamais l'inverse.
2. **Décision = acte typé, discussion = texte libre.** Discussion en prose dans
   les threads autant qu'on veut ; trancher = bouton explicite (Approuver /
   Rejeter / Éditer / Forcer...). Le système ne parse jamais la prose (owner
   ou agent) pour deviner une décision (P3 appliqué à l'owner).
3. **Tout ticket a une expiry + un défaut annoncé.** Pas de ticket qui pourrit.
   À l'expiry : défaut conservateur connu d'avance (voir tableau §4).
4. **LLM rédige, déterministe gère.** Le LLM écrit les drafts, résume les
   threads, propose ; le lifecycle (états, expiry, routage, exécution) est
   100 % déterministe. Aucun LLM ne décide qu'un ticket est approuvé.
5. **Même vérité partout** (constitution §16). Discord et `/owner` montrent les
   mêmes tickets, états, boutons. Un Yes sur l'un = Yes sur l'autre.
6. **FR + contexte + belle UI (ré R1-explicite Julien).**
   - Toute interaction owner est **en français**, sans jargon interne (ou avec
     définitions), avec **remise en contexte systématique** (où on en est,
     pourquoi on me parle, ce qu'on attend de moi — 1-3 lignes, jamais supposé
     connu).
   - Exploitation maximale de l'UI Discord : embeds, boutons, select menus,
     threads. **Jamais de pavé brut.**
   - **Serge raisonne dans sa langue de travail interne (anglais)** — le FR
     est une couche de présentation (renderer), pas une contrainte de
     raisonnement. Le ticket stocke du structuré ; le renderer FR produit la
     carte. Valable aussi pour Mission Control.
   - Quand pertinent : **choix multiples + réponse libre + bouton "Discuter"**
     (thread dédié) plutôt qu'un binaire sec.

---

## 2. Structure Discord (option validée : forum + urgent + digest)

- **Forum `🎫-tickets-serge`** (1 post = 1 ticket), tags : `veto` `hypothèse`
  `publication` `mémoire` `policy` `R1` `guichet` `question` `alerte`.
  Chaque post = carte de décision + thread + boutons. Tri/recherche natifs.
- **Canal `🔴-urgent`** : miroir auto des `GUICHET` + veto expirant < 1h +
  `ALERT`, avec mention @owner. Rien d'autre. Si ça sonne ici, c'est urgent.
- **Canal `📣-digest`** : FYI, résultats, signaux, rapports. Lecture seule côté
  Serge (il poste). Réaction 🧵 = ouvre un ticket de discussion.

---

## 3. Lifecycle (déterministe)

États : `DRAFT` → `OPEN` → `DISCUSSING` (optionnel) → `DECIDED`
(APPROVED / REJECTED / EDITED) → `EXECUTED` → `CLOSED`.
Branches : `EXPIRED` (→ défaut annoncé + log), `CANCELLED` (Serge : devenu
obsolète, logué avec raison).

Cas spéciaux :
- **MEMORY** : 1 ticket parent par consolidation + N items (leçons). Boutons
  par item (garder / modifier / jeter) + "tout approuver". Discussion en thread.
- **HYPOTHESIS** : versionné (v1, v2...). Commentaires en thread, révisions par
  Serge, validation d'une version précise (référencée, pas "l'idée générale").
- **QNA** : QCM + libre + "Discuter". Expiry 72h, défaut = "Serge décide seul
  et logue" (jamais un veto déguisé qui paralyse).

---

## 4. Expiries et défauts (validés)

| Type | Expiry par défaut | Défaut à l'expiry |
|---|---|---|
| HYPOTHESIS | 48h | Pas de test (refus conservateur) |
| VETO_AMONT | 24h | Refus (ne pas créer) |
| GUICHET | 10-30 min (selon TTL externe) | Tâche en pause propre, re-proposée au prochain cycle |
| PUBLICATION | 24h | Non publié |
| MEMORY | 48h | Leçons auto-acceptées sauf veto (semi-interactif) |
| POLICY | 72h | Pas de changement |
| R1_OVERRIDE | 24h | Découpage imposé |
| QNA | 72h | Serge décide seul + logue |
| ALERT | — (pas de décision) | — (tracé, actions déjà exécutées loguées) |
| FYI | Jamais | Rien |
| OWNER_ORDER (confirmation) | 24h | Ordre non exécuté |

---

## 5. Carte de décision (constitution §17, obligatoire)

Chaque ticket OPEN affiche : quoi est bloqué, pourquoi Serge ne peut pas seul,
sa recommandation, conséquences de Yes et de No, impact financier/contractuel,
expiry + défaut. En français, avec contexte, en embed Discord (jamais de pavé).
Pas d'IDs opaques visibles (binding backend uniquement).

Exemple (GUICHET) :

> **🔴 Guichet — CAPTCHA compte Malt** (expire dans 12 min → pause propre + re-proposition)
> **Contexte :** création du compte Malt pour le bootstrap (démarrée hier 14h).
> **Bloqué à :** 90 % fait (profil rempli, email vérifié). Reste : CAPTCHA image.
> **Pourquoi toi :** je ne peux pas le résoudre moi-même (§14.1b : guichet, pas mur).
> **Recommandation :** résoudre (compte stratégique).
> **Si Oui :** [voir l'écran] → tu résous → je termine (2 min). **Si Non/timeout :** pause propre, retenté demain, 0 € dépensé.
> [🖥️ Voir l'écran] [✅ C'est fait] [❌ Abandonner]

---

## 6. Sens inverse : toi → Serge (validé avec bypass)

Trois voies :
- **Mention @Serge + texte libre** (n'importe quel thread/canal) : routé par un
  classifier (LLM jugé unique, P2) → réponse directe (question factuelle) /
  nouveau ticket (ordre, veto) / ajout au thread courant.
- **Slash `/serge`** : `ask`, `order`, `veto`, `info` — explicite, sans ambiguïté.
- **Boutons** sur tickets existants (cas principal).

**Ordres à grosse conséquence → mini-ticket de confirmation (validé).**
- Un **juge LLM** évalue si l'ordre est à grosse conséquence (critères :
  irréversible ? financier ? externe visible ? N affectés ? juridique ?).
  Déclaration P2 obligatoire pour ce juge.
- Si oui : mini-ticket "tu as demandé X, conséquences : Y. Confirmer ?"
  + Serge peut **discuter l'ordre** (recommandation, contre-proposition) et
  **ouvrir un thread** de discussion. Exécution après confirmation.
- Si non : exécution directe + accusé.
- **Bypass owner** : préfixe `!` / suffixe `--force` / "sans confirmation" /
  `/serge order --force` → exécute sans confirmation. Toujours logué ;
  post-hoc : ticket FYI avec ce qui a été fait (+ undo quand possible).
- **Limite dure : la constitution.** Même avec bypass, un ordre violant les
  interdits §14.1a (faux avis, usurpation, spam illégal...) est **refusé avec
  explication**. Le bypass saute la confirmation, jamais la constitution.

---

## 7. Backend : taxonomie en données (scalable, P1)

Nouveaux types sans toucher au moteur : `config/ticket-types.yaml` (versionné)
déclare chaque type — champs obligatoires (schéma), boutons, expiry, défaut,
rendu (embed/couleur/icônes), template de carte. Le moteur `tickets/` ne
connaît que le lifecycle générique ; le rendu Discord/Mission Control se
construit depuis la déclaration.

Tables (P4, SQLite autorité) : `tickets` (id, type, titre, état, payload JSON
validé, expiry, défaut, thread Discord, versions...), `ticket_events`
(append-only : créé, commenté, décidé, exécuté, expiré...), `ticket_items`
(MEMORY multi-leçons, QCM...). Tools partagés : `open_ticket()`,
`decide_ticket()`, `expire_due_tickets()` (job déterministe chaque cycle),
`render_card()`. Bot Discord et Mission Control = adaptateurs sans logique
métier (P1 : dépendances en arbre).

Idempotence : chaque décision porte `decision_id` ; double-clic = 1 acte.

---

## 8. Mission Control — parité temps réel

Page `/owner/tickets` : même liste, états, actes que Discord, plus : vue diff
(policy, R1), historique complet, recherche/filtres, fenêtre `requested` P3
(lecture + contexte), fenêtre Policy Mission Control (dernier snapshot, R4).
**Règle : tout ce qui est faisable sur Discord est faisable sur /owner, et
inversement.** Discord = rapide/mobile ; /owner = confortable/complet.
Même source (DB), mêmes outils, mises à jour temps réel des deux côtés.

---

## 9. Anti-fatigue + trust zones (validés)

- **Batching** : digest quotidien (FYI + décisions auto + expirations), pas
  15 notifications. Urgent seul = push immédiat.
- **Quiet hours** paramétrables (ex. 23h-8h : seul GUICHET TTL < 15 min notifie).
- **Métriques** (Mission Control) : temps médian de réponse par type, taux
  d'approbation, expirations/semaine, tickets/semaine. Hausse = signal pour
  étendre les trust zones.
- **Trust zones** (après les premiers tickets manuels) : auto-approbation par
  type/venue (ex. "PUBLICATION auto-OK si karma > 500, pas de lien commercial,
  venue en liste verte"). Règle d'extension : taux d'approbation > 95 % sur
  20 tickets → candidate. Chaque auto-approbation loguée, visible, réversible
  quand possible, kill-switch global.

---

## 10. Sécurité

Canaux owner-only. Jamais de secret/PII dans Discord (§15 : liens signés
expirables pour écrans sensibles, ex. stream CAPTCHA — pas de contenu brut).
Auth Discord = snowflake existant ; Mission Control = token existant.
Tout acte sensible = ticket + log + traçabilité.

---

## 11. Migration : remplacer, pas migrer (validé, kit uniquement)

Le nouveau module `tickets/` (+ bot minimal + page /owner) est construit **neuf
sous charte** dans le kit. L'ancien système (approval_broker, owner_console,
endpoint interactions, poll comm) n'est pas recâblé : il reste sur le live
jusqu'au cutover, puis est supprimé (P5 delete-first, E2E des deux faces +
expiry). Les `human_block` en queue au cutover sont **re-créés** comme tickets
GUICHET/VETO propres, pas importés en vrac. Zéro dette héritée.

---

## 12. Métriques de suivi (Mission Control, plus tard)

Tickets/semaine par type, temps médian de réponse, taux approbation/rejet/expiry,
auto-approbations, bypass utilisés, GUICHET résolus vs expirés, backlog actuel.
