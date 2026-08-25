#!/usr/bin/env bash
# launch_node.sh N   (N = 1 | 2 | 3)
# Launches one teammate node as its own OS user, reproducing the working
# distributed-mode invocation. Reads model/API env from the parent shell.
#
#   1 -> jw_cnode1  HOME=/srv/jwteam_clone/cnode1  bootstrap 28710  server 18193  (planner)
#   2 -> jw_cnode2  HOME=/srv/jwteam_clone/cnode2  bootstrap 28720  server 18194  (executor)
#   3 -> jw_cnode3  HOME=/srv/jwteam_clone/cnode3  bootstrap 28730  server 18195  (verifier)
#
# Prereqs: registry up on :8100; configure_task.sh already run; conda env's
# python on the PATH below. Run nodes 1,2,3 (each in its own terminal, or
# background with `&`) BEFORE launching the leader.
set -euo pipefail

N="${1:?usage: launch_node.sh <1|2|3>}"
case "$N" in 1|2|3) ;; *) echo "N must be 1, 2, or 3" >&2; exit 2;; esac

# per-node ports (from the pin fix — distinct bootstrap ports are REQUIRED)
declare -A BOOT=( [1]=28710 [2]=28720 [3]=28730 )
declare -A SRV=(  [1]=18193 [2]=18194 [3]=18195 )

# model/API config must be exported in the calling shell
: "${API_BASE:?export API_BASE first}"
: "${API_KEY:?export API_KEY first}"
: "${MODEL_NAME:?export MODEL_NAME first}"
: "${MODEL_PROVIDER:?export MODEL_PROVIDER first}"
: "${JIUWEN_TEAM_WORKSPACE_ROOT:?export JIUWEN_TEAM_WORKSPACE_ROOT first}"

CONDA_BIN=/home/cz776/miniconda3/envs/jwclone/bin

# per-role react max_iterations cap (fixed role->node pin: cnode1=planner, cnode2=executor,
# cnode3=verifier). Read by the CLONE patch in openjiuwen/harness/deep_agent.py, which caps the
# react loop AND forces a single react round (no task-loop re-run) = paper hard-total semantics.
case "$N" in
  1) CAP="${JW_CAP_PLANNER:-15}";;
  2) CAP="${JW_CAP_EXECUTOR:-35}";;
  3) CAP="${JW_CAP_VERIFIER:-10}";;
  *) CAP="${JW_CAP_DEFAULT:-25}";;
esac

echo "launching node $N: HOME=/srv/jwteam_clone/cnode${N} bootstrap=${BOOT[$N]} server=${SRV[$N]} cap=$CAP"

sudo -u "jw_cnode${N}" env \
  HOME="/srv/jwteam_clone/cnode${N}" \
  PATH="${CONDA_BIN}:/home/cz776/.local/bin:/home/cz776/.local/go/bin:/usr/bin:/bin" \
  API_BASE="$API_BASE" API_KEY="$API_KEY" \
  MODEL_NAME="$MODEL_NAME" MODEL_PROVIDER="$MODEL_PROVIDER" \
  JIUWEN_TEAM_WORKSPACE_ROOT="$JIUWEN_TEAM_WORKSPACE_ROOT" \
  JW_TEAMMATE_MAX_ITERS="$CAP" \
  TEAM_BOOTSTRAP_PORT="${BOOT[$N]}" AGENT_SERVER_PORT="${SRV[$N]}" \
  GIT_AUTHOR_NAME=bot GIT_AUTHOR_EMAIL=bot@x.com \
  GIT_COMMITTER_NAME=bot GIT_COMMITTER_EMAIL=bot@x.com \
  bash -c "cd /srv/jwteam_clone/cnode${N} && umask 002 && exec python -m jiuwenswarm.server.app_agentserver"
