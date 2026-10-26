#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert sys.version_info[:2] == (3,12), "Use Python 3.12 (set PYTHON=/path/to/python3.12)."'
"$PYTHON" -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python setup_upstream.py
.venv/bin/python demo/download_models.py
echo 'Ready. Run: ./demo.sh'
