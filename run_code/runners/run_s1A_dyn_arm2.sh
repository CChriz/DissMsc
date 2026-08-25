#!/usr/bin/env bash
# run_s1A_dyn_arm2.sh — S1A solo-sufficient (12 1A tasks), PROMPT-ONLY arm, ARM-2
# task-specialised personas (+ roster + peer-ask escalation). Matches the stock
# S1A_team_dyn_pro leader config (leader_home_dynamic; NO jw_leader) so the ONLY
# difference from the stock prompt-only batch is the persona reskin.
#   ~/jwclone/jwrun/run_s1A_dyn_arm2.sh [--tasks "spec5 lh5"]
# Archives -> Runs/S1A_team_dyn_pro_arm2/  (stock S1A_team_dyn_pro untouched). Resumable.
set -uo pipefail
JWRUN="${JWRUN:-$HOME/jwclone/jwrun}"
ROOT=/home/cz776/jwclone/batch_roots/scenario1
BATCH_ROOT=/mnt/c/Users/cz776/Downloads/Runs/S1A_team_dyn_pro_arm2
KICKOFF_BASE=/home/cz776/jwclone/kickoff_dynamic.txt
DYNCFG=/home/cz776/jwclone/leader_home_dynamic/.jiuwenswarm/config/config.yaml
export JW_POOL_SIZE=9 JW_MODEL_NAME=deepseek-v4-pro
export JW_PERSONA_CFG="$DYNCFG"          # persona_setup edits the prompt-only leader config
export JW_NO_LEADER_ESCALATION=1         # arm-2 peer-ask escalation (largely inert w/o ACLs)
# NOTE: JW_LEADER_USER intentionally unset -> leader_home_dynamic (matches stock arm-1).

TASKS=(spec5 lh5 spec6 test9 p5 cr4 cross3 crypto1 pipe3_stream_processing multi4 ir2 api1)
[ "${1:-}" = "--tasks" ] && { read -r -a TASKS <<< "$2"; }

trap '"$JWRUN/persona_setup.sh" _ stock' EXIT   # restore stock personas on exit
mkdir -p "$BATCH_ROOT"
RESULTS="$BATCH_ROOT/batch_results.tsv"
[ -f "$RESULTS" ] || printf "timestamp\ttask\tarm\toutcome\ttraces\tarchive\n" > "$RESULTS"
echo "=== S1A prompt-only ARM-2: ${#TASKS[@]} tasks -> $BATCH_ROOT ==="

for task in "${TASKS[@]}"; do
  label="${task}_prompt-only"
  if ls -d "$BATCH_ROOT/${label}-"* >/dev/null 2>&1; then
    echo "----- SKIP $label (archive exists) -----"; continue
  fi
  "$JWRUN/persona_setup.sh" "$task" generated || { echo "persona_setup FAILED $task" >&2; continue; }
  KTMP="$(mktemp "${TMPDIR:-/tmp}/kickoff_s1a.XXXXXX.txt")"
  { cat "$KICKOFF_BASE"; [ -f /tmp/jw_roster.txt ] && { echo; cat /tmp/jw_roster.txt; }; } > "$KTMP"
  echo "----- $label -----"
  OUT="$("$JWRUN/run_one.sh" "$ROOT/${task}_0_team" --arm prompt-only --roster dynamic \
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
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$(date '+%F %T')" "$task" "prompt-only" "$outcome" "$traces" "${archive:-none}" >> "$RESULTS"
  echo "  -> $task: $outcome traces=$traces"
done
echo "=== S1A prompt-only ARM-2 complete ==="
column -t -s $'\t' "$RESULTS" 2>/dev/null || cat "$RESULTS"
