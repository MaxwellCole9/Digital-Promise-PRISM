#!/usr/bin/env bash

# Resolve absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Trap errors and pause
trap 'echo -e "\n[ERROR] An error occurred. Press Enter to exit."; read' ERR
set -e

cd "$ROOT_DIR"

python3 -m venv venv
source venv/bin/activate
pip install -r setup/requirements.lock

cp .env.example .env

echo ""
echo "[SUCCESS] Setup complete."
echo "[NEXT STEP] Open the .env file in the PRISM folder, fill in your keys, and then run PRISM using run.command or run.bat."
echo ""
read -p "Press Enter to close..."