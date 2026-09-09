# Outillage dev (charte R2)

Stack : `uv` + `ruff` (lint/format) + `ty` (type-check) + `pre-commit`.
Voir charte R2 ([CODEBASE_CHARTER.md](CODEBASE_CHARTER.md)) pour le rationnel
(ty choisi pour sa vitesse, sa toolchain Astral et son silence sur le legacy
non annoté ; Pyrefly à réévaluer dans 6 mois).

## Setup (5 min)

```sh
# 1. uv (une fois par machine)
curl -LsSf astral.sh/uv/install.sh | sh

# 2. deps (depuis la racine du repo)
uv sync --group dev

# 3. hooks (une fois par clone)
uv tool install pre-commit
pre-commit install
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
uv run ruff check kit scripts/serge-builder.py   # lint périmètre charte
uv run ruff format --check kit                   # format (check only)
uv run ty check kit scripts/                     # type-check
pre-commit run --all-files                       # tout, comme au commit
python3 -m unittest discover -s tests            # suite complète
```

## Périmètre

Les gates (ruff, ty) couvrent tout le dépôt : `kit/`, `serge/`,
`scripts/serge-*`, tests. Nouveau code : toujours sous charte dès l'écriture.

`uv.lock` est commité (reproducibilité). `.venv/` ne l'est pas.
