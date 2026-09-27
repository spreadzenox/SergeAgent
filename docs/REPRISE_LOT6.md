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

## Ce qui est fait sur `Clem`, pas encore fusionné

- **L'interpréteur** (commit « Écrire l'interpréteur qui exécute n'importe
  quelle invocation »), dans `serge/interpreter/` :
  - `tasks.py` : la file des tâches, avec une clé stable ;
  - `tools.py` : une fonction par capacité (`RUNNERS`), l'exécution d'un
    outil avec ses paramètres figés, le schéma montré au modèle ;
  - `output.py` : décrire et vérifier le format de réponse ;
  - `rules.py` et `writer.py` : l'écriture générique et ses protections ;
  - `flow.py` : les liens et les déclencheurs ;
  - `prompt.py` : le prompt, les outils donnés d'office, la conversation
    avec les outils appelables ;
  - `run.py` : exécuter une tâche de bout en bout ;
  - `queue.py` : vider une file, une tâche après l'autre, en enregistrant
    après chacune.

  Testé par `tests/test_interpreter.py` (vert).

## Ce qui est en cours sur `Clem` : la bascule (étape 6.2)

Le dernier commit de `Clem` est un **travail en cours** : les tests ne
passent pas. Ne pas fusionner dans `main` avant la fin de l'étape 6.2.

### Déjà fait dans ce commit

- L'ancien code en dur est **rangé** (pas détruit) dans
  `pas_encore_branche/`, en gardant les mêmes chemins : `serge/workers/`,
  `serge/points/`, `serge/allocator/`, `serge/scheduler.py`,
  `serge/runner.py`, `serge/llm_registre.py`, `config/llm-points.yaml`,
  `serge/tech_registre.py`, `serge/db_readers.py`,
  `serge/db_reader_exec.py`, `serge/llm/boucle.py`,
  `serge/llm/outils_exec.py`, `serge/observe/router.py`,
  `serge/memory/consolidate.py`, `serge/discord/owner_flow.py`,
  `serge/discord/owner_in.py`, `serge/listen/memory.py`,
  `serge/catalogue.py`, `serge/outils.py`, `scripts/serge-runner.py`.
  Une copie complète de `serge/registry.py`, `serge/llm/runtime.py` et
  `serge/coupe_circuit.py` y est aussi, parce que ces trois fichiers
  restent en production mais vont perdre leurs parties liées à l'ancien
  fonctionnement.
- Leurs tests sont rangés dans `pas_encore_branche/tests/`.
- `strip_ids` a été sorti de `serge/points/interact.py` vers
  `serge/text_ids.py`, parce que Mission Control et le rendu Discord s'en
  servent.

### Reste à faire pour finir 6.2, dans l'ordre

1. **Retirer les imports cassés** (lancer les tests pour les voir tous) :
   - `serge/db/boot.py` : retirer `ensure_llm_points`, `ensure_db_readers`,
     `ensure_tech_invocations`, `ensure_etape_liens`, `ensure_tools`,
     `verifier_catalogue` ;
   - `serge/registry.py` : garder `load_ticket_types` et ce qui sert aux
     tickets ; retirer les invocations LLM (`load_llm_points`,
     `llm_enabled`, `runtime_allows`, `poser_kill`, `retirer_kill`) ;
   - `serge/llm/runtime.py` : garder `resolve_model`, `read_api_key`,
     `daily_tokens` ; retirer `run_point`, `run_registered_point` ; adapter
     `serge/llm/__init__.py` ;
   - `serge/coupe_circuit.py` : retirer tout ce qui concerne les « kinds »
     (garder la coupure générale, `heartbeat_marche`) ;
   - `serge/observe/__init__.py` : n'exporte plus `ingest` ;
   - `serge/discord/bot.py` : retirer `render_context_fr` (le ticket est
     recopié sans résumé LLM) et le traitement des messages libres de
     Julien (`on_message` ne fait plus rien, en le disant dans sa
     docstring) ;
   - `serge/canaux.py` : la jonction `brique_canaux` pointait vers
     `llm_points` et `tech_invocations` ; la vider ;
   - `serge/objet_sha.py` : retirer les sortes `llm`, `tech`, `lien` ;
   - `serge/etapes.py` : retirer `kinds_json`.
2. **Les outils passent dans `config/pipeline.yaml`** : ajouter à
   `serge/pipeline_seed.py` une section `tools` (id, titre, description,
   capacité, `montre_partout`, et pour une lecture de la base son
   catalogue : tables, colonnes, filtres, jointures, paramètres, qui
   remplissent les tables `tool_db_*` existantes). Recopier dans le YAML
   les outils de lecture de `pas_encore_branche/serge/db_readers.py`
   (`current_listen_cycle`, `listen_cycle_documents`,
   `known_business_candidates`, `eligible_poc_candidates`) et les outils
   `web_search`, `memory_search`, `demande_capacite` avec leur capacité.
3. **Migration v25** (`serge/db/v025.py`) : supprimer `llm_points`,
   `llm_point_tools`, `tech_invocations`, `db_readers`,
   `llm_point_readers`, `db_reader_fixed_params`, `db_reader_fixed_joins`,
   `etape_liens`, `work_items`, les lignes de `brique_canaux`, la colonne
   `kinds_json` de `pipeline_steps`, la colonne `kind` de `tools`, et les
   interrupteurs `kind.*` et `llm.*` de `runtime_flags`. Ce qui existait
   avant n'a pas à être recopié (décision Q58). Mettre à jour
   `SCHEMA_VERSION`, `TABLES` dans `serge/db/schema.py`, et `DB.md`.
4. **Le nouveau runner** : un script `scripts/serge-queue.py --queue
   <conversations|works>` qui ouvre la base et appelle
   `serge.interpreter.queue.run_forever`, en expirant aussi les tickets
   dus (`serge.tickets.expire_due`) à chaque tour. Remplacer, dans
   `systemd/templates/` et `kit/units.py`, `serge-pipeline.service` et son
   timer par deux services qui tournent en continu (un par file,
   `Restart=always`).
5. **Mission Control sur les nouvelles tables** (étape 6.2c). Garder les
   mêmes formats JSON pour ne pas toucher au JavaScript quand c'est
   possible :
   - `proj_live.py`, `proj_ilots.py`, `proj_public.py`, `proj_trace.py`,
     `proj_traces.py` : lire `tasks` et `task_params` au lieu de
     `work_items` ;
   - `proj_cerveau.py`, `proj_llm.py`, `llm_actions.py`, `actions.py` :
     lire et modifier `invocations` (prompt, `model_tier`, `priority`,
     `enabled`) au lieu de `llm_points` ; éteindre une invocation, c'est
     `enabled` = 0 ;
   - `proj_etape.py`, `proj_graphe.py` : l'ordre et les liens viennent de
     `invocations` et `links` (plus de liste `ORDRE` écrite dans le code,
     plus de `etape_liens`) ;
   - `proj_ecoute.py`, `ecoute_actions.py` : le bouton « lancer un cycle »
     appelle `serge.interpreter.flow.fire_button` (le déclencheur sera
     écrit à l'étape 6.3) ;
   - `coupe_actions.py`, `proj_coupes.py`, `proj_voice.py` : plus de
     « kinds » ; on coupe Serge entier, une étape, une file ou une
     invocation ;
   - `proj_memory.py` : la consolidation est « pas encore branchée » ;
   - `proj_objet.py`, `proj_outil.py`, `proj_sqlite.py` : fiches des
     nouvelles tables, plus de fiches pour les tables supprimées ;
   - adapter les tests MC (`tests/test_mc_*.py`) qui insèrent des
     `work_items` ou lisent `llm_points`, et `scripts/mc-demo.py`.
6. **Tests à adapter hors MC** : `test_demande_capacite.py` (retirer la
   partie `outils_exec`), `test_policy_registry.py` (retirer les tests des
   invocations LLM), `test_canaux.py`, `test_coupe_circuit.py`,
   `test_discord_bot.py`.
7. **Vérifier** : `ruff check`, `ruff format --check`, `.venv/bin/ty
   check`, puis toute la suite (voir plus bas). Committer, pousser sur
   `Clem`, puis fusionner dans `main` par une pull request.

## Ensuite : l'étape 6.3

- Décrire le cycle d'écoute d'aujourd'hui dans `config/pipeline.yaml`
  (exemple complet dans `LOT6_CONCEPTION.md`, partie 12), avec un test de
  bout en bout et un faux modèle, sur le modèle de
  `tests/test_interpreter.py`. Les prompts d'origine sont dans
  `pas_encore_branche/serge/points/listen_pts.py`.
- Mission Control affiche tout ce qui est en base : capacités, outils,
  invocations et leurs réglages, format de réponse, règles d'écriture,
  liens, déclencheurs, files, tâches, lignes reçues (`task_inputs`).
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
