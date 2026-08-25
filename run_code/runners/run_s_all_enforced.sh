#!/usr/bin/env bash
# run_s_all_enforced.sh — the full 30-run ENFORCED batch on the 8-member dynamic team:
#   1A solo-sufficient (12) -> 1B solo-insufficient (8) -> S2 pairs (10)
# deepseek-v4-pro, per-role ACLs (capability-table matrix, validated 2026-08-08),
# leader = cz776 (exempt; jw_leader layer not used). Timeouts auto: 800s/1600s.
# Sequential in ONE driver process (watcher-chaining proved unreliable).
# Resumable per batch; archives + batch_results.tsv per set.
set -uo pipefail
export JW_POOL_SIZE=9
export JW_MODEL_NAME="deepseek-v4-pro"
B=/home/cz776/jwclone/jwrun/run_batch.sh

echo "===== [1/3] 1A solo-sufficient, enforced ====="
"$B" --roster dynamic --arms "enforced" \
  --root /home/cz776/jwclone/batch_roots/scenario1 \
  --tasks "spec5 lh5 spec6 test9 p5 cr4 cross3 crypto1 pipe3_stream_processing multi4 ir2 api1" \
  --batch-root /mnt/c/Users/cz776/Downloads/Runs/S1A_team_enf_pro

echo "===== [2/3] 1B solo-insufficient, enforced ====="
"$B" --roster dynamic --arms "enforced" \
  --root /home/cz776/jwclone/batch_roots/scenario1 \
  --tasks "dist2 gh14 synth1 dist1 test1 test4 multi5 pipe2" \
  --batch-root /mnt/c/Users/cz776/Downloads/Runs/S1B_team_enf_pro

echo "===== [3/3] S2 pairs, enforced ====="
"$B" --roster dynamic --arms "enforced" \
  --root /home/cz776/jwclone/multitask/combos_s2 \
  --tasks "P1 P2 P3 P4 P5 P6 P7 P8 P9 P10" \
  --batch-root /mnt/c/Users/cz776/Downloads/Runs/S2_pairs_enf_pro

echo "===== ALL THREE ENFORCED BATCHES COMPLETE ====="
