#!/usr/bin/env bash
# wait_for_done.sh — block until THIS run's pipeline completes.
#
# SINGLE signal: teammates pause their polling loops exactly once, at the very end,
# when the framework broadcasts TEAM_STANDBY. In the node team.log:
#   <ts> | team | sess_xxx | INFO | [planner] received TEAM_STANDBY, pausing polls
#   <ts> | team | sess_xxx | INFO | EventBus[teammate] pausing polls
# We key on "pausing polls". team.log ACCUMULATES across runs and is not cleared by
# --clean-traces, so a previous run's "pausing polls" would false-match and tear down
# a live run mid-build. We therefore require the line's TIMESTAMP to be NEWER THAN
# this run's start (--since epoch, set by run_one.sh).
#
# No other completion heuristics — only this signal, bounded by --timeout.
# Exit 0 = standby seen (done). Exit 1 = timeout.
set -uo pipefail
TIMEOUT="${JW_DONE_TIMEOUT:-900}"; POLL="${JW_DONE_POLL:-10}"; VERBOSE=1
SINCE="${JW_SINCE:-$(date +%s)}"
# JW_DONE_LOGS overrides for the dynamic pool (variable node count, cz776 homes).
if [ -n "${JW_DONE_LOGS:-}" ]; then
  # shellcheck disable=SC2206
  NODE_LOGS=(${JW_DONE_LOGS})
else
  NODE_LOGS=(
    "/srv/jwteam_clone/cnode1/logs/logs/team.log"
    "/srv/jwteam_clone/cnode2/logs/logs/team.log"
    "/srv/jwteam_clone/cnode3/logs/logs/team.log"
  )
fi
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2;;
    --since) SINCE="$2"; shift 2;;
    --quiet) VERBOSE=0; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
log(){ [ "$VERBOSE" = 1 ] && echo "[wait_for_done] $*" >&2 || true; }

# the ONLY signal: a "pausing polls" line NEWER THAN $SINCE in any node team.log.
pausing_polls_since(){
  python3 - "$SINCE" "${NODE_LOGS[@]}" <<'PY'
import sys, re, datetime, os
since=int(float(sys.argv[1]))
files=sys.argv[2:]
marker=re.compile(r'pausing polls|TEAM_STANDBY')
ts_re=re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})')
for f in files:
    if not os.path.exists(f): continue
    try:
        for line in open(f, encoding="utf-8", errors="ignore"):
            if not marker.search(line): continue
            m=ts_re.match(line)
            if not m: continue
            try:
                t=datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
            except ValueError:
                continue
            if t >= since:
                sys.exit(0)
    except FileNotFoundError:
        pass
sys.exit(1)
PY
}

t=0
log "watching for 'pausing polls' since $(date -d @"$SINCE" '+%T' 2>/dev/null || echo "$SINCE") (timeout ${TIMEOUT}s)"
while [ "$t" -lt "$TIMEOUT" ]; do
  if pausing_polls_since; then
    log "DONE — teammates paused polls (TEAM_STANDBY, this run) after ${t}s"; exit 0
  fi
  [ $((t % 60)) -eq 0 ] && log "…running (${t}s)"
  sleep "$POLL"; t=$((t+POLL))
done
log "TIMEOUT ${TIMEOUT}s — no 'pausing polls' for this run (stalled?)"
exit 1
