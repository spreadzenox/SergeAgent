# Charte belle codebase Serge

Version : 1.2 (2026-09-15)
Statut : OWNER-CONTROLLED — Julien seul peut amender. Propositions (assistant, Serge, Meta-Grok) avec rationnel + preuve, jamais en autonome.
S'applique à : tout code produit pour Serge à partir de cette date — assistant, Serge lui-même, Meta-Grok (quand il reviendra), futurs contributeurs.
Objectif : le maximum de capacité économique avec le minimum de code, lisible, scalable, sans attracteurs ni compute inutile.

Les 5 principes (P1-P5) ci-dessous sont FIGÉS avec Julien le 2026-09-09.
Les 5 règles opérationnelles (R1-R5) sont FIGÉES avec Julien le 2026-09-09 — voir §7.
R6 (doc vivante) ajoutée par Julien le 2026-09-12.
R7 + §8 (catalogue, SHA, pas de code mort) ajoutés par Julien le 2026-09-14.
R8 (checklist avant merge) ajoutée par Julien le 2026-09-15.
MC = Mission Control

---

## P1 — Un fichier = une responsabilité, < 500 lignes de logique

**Règle.** Un fichier fait une chose, dicible en une phrase, lisible en ~15 min.
Plafond : **500 lignes de logique** (hors lignes vides et imports triviaux).

**Privilégier le mapping** Lors de l'implémentation d'une logique conditionnelle à multiples conditions d'entrées et de sorties, créer une table json ou yaml pour écrire les règles de mapping. Les tables de règles ne comptent pas comme logique.

## P2 — Règles régissant les invocations llm

**Règle.** Chaque point de llm-points LLM est **déclaré** dans le code et dans la database, son intervention doit être absolument nécéssaire.

**Prompts modifiables facilement** Pas de prompt directement dans le code métier :
Tout doit être dans la base de donnée et directement modifiable depuis le mission control.

**Mesure des performances des llm-points**: Pour chaque jugement, il faut répertorier en base de données les métriques suivantes, construites au fur et à mesure des utilisations:
- coût moyen par invocation
- coût total des invocations effectuées

**Pas de passage de contexte**: Le contexte initial d'un llm lors d'une invocation est déterministe. Il reçoit dans son contexte uniquement un prompt system défini depuis le MC et ses outils. Le travail des autres llm est contenue dans la DB. Les agents parlent entre eux uniquement via les données laissés en BDD.

**Organisation des outils de récupération mémoire**: Toute la mémoire d'un llm est contenue dans la DB. Il peut lire que certaines tables de celle-ci. Chaque jugement llm a un outil personnalisé de lecture mémoire d'un type dédié. Un outil de ce type est instancié en précisant:
- les tables auxquelles de llm a accès
- dans ces tables, à quelles colonnes il a accès
- dans ces colonnes, à quelle lignes à t'il accès. Les lignes auxquelle il a accès sont paramétrées uniquement par les colonnes catégorielles (enum sql).
Tout ce qui régie les permissions de l'outil sont modifiables depuis le MC, dans la page de l'outil.
Dans la description de l'outil, celui ci déclare les accès mémoire dont il dispose au llm, il déclare également la description de chaque table et ce qu'elle contient.

**Contrôle des mauvais formats** Certains llm seront amenés à rendre du texte dans un format particulier (comme des json par exemple), le format devra systématiquement être vérifié par une class Pydantic. En cas d'échec, le llm est rappelé directement avec son contexte + le détail de l'erreur. Ce n'est pas une nouvelle invocation llm. Le llm aura droit à un nombre fini d'échec, paramétrable depuis le MC.

## P3 — Tout vie en base de donnée

**Une information est stockée à un unique endroit**: Toute information destinée à être mutable ou paramétrable est stockée une unique fois en base de donnée et les objets paramétrables de l'architecture de Serge y sont stockés. Par exemple, la liste des llm-points et leur ordre, les prompts system des llm ou bien l'ensemble des permissions mémoire des llm-points sont stockés en bdd.

**La documentation vivante**: Toutes les documentations du code vivent en base de données et doivent impérativement être updatées à chaque changement. Le MC est généré dynamiquement en fonction de ce qui existe en base de donnée.

**Liens code/DB** : Comme chaque fonctionnalité de Serge existe en BDD, le code qui régit chaque objet et chacune de ses fonctionnalitées (l'ensemble des fichiers) est traqué en BDD. Chaque table d'objet a une colonne qui référence l'ensemble des fichiers qui régissent son comportement. Le SHA de ces fichiers est recalculé par les tests

---

## P5 — Les tests prouvent le comportement, pas l'implémentation

**Règle.** Un test valide **reste vert quand on change l'implémentation sans
changer le comportement, et rouge quand le comportement change.**
Les tests de détails d'implémentation (format de clé, structure interne,
ordre d'appels privés) sont du bruit et partent.

**E2E fonctionnels en priorité, 3 niveaux.**
Où ça tourne : [DEV_TOOLING.md](DEV_TOOLING.md).

| Niveau | Quoi | Quand | Où |
|---|---|---|---|
| E2E déterministe | Funnel complet, LLM mockés (verdicts scriptés) : prospect → envoi → réponse simulée → décision | Chaque push / PR | CI PR/`main` + pre-push (0 token) |
| E2E LLM réel ciblé | Point critique (`classify_reply`) via OpenRouter, fixtures, cap 3 | Chaque `git push` | pre-push seulement (clé locale) |
| E2E live canary | Cycle réel sandbox wrappé (1 prospect test, 1 € owner→owner) | Hebdo ou avant activation d'une feature externe | Manuel — jamais CI ni hook |

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

## §7 — Règles opérationnelles R1-R8 (R1-R5 FIGÉES le 2026-09-09 ; R6 le 2026-09-12 ; R7 le 2026-09-14 ; R8 le 2026-09-15)

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
- `pre-commit` : ruff + ty + scan secrets au commit ; au pre-push, gates
  + suite complète (E2E + LLM live). Pas de clé OpenRouter locale = pas
  de push. Jamais de secret en CI PR. `pre-commit install` requis après
  clone.

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
- un point de llm-points → `docs/LLM_MATRIX.md` (+ prompts si P2)
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

### R7 — Pas de code mort, pas de documentation morte

**Règle.** On n'empile pas une feature à moitié. Pas de bouton sans
writer, pas d'API sans appelant, pas de projecteur orphelin, pas de
paragraphe qui décrit un écran supprimé. Soit on finit, soit on
enlève — y compris tests et docs du même lot (R6).

« On gardera pour plus tard » n'est pas une raison de laisser du mort.
Un commentaire `TODO` sans ticket = écart (`écart R7 : …`).

### R8 — Checklist avant merge

Validée par Julien le 2026-09-15. S'applique à toute PR avant merge.
Pas une quatrième liste d'objets : on ouvre les sources (§8, trois
familles). Écart : `écart merge : …` dans le commit, jamais silencieux.
R1, secrets, `docs/slides/` interdit, branches + PR (pas de push
`main`) restent en vigueur.

Pour chaque objet touché (ajout / modification / suppression), dans les
trois familles (catalogue, schéma, policy) :

1. **Docs vivantes.** Aucun paragraphe de `docs/` ne contredit le diff.
   On corrige celui qui ment ; on n'empile pas une note.
2. **Base.** Semence ou migration posée ; fiche / `doc_md` / champs
   Policy à jour ; SHA recalculé si famille catalogue ;
   `tests.test_catalogue_sha` vert.
3. **Liens et appelants.** Graphe n-n, enums fermés, et tout
   reader / writer / garde existant qui doit parler le nouveau contrat.
   Suppression : plus aucune mention (code, docs, MC, tests). À défaut :
   ticket explicite dans le même lot.
4. **Tests.** P5 passant + refusé. E2E déterministe si un flux
   opérateur ou un kind change. E2E LLM seulement si un llm-points /
   prompt / tool exposé au LLM change. Pas de test fantôme, pas de
   harnais LLM inventé pour du déterministe.
5. **Mission Control.** Si c'est censé se voir, un parcours opérateur
   le montre (pas une capture). Aucune jauge ni phrase qui invente un
   fait absent du canon. Les autres pages qui lisent le même fait
   restent d'accord.

---

## §8 — Comment modifier Serge (catalogue, doc en base, SHA)

Ajouté par Julien le 2026-09-14. S'applique à tout assistant / IA /
contributeur qui touche le dépôt.

### Serge est un catalogue d'objets, pas un tas de pages

La vérité des **objets** (étapes, invocations LLM, tools, invocations
techniques, canaux, liens d'épine) vit dans **SQLite** :

| Objet | Table | Semence code |
|---|---|---|
| Étape | `pipeline_steps` | `serge/etapes.py` + `serge/etape_fiches.py` |
| Lien d'épine | `etape_liens` | `serge/etape_fiches.py` (`LIENS`) |
| Invocation LLM | `llm_points` | `serge/llm_registre.py` + `config/llm-points.yaml` |
| Tool | `tools` | `serge/outils.py` (`SEED`) |
| Invocation technique | `tech_invocations` | `serge/tech_registre.py` |
| Canal | `canaux` + `brique_canaux` | `serge/canaux.py` (`SEED`, `JONCTIONS`) |

Mission Control **lit la base** (fiches, graphe Live, docs d'étape).
Changer un texte de fiche = changer la semence, laisser le boot
remettre la base à jour — **pas** dupliquer le texte dans un JS ou
un markdown « en plus ».

P4 : un fait = une source. Le hostname, un prix, un titre d'étape,
un SHA de fichier : **une** colonne, pas deux copies.

### Trois familles d'objets vivants

Pas d'inventaire markdown parallèle (il pourrirait). On ouvre :

1. **Catalogue** — table ci-dessus. Semence + `doc_md` + SHA.
2. **Faits / schéma** — `TABLES` + migrations `apply_v00N`. Fiche
   table MC (`serge/mc/proj_sqlite.py`, `CATALOGUE`).
3. **Policy / flags / instance** — `config/policy.yaml`, snapshots,
   contrat d'instance. Champs du formulaire MC.

Avant merge : R8.

### Comment ajouter ou modifier un tool / un point / une étape

Dans **le même changement** (R1 peut découper, R6 et les tests suivent) :

1. **Déclarer l'objet** dans la semence (table ci-dessus). Id fermé (P3).
2. **Pointer les fichiers** qui l'encodent :
   - tools / LLM / tech / canaux : colonne `code_path` (chemin relatif repo) ;
   - étapes / liens / canaux : chemins dans `serge/objet_sha.py` (`_FICHIERS_FIXES`).
   **Tout nouveau fichier** que tu crées pour ce tool (handler, prompt,
   helper dédié) doit être dans `code_path` **ou** ajouté à
   `_FICHIERS_FIXES` — sinon le SHA ne le voit pas.
3. **Écrire la doc de l'objet en base** : `titre`, `doc_md` (ou champs
   fiche d'étape). C'est ce que MC affiche. Un `docs/*.md` qui répète
   le même fait sans être la source = doublon interdit.
4. **Tests de comportement** (P5) : chemin passant + chemin refusé.
5. **Verrou SHA** : `tests.test_catalogue_sha` doit rester vert.
   S'il hurle « rajouté / supprimé / SHA » :
   - tu as oublié la semence, ou
   - tu as oublié `code_path` / `_FICHIERS_FIXES`, ou
   - le contenu a changé → recopier le SHA calculé dans
     `serge/catalogue_lock.py` **dans ce commit**.
   Ne jamais désactiver le test. Ne jamais committer un SHA inventé.
6. **R6** : le document qu'un étranger lirait (`docs/DB.md`,
   `docs/MISSION_CONTROL.md`, `docs/LLM_MATRIX.md`…) décrit l'état
   réel après le changement.

Sans 1–6, le changement n'est pas fini. Le pre-push / CI refuse.

### Documentation vivante (deux couches)

- **Fiches d'objets** → colonnes SQLite (source). Semées au boot.
- **Procédures, contrats, cette charte** → `docs/*.md` (R6).

Changer le comportement d'une étape sans toucher `etape_fiches.py`
(donc la base) = le MC ment. Changer le MC sans changer la base =
théâtre.

### Coupe-circuits (En direct)

Trois nappes, une API `POST /owner/api/coupe` :

1. Serge (heartbeat ordonnanceur) — bouton rouge en haut.
2. Étapes (`pipeline_steps.enabled`) — bas de page.
3. Kinds (`runtime_flags.kind.*`) — bas de page.

Pas de second kill voix dans l'onglet Voix : même levier, En direct.
