# Reprendre le lot 6 là où il s'est arrêté

Ce fichier sert à reprendre le travail dans une nouvelle session (par
exemple Claude Code en local) sans avoir à réexpliquer le contexte. Il
décrit exactement où on en est sur la branche `Clem` et ce qu'il reste à
faire, dans l'ordre. Une fois le lot 6 fini,
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

## Étape 6.2 (la bascule), fusionnée dans `main`

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

### Choix faits pendant 6.2, validés par Clem

1. `brique_canaux` est supprimée : aucun code ne l'écrivait plus. Le lien
   entre un canal et ses outils d'envoi reviendra au lot 8.
2. Le plafond de dépense LLM du jour est gardé : au-delà, les tâches LLM
   attendent le lendemain, les autres continuent.
3. Les outils « partout » (`tools.montre_partout` = 1, par exemple
   `demande_capacite`) sont appelables par toutes les invocations LLM.
4. Le bouton de la page Écoute est générique : il lance le déclencheur
   `button` des invocations de l'étape 1 (`POST /owner/api/bouton`).
5. Le déploiement remplace l'ancien timer tout seul.
6. Une tâche interrompue par un arrêt est reprise au démarrage de sa file.
7. Quand Serge est arrêté, les déclencheurs horaires ne créent pas de
   tâche.

## Fait après 6.2, à la demande de Clem (fusionné aussi)

- **Serge est arrêté par défaut** (`serge/coupe_circuit.py`). Il ne tourne
  qu'après un clic sur « Démarrer Serge » en haut de la page En direct
  (avec une confirmation). Les deux services des files tournent mais ne
  créent ni ne prennent de tâche ; la voix ne décroche pas (agent temps
  réel et appel de secours) et n'appelle pas (`serge_arrete`). Un
  déploiement ou une instance neuve ne démarre jamais Serge.
- **Un demi-cycle de démonstration** dans `config/pipeline.yaml` : le
  bouton « Lancer un cycle (démo) », puis « Ouvrir un cycle (démo) » (sans
  LLM), « Formuler des idées (démo) » et « Choisir un business (démo) »,
  avec les protections de la table `ventures` (statuts permis, doublons).
  Testé de bout en bout avec un faux modèle, et dans le navigateur
  (`tests/test_pipeline_demo.py`). Le vrai pipeline est l'objet du lot 7.
- **Le test de la règle** (`tests/test_regle_interpreteur.py`) : aucun nom
  d'invocation de `config/pipeline.yaml` dans `serge/`, `scripts/`,
  `kit/`, `bin/`.
- **La charte** (partie 4) décrit les invocations en base ; Clem l'a
  autorisé exceptionnellement.

### Fusionné dans `main`

La bascule 6.2 et ce qui suit sont fusionnés dans `main`
([PR #31](https://github.com/spreadzenox/SergeAgent/pull/31), 27 septembre
2026) et déployés sur le serveur de Julien : l'ancien timer y a été
remplacé par les deux files, et Serge y reste arrêté jusqu'au clic sur
« Démarrer Serge ».

## Ensuite : ce qui reste du lot 6 (sur `Clem`, pas encore dans `main`)

Fait sur `Clem` depuis la fusion (commits locaux, pas encore poussés) :
les finitions (jours en français, « Relancer la tâche », boutons de
l'Écoute) et les réglages des invocations et quotas des tables sur la
page Policy (migration v26). 648 tests passent.

**Étape 3, à commencer : ce que voit une invocation** (conception :
[`LOT6_CONCEPTION.md`](LOT6_CONCEPTION.md) partie 16). Plan arrêté :

- Migration v27 : `table_views` (table, titre, description, colonne
  d'ordre), `table_view_columns` (colonne, courte ou non, description),
  `invocation_compare_tables` (ajouter ou retirer une table à comparer),
  `event_rows` (quel événement du journal concerne quelle ligne, rempli
  par l'écriture et par `append_event` pour `venture_id`, avec reprise des
  anciens événements), `task_seen_tables` (lignes données et laissées de
  côté, par table, pour la fiche de la tâche).
- `config/pipeline.yaml` : une section `table_views` (business, cycles)
  et deux outils « partout » : « Lire les tables que je vois » et « Lire
  l'historique » ; retirer « Les business déjà connus » de la démo, que
  la version courte remplace.
- Deux capacités de plus dans `serge/capabilities.py`, portées par un
  nouveau `serge/interpreter/seen.py` : leurs tables permises sont
  calculées à chaque appel à partir de l'invocation (tables où elle
  écrit, plus ou moins les ajustements), et le schéma montré au modèle ne
  propose que ces tables.
- Le catalogue de lecture trie par la colonne d'ordre de la table (les
  plus récentes d'abord) et compte le total exact (au-delà de 200).
- `serge/interpreter/intro.py` : le bloc « Qui est Serge » complet (les 8
  étapes lues dans `pipeline_steps`, sa place, avant et après elle lus
  dans les liens) et ses leçons (portée `invocation:<id>`, puis
  `etape:<id>`, puis `global`, les plus fiables d'abord).
- MC : sur la fiche d'une invocation, un cadre « Ce qu'elle voit pour
  comparer » avec des boutons ajouter/retirer, et ses leçons ; sur la
  fiche d'une tâche, les tables reçues. Dire « lecture donnée d'office »
  et non « outil donné d'office » (Q64).

**Étape 4** : passer un lien à la main, et la page « Pipeline » de MC.

Puis le lot 7 : le vrai cycle de l'étape 1, qui remplace le demi-cycle de
démonstration (le marquer supprimé en base).

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
