#!/usr/bin/env bash
# run_one.sh — ONE full run: clean→launch→ready→inject→wait-done→settle→archive→stop.
# Pins the Python interpreter (JW_PY) so the active conda env can't break the inject
# (leader_send.py needs `websockets`, which lives in the jwclone env).
#
# Usage: run_one.sh <task_dir> [--arm A] [--roster R] [--label L] [--kickoff F] [--timeout S] [--no-stop]
#   --roster predefined (default) | dynamic   (dynamic = leader designs its own team; prompt-only only)
set -uo pipefail
JWRUN="${JWRUN:-$HOME/jwclone/jwrun}"
JW_PY="${JW_PY:-$HOME/miniconda3/envs/jwclone/bin/python}"   # interpreter with websockets
TASK=""; ARM="enforced"; LABEL=""; KICKOFF="${JW_KICKOFF:-/home/cz776/jwclone/kickoff.txt}"
TIMEOUT="${JW_DONE_TIMEOUT:-}"; SETTLE="${JW_SETTLE:-8}"; DO_STOP=1   # empty = roster-based default below
ATTEST="${JW_ATTESTATION:-/srv/jwteam_clone/shared/run_current/attestation.json}"
ARCHIVE_ROOT="${JW_ARCHIVE_ROOT:-$HOME/jwclone/jwruns}"
ROSTER="predefined"; ARM_SET=0; KICKOFF_SET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --arm) ARM="$2"; ARM_SET=1; shift 2;; --label) LABEL="$2"; shift 2;;
    --roster) ROSTER="$2"; shift 2;;
    --kickoff) KICKOFF="$2"; KICKOFF_SET=1; shift 2;; --timeout) TIMEOUT="$2"; shift 2;;
    --no-stop) DO_STOP=0; shift;;
    --archive-root) ARCHIVE_ROOT="$2"; shift 2;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) TASK="$1"; shift;;
  esac
done

# ---- roster profile: dynamic = leader routes work over the standing catalog pool ----
# Pool modes: os (jw_cpoolK users @ /srv/pnodeK; enforced-capable) | cz776 (legacy; prompt-only).
case "$ROSTER" in
  predefined) ;;
  dynamic)
    POOL_MODE="${JW_POOL_MODE:-}"
    if [ -z "$POOL_MODE" ]; then
      if getent passwd jw_cpool1 >/dev/null 2>&1; then POOL_MODE=os; else POOL_MODE=cz776; fi
    fi
    export JW_POOL_MODE="$POOL_MODE"
    [ "$ARM_SET" = 1 ] || ARM="prompt-only"   # dynamic defaults to prompt-only
    if [ "$ARM" = "enforced" ] && [ "$POOL_MODE" != os ]; then
      echo "ERROR: enforced dynamic needs the OS-user pool (jw_cpool1..10)." >&2
      echo "       One-time setup: sudo bash ~/jwclone/setup_pool_system.sh" >&2; exit 2
    fi
    [ "$KICKOFF_SET" = 1 ] || KICKOFF="/home/cz776/jwclone/kickoff_dynamic.txt"
    # Leader OS user (opt-in): JW_LEADER_USER=jw_leader -> leader runs under its own
    # uid from the jw_leader-owned lnode home (per-scenario ACLs via JW_LEADER_ACL).
    if [ -n "${JW_LEADER_USER:-}" ]; then
      export JW_LEADER_USER
      export JW_LEADER_HOME="${JW_LEADER_HOME:-/srv/jwteam_clone/lnode}"
      # jw_leader boots ~90-120s (cold caches on the separate uid) vs cz776 ~40s;
      # give wait_ready more headroom so it doesn't abort mid-boot.
      export JW_READY_TIMEOUT="${JW_READY_TIMEOUT:-240}"
    fi
    export JW_LEADER_HOME="${JW_LEADER_HOME:-/home/cz776/jwclone/leader_home_dynamic}"
    # wait_ready.sh (called below) reads the leader handshake log + ready ports from env:
    export JW_LEADER_LOG="${JW_LEADER_LOG:-$JW_LEADER_HOME/.jiuwenswarm/agent/.logs/full.log}"
    if [ "$POOL_MODE" = os ]; then POOL_HOME_TPL="/srv/jwteam_clone/pnode%s"
    else POOL_HOME_TPL="/home/cz776/jwclone/pool/node%s"; fi
    # blank nodes (no catalog member pinned): skip entirely — never launched, not
    # waited on, not log-watched. Default 3 (planner3 removed 2026-08-07); node10
    # is excluded via JW_POOL_SIZE=9. Override with JW_POOL_SKIP="" to launch all.
    export JW_POOL_SKIP="${JW_POOL_SKIP-3}"
    _ps="${JW_POOL_SIZE:-10}"; _pp=""; _dl=""
    for _k in $(seq 1 "$_ps"); do
      case " $JW_POOL_SKIP " in *" $_k "*) continue;; esac
      _pp="$_pp $((18192 + _k))"
      _dl="$_dl $(printf "$POOL_HOME_TPL" "$_k")/logs/logs/team.log"
    done
    export JW_READY_PORTS="8100${_pp} 18192 19101 19100"
    export JW_DONE_LOGS="$_dl"   # wait_for_done.sh watches pool node team.logs (cz776:rX ACL keeps them readable)
    ;;
  *) echo "ERROR: --roster must be 'predefined' or 'dynamic'." >&2; exit 2;;
esac

[ -n "$TASK" ] && [ -d "$TASK" ] || { echo "ERROR: valid task dir required" >&2; exit 2; }
[ -f "$KICKOFF" ] || { echo "ERROR: kickoff not found: $KICKOFF" >&2; exit 2; }

# ---- timeout defaults (explicit --timeout / JW_DONE_TIMEOUT always win) ----
# Dynamic roster: combined/parallel tasks (inner COMBO_* dir) 1600s, singles 800s
# (flash + claim-handshake kickoff: singles need ~850-1000s; July pro-era 143-515s no longer applies).
if [ -z "$TIMEOUT" ]; then
  if [ "$ROSTER" = dynamic ]; then
    shopt -s nullglob; _combo=( "$TASK"/COMBO_*/ ); shopt -u nullglob
    if [ "${#_combo[@]}" -gt 0 ]; then TIMEOUT=1600; else TIMEOUT=800; fi
  else
    TIMEOUT=900
  fi
fi
[ -x "$JW_PY" ] || { echo "WARNING: JW_PY not executable ($JW_PY); falling back to python3" >&2; JW_PY="python3"; }
[ -n "$LABEL" ] || LABEL="$(basename "$TASK" | sed 's/_0_team$//')_$ARM"
say(){ echo "[run_one] $*"; }
stop_team(){ "$JWRUN/run_team.sh" --stop >/dev/null 2>&1 || true; }

say "===== $LABEL (task=$(basename "$TASK") arm=$ARM timeout=${TIMEOUT}s)  py=$JW_PY ====="
say "stopping any prior team..."; stop_team
# clear node logs/logs/*.log so they don't grow unboundedly AND so stale completion
# markers can't accumulate. (timestamp filter already guards detection; this is hygiene.)
# archive_run.py snapshots logs into the run archive, so truncating the live ones is safe.
# (predefined only — pool node logs are truncated by launch_pool_node.sh, no sudo)
if [ "${JW_CLEAN_LOGS:-1}" = 1 ] && [ "$ROSTER" != dynamic ]; then
  say "clearing node logs..."
  for n in 1 2 3; do
    for lg in /srv/jwteam_clone/cnode$n/logs/logs/*.log /srv/jwteam_clone/cnode$n/logs/logs/run/*.log; do
      [ -f "$lg" ] && sudo truncate -s 0 "$lg" 2>/dev/null || true
    done
  done
fi
for i in $(seq 1 15); do ss -ltn 2>/dev/null | grep -qE ":8100|:1819[2-5]|:1910[01]" || break; sleep 1; done

RUN_START="$(date +%s)"   # epoch; only completion markers newer than this count
say "launching..."
"$JWRUN/run_team.sh" "$TASK" --arm "$ARM" --roster "$ROSTER" --clean-traces --no-attach || { say "LAUNCH FAILED"; exit 1; }
say "waiting for ready..."
"$JWRUN/wait_ready.sh" || { say "NOT READY — aborting"; stop_team; exit 1; }

# dynamic roster: prepend the public task brief to the leader's kickoff so it can
# size the team to THIS task (the leader has no file-read tools of its own).
INJECT_FILE="$KICKOFF"; INJECT_TMP=""
if [ "$ROSTER" = "dynamic" ]; then
  BRIEF="/srv/jwteam_clone/shared/run_current/brief.md"
  INJECT_TMP="$(mktemp "${TMPDIR:-/tmp}/kickoff_dyn.XXXXXX.txt")"
  { echo "TASK BRIEF (public summary of the work to be done):"; echo
    if [ -r "$BRIEF" ]; then cat "$BRIEF"; else echo "(brief unavailable)"; fi
    echo; echo "----------------------------------------"; echo
    cat "$KICKOFF"; } > "$INJECT_TMP"
  INJECT_FILE="$INJECT_TMP"
  say "assembled dynamic kickoff (brief + instructions)"
fi

say "injecting kickoff..."
SESSION=""
INJECT_OUT="$("$JW_PY" "$JWRUN/leader_send.py" --file "$INJECT_FILE")" || { say "INJECT NOT ACCEPTED — aborting"; [ -n "$INJECT_TMP" ] && rm -f "$INJECT_TMP"; stop_team; exit 1; }
[ -n "$INJECT_TMP" ] && rm -f "$INJECT_TMP"
SESSION="$(printf '%s\n' "$INJECT_OUT" | sed -n 's/^SESSION=//p' | tail -1)"
say "leader accepted; pipeline running. session=${SESSION:-<unknown>}"

if "$JWRUN/wait_for_done.sh" --timeout "$TIMEOUT" --since "$RUN_START"; then DETECT="finished"; else DETECT="TIMEOUT"; fi
say "settling ${SETTLE}s..."; sleep "$SETTLE"

say "archiving as $LABEL..."
ARCHIVE_EXTRA=()
if [ "$ROSTER" = dynamic ]; then
  # dynamic traces are cz776-readable (owner on the cz776 pool; cz776:rX ACL on the OS pool),
  # so archiving stays no-sudo in both modes.
  POOL_TPL="${POOL_HOME_TPL/\%s/\{n\}}"
  ARCHIVE_EXTRA=( --no-sudo --nodes "${JW_POOL_SIZE:-10}"
    --leader-dir "$JW_LEADER_HOME/.jiuwenswarm/.agent_teams/traces"
    --node-trace "${POOL_TPL}/.jiuwenswarm/.agent_teams/traces"
    --node-log   "${POOL_TPL}/.jiuwenswarm/agent/.logs" )
fi
ARCHIVE_OUT="$("$JWRUN/archive_run.py" "$LABEL" --arm "$ARM" --archive-root "$ARCHIVE_ROOT" "${ARCHIVE_EXTRA[@]}" 2>&1)" && echo "$ARCHIVE_OUT" || { echo "$ARCHIVE_OUT"; say "WARNING: archive failed"; }
# find the archive dir from "done -> /path" (fallback: newest matching dir)
ARCHIVE_DIR="$(printf '%s\n' "$ARCHIVE_OUT" | sed -n 's/.*done -> //p' | tail -1)"
[ -d "$ARCHIVE_DIR" ] || ARCHIVE_DIR="$(ls -dt "$ARCHIVE_ROOT"/"$LABEL"-* 2>/dev/null | head -1)"

# ---- ARCHIVE COMPLETENESS CHECK + RECOVERY (2026-08-08) ----------------------
# archive_run.py sometimes silently captures NOTHING (empty traces/, no manifest).
# The raw streams are only recoverable RIGHT NOW — before the next run's
# configure_task_pool purges the live per-node/leader homes. Detect -> retry ->
# raw-copy fallback -> loud flag. Only meaningful for the dynamic pool.
if [ "$ROSTER" = dynamic ] && [ -n "$ARCHIVE_DIR" ] && [ -d "$ARCHIVE_DIR" ]; then
  _nstreams(){ find "$ARCHIVE_DIR/traces/nodes" -name '*-full.jsonl' 2>/dev/null | wc -l; }
  if [ "$(_nstreams)" -eq 0 ] || [ ! -f "$ARCHIVE_DIR/manifest.json" ]; then
    say "ARCHIVE INCOMPLETE (node_streams=$(_nstreams), manifest=$([ -f "$ARCHIVE_DIR/manifest.json" ] && echo Y || echo N)) — retrying archive_run.py..."
    "$JWRUN/archive_run.py" "$LABEL" --arm "$ARM" --archive-root "$ARCHIVE_ROOT" "${ARCHIVE_EXTRA[@]}" >/dev/null 2>&1 || true
    ARCHIVE_DIR="$(ls -dt "$ARCHIVE_ROOT"/"$LABEL"-* 2>/dev/null | head -1)"
  fi
  if [ "$(_nstreams)" -eq 0 ]; then
    say "retry still empty — raw-copying live node/leader streams as fallback (last recoverable window)"
    for k in $(seq 1 "${JW_POOL_SIZE:-9}"); do
      case " ${JW_POOL_SKIP:-} " in *" $k "*) continue;; esac
      src="$(printf "$POOL_HOME_TPL" "$k")/.jiuwenswarm/.agent_teams/traces"
      [ -d "$src" ] || continue
      mkdir -p "$ARCHIVE_DIR/traces/nodes/node$k"
      cp -p "$src"/*-full.jsonl "$ARCHIVE_DIR/traces/nodes/node$k/" 2>/dev/null || true
    done
    lsrc="$JW_LEADER_HOME/.jiuwenswarm/.agent_teams/traces"
    [ -d "$lsrc" ] && { mkdir -p "$ARCHIVE_DIR/traces/leader"; cp -p "$lsrc"/*-full.jsonl "$ARCHIVE_DIR/traces/leader/" 2>/dev/null || true; }
    printf 'ARCHIVE INCOMPLETE %s — archive_run.py captured nothing; raw streams copied directly from live homes as fallback. Derived files (manifest/members/turns_by_member) are ABSENT; recompute from traces/ via teamtrace.py.\n' "$(date '+%F %T')" > "$ARCHIVE_DIR/ARCHIVE_INCOMPLETE.txt"
  fi
  if [ "$(_nstreams)" -eq 0 ]; then
    say "!!! ARCHIVE UNRECOVERABLE — no streams found for $LABEL; raw streams will be lost at next configure !!!"
    printf 'UNRECOVERABLE — no node streams found in archive OR live homes.\n' >> "$ARCHIVE_DIR/ARCHIVE_INCOMPLETE.txt" 2>/dev/null || true
  else
    [ -f "$ARCHIVE_DIR/ARCHIVE_INCOMPLETE.txt" ] && say "archive RECOVERED via raw-copy: $(_nstreams) node streams (flagged ARCHIVE_INCOMPLETE.txt)"
  fi
fi
# capture THIS run's slice of each node team.log (handoffs/standby/coordination)
# team.log accumulates across runs, so we extract only lines at/after RUN_START.
if [ -n "$ARCHIVE_DIR" ] && [ -d "$ARCHIVE_DIR" ]; then
  mkdir -p "$ARCHIVE_DIR/traces/team_logs" 2>/dev/null || true
  # predefined: 3 jw_cnode team.logs (need sudo). dynamic: pool node team.logs (cz776, no sudo).
  if [ "$ROSTER" = dynamic ]; then
    SUDOL=""; team_logs=""   # pool logs readable as cz776 (owner, or cz776:rX ACL on OS pool)
    for k in $(seq 1 "${JW_POOL_SIZE:-10}"); do
      case " ${JW_POOL_SKIP:-} " in *" $k "*) continue;; esac
      team_logs="$team_logs node${k}:$(printf "$POOL_HOME_TPL" "$k")/logs/logs/team.log"
    done
  else
    SUDOL="sudo"; team_logs=""
    for n in 1 2 3; do team_logs="$team_logs node${n}:/srv/jwteam_clone/cnode${n}/logs/logs/team.log"; done
  fi
  for entry in $team_logs; do
    tag="${entry%%:*}"; tl="${entry#*:}"
    [ -f "$tl" ] || continue
    # RUN_START epoch -> "YYYY-MM-DD HH:MM:SS"; keep lines with ts >= that.
    $SUDOL "$JW_PY" - "$tl" "$RUN_START" "$ARCHIVE_DIR/traces/team_logs/${tag}-team.log" <<'PYIN' 2>/dev/null || true
import sys, datetime
src, since, dst = sys.argv[1], int(float(sys.argv[2])), sys.argv[3]
cut = datetime.datetime.fromtimestamp(since)
out = []
keep = False
import re
ts_re = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
for line in open(src, encoding="utf-8", errors="ignore"):
    m = ts_re.match(line)
    if m:
        try:
            t = datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
            keep = (t >= cut)
        except ValueError:
            pass
    if keep:
        out.append(line)
open(dst, "w", encoding="utf-8").write("".join(out))
PYIN
  done
  $SUDOL chown -R "$(id -un):$(id -gn)" "$ARCHIVE_DIR/traces/team_logs" 2>/dev/null || true
  say "captured per-run team.log slices -> traces/team_logs/"
fi

[ "$DO_STOP" = 1 ] && { say "stopping team..."; stop_team; }

# read verdict from the ARCHIVED attestation (cz776-readable; the live one under
# run_current is owned by jw_cnode3 and not readable as cz776).
ARCH_ATTEST="$ARCHIVE_DIR/run_current/attestation.json"
if [ -f "$ARCH_ATTEST" ] && [ -s "$ARCH_ATTEST" ]; then
  VERDICT="$("$JW_PY" -c "
import json,sys
d=json.load(open(sys.argv[1]))
# bundle attestation (combined tasks): per-subtask verdicts, either as a
# dict under 'subtasks' (P1 style) or a list under 'results'/'subtasks' (P2 style)
ent=[]
for key in ('subtasks','results','verifications'):
    s=d.get(key)
    if isinstance(s,dict): ent+=[x for x in s.values() if isinstance(x,dict)]
    elif isinstance(s,list): ent+=[x for x in s if isinstance(x,dict)]
ent=[x for x in ent if 'verdict' in x]
if ent:
    vs=[str(x.get('verdict','')).strip().lower() for x in ent]
    v=('pass' if vs and all(x in ('pass','passed') for x in vs)
       else 'fail' if any(x in ('fail','failed') for x in vs) else '')
else:
    C=[d]+[d[w] for w in ('attestation','summary','result') if isinstance(d.get(w),dict)]
    v=next((str(o[k]) for o in C for k in ('verdict','overall_verdict','result') if isinstance(o.get(k),str)),'').strip().lower()
    v=v or next((str(o['pass']).strip().lower() for o in C if isinstance(o.get('pass'),bool)),'')
print(('pass' if v in ('pass','passed','true','ok') else 'fail' if v in ('fail','failed','false') else v) or 'no_verdict')
" "$ARCH_ATTEST" 2>/dev/null || echo "unparseable")"
else
  VERDICT="no_attestation"
fi
case "$VERDICT" in
  pass|fail) OUTCOME="$DETECT/$VERDICT";;
  no_attestation) OUTCOME="$DETECT/NO_ATTESTATION";;
  no_verdict) OUTCOME="$DETECT/EMPTY_VERDICT";;
  *) OUTCOME="$DETECT/$VERDICT";;
esac
say "DONE  label=$LABEL  outcome=$OUTCOME"
case "$OUTCOME" in finished/pass|finished/fail) exit 0;; *) exit 1;; esac
