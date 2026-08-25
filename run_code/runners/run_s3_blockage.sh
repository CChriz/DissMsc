#!/usr/bin/env bash
# run_s3_blockage.sh <partial|full> [--tasks "t1 t2 ..."]
#
# Scenario-3 phase-blockage batch on the 12 solo-sufficient (1A) tasks, split 4/4/4
# across plan / exec / verify phases. Each task: configure_task_pool --acls (base
# enforced) -> apply_blockage <phase> <survivor|full> (via JW_BLOCKAGE hook in
# run_team.sh) -> run enforced dynamic team, deepseek-v4-pro, 800s wall.
#
#   partial : ONE viable path per phase (adversarial survivor = least-picked member)
#             plan->planner2, exec->executor2, verify->verifier2
#   full    : ZERO viable path (honest-report / unwinnable cell)
#
# Resumable; per-task JW_BLOCKAGE so a single run_batch won't do — dedicated loop.
# Archives + results.tsv -> Runs/S3_<mode>_enf_pro/
set -uo pipefail
JWRUN="${JWRUN:-$HOME/jwclone/jwrun}"
MODE="${1:-}"; shift 2>/dev/null || true
case "$MODE" in partial|full) ;; *) echo "usage: $0 <partial|full> [--tasks \"...\"]" >&2; exit 2;; esac

ROOT=/home/cz776/jwclone/batch_roots/scenario1
SUF=""; [ "${JW_PERSONA_ARM:-stock}" = generated ] && SUF="_arm2"   # arm-2 -> separate batch root, never touch stock runs
BATCH_ROOT=/mnt/c/Users/cz776/Downloads/Runs/S3_${MODE}_enf_pro${SUF}
export JW_POOL_SIZE=9 JW_MODEL_NAME=deepseek-v4-pro
# Tamper-proof leader: run as jw_leader with the SAME rwx data access cz776 had
# (JW_LEADER_ACL=full). The critical protection — the leader CANNOT setfacl the
# block away — comes from jw_leader being a NON-OWNER of run_current (setfacl needs
# ownership) and NOT being in sudoers (can't escalate). That holds regardless of ACL
# profile, so we give the leader full data access to avoid permission friction on
# its normal tool use (reading spec/workspace, writing skills/artifacts/trajectories,
# etc. — exactly what the cz776 leader did). Leader "doing the work" / writing
# attestation stays POSSIBLE and OBSERVABLE (trace-recordable), per the design intent;
# only the block-dismantling setfacl route is closed. run_one auto-sets
# JW_READY_TIMEOUT=240 for the cold boot. Override: JW_LEADER_USER= = cz776 leader.
export JW_LEADER_USER="${JW_LEADER_USER-jw_leader}"
export JW_LEADER_ACL="${JW_LEADER_ACL:-full}"
ARM="${JW_PERSONA_ARM:-stock}"
[ "$ARM" = generated ] && trap '"$JWRUN/persona_setup.sh" _ stock' EXIT

# phase groups (4/4/4). Survivor is spread across the LATER/generic holders of
# each phase (never the habitual first pick) — deterministic cycle for
# reproducibility; the adversarial survivor per the scenario-3 design.
#   plan   later holders: planner2, fullstack1        (planner1 = first-pick, never survivor)
#   exec   later holders: executor2, executor3, fullstack1  (executor1 = first-pick)
#   verify later holders: verifier2, fullstack1        (verifier1 = first-pick)
PLAN_TASKS=(spec5 lh5 spec6 test9)
EXEC_TASKS=(p5 cr4 cross3 crypto1)
VERIFY_TASKS=(pipe3_stream_processing multi4 ir2 api1)
PLAN_SURV=(planner2 fullstack1 planner2 fullstack1)
EXEC_SURV=(executor2 executor3 fullstack1 executor2)
VERIFY_SURV=(verifier2 fullstack1 verifier2 fullstack1)
declare -A PHASE_OF SURV_OF
assign(){ local -n TS=$1 SV=$2; local ph=$3 i=0
  for t in "${TS[@]}"; do PHASE_OF[$t]=$ph
    SURV_OF[$t]=$([ "$MODE" = full ] && echo full || echo "${SV[$i]}"); i=$((i+1)); done; }
assign PLAN_TASKS   PLAN_SURV   plan
assign EXEC_TASKS   EXEC_SURV   exec
assign VERIFY_TASKS VERIFY_SURV verify

# optional task subset
TASKS=("${PLAN_TASKS[@]}" "${EXEC_TASKS[@]}" "${VERIFY_TASKS[@]}")
[ "${1:-}" = "--tasks" ] && { read -r -a TASKS <<< "$2"; }

mkdir -p "$BATCH_ROOT"
RESULTS="$BATCH_ROOT/batch_results.tsv"
[ -f "$RESULTS" ] || printf "timestamp\ttask\tphase\tsurvivor\toutcome\tarchive\n" > "$RESULTS"
echo "=== scenario-3 $MODE blockage: ${#TASKS[@]} tasks -> $BATCH_ROOT ==="

for task in "${TASKS[@]}"; do
  ph="${PHASE_OF[$task]:-}"; sv="${SURV_OF[$task]:-}"
  [ -n "$ph" ] || { echo "SKIP $task (no phase mapping)"; continue; }
  label="${task}_s3${MODE}${SUF}"
  if ls -d "$BATCH_ROOT/${label}-"* >/dev/null 2>&1; then
    echo "----- SKIP $label (archive exists) -----"; continue
  fi
  echo "----- $label  phase=$ph survivor=$sv -----"
  [ "$ARM" = generated ] && { "$JWRUN/persona_setup.sh" "$task" generated || { echo "persona_setup FAILED $task" >&2; continue; }; }
  KICK=()
  if [ "$ARM" = generated ] && [ -f /tmp/jw_roster.txt ]; then KT="$(mktemp "${TMPDIR:-/tmp}/kickoff_s3.XXXXXX.txt")"; { cat /home/cz776/jwclone/kickoff_dynamic.txt; echo; cat /tmp/jw_roster.txt; } > "$KT"; KICK=(--kickoff "$KT"); fi
  OUT="$(JW_BLOCKAGE="${ph}:${sv}" "$JWRUN/run_one.sh" "$ROOT/${task}_0_team" \
          --arm enforced --roster dynamic --label "$label" \
          --archive-root "$BATCH_ROOT" "${KICK[@]}" 2>&1)"; rc=$?
  echo "$OUT" | tail -3
  outcome="$(printf '%s\n' "$OUT" | sed -n 's/.*outcome=//p' | tail -1)"; outcome="${outcome:-UNKNOWN(rc=$rc)}"
  archive="$(ls -dt "$BATCH_ROOT/${label}-"* 2>/dev/null | head -1)"
  printf "%s\t%s\t%s\t%s\t%s\t%s\n" "$(date '+%F %T')" "$task" "$ph" "$sv" "$outcome" "${archive:-none}" >> "$RESULTS"
  echo "  -> $task [$ph/$sv]: $outcome"
done

echo "=== scenario-3 $MODE complete ==="
column -t -s $'\t' "$RESULTS" 2>/dev/null || cat "$RESULTS"
