#!/usr/bin/env bash
# Batch driver for C²oBra on Test-Comp tasks: runs batch/mass_test.py with the project venv
# (the system python3 has no tree_sitter). Options: batch/mass_test.sh --help
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$DIR/venv/bin/python3"
[ -x "$PY" ] || PY=python3
exec "$PY" "$DIR/batch/mass_test.py" "$@"
