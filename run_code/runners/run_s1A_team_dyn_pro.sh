#!/usr/bin/env bash
# run_s1A_team_dyn_pro.sh — scenario-1A SOLO-SUFFICIENT set (n=12) on the 9-member
# dynamic team (standing catalog, OS pool, 9 nodes), deepseek-v4-pro, PROMPT-ONLY
# (clean workspace, no ACL enforcement). Timeouts: run_one auto (700s single).
#
#   ~/jwclone/jwrun/run_s1A_team_dyn_pro.sh                    # all 12 tasks
#   ~/jwclone/jwrun/run_s1A_team_dyn_pro.sh --tasks "spec5 lh5"  # subset
#
# Resumable; archives + batch_results.tsv -> /mnt/c/Users/cz776/Downloads/Runs/S1A_team_dyn_pro/
set -uo pipefail
export JW_POOL_SIZE=9
export JW_MODEL_NAME="deepseek-v4-pro"
exec /home/cz776/jwclone/jwrun/run_batch.sh \
  --roster dynamic \
  --root /home/cz776/jwclone/batch_roots/scenario1 \
  --tasks "spec5 lh5 spec6 test9 p5 cr4 cross3 crypto1 pipe3_stream_processing multi4 ir2 api1" \
  --arms "prompt-only" \
  --batch-root /mnt/c/Users/cz776/Downloads/Runs/S1A_team_dyn_pro \
  "$@"
