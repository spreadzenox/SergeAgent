#!/bin/sh
# Gates charte (R2) + suite déterministe (P5 niveau 1). Aucun secret, aucun live.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"

uv run ruff check kit serge scripts/serge-builder.py \
  scripts/serge-instance-wizard.py scripts/serge-mandate-wizard.py \
  scripts/serge-install.py scripts/serge-update.py \
  scripts/serge-deploy.py scripts/pre-push-check.py tests
# format --check sur tout le dépôt : proj_objet.py dépasse 500 lignes
# une fois reformaté (P1). Le hook pre-commit formate le diff.
uv run ty check kit serge scripts/serge-builder.py \
  scripts/serge-instance-wizard.py scripts/serge-mandate-wizard.py \
  scripts/serge-update.py scripts/serge-deploy.py \
  scripts/pre-push-check.py
uv run python scripts/scan-repo-secrets.py

# Navigateur requis : skip E2E MC = échec. Live-prudent (clés) reste skippé.
# Instance locale hors CI : ne pas polluer la suite.
export SERGE_CI=1
unset SERGE_ENV SERGE_INSTANCE_FILE SERGE_SYSTEM_ROOT SERGE_CONFIG_DIR \
  SERGE_AGE_IDENTITY SERGE_SECRETS_DOTENV SERGE_MANDATE_PATH SERGE_POLICY_PATH
uv run python -m unittest discover -s tests -q
