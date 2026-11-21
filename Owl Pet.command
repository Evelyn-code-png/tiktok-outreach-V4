#!/bin/bash
# Start the Outreach owl on macOS: it peeks out from the edge of the screen; click it to open the workspace.
OUTREACH_DIR="$(cd "$(dirname "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1 || ! python3 -c 'import sys, tkinter; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' >/dev/null 2>&1; then
  echo "The owl needs Python 3.10 or newer with Tkinter."
  echo "Install Python from https://www.python.org/downloads/macos/ (it includes Tkinter) and open this file again."
  read -r -p "Press Enter to close. " _owl_close
  exit 1
fi
nohup python3 "$OUTREACH_DIR/scripts/owl_pet.py" >/dev/null 2>&1 &
echo "The owl is starting. You can close this window."
