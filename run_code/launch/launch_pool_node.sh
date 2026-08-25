#!/usr/bin/env bash
# launch_pool_node.sh K  — launch DYNAMIC-pool node K.
#
# Two modes, auto-detected (override with JW_POOL_MODE=os|cz776):
#   os    : node runs as its OWN OS user jw_cpoolK, HOME=/srv/jwteam_clone/pnodeK
#           (per-uid isolation -> enforced arm possible; launched via passwordless
#           sudo -u per /etc/sudoers.d/jwclone_pool; setup_pool_system.sh creates all)
#   cz776 : legacy no-sudo pool, HOME=~/jwclone/pool/nodeK (prompt-only only)
#
# Ports derive from K:  bootstrap 28700+10K   direct 28700+10K+1   server 18192+K.
set -euo pipefail

K="${1:?usage: launch_pool_node.sh <K>}"
case "$K" in ''|*[!0-9]*) echo "K must be a positive integer" >&2; exit 2;; esac

: "${API_BASE:?export API_BASE first}"
: "${API_KEY:?export API_KEY first}"
: "${MODEL_NAME:?export MODEL_NAME first}"
: "${MODEL_PROVIDER:?export MODEL_PROVIDER first}"
: "${JIUWEN_TEAM_WORKSPACE_ROOT:?export JIUWEN_TEAM_WORKSPACE_ROOT first}"

CONDA_BIN=/home/cz776/miniconda3/envs/jwclone/bin
BOOT=$((28700 + K*10))
SRV=$((18192 + K))

# mode auto-detect: OS pool if the user exists (setup_pool_system.sh has been run)
MODE="${JW_POOL_MODE:-}"
if [ -z "$MODE" ]; then
  if getent passwd "jw_cpool${K}" >/dev/null 2>&1; then MODE=os; else MODE=cz776; fi
fi

if [ "$MODE" = os ]; then
  HOME_K="/srv/jwteam_clone/pnode${K}"
  RUNAS=(sudo -n -u "jw_cpool${K}")
else
  HOME_K="/home/cz776/jwclone/pool/node${K}"
  RUNAS=(env)   # no-op prefix; exec env below carries the vars either way
fi

[ -f "$HOME_K/.jiuwenswarm/config/config.yaml" ] || {
  echo "ERROR: pool node $K not provisioned ($HOME_K). Run $([ "$MODE" = os ] && echo 'sudo bash ~/jwclone/setup_pool_system.sh' || echo "provision_pool.sh $K") first." >&2; exit 1; }

# per-run determinism for the cz776 pool (the OS pool is purged by configure_task_pool.sh under sudo)
if [ "$MODE" = cz776 ]; then
  rm -rf "$HOME_K/.jiuwenswarm/.agent_teams" \
         "$HOME_K/.jiuwenswarm/.openjiuwen" \
         "$HOME_K/.jiuwenswarm/agent/.checkpoint" \
         "$HOME_K/.jiuwenswarm/agent/sessions" \
         "$HOME_K/.a2x_registry_client" \
         "$HOME_K/.team" 2>/dev/null || true
  mkdir -p "$HOME_K/logs/logs"
  find "$HOME_K/logs/logs" -maxdepth 2 -name '*.log' -exec truncate -s 0 {} + 2>/dev/null || true
fi

# per-role react max_iterations cap (fixed layout: 1-3 planner, 4-6 executor, 7-8 verifier, 9-10 generic).
# JW_TEAMMATE_MAX_ITERS is read by the CLONE patch in openjiuwen/harness/deep_agent.py, which
# caps the react loop even under enable_task_loop (which otherwise sets it to sys.maxsize).
if   [ "$K" -le 3 ]; then CAP="${JW_CAP_PLANNER:-30}"
elif [ "$K" -le 6 ]; then CAP="${JW_CAP_EXECUTOR:-40}"
elif [ "$K" -le 8 ]; then CAP="${JW_CAP_VERIFIER:-30}"
else                      CAP="${JW_CAP_GENERIC:-50}"; fi

echo "launching pool node $K [$MODE]: HOME=$HOME_K bootstrap=$BOOT direct=$((BOOT+1)) server=$SRV cap=$CAP"

exec "${RUNAS[@]}" env \
  HOME="$HOME_K" \
  PATH="${CONDA_BIN}:/home/cz776/.local/bin:/home/cz776/.local/go/bin:/usr/bin:/bin" \
  API_BASE="$API_BASE" API_KEY="$API_KEY" \
  MODEL_NAME="$MODEL_NAME" MODEL_PROVIDER="$MODEL_PROVIDER" \
  JIUWEN_TEAM_WORKSPACE_ROOT="$JIUWEN_TEAM_WORKSPACE_ROOT" \
  JW_TEAMMATE_MAX_ITERS="$CAP" \
  TEAM_BOOTSTRAP_PORT="$BOOT" AGENT_SERVER_PORT="$SRV" \
  GIT_AUTHOR_NAME=bot GIT_AUTHOR_EMAIL=bot@x.com \
  GIT_COMMITTER_NAME=bot GIT_COMMITTER_EMAIL=bot@x.com \
  bash -c "cd '$HOME_K' && umask 002 && exec python -m jiuwenswarm.server.app_agentserver"
