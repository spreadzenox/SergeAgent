# Outillage dev — lint, tests, hooks, CI

Socle en place (charte R2 / P5). Après clone : `uv sync --group dev`,
`uv run pre-commit install`, Chromium Playwright, clé OpenRouter
instance. Rien de rouge ne part.

Trois couches, volontairement inégales :

| Couche | Quand | Quoi | Secret |
|---|---|---|---|
| **Commit** | `git commit` | ruff (lint + format du diff), ty, scan secrets | aucun |
| **Push** | `git push` | mêmes gates + **toute** la suite (E2E MC compris) + LLM OpenRouter réel | clé locale, jamais affichée |
| **CI GitHub** | PR et push `main` | mêmes gates + suite déterministe + Chromium | **aucun** — le dépôt est public |

Rouge à n’importe quelle couche = le git s’arrête (commit, push) ou le
merge est bloqué (check requis `lint tests e2e` sur `main`).

## Branches et PR

Plus de commit ni de push direct sur `main`. Une idée = une branche +
une PR. `main` ne bouge que par merge, CI verte.

```sh
git checkout main && git pull
git checkout -b sujet-court
# ... commits ...
git push -u origin HEAD
gh pr create --base main
```

Nom de branche : `sujet` (un verbe / un objet, ASCII, tirets). Ex.
`hooks-pre-push`, `mc-css-statique`. Pas de `main`, pas de date.

La PR cible `main`. Le check `lint tests e2e` doit être vert. Review
humaine puis merge. Après merge : supprimer la branche, `git checkout
main && git pull`.

Admin GitHub peut encore forcer `main` (bypass ruleset) : ne pas s’en
servir, sauf urgence réelle.

## Ce qui tourne où

**Commit** (`.pre-commit-config.yaml`, hooks `pre-commit`) :

- `ruff` + `ruff format` sur `kit/`, `serge/`, `scripts/`, `tests/`
- `ty check` (périmètre charte + `scripts/pre-push-check.py`)
- `scripts/scan-repo-secrets.py`

Pas de `--check` format sur tout le dépôt : reformater `proj_objet.py`
le ferait dépasser P1 (500 lignes). Le hook formate le diff.

**Push** (`scripts/pre-push-check.py`) — le gros check local :

1. Pas de clé OpenRouter (`OPENROUTER_API_KEY` ou
   `~/.config/serge/secrets/openrouter-api-key`) → **push refusé**.
   Les collaborateurs ont la même clé instance.
2. Gates (ruff, ty, scan) — même liste que `scripts/ci.sh`.
3. Suite déterministe entière (`unittest discover`, `SERGE_CI=1`) :
   E2E Mission Control requis (Chromium skippé = échec). Policy prod,
   pas d’overlay test. L’instance locale (`SERGE_INSTANCE_FILE`, etc.)
   est ignorée pour ne pas polluer.
4. Puis `tests/test_live_llm.py` avec `SERGE_ENV=test` + la clé
   (1 appel OpenRouter, cap 3). Skip ou rouge → **push refusé**.
   L’overlay `policy.test.yaml` (plafonds 2 €) ne s’applique qu’ici :
   sinon les tests policy voient 2.0 au lieu de 5.0.

**CI** (`.github/workflows/ci.yml` → `scripts/ci.sh`) :

- `uv sync --frozen`, Chromium + deps, puis `scripts/ci.sh`
- `SERGE_CI=1`, aucun secret injecté, `SERGE_ENV` unset
- live LLM / Discord / Stripe **skippés** (charte P5 : hors PR)
- check GitHub : nom exact `lint tests e2e`

Les callers LLM injectés en test ne lisent plus la clé locale : une
machine sans `~/.config/serge` (Actions) reste verte.

## Hors de ces gates

- Discord live (`tests/test_live_discord.py`) et Stripe canary
  (`tests/test_live_collect.py`) : manuels,
  `SERGE_ENV=test` + leurs propres variables.
- Canary 1 € / activation d’une feature externe : jamais dans un hook.

## Setup (une fois par clone)

```sh
curl -LsSf astral.sh/uv/install.sh | sh
uv sync --group dev
uv run pre-commit install
uv run playwright install chromium
```

`pre-commit install` pose les deux hooks (commit + push). Sans ça, un
push part sans la suite.

> Worktree git (ex. `/home/serge/serge-kit`) : `.git/hooks` est partagé
> avec le repo principal — ne jamais y installer les hooks kit.
> Hook worktree-local :
>
> ```sh
> git config extensions.worktreeConfig true
> git config --worktree core.hooksPath /abs/path/.githooks
> ```
>
> `.githooks/pre-commit` lance `pre-commit run` avec la config du
> worktree.

## Relancer à la main

```sh
uv run pre-commit run --all-files
uv run pre-commit run pre-push-check --hook-stage pre-push
scripts/ci.sh
```

`scripts/ci.sh` = ce que GitHub exécute (déterministe, zéro secret).
Le pre-push local = `ci.sh` + le passage OpenRouter.

## Fichiers

| Fichier | Rôle |
|---|---|
| `.pre-commit-config.yaml` | Hooks commit + push |
| `scripts/ci.sh` | Gates + suite déterministe (CI) |
| `scripts/pre-push-check.py` | Gros check local (clé obligatoire) |
| `.github/workflows/ci.yml` | Actions : PR + `main`, job `lint tests e2e` |
| `scripts/scan-repo-secrets.py` | Interdit un secret versionné |

`uv.lock` est commité. `.venv/` ne l’est pas.

Pour bloquer le merge si la CI est rouge : GitHub → Settings → Rules →
ruleset `main` → Require status checks → `lint tests e2e`.

Rationnel ty / uv : charte R2
([CODEBASE_CHARTER.md](CODEBASE_CHARTER.md)).
