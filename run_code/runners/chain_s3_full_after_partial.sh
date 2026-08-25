#!/usr/bin/env bash
# chain_s3_full_after_partial.sh — waits for the running S3 PARTIAL batch to
# finish, then launches the S3 FULL batch. Fully detached (setsid) so it survives
# the launching session ending. Each full run applies its own fresh ACL config
# (configure_task_pool --acls + apply_blockage <phase> full) with the tamper-proof
# jw_leader leader — all baked into run_s3_blockage.sh, nothing to pass here.
set -uo pipefail
LOG=/home/cz776/jwclone/jwruns/s3_chain.log
exec >>"$LOG" 2>&1
echo "=== chain started $(date '+%F %T') — waiting for partial batch to finish ==="

# Wait until the partial batch driver process is gone. Poll every 60s.
# (Guard: also require the partial results TSV to have >= 12 data rows, so we
#  don't fire early if the process is briefly absent between tasks.)
PART_TSV=/mnt/c/Users/cz776/Downloads/Runs/S3_partial_enf_pro/batch_results.tsv
while true; do
  running=0
  pgrep -f "run_s3_blockage.sh partial" >/dev/null 2>&1 && running=1
  rows=$(( $(wc -l < "$PART_TSV" 2>/dev/null || echo 1) - 1 ))
  if [ "$running" = 0 ] && [ "$rows" -ge 12 ]; then
    echo "=== partial finished ($rows rows, driver gone) at $(date '+%T') ==="
    break
  fi
  sleep 60
done

sleep 45   # let the last partial run's team fully tear down + archive
echo "=== launching FULL batch $(date '+%F %T') ==="
/home/cz776/jwclone/jwrun/run_s3_blockage.sh full > /home/cz776/jwclone/jwruns/s3_full_batch.log 2>&1
echo "=== FULL batch finished $(date '+%F %T') ==="
