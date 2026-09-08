#!/usr/bin/env bash
# Lance l'evaluation automatisee en une seule commande : cree le venv si
# besoin, installe les dependances, charge .env, puis lance eval_agent.py.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi

. .venv/bin/activate
pip install -q -r requirements.txt

if [ -f .env ]; then
    set -a
    . ./.env
    set +a
else
    echo "Avertissement : .env introuvable (copiez .env.example), les scenarios Claude seront SKIP." >&2
fi

python scripts/eval_agent.py
