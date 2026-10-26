#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python demo/server.py "$@"
else
  exec "${PYTHON:-python3}" demo/server.py --replay-only "$@"
fi
