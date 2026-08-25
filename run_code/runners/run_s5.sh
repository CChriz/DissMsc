#!/usr/bin/env bash
# run_s5.sh <partial|minimal> [--tasks "t1 t2 ..."] — S5 asymmetric planner/verifier spec
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
REGIME="${1:-}"; shift 2>/dev/null || true
case "$REGIME" in partial|minimal) ;; *) echo "usage: $0 <partial|minimal> [--tasks \"...\"]" >&2; exit 2;; esac
DOSE="$REGIME"
ARM="${JW_PERSONA_ARM:-generated}"
"$JWRUN/s5/verifier_execdeny.sh" on || exit 1
trap '"$JWRUN/s5/verifier_execdeny.sh" off; "$JWRUN/persona_setup.sh" _ stock' EXIT

ROOT=/home/cz776/jwclone/batch_roots/scenario1
SUF=""; [ "${JW_PERSONA_ARM:-stock}" = generated ] && SUF="_arm2"   # arm-2 -> separate batch root, never touch stock runs
BATCH_ROOT=/mnt/c/Users/cz776/Downloads/Runs/S5_${REGIME}_enf_pro${SUF}
KICKOFF_BASE="$JWRUN/s5/kickoff_s5.txt"
export JW_POOL_SIZE=9 JW_MODEL_NAME=deepseek-v4-pro
# S5 negotiation loop (plan covers a fraction -> verifier surfaces the rest ->
# fix -> judgment-only verify) needs more wall than the 800s single-task default:
# cross3 converged+attested at ~780s. 1200s unless caller overrides.
export JW_DONE_TIMEOUT="${JW_DONE_TIMEOUT:-1200}"
# Tamper-proof leader, same rationale as S3 (see run_s3_blockage.sh header):
# jw_leader cannot setfacl the split away (non-owner, no sudo); full data access
# so normal tool use is frictionless; leader interference stays observable.
export JW_LEADER_USER="${JW_LEADER_USER-jw_leader}"
export JW_LEADER_ACL="${JW_LEADER_ACL:-full}"

if [ "$REGIME" = partial ]; then TASKS=(spec5 spec6 p5 api1 cr4 cross3)
else TASKS=(crypto1 pipe3_stream_processing multi4 test9 lh5 ir2); fi
[ "${1:-}" = "--tasks" ] && { read -r -a TASKS <<< "$2"; }

mkdir -p "$BATCH_ROOT"
RESULTS="$BATCH_ROOT/batch_results.tsv"
[ -f "$RESULTS" ] || printf "timestamp\ttask\tdose\toutcome\ttraces\tarchive\n" > "$RESULTS"
echo "=== scenario-4 $DOSE split: ${#TASKS[@]} tasks -> $BATCH_ROOT ==="

for task in "${TASKS[@]}"; do
  label="${task}_s5${REGIME}${SUF}"
  if ls -d "$BATCH_ROOT/${label}-"* >/dev/null 2>&1; then
    echo "----- SKIP $label (archive exists) -----"; continue
  fi
  [ -f "$JWRUN/s5/specs/${task}/p_spec.md" ] || { echo "SKIP $task (no spec pair)"; continue; }
  "$JWRUN/persona_setup.sh" "$task" "$ARM" --specsplit || { echo "persona_setup FAILED $task" >&2; continue; }
  KTMP="$(mktemp "${TMPDIR:-/tmp}/kickoff_s5.XXXXXX.txt")"
  cat "$KICKOFF_BASE" > "$KTMP"; [ "$ARM" = generated ] && [ -f /tmp/jw_roster.txt ] && { echo >> "$KTMP"; cat /tmp/jw_roster.txt >> "$KTMP"; }
  echo "----- $label -----"
  OUT="$(JW_SPECSPLIT="${task}" "$JWRUN/run_one.sh" "$ROOT/${task}_0_team" \
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
