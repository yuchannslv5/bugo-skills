#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${BUGO_TEXT:-}" ]]; then
  echo '{"error":"BUGO_TEXT is required","error_code":"MISSING_TEXT"}'
  exit 1
fi

if [[ -z "${BUGO_CHANNEL_ID:-}" ]]; then
  echo '{"error":"BUGO_CHANNEL_ID is required","error_code":"MISSING_CHANNEL_ID"}'
  exit 1
fi

python3 -m venv .venv
source .venv/bin/activate

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r scripts/requirements.txt

python3 scripts/send_tts.py

