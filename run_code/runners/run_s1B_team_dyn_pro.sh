#!/usr/bin/env bash
# run_s1B_team_dyn_pro.sh — scenario-1B SOLO-INSUFFICIENT set (n=8) on the 9-member
# dynamic team (standing catalog, OS pool, 9 nodes), deepseek-v4-pro, PROMPT-ONLY
# (clean workspace, no ACL enforcement). Timeouts: run_one auto (700s single).
#
#   ~/jwclone/jwrun/run_s1B_team_dyn_pro.sh                    # all 8 tasks
#   ~/jwclone/jwrun/run_s1B_team_dyn_pro.sh --tasks "dist2"      # subset
#
# Resumable; archives + batch_results.tsv -> /mnt/c/Users/cz776/Downloads/Runs/S1B_team_dyn_pro/
set -uo pipefail
export JW_POOL_SIZE=9
export JW_MODEL_NAME="deepseek-v4-pro"
exec /home/cz776/jwclone/jwrun/run_batch.sh \
  --roster dynamic \
  --root /home/cz776/jwclone/batch_roots/scenario1 \
  --tasks "dist2 gh14 synth1 dist1 test1 test4 multi5 pipe2" \
  --arms "prompt-only" \
  --batch-root /mnt/c/Users/cz776/Downloads/Runs/S1B_team_dyn_pro \
  "$@"
