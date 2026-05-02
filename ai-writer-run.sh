#!/bin/bash
# Скачивает ai_writer.py / pb_client.py и запускает генерацию статьи (cron).
set -euo pipefail

BASE='https://raw.githubusercontent.com/dantrusov10/parse.py/refs/heads/main'
TARGET_DIR='/usr/local/bin'

curl -fsSL "${BASE}/ai_writer.py" -o "${TARGET_DIR}/ai-writer.py.tmp"
curl -fsSL "${BASE}/pb_client.py" -o "${TARGET_DIR}/pb_client.py.tmp"
mv -f "${TARGET_DIR}/ai-writer.py.tmp" "${TARGET_DIR}/ai-writer.py"
mv -f "${TARGET_DIR}/pb_client.py.tmp" "${TARGET_DIR}/pb_client.py"
chmod +x "${TARGET_DIR}/ai-writer.py"

export PYTHONPATH="${TARGET_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec /usr/bin/python3 "${TARGET_DIR}/ai-writer.py"
