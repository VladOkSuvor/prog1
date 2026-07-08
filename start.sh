#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [ ! -d ".venv" ]; then
    echo "Створюю virtualenv (.venv)…"
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

echo "Запускаю Polymarket AI на http://127.0.0.1:${WEB_PORT:-5050}"
exec python -m polymarket_ai.webapp.app
