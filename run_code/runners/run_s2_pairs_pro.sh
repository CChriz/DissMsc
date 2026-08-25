#!/usr/bin/env bash
# run_s2_pairs_pro.sh — scenario-2 PAIR bundles (P1-P10, 2 independent subtasks each)
# on the 8-member dynamic team, deepseek-v4-pro, PROMPT-ONLY. Timeout: run_one
# auto-detects the COMBO_* inner dir -> 1600s per run.
#
#   ~/jwclone/jwrun/run_s2_pairs_pro.sh                  # P2-P10 (P1 already run via run_one)
#   ~/jwclone/jwrun/run_s2_pairs_pro.sh --tasks "P2 P3"    # subset
#
# Resumable; archives + batch_results.tsv -> /mnt/c/Users/cz776/Downloads/Runs/S2_pairs_pro/
set -uo pipefail
export JW_POOL_SIZE=9
export JW_MODEL_NAME="deepseek-v4-pro"
exec /home/cz776/jwclone/jwrun/run_batch.sh \
  --roster dynamic \
  --root /home/cz776/jwclone/multitask/combos_s2 \
  --tasks "P2 P3 P4 P5 P6 P7 P8 P9 P10" \
  --arms "prompt-only" \
  --batch-root /mnt/c/Users/cz776/Downloads/Runs/S2_pairs_pro \
  "$@"
