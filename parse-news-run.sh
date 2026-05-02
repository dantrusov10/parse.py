#!/bin/bash
set -euo pipefail

set -a
[ -f /etc/default/newlevel-parser ] && . /etc/default/newlevel-parser
set +a

BASE='https://raw.githubusercontent.com/dantrusov10/parse.py/main'
TARGET_DIR='/usr/local/bin'

curl -fsSL "${BASE}/parse.py" -o "${TARGET_DIR}/parse-news.py.tmp"
curl -fsSL "${BASE}/pb_client.py" -o "${TARGET_DIR}/pb_client.py.tmp"
curl -fsSL "${BASE}/telegram_publisher.py" -o "${TARGET_DIR}/telegram_publisher.py.tmp"
curl -fsSL "${BASE}/tg_manual_post.py" -o "${TARGET_DIR}/tg_manual_post.py.tmp"
mv -f "${TARGET_DIR}/parse-news.py.tmp" "${TARGET_DIR}/parse-news.py"
mv -f "${TARGET_DIR}/pb_client.py.tmp" "${TARGET_DIR}/pb_client.py"
mv -f "${TARGET_DIR}/telegram_publisher.py.tmp" "${TARGET_DIR}/telegram_publisher.py"
mv -f "${TARGET_DIR}/tg_manual_post.py.tmp" "${TARGET_DIR}/tg_manual_post.py"
chmod +x "${TARGET_DIR}/parse-news.py" "${TARGET_DIR}/tg_manual_post.py"

export PYTHONPATH="${TARGET_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
exec /usr/bin/python3 "${TARGET_DIR}/parse-news.py"
