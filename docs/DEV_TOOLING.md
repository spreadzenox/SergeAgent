# Outillage dev (charte R2)

Stack : `uv` + `ruff` (lint/format) + `ty` (type-check) + `pre-commit` +
CI GitHub Actions. Voir charte R2 ([CODEBASE_CHARTER.md](CODEBASE_CHARTER.md))
pour le rationnel (ty choisi pour sa vitesse, sa toolchain Astral et son
silence sur le legacy non annoté ; Pyrefly à réévaluer dans 6 mois).

## Setup (5 min)

```sh
# 1. uv (une fois par machine)
curl -LsSf astral.sh/uv/install.sh | sh

# 2. deps (depuis la racine du repo)
uv sync --group dev

# 3. hooks (une fois par clone — même venv que le projet)
uv run pre-commit install

# 4. Chromium pour les E2E Mission Control (une fois)
uv run playwright install chromium
```

> Worktree git (ex. `/home/serge/serge-kit`) : `.git/hooks` est partagé
> avec le repo principal — ne jamais y installer les hooks kit.
> Utiliser le hook worktree-local (déjà configuré ici) :
>
> ```sh
> git config extensions.worktreeConfig true
> git config --worktree core.hooksPath /abs/path/.githooks
> ```
>
> Le hook `.githooks/pre-commit` lance `pre-commit run` avec la config du
> worktree. Rien n'est installé dans le repo principal.

## Commandes

```sh
uv run pre-commit run --all-files   # ruff + ty + scan secrets (comme au commit)
scripts/ci.sh                       # gates + suite déterministe + E2E MC
```

`scripts/ci.sh` pose `SERGE_CI=1` : un E2E navigateur skippé = échec.
Les tests live-prudents (`SERGE_ENV=test` + vraies clés) ne tournent **pas**
dans ce script : charte P5, niveaux 2–3 (LLM réel / canary) hors PR.

Le format (`ruff format`) est le hook pre-commit sur le diff, pas un
`--check` sur tout le dépôt : reformater `proj_objet.py` le ferait
passer P1 (500 lignes).

## CI GitHub Actions

Chaque PR et chaque push sur `main` lance [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) :
même script, plus l’install Chromium. Aucun secret n’est injecté.

Pour bloquer le merge tant que c’est rouge : GitHub → Settings → Rules →
Ruleset `main` → Require status checks → `lint tests e2e`.

## Périmètre

Les gates (ruff, ty) couvrent tout le dépôt : `kit/`, `serge/`,
`scripts/serge-*`, tests. Nouveau code : toujours sous charte dès l'écriture.

`uv.lock` est commité (reproducibilité). `.venv/` ne l'est pas.
