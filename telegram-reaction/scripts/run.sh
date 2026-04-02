#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BUGO_CHAT_ID:-}" ]]; then
  echo '{"error":"BUGO_CHAT_ID is required","error_code":"MISSING_CHAT_ID"}'
  exit 1
fi

if [[ -z "${BUGO_MESSAGE_ID:-}" ]]; then
  echo '{"error":"BUGO_MESSAGE_ID is required","error_code":"MISSING_MESSAGE_ID"}'
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r scripts/requirements.txt

python3 scripts/set_reaction.py
