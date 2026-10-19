#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 scripts/team_setup.py
echo 'Setup complete. Open Dashboard.command next.'
read -r -p 'Press Enter to close. ' _outreach_close
