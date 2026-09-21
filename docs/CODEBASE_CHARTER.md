# Charte de la codebase Serge

**Statut.** Julien est le seul à amender cette charte. Une IA ou un
contributeur peut proposer un changement avec son rationnel et une preuve,
mais ne l'applique pas de sa propre initiative.

**Périmètre.** Cette charte s'applique au code, aux tests, aux migrations,
aux seeds et à Mission Control du dépôt.

**Objectif.** Maximiser la capacité économique avec le minimum de code,
lisible, testable et sans compute inutile.

**MC** signifie Mission Control.

---

## P1 — Une responsabilité par fichier

Un fichier fait une chose, exprimable en une phrase et lisible rapidement.
Le code Python de `kit/` et `serge/` reste sous **500 lignes par fichier**.
Cette limite est vérifiée par `tests/test_charter.py`.

Une logique conditionnelle avec beaucoup de cas peut être décrite par des
données YAML ou JSON et exécutée par un moteur simple. Les données ne doivent
pas cacher un moteur de décision difficile à lire.

Les imports locaux restent acycliques. Les helpers vivent près de l'invariant
qu'ils protègent ; pas de fourre-tout `utils.py`, `helpers.py` ou `common.py`
pour éviter de choisir un vrai propriétaire.

## P2 — LLM déclarés, mesurés et contrôlables

Chaque point LLM est déclaré dans `config/llm-points.yaml`, dans les registres
du code et dans la table SQLite `llm_points`. La déclaration porte notamment
sur le verdict, le tier, le format de sortie, l'information externe, le
garde-fou, le repli et l'activation.

Un LLM est utilisé lorsqu'une règle déterministe ne suffit pas : entrée libre,
sortie ouverte, information externe ou dérive du domaine. Une entrée fermée,
une sortie enumérée et un domaine stable doivent rester déterministes.

Le prompt effectivement utilisé par le runtime vient de
`llm_points.prompt`. Le code et le YAML fournissent le seed initial ; ils ne
doivent pas écraser une modification runtime. Le propriétaire peut modifier
le prompt, le mode de sortie et l'information externe depuis l'API Mission
Control.

Chaque invocation enregistre dans `llm_usage` le point, le modèle, les tokens,
la latence et le verdict. Le coût affiché par Mission Control est une
estimation calculée avec le tarif de la policy ; une moyenne de coût n'est pas
stockée par invocation.

Les outils autorisés et les capsules de lecture sont reliés au point en DB.
Les tools `db_read` limitent leurs tables, colonnes, filtres, paramètres et
jointures par un catalogue vérifié avant exécution.

Les sorties JSON structurées sont validées par le prédicat du point dans
`serge/points/jsonio.py`. Les recalls sont bornés par
`policy.quotas.llm_recalls_json` et chaque recall est une nouvelle invocation
avec une consigne de réparation.

La boucle d'outils est plafonnée par la policy, avec une limite maximale de
12 tours. Le kill-switch, le budget journalier et le metering sont appliqués
par `serge/llm/runtime.py`.

## P3 — Les interpréteurs utilisent des contrats structurés

Un interpréteur déterministe ne route pas sur une phrase libre. Les décisions
passent par des objets JSON ou dicts validés, des codes et des enums fermés.

Le champ `requested`, quand un contrat le prévoit, exprime une demande
d'évolution. Il est affichable et traitable séparément ; il ne remplace pas
le code structuré qui décide du routage.

Les messages, prompts et traces peuvent rester textuels pour l'affichage et
la mémoire. Ce texte ne remplace pas les champs structurés nécessaires aux
workers, aux guards et aux projecteurs.

## P4 — SQLite est l'autorité du runtime

SQLite est l'autorité des faits métier, des états runtime, des permissions
LLM, des snapshots de policy et des occurrences d'exécution. Les projections
Mission Control lisent cette base ; elles ne deviennent pas une seconde
source de vérité.

Le code et les fichiers YAML restent les seeds et les paramètres de
configuration. Ils ne doivent pas créer une seconde copie mutable d'un fait
déjà établi en DB. Les ledgers explicitement séparés, comme la voix, sont
documentés dans `docs/DB.md` et ne doivent pas être confondus avec le canon
SQLite principal.

Les fiches d'objets affichées par Mission Control vivent dans les colonnes de
catalogue SQLite. Les procédures, contrats et explications générales vivent
dans `docs/*.md`.

## P5 — Les tests prouvent le comportement

Un test reste vert quand l'implémentation change sans changement de
comportement, et devient rouge quand le comportement change. Les tests qui
vérifient seulement un détail privé ou une structure interne sont à supprimer
ou à remplacer par un test de contrat.

Trois niveaux de vérification existent :

| Niveau | Exécution | Secret |
|---|---|---|
| Suite déterministe | `scripts/ci.sh` et le pre-push ; `unittest discover`, avec les E2E Mission Control | Aucun |
| LLM réel ciblé | `tests/test_live_llm.py`, uniquement au pre-push | Clé OpenRouter locale |
| Live externe | Discord, Stripe et canaries manuels | Variables dédiées |

La CI exécute la suite déterministe sans secret. Le pre-push ajoute le test
LLM réel et refuse un skip ou un échec. Aucun test CI ne doit agir sur le
monde réel.

Avant de supprimer du code, il faut un test passant et, pour une capacité
externe, un test de garde-fou ou de refus. Le code mort, son test et sa
documentation sont supprimés ensemble.

## Métriques actuellement affichées dans Mission Control

- LOC total et plus gros fichier de `kit/` et `serge/`.
- Tokens par euro de revenu, calculés depuis `llm_usage` et les transactions
  payées.
- Nombre de demandes `REQUESTED` encore ouvertes.
- Pour chaque point LLM : tokens, latence, modèle et verdict des derniers
  passages.

## Application aux contributeurs

- Tout écart à la charte est signalé explicitement dans le diff, avec sa
  raison et son impact.
- Un changement qui touche un contrat, une table, un point LLM, une policy,
  une API ou une UI met à jour la documentation correspondante.
- Les amendements de cette charte suivent la règle d'approbation ci-dessus.

---

## Règles opérationnelles

### R1 — Diffs limités

Un changement fait moins de **300 lignes de code de production** par défaut.
Un dépassement nécessite l'approbation explicite de Julien et une justification
dans le changement. Les tests, la documentation, les migrations mécaniques,
les fichiers générés et les lockfiles sont hors de ce plafond lorsqu'ils sont
réellement mécaniques ou documentaires.

### R2 — Docstrings, typage et outillage

- Les modules et fonctions publiques expliquent leur contrat ; les fonctions
  privées ont au moins une explication quand leur logique n'est pas évidente.
- `ruff` vérifie le lint et le format.
- `ty` vérifie le périmètre de code de la charte.
- Le scan de secrets refuse les secrets versionnés.
- `pre-commit` exécute ces contrôles au commit ; le pre-push exécute en plus
  les gates, la suite et le test LLM réel.
- `uv` et `uv.lock` sont la toolchain et le verrou des dépendances.

### R3 — Dépendances déclarées

Toute nouvelle dépendance est déclarée dans `pyproject.toml` et verrouillée
dans `uv.lock`. Son usage, son coût et les données auxquelles elle accède
doivent être relus avant activation.

### R4 — Policy validée et modifiable par le propriétaire

`config/policy.yaml` porte la policy de base. `validate_policy` refuse les
types, clés et valeurs invalides au chargement.

Les modifications appliquées sont validées par le même schéma, enregistrées
dans `policy_snapshots` et accompagnées d'un événement d'audit. La page Policy
de Mission Control permet à l'owner d'éditer la policy et les paramètres de
testing ; une proposition reste une proposition tant qu'elle n'est pas
appliquée par l'owner.

### R5 — Revue après chaque fix

Chaque changement doit répondre brièvement à ces questions :

- P1 : les fichiers restent-ils sous la limite et à responsabilité unique ?
- P2 : un nouvel appel LLM, outil ou prompt est-il déclaré et contrôlé ?
- P3 : les contrats structurés et leurs validations sont-ils à jour ?
- P4 : un nouveau fait ou état runtime a-t-il la bonne source SQLite ?
- P5 : le comportement passant et le refus important sont-ils testés ?
- R6 : la documentation décrivant le comportement est-elle à jour ?

### R6 — Documentation dans le même changement

Un changement qui modifie un comportement, une surface API/UI/CLI, un
contrat, un point LLM, une table ou une procédure d'installation met à jour
le document qu'un étranger lirait pour comprendre l'état réel.

Ce n'est pas un journal de bord. On corrige le paragraphe qui ment ; on
n'empile pas une note « aussi, on a changé X ».

Le document cible est généralement :

- Mission Control : `docs/MISSION_CONTROL.md` ;
- un point LLM : `docs/LLM_MATRIX.md` ;
- mémoire, funnel ou interaction : l'architecture concernée ;
- installation et contrat d'instance : les documents correspondants ;
- une capacité sans document : un paragraphe nouveau ou un ticket explicite.

### R7 — Pas de code mort ni de documentation morte

Pas de bouton sans writer, d'API sans appelant, de projecteur orphelin ou de
paragraphe décrivant un écran supprimé. On termine la capacité ou on enlève
le code, les tests et la documentation associés.

Un `TODO` sans ticket ou contexte exploitable est un écart à traiter.

### R8 — Checklist avant merge

Pour chaque objet touché, vérifier :

1. La documentation ne contredit pas le diff.
2. La semence, la migration, la fiche SQLite et la policy sont à jour.
3. Les liens, readers, writers, guards et appelants parlent le nouveau
   contrat ; une suppression ne laisse pas de référence orpheline.
4. Les tests de comportement et les E2E requis sont verts ;
   `tests.test_catalogue_sha` reste vert pour le catalogue.
5. Mission Control expose le changement quand il doit être visible, sans
   inventer un fait absent du canon.

---

## Catalogue, documentation et SHA

Serge est un catalogue d'objets dont les fiches runtime vivent dans SQLite :

| Objet | Table | Semence code |
|---|---|---|
| Étape | `pipeline_steps` | `serge/etapes.py` + `serge/etape_fiches.py` |
| Lien d'épine | `etape_liens` | `serge/etape_fiches.py` (`LIENS`) |
| Invocation LLM | `llm_points` | `serge/llm_registre.py` + `config/llm-points.yaml` |
| Tool | `tools` | `serge/outils.py` (`SEED`) |
| Invocation technique | `tech_invocations` | `serge/tech_registre.py` |
| Canal | `canaux` + `brique_canaux` | `serge/canaux.py` (`SEED`, `JONCTIONS`) |

Mission Control lit les fiches, le graphe et les états dans la base. Un texte
de fiche se modifie dans sa semence ou depuis l'action runtime prévue, puis le
boot remet la base à niveau ; il ne faut pas dupliquer ce texte dans un JS.

Chaque objet catalogue doit pointer les fichiers qui encodent son comportement
et porter un SHA vérifiable. Pour les tools, points LLM, invocations techniques
et canaux, le chemin est `code_path`. Pour les étapes et les liens, les chemins
fixes sont déclarés dans `serge/objet_sha.py`. Un nouveau fichier dédié doit
être ajouté à l'un de ces mécanismes, sinon le verrou ne le voit pas.

Pour ajouter ou modifier un objet :

1. Modifier la semence de l'objet et les migrations nécessaires.
2. Mettre à jour sa fiche SQLite et ses liens.
3. Ajouter les tests de comportement, passant et refusé quand le refus est
   contractuel.
4. Recalculer le SHA dans `serge/catalogue_lock.py` si le contenu encodant
   l'objet change.
5. Mettre à jour le document qu'un étranger lirait.

Ne jamais désactiver `tests.test_catalogue_sha` ni inventer un SHA.

Les fiches d'objets sont une couche de documentation en base. Les procédures,
contrats et cette charte sont une seconde couche dans `docs/*.md`. Ces deux
couches ne doivent pas porter deux versions contradictoires du même fait.

## Coupe-circuits Mission Control

Les coupe-circuits utilisent la même API `POST /owner/api/coupe` :

1. le heartbeat de Serge ;
2. les étapes via `pipeline_steps.enabled` ;
3. les kinds via `runtime_flags.kind.*`.

La voix ne possède pas un second kill indépendant dans son onglet : le même
levier est utilisé.
