#!/usr/bin/env bash
# run_s4_split.sh [--tasks "t1 t2 ..."]   (single condition: closed/fully-invisible)
#
# Scenario-4 complementary-access batch on the 12 1A tasks (same set as S3).
# Each task: configure_task_pool --acls (base enforced) -> apply_split <task> <dose>
# (via JW_SPLIT hook in run_team.sh) -> enforced dynamic team, deepseek-v4-pro.
# Kickoff = kickoff_dynamic.txt + s4/kickoffs/<task>.kickoff.txt (zone map +
# coordination rule + leader non-intervention; exact member names).
#
#   Visibility (user-fixed 2026-08-09): non-owners get --- on the other zone —
#   fully invisible; every cross-zone fact must cross the message channel.
#
# Zones fixed: A=executor1+executor2 (jw_cpool4/5), B=executor3+fullstack1
# (jw_cpool6/9). Design: benchmark7/S4_DESIGN.md + S4_SPLITS.md.
# Resumable. Archives + results.tsv -> Runs/S4_<dose>_enf_pro/.
# Per-run TRACE CHECK: canary/seam analysis has NO structural fallback (3 S3-full
# archives silently lost traces), so each fresh archive is checked for non-empty
# streams + manifest and the row is flagged TRACE_FAIL if capture failed.
set -uo pipefail
JWRUN="${JWRUN:-$HOME/jwclone/jwrun}"
DOSE=closed

ROOT=/home/cz776/jwclone/batch_roots/scenario1
SUF=""; [ "${JW_PERSONA_ARM:-stock}" = generated ] && SUF="_arm2"   # arm-2 -> separate batch root, never touch stock runs
BATCH_ROOT=/mnt/c/Users/cz776/Downloads/Runs/S4_enf_pro${SUF}
KICKOFF_BASE=/home/cz776/jwclone/kickoff_dynamic.txt
export JW_POOL_SIZE=9 JW_MODEL_NAME=deepseek-v4-pro
# Tamper-proof leader, same rationale as S3 (see run_s3_blockage.sh header):
# jw_leader cannot setfacl the split away (non-owner, no sudo); full data access
# so normal tool use is frictionless; leader interference stays observable.
export JW_LEADER_USER="${JW_LEADER_USER-jw_leader}"
export JW_LEADER_ACL="${JW_LEADER_ACL:-full}"
ARM="${JW_PERSONA_ARM:-stock}"
[ "$ARM" = generated ] && trap '"$JWRUN/persona_setup.sh" _ stock' EXIT

TASKS=(spec5 lh5 spec6 test9 p5 cr4 cross3 crypto1 pipe3_stream_processing multi4 ir2 api1)
[ "${1:-}" = "--tasks" ] && { read -r -a TASKS <<< "$2"; }

mkdir -p "$BATCH_ROOT"
RESULTS="$BATCH_ROOT/batch_results.tsv"
[ -f "$RESULTS" ] || printf "timestamp\ttask\tdose\toutcome\ttraces\tarchive\n" > "$RESULTS"
echo "=== scenario-4 $DOSE split: ${#TASKS[@]} tasks -> $BATCH_ROOT ==="

for task in "${TASKS[@]}"; do
  label="${task}_s4${SUF}"
  if ls -d "$BATCH_ROOT/${label}-"* >/dev/null 2>&1; then
    echo "----- SKIP $label (archive exists) -----"; continue
  fi
  KADD="$JWRUN/s4/kickoffs/${task}.kickoff.txt"
  [ -f "$KADD" ] || { echo "SKIP $task (no kickoff addition $KADD)"; continue; }
  [ -f "$JWRUN/s4/maps/${task}.split.json" ] || { echo "SKIP $task (no split map)"; continue; }
  [ "$ARM" = generated ] && { "$JWRUN/persona_setup.sh" "$task" generated || { echo "persona_setup FAILED $task" >&2; continue; }; }
  KTMP="$(mktemp "${TMPDIR:-/tmp}/kickoff_s4.XXXXXX.txt")"
  { cat "$KICKOFF_BASE"; echo; cat "$KADD"; [ "$ARM" = generated ] && [ -f /tmp/jw_roster.txt ] && { echo; cat /tmp/jw_roster.txt; }; } > "$KTMP"
  echo "----- $label -----"
  OUT="$(JW_SPLIT="${task}:${DOSE}" "$JWRUN/run_one.sh" "$ROOT/${task}_0_team" \
          --arm enforced --roster dynamic --label "$label" \
          --archive-root "$BATCH_ROOT" --kickoff "$KTMP" 2>&1)"; rc=$?
  rm -f "$KTMP"
  echo "$OUT" | tail -3
  outcome="$(printf '%s\n' "$OUT" | sed -n 's/.*outcome=//p' | tail -1)"; outcome="${outcome:-UNKNOWN(rc=$rc)}"
  archive="$(ls -dt "$BATCH_ROOT/${label}-"* 2>/dev/null | head -1)"
  # trace non-emptiness check (S3 lesson: 3 archives lost traces silently)
  traces=TRACE_FAIL
  if [ -n "$archive" ]; then
    nstreams="$(find "$archive/traces" -name '*-full.jsonl' -size +0c 2>/dev/null | wc -l)"
    if [ "$nstreams" -ge 2 ] && [ -f "$archive/manifest.json" ]; then traces="ok($nstreams)"; fi
  fi
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$(date '+%F %T')" "$task" "$DOSE" "$outcome" "$traces" "${archive:-none}" >> "$RESULTS"
  echo "  -> $task [$DOSE]: $outcome traces=$traces"
done

echo "=== scenario-4 $DOSE complete ==="
column -t -s $'\t' "$RESULTS" 2>/dev/null || cat "$RESULTS"
