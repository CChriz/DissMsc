#!/usr/bin/env bash
# wait_ready.sh — block until the team is actually ready to receive the kickoff.
# Two gates: (1) all sockets listening, (2) gateway<->AgentServer handshake done.
# Usage:  wait_ready.sh [--timeout N] [--quiet]   ; exit 0 ready, 1 timeout.
set -uo pipefail

TIMEOUT="${JW_READY_TIMEOUT:-120}"
QUIET=0
LEADER_LOG="${JW_LEADER_LOG:-/home/cz776/jwclone/leader_home/.jiuwenswarm/agent/.logs/full.log}"
# ports that must be listening: registry, node(s), leader agentserver, gateway, web.
# JW_READY_PORTS overrides for the dynamic pool (variable node count).
if [ -n "${JW_READY_PORTS:-}" ]; then
  # shellcheck disable=SC2206
  PORTS=(${JW_READY_PORTS})
else
  PORTS=(8100 18193 18194 18195 18192 19101 19100)
fi

while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT="$2"; shift 2;;
    --quiet) QUIET=1; shift;;
    --leader-log) LEADER_LOG="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
log(){ [ "$QUIET" = 1 ] || echo "[wait_ready] $*" >&2; }

# mark the point in the log we start watching, so we only match THIS run's handshake
log_start_lines=$( [ -f "$LEADER_LOG" ] && wc -l < "$LEADER_LOG" || echo 0 )

ports_up() {
  for p in "${PORTS[@]}"; do
    ss -ltn 2>/dev/null | grep -q ":$p " || { MISSING="$p"; return 1; }
  done
  return 0
}

# look for the AgentServer-ready handshake AFTER where we started watching
handshake_done() {
  [ -f "$LEADER_LOG" ] || return 1
  tail -n +"$((log_start_lines+1))" "$LEADER_LOG" 2>/dev/null \
    | grep -qE "connection\.ack|AgentServer 已就绪|connected to AgentServer"
}

t=0
# phase 1: ports
until ports_up; do
  [ "$t" -ge "$TIMEOUT" ] && { log "TIMEOUT waiting for port :$MISSING"; exit 1; }
  log "waiting for ports… (missing :$MISSING, ${t}s)"
  sleep 2; t=$((t+2))
done
log "all ports listening (${t}s)"

# phase 2: gateway<->AgentServer handshake
until handshake_done; do
  [ "$t" -ge "$TIMEOUT" ] && { log "TIMEOUT waiting for AgentServer handshake"; exit 1; }
  log "ports up, waiting for AgentServer handshake… (${t}s)"
  sleep 2; t=$((t+2))
done
log "READY: ports up + AgentServer handshake complete (${t}s)"

# small settle so the gateway finishes wiring method handlers before we send
sleep "${JW_READY_SETTLE:-2}"
exit 0
