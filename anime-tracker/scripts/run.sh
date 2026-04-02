#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BUGO_ANIME_CMD:-}" ]]; then
  echo '{"error":"BUGO_ANIME_CMD is required","error_code":"MISSING_CMD"}'
  exit 1
fi

if [[ -z "${BUGO_STATE_PATH:-}" ]]; then
  echo '{"error":"BUGO_STATE_PATH is required","error_code":"MISSING_STATE_PATH"}'
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$(dirname "$SCRIPT_DIR")"

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r scripts/requirements.txt

python3 scripts/anime_tracker.py
