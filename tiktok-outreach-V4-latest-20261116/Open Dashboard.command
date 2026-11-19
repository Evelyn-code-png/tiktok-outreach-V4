#!/bin/bash
set -e
OUTREACH_DIR="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Outreach V4 requires Python 3.10 or newer."
  echo "Install Python from https://www.python.org/downloads/ and open this file again."
  read -r -p "Press Enter to close. " _outreach_close
  exit 1
fi
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
  echo "Outreach V4 requires Python 3.10 or newer. Please update Python, then try again."
  read -r -p "Press Enter to close. " _outreach_close
  exit 1
fi
exec python3 "$OUTREACH_DIR/scripts/dashboard.py" --reuse
