#!/usr/bin/env sh
# Harness TPI init (validator). Delegates to the portable Python implementation.
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "HARNESS INIT: FAIL - python no disponible" >&2
  echo "STOP - DO NOT MODIFY THE REPOSITORY - REQUEST HUMAN ASSISTANCE" >&2
  exit 1
fi
exec "$PY" "$ROOT/scripts/harness/init.py" "$@"
