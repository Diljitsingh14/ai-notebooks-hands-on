#!/usr/bin/env bash
set -euo pipefail

# Write all stdout/stderr to both console and /job/out/log.txt
mkdir -p /job/out
LOG="/job/out/log.txt"
touch "$LOG"

# Optional requirements
if [[ -f "/job/requirements.txt" ]] && [[ -s "/job/requirements.txt" ]]; then
  echo "[sandbox] Installing requirements..." | tee -a "$LOG"
  python -m pip install --user -r /job/requirements.txt 2>&1 | tee -a "$LOG"
fi

echo "[sandbox] Running script.py..." | tee -a "$LOG"

# Force matplotlib default save dir if user forgets path
export MPLCONFIGDIR="/job/.mpl"
mkdir -p "$MPLCONFIGDIR"

# Execute script; stream output
python /job/script.py 2>&1 | tee -a "$LOG"

echo "[sandbox] Completed." | tee -a "$LOG"
