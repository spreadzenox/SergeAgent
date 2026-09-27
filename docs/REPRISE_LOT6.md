# Reprendre le lot 6 là où il s'est arrêté

Ce fichier sert à reprendre le travail dans une nouvelle session (par
exemple Claude Code en local) sans avoir à réexpliquer le contexte. Il
décrit exactement où on en est sur la branche `Clem`, ce qui est cassé
exprès, et ce qu'il reste à faire, dans l'ordre. Une fois le lot 6 fini,
ce fichier est supprimé.

## À lire d'abord, dans cet ordre

1. [`TODO.md`](../TODO.md) : « La règle qui vaut pour tous les lots » et la
   partie « Lot 6 ».
2. [`docs/LOT6_CONCEPTION.md`](LOT6_CONCEPTION.md) : la conception validée
   des tables et du déroulé d'une invocation.
3. [`docs/DECISIONS_REVUE.md`](DECISIONS_REVUE.md), questions 50 à 59 :
   les décisions prises avec Clem et Julien pendant ce lot.
4. [`docs/CHARTE.md`](CHARTE.md) : les règles d'écriture du code et le style
   des documents (phrases courtes, exemples concrets, pas de jargon).

La règle en une phrase : **le code n'est qu'un interpréteur de la base ;
il n'y a jamais de code propre à une invocation**, même pour écrire en
base.

## Ce qui est fait et fusionné dans `main`

- **Étape 6.1** ([PR #30](https://github.com/spreadzenox/SergeAgent/pull/30)) :
  migration v24 (toutes les tables du pipeline en base),
  `serge/capabilities.py` (les capacités déclarées par le code),
  `config/pipeline.yaml` et `serge/pipeline_seed.py` (remplissage de la base
  sans jamais écraser ni recréer ce qui a été supprimé),
  `tests/test_pipeline_seed.py`.

## Ce qui est fait sur `Clem` : l'étape 6.2 (la bascule), tests verts

- **L'interpréteur** (`serge/interpreter/`) : la file des tâches
  (`tasks.py`), une fonction par capacité (`tools.py`), le format de
  réponse (`output.py`), l'écriture générique et ses protections
  (`rules.py`, `writer.py`), les liens et déclencheurs (`flow.py`), le
  prompt et la conversation avec les outils (`prompt.py`), une tâche de
  bout en bout (`run.py`), vider une file (`queue.py`).
- **L'ancien code en dur est rangé** dans `pas_encore_branche/` (voir son
  README), avec ses tests. `strip_ids` est sorti vers `serge/text_ids.py`.
- **Les imports cassés sont retirés** : `serge/db/boot.py`,
  `serge/registry.py` (ne garde que les types de tickets),
  `serge/llm/runtime.py` (modèle par niveau, clé, tokens du jour, plafond
  de dépense), `serge/coupe_circuit.py` (Serge, étape, file, invocation),
  `serge/observe/`, `serge/discord/bot.py` (ticket recopié sans résumé
  LLM, messages libres de Julien ignorés), `serge/canaux.py`,
  `serge/objet_sha.py`, `serge/etapes.py`, `serge/etape_fiches.py` (plus
  de liens d'épine écrits en dur).
- **Les outils sont dans `config/pipeline.yaml`** (section `tools`) : les
  quatre lectures de l'ancien catalogue, `web_search`, `memory_search`,
  `demande_capacite`. Le catalogue de lecture est rempli par
  `serge/db/query_catalogue.py` (`seed_read_catalogue`), et ses jointures
  sont toujours faites : les pages d'un cycle reviennent avec leur titre et
  leur texte (c'était le bug des capsules).
- **Migration v25** (`serge/db/v025.py`) : les anciennes tables sont
  supprimées, `tools` est recréée sans `kind`, le catalogue de lecture est
  vidé puis rempli de nouveau au démarrage, `kinds_json` et les
  interrupteurs `kind.*`/`llm.*` disparaissent.
- **Le nouveau runner** : `scripts/serge-queue.py --queue <file>`, lancé
  par le modèle d'unit `serge-queue@.service` (deux instances,
  `Restart=always`). Il expire aussi les tickets dus à chaque tour. Au
  déploiement, `kit/deploy.py` arrête, désactive et efface l'ancien
  `serge-pipeline.timer`, et lance les deux files s'il tournait.
  `bin/serge-runner` devient `bin/serge-queue`.
- **Mission Control lit les nouvelles tables** : la file (`proj_taches.py`,
  fiche `task`), le graphe et les étapes (ordre des invocations lu dans les
  liens), la page Cerveau (toutes les invocations ; « Éteindre » passe par
  le coupe-circuit), la fiche d'une invocation (tout ce que la base dit
  d'elle), la fiche d'un outil (sa capacité et son catalogue de lecture),
  la page Écoute (le bouton lance le déclencheur « bouton » de l'étape 1,
  `POST /owner/api/bouton`), la page Mémoire (consolidation « pas encore
  branchée »), les coupe-circuits (étapes, files, invocations).
  `POST /owner/api/invocation` modifie prompt, niveau, file, priorité et
  interrupteur. `llm_roles.py` (un texte écrit à la main par invocation)
  est rangé dans `pas_encore_branche/`.
- **Tests** : tous verts, `ruff`, `ty` et le scan des secrets aussi.

### Choix faits pendant 6.2, à faire valider par Clem ou Julien

1. **`brique_canaux` est supprimée**, pas seulement vidée : une table que
   personne n'écrit n'a pas sa place (charte). Le lien entre un canal et
   ses outils d'envoi reviendra au lot 8.
2. **Le plafond de dépense LLM du jour est gardé** : l'ancien runtime
   refusait d'appeler le modèle au-delà du plafond de la policy. La file
   laisse maintenant attendre les tâches LLM jusqu'au lendemain ; les
   autres continuent (`serge/llm/runtime.py`, `budget_spent`).
3. **Les outils « partout »** (`tools.montre_partout` = 1, par exemple
   `demande_capacite`) sont appelables par toutes les invocations LLM,
   sans paramètre figé.
4. **Le bouton de la page Écoute est générique** : il lance le premier
   déclencheur `button` des invocations de l'étape 1, avec le champ
   « guide » du formulaire. Plus de route `listen/start` propre à l'écoute.
5. **Le déploiement remplace l'ancien timer** tout seul (voir plus haut),
   pour ne pas laisser tourner chaque minute un runner qui n'existe plus.
6. **Une tâche interrompue est reprise** : au démarrage d'une file, une
   tâche restée « en cours » (programme arrêté pendant l'appel au modèle,
   par exemple par un déploiement) repart de zéro, avec une note
   `task.resumed` au journal. C'est sans risque tant qu'aucune capacité
   n'agit hors de Serge ; le lot 8 ajoutera l'état « à vérifier ».
7. **Quand Serge est arrêté en entier**, les déclencheurs horaires ne
   créent plus de tâche (sinon un arrêt d'une nuit laisserait une pile de
   tâches à rattraper).
8. **La charte n'est pas à jour** : sa partie 4 cite encore `llm_points` et
   `config/llm-points.yaml`. Seul Julien peut la modifier.

### Reste à faire pour finir 6.2

Pousser `Clem` et fusionner dans `main` par une pull request (chaque
fusion redéploie Serge sur le serveur de Julien).

## Ensuite : l'étape 6.3

- Décrire le cycle d'écoute d'aujourd'hui dans `config/pipeline.yaml`
  (exemple complet dans `LOT6_CONCEPTION.md`, partie 12), avec un test de
  bout en bout et un faux modèle, sur le modèle de
  `tests/test_interpreter.py`. Les prompts d'origine sont dans
  `pas_encore_branche/serge/points/listen_pts.py`.
- Mission Control : la fiche d'une invocation, d'un outil et d'une tâche
  montrent déjà tout ce qui les décrit. Il manque une vue d'ensemble des
  capacités, des outils, des liens (avec ce qui est passé, ce qui attend,
  et un bouton « passer à la suite ») et des déclencheurs.
- Les outils donnés partout : lire l'historique de l'objet traité, lire
  ses leçons (seul « demander une nouvelle capacité » existe).
- Ce que voit une invocation : les lignes les plus récentes d'abord (le
  catalogue de lecture n'a pas encore d'ordre), la version courte des
  tables où elle écrit, ses leçons.
- Le test de la règle : il échoue si le nom d'une invocation de
  `config/pipeline.yaml` apparaît dans `serge/`, `scripts/` ou `kit/`.
  `pas_encore_branche/` et `tests/` sont ignorés.

## Lancer les vérifications en local

```bash
uv sync                              # installe les dépendances
find . -name __pycache__ -prune -exec rm -rf {} +
SERGE_CI=1 .venv/bin/python -m unittest discover -s tests -q
ruff check serge tests scripts && ruff format --check serge tests scripts
.venv/bin/ty check
.venv/bin/python scripts/scan-repo-secrets.py
```

Les tests de Mission Control ouvrent un vrai navigateur (Playwright). Sans
navigateur installé, ils échouent avec « playwright manquant en CI » : il
faut installer Chromium une fois avec `uv run playwright install
chromium`.

## Règles de travail à garder

- Travailler sur la branche `Clem` ; fusionner dans `main` par une pull
  request, seulement avec tous les tests verts. Chaque fusion dans `main`
  redéploie Serge sur le serveur de Julien.
- Messages de commit en français : ce qui change, pourquoi, comment on
  vérifie.
- Documents et TODO dans le style descriptif demandé par Clem : chaque
  tâche est une case à cocher, un titre en gras, puis un paragraphe qui
  explique d'où on part, ce qu'il faut faire, pourquoi, et ce qui est
  réglable dans Mission Control.
- Ne jamais écrire de code propre à une invocation. Si une tâche semble en
  demander, il manque une capacité générale ou un réglage en base.
