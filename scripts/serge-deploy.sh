#!/bin/sh
# Point d’entrée mince pour le runner GitHub (même contrat que serge-deploy.py).
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 "$root/scripts/serge-deploy.py" "$@"
