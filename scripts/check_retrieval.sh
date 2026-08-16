#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
if [ -d .deps ]; then
  export PYTHONPATH=".deps:${PYTHONPATH:-}"
fi
exec python3 scripts/check_retrieval.py
