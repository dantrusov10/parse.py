#!/bin/bash
set -euo pipefail

# Daily maintenance: remove duplicate imported articles by normalized title.
# Keeps newest record per title and leaves ai-* posts untouched.

SCRIPT_PATH="/usr/local/bin/delete_duplicate_articles.py"

if [ ! -f "$SCRIPT_PATH" ]; then
  echo "Missing $SCRIPT_PATH"
  exit 1
fi

systemctl stop pb-cms.service
trap 'systemctl start pb-cms.service' EXIT

/usr/bin/python3 "$SCRIPT_PATH" --confirm --show 5
systemctl start pb-cms.service
trap - EXIT

