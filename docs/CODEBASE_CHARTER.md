# Charte belle codebase Serge

Version : 1.0 (2026-09-09)
Statut : OWNER-CONTROLLED — Julien seul peut amender. Propositions (assistant, Serge, Meta-Grok) avec rationnel + preuve, jamais en autonome.
S'applique à : tout code produit pour Serge à partir de cette date — assistant, Serge lui-même, Meta-Grok (quand il reviendra), futurs contributeurs.
Objectif : le maximum de capacité économique avec le minimum de code, lisible, scalable, sans attracteurs ni compute inutile.

Les 5 principes (P1-P5) ci-dessous sont FIGÉS avec Julien le 2026-09-09.
Les 5 règles opérationnelles (R1-R5) sont FIGÉES avec Julien le 2026-09-09 — voir §7.
R6 (doc vivante) ajoutée par Julien le 2026-09-12.

---

## P1 — Un fichier = une responsabilité, < 500 lignes de logique

**Règle.** Un fichier fait une chose, dicible en une phrase, lisible en ~15 min.
Plafond : **500 lignes de logique** (hors lignes vides et imports triviaux).

**Données déclaratives à part (exception validée).** Un module légitimement gros
(réducteur 40 tables, policy 50 règles) passe en **données, pas en code** :
fichier YAML/JSON de règles + moteur maigre (< 150 lignes). Les 500 lignes
s'appliquent au code ; les tables de règles ne comptent pas comme logique.

**Dépendances en arbre, pas en grappe.** `guard.py` peut importer
`retry_policy.py`, l'inverse est interdit. Pas d'imports circulaires dans
`orchestrator/` — vérifié par test (`test_no_circular_imports`).

**Méthode de refactor (extraction progressive, pas big-bang).** On n'efface pas,
on extrait module par module, chaque extraction validée par les tests qui
restent verts. Ordre suggéré : raisons/codes d'abord (facile), policies
ensuite, scheduler en dernier.

**Exemples cibles (état live au 2026-09-09).**

`portfolio_guard.py` (7 937 lignes) → `portfolio/` :

```text
portfolio/
  guard.py          # ~200 lignes : "cette tâche passe-t-elle ? oui/non + code"
  retry_policy.py   # ~300 lignes : RETRY_BLOCKED_*, limites, backoff, gel
  disposition.py    # ~300 lignes : SELECT/REJECT/WAIT des candidats
  freeze.py         # ~200 lignes : gel "once-miss"
  reasons.py        # ~150 lignes : codes de refus en enum, pas de prose
```

`orchestrator.py` (20 385 lignes) → `orchestrator/` :

```text
orchestrator/
  scheduler.py      # "quel est le prochain READY ?" — 100 % SQL, 0 LLM
  director.py       # planification — seul fichier autorisé à planifier au LLM
  worker.py         # invocation (un rôle, une tâche, un budget)
  contracts.py      # validation des contrats runtime
  tokens.py         # budgets, occupancy, réservations
```

Ce découpage prépare P2 : la frontière LLM/déterministe devient une
**frontière de fichiers**, vérifiable par `grep`.

**Contre-exemples à démanteler en premier.** `orchestrator.py` (20 k),
`portfolio_guard.py` (8 k), `economic_action_class.py` (5 k),
`experiment_decision.py` (3,6 k), `burn_in.py` (2,7 k — devrait vivre
dans `tests/`, pas dans l'orchestrateur).

---

## P2 — Frontière LLM/déterministe explicite, mesurée et révisable

**Règle.** Chaque point de jugement LLM est **déclaré** dans le code, avec la
checklist du test du besoin (4 cases obligatoires) + le risque de propagation.
Pas de LLM invisible noyé dans des prompts ou des `invoke_*` génériques.

**Checklist du test du besoin (vraie checklist, obligatoire).** Plus on coche
de cases, plus le LLM est justifié :

1. **Entrée variable ?** L'input ne tient pas dans un schéma fermé (texte
   libre, pages web, réponses humaines).
2. **Sortie variable + décision difficile ?** L'output n'est pas une valeur
   dans un enum mais un choix ouvert (rédiger, négocier, concevoir,
   prioriser) que des règles ne couvriraient qu'au prix d'une combinatoire
   explosive.
3. **Information externe nécessaire ?** La tâche exige d'aller chercher
   (recherche web, lecture de docs, exploration) avant de décider — le LLM
   comme agent chercheur, pas comme fonction.
4. **Dérive absorbée ?** Le domaine dérive vite (formulations prospects,
   layouts web, APIs) : la règle marcherait aujourd'hui mais pourrirait en
   6 mois ; le LLM absorbe la dérive gratuitement.

Test qui **disqualifie** le LLM : entrée fermée + sortie dans un enum + pas de
recherche + domaine stable = règle, sans discussion (ex. scheduling :
"quel est le prochain READY ?" = requête SQL).

**Risque de propagation (détermine le garde-fou).** Deux composantes :

- **Criticité** : irréversible financier/juridique/contractuel (paiement,
  signature, engagement) → barre haute, garde-fou proportionné.
- **Perte de productivité** = probabilité d'erreur × travail aval gaspillé
  × temps de détection. Une erreur en amont (mauvaise venture créée) se
  propage en cascade (tâches, artifacts, semaines) ; une erreur en aval
  (mauvais slot de template) est locale et détectée au cycle suivant.

**Hiérarchie par défaut (idée conservée, définitions précises repoussées à la
fin du rework architectural).**

- **Aval** (classifier une réponse, remplir un slot) : LLM libre, erreur
  locale.
- **Milieu** (qualifier un prospect, scorer un test) : LLM + seuils
  déterministes, erreur bornée par quotas.
- **Amont** (créer une venture, choisir un marché, hypothèse de test, prix) :
  LLM + veto/notification owner, car l'erreur se propage.

**Mesure, pas de cap arbitraire.** Chaque point enregistre tokens, durée,
verdict (traçabilité). Pas de plafond tokens par call — le call se termine
quand il se termine. **Alertes sur dérives vs médiane 7 jours**
("3× la médiane", "50 invocations/cycle au lieu de 2" = attracteur suspect
→ gel + remontée). Repli routable obligatoire en cas d'échec. Retry aveugle
interdit : chaque retry change quelque chose (contexte, modèle, découpage),
puis code routable après N tentatives. **Seul budget dur : le plafond
financier global** (€/jour compute LLM, dégradation gracieuse au-delà).

**La frontière se déplace dans les deux sens** via la consolidation :
LLM → règle quand le pattern se stabilise ("2 verdicts distincts en 500
calls"), règle → LLM quand les edge cases s'accumulent (signal de dérive).

**Format de déclaration (exemple).**

```python
# LLM-CHECKLIST: entree=oui (texte libre prospect)
#                sortie=oui (binaire + justification 1 phrase)
#                info_externe=non | derive=oui (formulations)
# LLM-RISK: propagation=moyen (1 email raté max, détecté au cycle suivant)
# LLM-FALLBACK: REJECT + code PROSPECT_UNQUALIFIED
# LLM-BUDGET: mesuré, alerte si > 3x médiane 7j
def qualify_prospect(prospect: Prospect, icp: ICP) -> QualifyVerdict:
    ...
```

**Prompts versionnés.** Pas de prompt inline dans le code métier :
dossier `prompts/`, un fichier par point de jugement, variables nommées,
relisables et amendables par la consolidation.

---

## P3 — Les interpréteurs déterministes ne lisent jamais de texte libre

**Règle.** Agents entre eux : **texte libre autorisé** (leur espace de
travail, probablement leur meilleur protocole — non réglementé).
Agent → interpréteur déterministe (parser, scheduler, guard, broker,
reducer) : **structures typées uniquement**. Si une décision dépend d'un
champ texte libre, c'est un bug.

**Forme imposée : enums fermés + champ `requested`.**

```python
@dataclass
class WorkerOutcome:
    status: WorkerStatus       # enum FERMÉ : DONE | BLOCKED | FAILED | NEEDS_INFO
    code: str                  # enum FERMÉ par domaine (liste fixée dans le code)
    evidence_ids: list[str]
    note: str                  # une phrase, logs humains et Mission Control UNIQUEMENT
    requested: str = ""        # "ce que je voudrais dire/faire et que les codes
                               #  ne permettent pas" — vide 99 % du temps
```

- Enums **fermés** : le déterministe route vite, sans ambiguïté, sans file
  bloquante.
- `requested` : frustration exprimée en langage naturel, **adressée à
  Meta-Grok/consolidation** (contexte max : tâche, venture, tentatives,
  pourquoi aucun code ne convient, proposition). Relu en batch (jamais
  bloquant), décide : nouveau code officiel, reformulation, ou bruit.
  Exposé dans Mission Control ("demandes d'évolution" + contexte).
  Le prompt d'aide à la rédaction (`à qui, quoi inclure pour être valide`)
  sera designé avec les prompts (P2).
- Le LLM produit du JSON structuré (function calling). Validation de schéma
  par l'appelant, fail-fast.

**JSON malformé.** 2 recalls silencieux au LLM d'origine ("voici l'erreur,
reformule") → si toujours raté, code routable `LLM_OUTPUT_MALFORMED` (c'est
suspect). Les recalls sont **comptés** dans les métriques du point
("40 % de recalls cette semaine" = prompt ou schéma à revoir).

---

## P4 — Zéro duplication de vérité

**Règle.** Un fait = une source. Si deux représentations divergent, on en
supprime une — jamais de couche de synchronisation. La chasse aux doublons
est une mission permanente (run Meta-Grok "chasse aux duplications" à garder
et consolider, cause historique de nombreux bugs).

1. **SQLite (`serge.db`) est l'autorité unique des faits métier** :
   ventures, tâches, prospects, communications, paiements, décisions,
   leçons. Un seul endroit où écrire, un seul où lire.
2. **Vues dérivées en mémoire uniquement, via des tools partagés.** Pas de
   fichiers intermédiaires (fini les JSON d'état périmés sans date de
   péremption). Quand Serge ou le code a besoin d'une vue, il appelle un
   tool qui lit la DB et met le résultat dans le contexte. Les tools sont
   partagés : scheduler déterministe, workers LLM (function calling),
   Mission Control — une seule implémentation, un seul comportement.
3. **Fichiers autorisés sous `state/`** : la DB elle-même, les traces
   append-only (logs, cycles, evidence), les artifacts opaques (landings
   HTML, PDFs). Tout le reste est un bug.
4. **Zéro constante métier dupliquée.** Un prix, seuil, hostname par défaut
   n'existe qu'à un endroit (fichier de policy, voir R4 en discussion).
5. **Cache mémoire avec TTL explicite si besoin de perf**, jamais de fichier
   cache. Un cache périmé se régénère ; il ne ment jamais plus de N secondes.

**`queue/` (dossiers pending/running/done/...) : archivé en lecture seule.**
Ne sert à personne (Julien ne s'en sert jamais), doublon de la table `tasks`.
Le nouveau scheduler est 100 % SQL dès le premier jour. Les dossiers
actuels restent sur disque comme archive historique (archéologie des bugs,
patterns à ne pas reproduire), déjà exclus du seed kit (`never_copy`).
Nouveau code : ne les lit ni ne les écrit.

**Test mécanique.** Toute vue dérivée est une fonction pure de la DB :
régénérer et comparer — si ça diffère, quelqu'un a écrit dans la vue,
c'est un bug.

---

## P5 — Les tests prouvent le comportement, pas l'implémentation

**Règle.** Un test valide **reste vert quand on change l'implémentation sans
changer le comportement, et rouge quand le comportement change.**
Les tests de détails d'implémentation (format de clé, structure interne,
ordre d'appels privés) sont du bruit et partent.

**E2E fonctionnels en priorité, 3 niveaux.**

| Niveau | Quoi | Quand | Compute |
|---|---|---|---|
| E2E déterministe | Funnel complet, LLM mockés (verdicts scriptés) : prospect → envoi → réponse simulée → décision | À chaque changement | Nul |
| E2E LLM réel ciblé | Points de jugement critiques (qualifier, classifier, scorer) avec vrais calls sur fixtures | Avant merge d'un changement de prompt/point | UN PEU (dizaines de calls) |
| E2E live canary | Cycle réel sandbox wrappé (1 prospect test, 1 € owner→owner) | Hebdo ou avant activation d'une feature externe | Borné et tracé |

Le niveau 1 attrape ~90 % des régressions pour 0 token. Jamais de test qui
spamme le monde réel pour valider un refactor.

**Code hors charte isolé.** Scripts one-shot, migrations, debug tools vivent
dans `scripts/` + `tools/`, avec `README.md` explicite : hors charte, pas de
garantie, pas de tests requis. **Interdiction d'importer depuis le code sous
charte vers ce dossier** — vérifiée par test de structure. Documenté pour les
futurs contributeurs.

**Delete-first.** Si les E2E sont verts et larges, on supprime directement
(git comme filet, pas de période d'observation). "Larges" est mesuré :
**chaque capacité externe (envoyer, payer, publier, appeler) a au moins un
E2E qui l'exerce en mock + un E2E qui vérifie son garde-fou** (refus si quota
dépassé, sans consentement...). Chemin passant + chemin refusé = filet réel.
Si le refus manque, on écrit le test manquant AVANT de supprimer.

---

## Métriques de suivi (à afficher dans Mission Control plus tard)

- LOC total, plus gros fichier (cible : aucun > 500 logique).
- Appels LLM par cycle, tokens par cycle (médiane + dérives).
- **Tokens par euro de revenu** — le coût cognitif par euro gagné tend vers zéro.
- `requested` non traités, recalls JSON, E2E passants/refusés par capacité.

## Application aux codeurs (assistant, Serge, Meta-Grok, contributeurs)

- Cette charte s'applique à tout nouveau code dès maintenant.
- Tout écart doit être signalé explicitement dans le diff ("écart P1 : ...,
  raison : ...") — jamais silencieux.
- Amendements : proposition + rationnel + preuve → décision Julien.

---

## §7 — Règles opérationnelles R1-R6 (R1-R5 FIGÉES le 2026-09-09 ; R6 le 2026-09-12)

### R1 — Diffs < 300 lignes, dépassement interactif obligatoire

Un changement fait **< 300 lignes de code prod** (ajouts + suppressions).
Tout dépassement exige l'approbation explicite de Julien, avec justification
écrite de pourquoi c'est impossible en moins (ex. "extraire ce module exige
de déplacer ses 400 lignes d'un coup, sinon les imports sont cassés entre
deux commits"). Pour les agents autonomes (plus tard) : ticket d'approbation,
même règle — ça rejoint l'architecture d'interactivité.

- **Tests et documentation exclus du plafond.** Le plafond s'applique au
  code prod. Si les tests dépassent 300 lignes, le codeur dit en une ligne
  pourquoi (ex. "couvre 6 capacités × passant/refusé"). La doc (R6) non plus
  ne compte pas — on ne saute pas un paragraphe pour tenir les 300.
- **Migrations mécaniques exclues** (renommage global, extraction pure sans
  changement de comportement) si et seulement si prouvées mécaniques : diff
  relue + E2E verts avant/après identiques. Sinon, approbation comme le reste.
- Fichiers générés et lockfiles exclus du comptage.

### R2 — Docstrings Google-style, typage fort, outillage moderne

**Docstrings.** Première ligne du module = quoi/pourquoi en une phrase.
Fonctions publiques : format Google complet (Args/Returns/Raises).
Fonctions privées (`_helper`) : une ligne suffit, sauf logique subtile.

```python
"""Décide si une tâche peut s'exécuter (point d'entrée du guard)."""


def decide(task: Task, policy: Policy) -> GuardVerdict:
    """Décide si une tâche passe le guard portfolio.

    Args:
        task: Tâche candidate avec son action, sa venture et son historique.
        policy: Policy active (quotas, fenêtres, capacités disponibles).

    Returns:
        Verdict avec décision booléenne et code routable
        (ex. ALLOWED, RETRY_BLOCKED, QUOTA_EXCEEDED).

    Raises:
        GuardError: Si le contrat de la tâche est invalide.
    """
```

**Pas de fourre-tout.** Interdit : `utils.py`, `helpers.py`, `common.py`.
Chaque helper vit dans le module qui possède son invariant ; s'il est
vraiment partagé, il obtient un vrai nom (`e164.py`, `backoff.py`, `csvio.py`).

**Typage fort + outillage (dans le repo, voir `pyproject.toml`).**

- `uv` comme gestionnaire (install : `curl -LsSf astral.sh/uv/install.sh | sh`).
- `ruff` : lint + format (hook pre-commit, fichiers modifiés).
- `ty` (Astral) : type checker, hook pre-commit + CI. Choisi pour : vitesse
  (Rust, 10-60× mypy), toolchain cohérente avec uv/ruff, et silence sur le
  code legacy non annoté (`Unknown`, pas d'erreur) → adoptable immédiatement
  sur 87 k lignes sans tout typer d'un coup. Alternative stricte (Pyrefly,
  Meta, 1.x stable, ~96 % conformance spec) : à réévaluer dans 6 mois quand
  `kit/` sera entièrement typé.
- `pre-commit` : ruff + ty + scan secrets. `pre-commit install` requis après
  clone ; un commit qui ne passe pas les hooks ne part pas.

### R3 — Dépendances : deux phases

**Phase rework (maintenant).** On fait tout ensemble de toute manière :
chaque nouvelle dépendance est discutée avec Julien, pas de processus
spécial nécessaire.

**Phase autonome (Serge seul, plus tard).** Serge peut dépenser et ajouter
des dépendances externes **sans approbation** si et seulement si :

- dans les limites : 50 €/mois, plafonds unitaires, constitution Serge +
  constitution Meta-Grok respectées ;
- chaque dépendance/service est **déclaré** (quoi, pourquoi, coût, données
  touchées) et **tracké** en subscription dans la DB (P4 : la DB est
  l'autorité, renouvellements suivis).

Tout ce qui dépasse (coût, nouveau compte tiers sensible, accès PII/secrets/
financier hors politique) = approbation Julien obligatoire, refusé sinon.

### R4 — Un fichier de policy + fenêtre Mission Control (UI à designer)

- **Un seul fichier**, `config/policy.yaml`, **versionné** : seuils,
  fenêtres, quotas, feature flags, limites financières. Typé, validé par
  schéma au chargement (seuil négatif ou quota absurde = refusé au boot).
  Zéro nombre magique dans le code — vérifié par test (grep + linter).
- **Fenêtre Mission Control "Policy"** (à designer ensemble avec le reste
  de Mission Control) : voir/modifier les valeurs, validation (même
  schéma), historique (qui, quand, avant → après), rollback en un clic.
  Droits : Julien modifie directement ; Serge et Meta-Grok proposent
  (diff + raison), n'appliquent jamais seuls.
- Propositions de Serge ("ce quota est atteint 9 fois sur 10, je suggère
  X → Y") : le canal exact (notif policy vs tickets vs canal dédié) sera
  décidé avec l'architecture d'interactivité — pas tranché ici.

### R5 — Review P1-P5 obligatoire après chaque fix

Pas juste "cleanup" : une vraie review, tracée dans le message de commit :

```text
fix: <quoi>

P1-P5 review:
- P1: fichiers touchés < 500 lignes ? nouveau découpage nécessaire ? non
- P2: nouvel appel LLM ? non (ou: oui, déclaration ajoutée)
- P3: nouvelle structure échangée ? non (ou: oui, enum fermé + requested)
- P4: nouveau fait stocké ? non (ou: oui, table X, tool Y)
- P5: E2E couvrent passant + refusé ? oui (tests: ...)
- R6: doc vivant à jour ? oui (docs/X.md §…) / écart + ticket
Cleanup: imports/branches mortes/commentaires périmés — fait.
```

Si une case révèle un problème (ex. "ce fix fait passer le fichier à
600 lignes"), le refactor suit dans le même changement ou fait l'objet
d'un ticket explicite — jamais ignoré silencieusement.

### R6 — La documentation vivante part dans le même changement

**Règle.** Un changement qui modifie un comportement, une surface (API, UI,
CLI), un contrat, un point LLM, une table, ou une procédure d'install
**met à jour le document qui le décrit**, dans le même commit — ou le
commit suivant immédiat du même lot si R1 force le découpage.

Ce n'est pas un journal de bord. C'est le **doc qu'un étranger lirait
aujourd'hui** pour comprendre l'état réel. On corrige le paragraphe qui
ment ; on n'empile pas une note « aussi, on a changé X ».

**Quel document.** Celui que lirait quelqu'un qui n'a pas le diff :

- Mission Control → `docs/MISSION_CONTROL.md`
- un point de jugement → `docs/LLM_MATRIX.md` (+ prompts si P2)
- mémoire / funnel / interaction → le `*_ARCHITECTURE.md` concerné
- install, secrets, contrat d'instance → `docs/INSTALL.md` et le contrat
- une capacité nouvelle sans doc → on écrit le paragraphe manquant

**Pas de doc ?** On l'écrit (un paragraphe suffit) ou on pose un ticket
explicite « doc manquante : … ». Jamais silencieux.

**Hors périmètre.** `scripts/` et `tools/` (déjà hors charte, P5).
Commentaires de code. Cette charte : Julien seul amende.

**Hors plafond R1.** Comme les tests : la doc ne compte pas dans les
300 lignes prod. On ne « gagne » pas un commit en laissant le doc périmé.

**Écart.** Code sans doc à jour = « écart R6 : … » dans le commit + ticket.
Sinon c'est un bug P4 : deux vérités (le code, et un markdown qui ment).
