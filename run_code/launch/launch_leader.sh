#!/usr/bin/env bash
# launch_leader.sh
# Launches the team LEADER (orchestrator) as cz776, reproducing the working
# distributed-mode invocation (history: python -m jiuwenswarm.app).
#
#   HOME=/home/cz776/jwclone/leader_home  server 18192  gateway 19101  web 19100
#
# Prereqs (in this order):
#   1. registry up on :8100           (a2x-registry)
#   2. configure_task.sh already run  (run_current populated, ACLs applied)
#   3. all THREE nodes up             (launch_node.sh 1 / 2 / 3)
# Then run this. Reads model/API env from the calling shell.
set -euo pipefail

# model/API config must be exported in the calling shell (same as the nodes)
: "${API_BASE:?export API_BASE first}"
: "${API_KEY:?export API_KEY first}"
: "${MODEL_NAME:?export MODEL_NAME first}"
: "${MODEL_PROVIDER:?export MODEL_PROVIDER first}"
: "${JIUWEN_TEAM_WORKSPACE_ROOT:?export JIUWEN_TEAM_WORKSPACE_ROOT first}"

CONDA_BIN=/home/cz776/miniconda3/envs/jwclone/bin

# Leader HOME selects the config profile: default = predefined roster;
# JW_LEADER_HOME=.../leader_home_dynamic selects the empty-roster (dynamic) profile.
LEADER_HOME="${JW_LEADER_HOME:-/home/cz776/jwclone/leader_home}"

# Leader OS user (opt-in): JW_LEADER_USER=jw_leader runs the leader under its own
# uid so per-scenario ACLs bind it (leader-as-cz776 = run_current owner = exempt).
# Requires setup_leader_system.sh (user + sudoers) and the lnode home.
RUNAS=()
if [ -n "${JW_LEADER_USER:-}" ]; then
  getent passwd "$JW_LEADER_USER" >/dev/null \
    || { echo "ERROR: JW_LEADER_USER=$JW_LEADER_USER not found — run: sudo bash ~/jwclone/setup_leader_system.sh" >&2; exit 1; }
  RUNAS=(sudo -n -u "$JW_LEADER_USER")
  case "$LEADER_HOME" in
    /home/cz776/*) echo "  [warn] leader home $LEADER_HOME is cz776-owned; $JW_LEADER_USER cannot write state there (expected /srv/jwteam_clone/lnode)";;
  esac
  echo "  leader OS user: $JW_LEADER_USER"
fi

# Stale persona-map env would contaminate role assignment — clear it.
unset JIUWEN_TEAM_PERSONA_MAP || true

echo "launching leader: HOME=$LEADER_HOME server=18192 gateway=19101 web=19100"

# Optional preflight: warn if registry / nodes aren't listening yet.
if command -v ss >/dev/null 2>&1; then
  for p in 8100 18193 18194 18195; do
    ss -ltn 2>/dev/null | grep -q ":$p " || echo "  [warn] nothing listening on :$p (registry/nodes up?)"
  done
fi

# Role->endpoint pins bind planner/executor/verifier to fixed nodes (predefined arm).
# The dynamic pool disables them (JW_PIN_ENDPOINTS=0) so every spawn_teammate
# reservation grabs any free blank from the pool instead of a fixed role slot.
PINS=()
if [ "${JW_PIN_ENDPOINTS:-1}" != 0 ]; then
  PINS=( PIN_PLANNER_ENDPOINT="tcp://127.0.0.1:28710"
         PIN_EXECUTOR_ENDPOINT="tcp://127.0.0.1:28720"
         PIN_VERIFIER_ENDPOINT="tcp://127.0.0.1:28730" )
  echo "  role->endpoint pins: planner=28710 executor=28720 verifier=28730"
else
  echo "  role->endpoint pins: DISABLED (dynamic pool; catalog members pinned via PIN_MEMBER_ENDPOINTS)"
fi

# Dynamic catalog: DETERMINISTIC member->node pinning (pool node K bootstrap = 28700+10K).
# Fixed layout so per-role caps + future ACL binds key off it:
#   planner1-2 -> node1-2 (28710/20) | executor1-3 -> node4-6 (28740/50/60)
#   verifier1-2 -> node7-8 (28770/80) | fullstack1 -> node9 (28790); node3+node10 = unused blanks
PIN_MEMBER_ENV=""
if [ "${JW_CATALOG_PINS:-0}" = 1 ]; then
  PIN_MEMBER_ENV='{"planner1":"tcp://127.0.0.1:28710","planner2":"tcp://127.0.0.1:28720","executor1":"tcp://127.0.0.1:28740","executor2":"tcp://127.0.0.1:28750","executor3":"tcp://127.0.0.1:28760","verifier1":"tcp://127.0.0.1:28770","verifier2":"tcp://127.0.0.1:28780","fullstack1":"tcp://127.0.0.1:28790"}'
  echo "  catalog pins: planner1-2->node1-2, executor1-3->node4-6, verifier1-2->node7-8, fullstack1->node9"
fi

exec "${RUNAS[@]}" env \
  HOME="$LEADER_HOME" \
  PATH="${CONDA_BIN}:/home/cz776/.local/bin:/home/cz776/.local/go/bin:/usr/bin:/bin" \
  API_BASE="$API_BASE" API_KEY="$API_KEY" \
  MODEL_NAME="$MODEL_NAME" MODEL_PROVIDER="$MODEL_PROVIDER" \
  JIUWEN_TEAM_WORKSPACE_ROOT="$JIUWEN_TEAM_WORKSPACE_ROOT" \
  AGENT_SERVER_PORT=18192 GATEWAY_PORT=19101 WEB_PORT=19100 \
  PIN_MEMBER_ENDPOINTS="$PIN_MEMBER_ENV" \
  "${PINS[@]}" \
  bash -c "cd '$LEADER_HOME' && umask 002 && exec python -m jiuwenswarm.app"
  # cd to LEADER_HOME first: logs are written relative to CWD, and a jw_leader
  # leader can't chmod logs under the launch CWD (cz776-owned /mnt/c DrvFs path) —
  # Errno 1 Operation not permitted on boot. Home is jw_leader-owned + writable.
