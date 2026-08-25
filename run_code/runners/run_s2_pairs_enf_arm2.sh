#!/usr/bin/env bash
# run_s2_pairs_enf_arm2.sh — S2 pair bundles (P1-P10), ENFORCED arm, ARM-2
# task-specialised personas (+ team roster + peer-ask escalation).
#
# Matches the stock S2_pairs_enf_pro batch (run_s_all_enforced.sh [3/3]) exactly:
# 8-member dynamic team, deepseek-v4-pro, base enforced ACL matrix via
# configure_task_pool.sh --acls, leader = cz776 (leader_home_dynamic; jw_leader
# layer NOT used — JW_LEADER_USER intentionally unset). The ONLY difference is
# the arm-2 persona bundle, applied per bundle key (personas_arm2.json has
# P1..P10 groups; authority-probe twin applied wholesale by persona_setup).
#
#   ~/jwclone/jwrun/run_s2_pairs_enf_arm2.sh                   # all 10
#   ~/jwclone/jwrun/run_s2_pairs_enf_arm2.sh --tasks "P3 P6"   # subset
#
# LAUNCH FROM A REAL TERMINAL (wrapper-launched detached runs get reaped).
# Timeout: run_one auto-detects the COMBO_* inner dir -> 1600s per run.
# Archives + batch_results.tsv -> Runs/S2_pairs_enf_pro_arm2/ (stock dir untouched).
# Resumable: a bundle is SKIPPED if a <label>-* archive dir already exists.
set -uo pipefail
JWRUN="${JWRUN:-$HOME/jwclone/jwrun}"
ROOT=/home/cz776/jwclone/multitask/combos_s2
BATCH_ROOT=/mnt/c/Users/cz776/Downloads/Runs/S2_pairs_enf_pro_arm2
KICKOFF_BASE=/home/cz776/jwclone/kickoff_dynamic.txt
DYNCFG=/home/cz776/jwclone/leader_home_dynamic/.jiuwenswarm/config/config.yaml
export JW_POOL_SIZE=9 JW_MODEL_NAME=deepseek-v4-pro
export JW_PERSONA_CFG="$DYNCFG"          # persona_setup edits the cz776 leader config
export JW_NO_LEADER_ESCALATION=1         # arm-2 peer-ask escalation (part of the arm-2 bundle)
# NOTE: JW_LEADER_USER intentionally unset -> leader_home_dynamic (matches stock
# S2_pairs_enf_pro, which ran with the cz776 leader, NOT jw_leader).

TASKS=(P1 P2 P3 P4 P5 P6 P7 P8 P9 P10)
[ "${1:-}" = "--tasks" ] && { read -r -a TASKS <<< "$2"; }

# Restore TRUE stock on exit: JW_NO_LEADER_ESCALATION must be OFF for the restore,
# or persona_setup re-applies the peer-ask rewrite on top of the stock copy
# (that exact residue was left behind by the S1A arm-2 batch trap).
trap 'JW_NO_LEADER_ESCALATION=0 "$JWRUN/persona_setup.sh" _ stock' EXIT

# sudo keep-alive (enforced arm: configure_task_pool --acls runs setfacl via sudo).
# Prime once; NOPASSWD whitelist covers the run path, keepalive guards the rest.
echo "[batch] priming sudo..."
if sudo -n true 2>/dev/null; then :
elif [ -t 0 ]; then sudo -v || { echo "[batch] sudo auth failed" >&2; exit 1; }
else echo "[batch] no tty + no cached sudo; relying on NOPASSWD whitelist"; fi
( while true; do sudo -n -v 2>/dev/null || true; sleep 60; kill -0 "$$" 2>/dev/null || exit 0; done ) &
SUDO_KEEPALIVE_PID=$!
trap 'kill "$SUDO_KEEPALIVE_PID" 2>/dev/null || true; JW_NO_LEADER_ESCALATION=0 "$JWRUN/persona_setup.sh" _ stock' EXIT

mkdir -p "$BATCH_ROOT"
RESULTS="$BATCH_ROOT/batch_results.tsv"
[ -f "$RESULTS" ] || printf "timestamp\ttask\tarm\toutcome\ttraces\tarchive\n" > "$RESULTS"
echo "=== S2 pairs ENFORCED ARM-2: ${#TASKS[@]} bundles -> $BATCH_ROOT ==="

for task in "${TASKS[@]}"; do
  label="${task}_enforced"
  if ls -d "$BATCH_ROOT/${label}-"* >/dev/null 2>&1; then
    echo "----- SKIP $label (archive exists) -----"; continue
  fi
  [ -d "$ROOT/${task}_0_team" ] || { echo "SKIP $task — no $ROOT/${task}_0_team" >&2; continue; }
  "$JWRUN/persona_setup.sh" "$task" generated || { echo "persona_setup FAILED $task" >&2; continue; }
  KTMP="$(mktemp "${TMPDIR:-/tmp}/kickoff_s2arm2.XXXXXX.txt")"
  { cat "$KICKOFF_BASE"; [ -f /tmp/jw_roster.txt ] && { echo; cat /tmp/jw_roster.txt; }; } > "$KTMP"
  echo "----- $label -----"
  OUT="$("$JWRUN/run_one.sh" "$ROOT/${task}_0_team" --arm enforced --roster dynamic \
          --label "$label" --kickoff "$KTMP" --archive-root "$BATCH_ROOT" 2>&1)"; rc=$?
  rm -f "$KTMP"
  echo "$OUT" | tail -3
  outcome="$(printf '%s\n' "$OUT" | sed -n 's/.*outcome=//p' | tail -1)"; outcome="${outcome:-UNKNOWN(rc=$rc)}"
  archive="$(ls -dt "$BATCH_ROOT/${label}-"* 2>/dev/null | head -1)"
  traces=TRACE_FAIL
  if [ -n "$archive" ]; then
    nstreams="$(find "$archive/traces" -name '*-full.jsonl' -size +0c 2>/dev/null | wc -l)"
    [ "$nstreams" -ge 2 ] && [ -f "$archive/manifest.json" ] && traces="ok($nstreams)"
  fi
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$(date '+%F %T')" "$task" "enforced" "$outcome" "$traces" "${archive:-none}" >> "$RESULTS"
  echo "  -> $task: $outcome traces=$traces"
done
echo "=== S2 pairs ENFORCED ARM-2 complete ==="
column -t -s $'\t' "$RESULTS" 2>/dev/null || cat "$RESULTS"
echo
echo "Post-batch:"
echo "  JW_S2_RUNS=$BATCH_ROOT JW_S2_LABEL=enforced python3 $JWRUN/regrade_s2_pairs.py"
echo "  python tbmetrics/trace_audit.py $BATCH_ROOT   (from Windows benchmark7/)"
