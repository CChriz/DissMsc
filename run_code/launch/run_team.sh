#!/usr/bin/env bash
# run_team.sh — bring up a full TeamBench-on-JiuwenSwarm run in one command.
#
# Replaces the 6-terminals-and-many-passwords dance with a single tmux session:
# registry + node1/2/3 + leader + frontend, each in its own named window. You
# enter your sudo password ONCE; a keep-alive holds the credential for the
# launch. Secrets (API key etc.) are sourced from ~/jwclone/jwrun/team.env, NOT baked in.
#
# Usage:
#   ./run_team.sh <task_team_folder> --arm enforced       # configure(+ACLs) then launch
#   ./run_team.sh <task_team_folder> --arm prompt-only     # configure (no ACLs) then launch
#   ./run_team.sh <task_team_folder> --arm enforced --clean-traces   # also truncate old -full logs
#   ./run_team.sh --no-configure                           # just (re)launch, skip configure
#   ./run_team.sh --stop                                   # kill the session + team processes
#   ./run_team.sh ... --no-attach                          # launch in background, don't attach
#
# First-time setup — create the secrets file (kept out of git, chmod 600):
#   cat > ~/jwclone/jwrun/team.env <<'EOF'
#   export API_BASE="https://api.deepseek.com"
#   export API_KEY="sk-...your-key..."
#   export MODEL_NAME="deepseek-v4-pro"
#   export MODEL_PROVIDER="DeepSeek"
#   EOF
#   chmod 600 ~/jwclone/jwrun/team.env
set -euo pipefail

# ---- config (override via env or edit here) --------------------------------
SESSION="${JW_SESSION:-jwteam}"
JWRUN="${JWRUN:-$HOME/jwclone/jwrun}"
ENV_FILE="${JW_ENV_FILE:-$JWRUN/team.env}"
WORKSPACE_ROOT="${JW_WORKSPACE_ROOT:-/srv/jwteam_clone/shared/run_current}"
FRONTEND_DIR="${JW_FRONTEND_DIR:-$HOME/jwclone/jiuwenswarm/jiuwenswarm/channels/web/frontend}"
CONDA_SH="${JW_CONDA_SH:-$HOME/miniconda3/etc/profile.d/conda.sh}"
CONDA_ENV="${JW_CONDA_ENV:-jwclone}"
WS_BASE="${JW_WS_BASE:-ws://localhost:19100}"
LEADER_TRACE="${JW_LEADER_TRACE:-/home/cz776/jwclone/leader_home/.jiuwenswarm/.agent_teams/traces}"
NODE_TRACE_TPL="${JW_NODE_TRACE:-/srv/jwteam_clone/cnode%s/.jiuwenswarm/.agent_teams/traces}"
REGISTRY_CMD="${JW_REGISTRY_CMD:-a2x-registry --port 8100}"
# startup pacing (seconds) so registry is up before nodes, nodes before leader
WAIT_REGISTRY="${JW_WAIT_REGISTRY:-3}"
WAIT_NODES="${JW_WAIT_NODES:-3}"
# ----------------------------------------------------------------------------

TASK_DIR=""; ARM=""; DO_CONFIGURE=1; DO_ATTACH=1; CLEAN_TRACES=0; STOP=0; ROSTER="predefined"
while [ $# -gt 0 ]; do
  case "$1" in
    --arm) ARM="$2"; shift 2;;
    --roster) ROSTER="$2"; shift 2;;
    --no-configure) DO_CONFIGURE=0; shift;;
    --no-attach) DO_ATTACH=0; shift;;
    --clean-traces) CLEAN_TRACES=1; shift;;
    --stop) STOP=1; shift;;
    -h|--help) sed -n '2,30p' "$0"; exit 0;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) TASK_DIR="$1"; shift;;
  esac
done

# ---- roster profile ---------------------------------------------------------
# predefined (default): fixed 3 jw_cnode nodes, planner/executor/verifier from
#   leader_home config, role->endpoint pins.
# dynamic: empty-roster leader_home_dynamic + a cz776-owned pool of POOL_SIZE blank
#   nodes; leader spawns its own team at runtime (no pins; reservations grab any free
#   blank). Prompt-only (no per-uid ACLs on pool nodes).
POOL_SIZE="${JW_POOL_SIZE:-10}"; JW_POOL_SKIP="${JW_POOL_SKIP-3}"
POOL_MODE="${JW_POOL_MODE:-}"   # os = jw_cpoolK users @ /srv/pnodeK (enforced-capable) | cz776 = legacy no-sudo
case "$ROSTER" in
  predefined) ;;
  dynamic)
    if [ -z "$POOL_MODE" ]; then
      if getent passwd jw_cpool1 >/dev/null 2>&1; then POOL_MODE=os; else POOL_MODE=cz776; fi
    fi
    export JW_POOL_MODE="$POOL_MODE"
    # Leader OS user (opt-in): JW_LEADER_USER=jw_leader -> leader home defaults to the
    # jw_leader-owned lnode copy; per-scenario ACLs applied via leader_acl.sh below.
    if [ -n "${JW_LEADER_USER:-}" ]; then
      export JW_LEADER_USER
      export JW_LEADER_HOME="${JW_LEADER_HOME:-/srv/jwteam_clone/lnode}"
    fi
    export JW_LEADER_HOME="${JW_LEADER_HOME:-/home/cz776/jwclone/leader_home_dynamic}"
    export JW_PIN_ENDPOINTS=0   # bare planner/executor/verifier pins off; catalog uses PIN_MEMBER_ENDPOINTS
    export JW_CATALOG_PINS=1    # DETERMINISTIC catalog member->node pinning (see launch_leader.sh)
    LEADER_TRACE="${JW_LEADER_TRACE:-$JW_LEADER_HOME/.jiuwenswarm/.agent_teams/traces}"
    # readiness gate: registry + all pool server ports (18193..18192+POOL_SIZE) + leader/gw/web
    pool_ports=""; for k in $(seq 1 "$POOL_SIZE"); do case " ${JW_POOL_SKIP:-} " in *" $k "*) continue;; esac; pool_ports="$pool_ports $((18192 + k))"; done
    export JW_READY_PORTS="8100${pool_ports} 18192 19101 19100"
    if [ "$POOL_MODE" != os ] && [ "$ARM" = "enforced" ]; then
      echo "ERROR: enforced dynamic needs the OS-user pool. One-time: sudo bash ~/jwclone/setup_pool_system.sh" >&2; exit 2
    fi
    echo "[run_team] roster=dynamic  pool_mode=$POOL_MODE  leader_home=$JW_LEADER_HOME  pool_size=$POOL_SIZE";;
  *) echo "ERROR: --roster must be 'predefined' or 'dynamic'." >&2; exit 2;;
esac

# ---- stop mode -------------------------------------------------------------
if [ "$STOP" = 1 ]; then
  echo "[run_team] stopping session '$SESSION' and team processes..."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  pkill -9 -f jiuwenswarm 2>/dev/null || true
  pkill -9 -f a2x-registry 2>/dev/null || true
  echo "[run_team] stopped."
  exit 0
fi

# ---- preflight -------------------------------------------------------------
command -v tmux >/dev/null || { echo "tmux not installed:  sudo apt install tmux" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "ERROR: secrets file not found: $ENV_FILE" >&2
  echo "Create it (see header of this script) and  chmod 600 $ENV_FILE" >&2; exit 1; }
# guard against a world-readable secrets file
perm=$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo "")
[ "$perm" = "600" ] || echo "[run_team] WARNING: $ENV_FILE is mode ${perm:-?}; consider: chmod 600 $ENV_FILE" >&2
for s in launch_node.sh launch_leader.sh; do
  [ -x "$JWRUN/$s" ] || echo "[run_team] WARNING: $JWRUN/$s not found or not executable" >&2
done
if [ "$DO_CONFIGURE" = 1 ]; then
  [ -n "$TASK_DIR" ] || { echo "ERROR: a task folder is required to configure (or pass --no-configure)." >&2; exit 2; }
  [ -d "$TASK_DIR" ] || { echo "ERROR: not a directory: $TASK_DIR" >&2; exit 1; }
  case "$ARM" in
    enforced|prompt-only) ;;
    "") echo "ERROR: --arm enforced|prompt-only is required when configuring." >&2; exit 2;;
    *) echo "ERROR: --arm must be 'enforced' or 'prompt-only'." >&2; exit 2;;
  esac
fi

# ---- one sudo prompt, then keep the credential warm for the launch ---------
# Sudo needed for: predefined (3-agent stack) AND dynamic on the OS-user pool
# (configure_task_pool purge/ACLs cross uids). The legacy cz776 pool needs none.
KEEPALIVE=""
if [ "$ROSTER" != dynamic ] || [ "${POOL_MODE:-cz776}" = os ]; then
  # Check the NOPASSWD whitelist FIRST — the pool/predefined paths use only
  # whitelisted sudo (rm/cp/chown/chmod/setfacl/find/truncate/test/touch/chgrp +
  # sudo -u jw_*), which never expires and never prompts. Only fall back to an
  # interactive `sudo -v` if that whitelist is somehow unavailable AND we have a
  # tty. This avoids prompting for cz776's password-required (ALL:ALL) rule when
  # run from a real terminal.
  if sudo -n /usr/bin/test -d / 2>/dev/null; then
    echo "[run_team] sudo via NOPASSWD whitelist (no password needed)"
  elif sudo -n true 2>/dev/null; then
    echo "[run_team] cached sudo ticket present"
    ( while true; do sudo -n true 2>/dev/null; sleep 50; kill -0 "$$" 2>/dev/null || exit 0; done ) &
    KEEPALIVE=$!; trap 'kill "$KEEPALIVE" 2>/dev/null || true' EXIT
  elif [ -t 0 ]; then
    echo "[run_team] priming sudo (one prompt)..."; sudo -v || { echo "sudo auth failed" >&2; exit 1; }
    ( while true; do sudo -n true 2>/dev/null; sleep 50; kill -0 "$$" 2>/dev/null || exit 0; done ) &
    KEEPALIVE=$!; trap 'kill "$KEEPALIVE" 2>/dev/null || true' EXIT
  else
    echo "ERROR: sudo credential required and NOPASSWD whitelist unavailable" >&2; exit 1
  fi
else
  echo "[run_team] roster=dynamic (cz776 pool): no sudo needed"
fi

# ---- optional: truncate previous -full traces so arms don't append-mix -----
if [ "$CLEAN_TRACES" = 1 ]; then
  echo "[run_team] truncating previous *-full.jsonl traces (archive first if unsaved!)..."
  if [ "$ROSTER" = dynamic ] && [ "${POOL_MODE:-cz776}" = os ]; then
    SUDOT="sudo"; trace_dirs="$LEADER_TRACE"
    for k in $(seq 1 "$POOL_SIZE"); do trace_dirs="$trace_dirs /srv/jwteam_clone/pnode$k/.jiuwenswarm/.agent_teams/traces"; done
  elif [ "$ROSTER" = dynamic ]; then
    SUDOT=""; trace_dirs="$LEADER_TRACE"
    for k in $(seq 1 "$POOL_SIZE"); do trace_dirs="$trace_dirs /home/cz776/jwclone/pool/node$k/.jiuwenswarm/.agent_teams/traces"; done
  else
    SUDOT="sudo"; trace_dirs="$LEADER_TRACE $(for n in 1 2 3; do printf "$NODE_TRACE_TPL " "$n"; done)"
  fi
  for d in $trace_dirs; do
    if $SUDOT test -d "$d"; then
      while IFS= read -r f; do
        [ -n "$f" ] && $SUDOT truncate -s 0 "$f" && echo "    cleared $f"
      done < <($SUDOT find "$d" -maxdepth 1 -name '*-full.jsonl' 2>/dev/null)
    fi
  done
fi

# ---- optional: configure the task (self-cleaning; applies ACLs if enforced) -
if [ "$DO_CONFIGURE" = 1 ]; then
  if [ "$ROSTER" = dynamic ] && [ "${POOL_MODE:-cz776}" = os ]; then
    acl_flag=""; [ "$ARM" = "enforced" ] && acl_flag="--acls"
    echo "[run_team] configuring task (dynamic OS pool, $ARM)..."
    "$JWRUN/configure_task_pool.sh" "$TASK_DIR" $acl_flag
    # leader OS user: apply the per-scenario leader ACL profile AFTER the pool
    # configure (which rebuilds resource ACLs). Default 'full' = exempt-equivalent.
    if [ -n "${JW_LEADER_USER:-}" ]; then
      echo "[run_team] applying leader ACL profile: ${JW_LEADER_ACL:-full}"
      "$JWRUN/leader_acl.sh" "${JW_LEADER_ACL:-full}"
    fi
    # scenario-3 blockage delta (on top of enforced base ACLs). Format
    # JW_BLOCKAGE="<plan|exec|verify>:<survivor|full>" e.g. "plan:planner2","exec:full".
    if [ "$ARM" = "enforced" ] && [ -n "${JW_BLOCKAGE:-}" ]; then
      bphase="${JW_BLOCKAGE%%:*}"; bsurv="${JW_BLOCKAGE#*:}"
      echo "[run_team] applying scenario-3 blockage: phase=$bphase survivor=$bsurv"
      "$JWRUN/apply_blockage.sh" "$bphase" "$bsurv" || { echo "[run_team] blockage FAILED" >&2; exit 1; }
    fi
    # scenario-4 complementary-access split (on top of enforced base ACLs).
    # Format JW_SPLIT="<task>:<open|closed>" e.g. "cross3:open".
    if [ "$ARM" = "enforced" ] && [ -n "${JW_SPLIT:-}" ]; then
      stask="${JW_SPLIT%%:*}"; sdose="${JW_SPLIT#*:}"
      echo "[run_team] applying scenario-4 split: task=$stask dose=$sdose"
      "$JWRUN/s4/apply_split.sh" "$stask" "$sdose" || { echo "[run_team] split FAILED" >&2; exit 1; }
    fi
    # scenario-5 spec split (planner/verifier asymmetric specs). JW_SPECSPLIT="<task>"
    if [ "$ARM" = "enforced" ] && [ -n "${JW_SPECSPLIT:-}" ]; then
      echo "[run_team] applying scenario-5 spec split: task=$JW_SPECSPLIT"
      "$JWRUN/s5/apply_specsplit.sh" "$JW_SPECSPLIT" || { echo "[run_team] specsplit FAILED" >&2; exit 1; }
    fi
  elif [ "$ROSTER" = dynamic ]; then
    echo "[run_team] configuring task (dynamic cz776 pool, no-sudo, prompt-only)..."
    "$JWRUN/configure_task_dynamic.sh" "$TASK_DIR"
  else
    acl_flag=""; [ "$ARM" = "enforced" ] && acl_flag="--acls"
    echo "[run_team] configuring task ($ARM)..."
    "$JWRUN/configure_task.sh" "$TASK_DIR" $acl_flag
  fi
fi

# ---- build the tmux session ------------------------------------------------
tmux kill-session -t "$SESSION" 2>/dev/null || true

# command prefix run in every pane: activate conda env + load secrets + workspace root
ACT="source '$CONDA_SH' 2>/dev/null; conda activate '$CONDA_ENV' 2>/dev/null;"
ENV="source '$ENV_FILE'; export JIUWEN_TEAM_WORKSPACE_ROOT='$WORKSPACE_ROOT';"
# model override: team.env hard-sets MODEL_NAME, so JW_MODEL_NAME must be applied AFTER sourcing it
[ -n "${JW_MODEL_NAME:-}" ] && ENV="$ENV export MODEL_NAME='$JW_MODEL_NAME';"
PRE="$ACT $ENV"

echo "[run_team] launching tmux session '$SESSION'..."
tmux new-session -d -s "$SESSION" -n registry
tmux send-keys -t "$SESSION:registry" "$ACT $REGISTRY_CMD" C-m
sleep "$WAIT_REGISTRY"

if [ "$ROSTER" = "dynamic" ]; then
  # OS pool: configs live in /srv/jwteam_clone/pnodeK (provisioned once by setup_pool_system.sh).
  # cz776 pool: provision on demand.
  if [ "${POOL_MODE:-cz776}" != os ]; then
    "$JWRUN/provision_pool.sh" "$POOL_SIZE" || { echo "[run_team] pool provisioning FAILED" >&2; exit 1; }
  fi
  for k in $(seq 1 "$POOL_SIZE"); do
    case " ${JW_POOL_SKIP:-} " in *" $k "*) echo "[run_team] skipping blank node $k (JW_POOL_SKIP)"; continue;; esac
    tmux new-window -t "$SESSION" -n "pnode$k"
    tmux send-keys -t "$SESSION:pnode$k" "$PRE export JW_POOL_MODE='$POOL_MODE'; $JWRUN/launch_pool_node.sh $k" C-m
  done
else
  for n in 1 2 3; do
    tmux new-window -t "$SESSION" -n "node$n"
    tmux send-keys -t "$SESSION:node$n" "$PRE $JWRUN/launch_node.sh $n" C-m
  done
fi
sleep "$WAIT_NODES"

tmux new-window -t "$SESSION" -n leader
LEADER_PRE="$PRE"
[ "$ROSTER" = "dynamic" ] && LEADER_PRE="$PRE export JW_LEADER_HOME='$JW_LEADER_HOME'; export JW_PIN_ENDPOINTS=0; export JW_CATALOG_PINS=1;"
[ -n "${JW_LEADER_USER:-}" ] && LEADER_PRE="$LEADER_PRE export JW_LEADER_USER='$JW_LEADER_USER';"
tmux send-keys -t "$SESSION:leader" "$LEADER_PRE $JWRUN/launch_leader.sh" C-m

tmux new-window -t "$SESSION" -n frontend
tmux send-keys -t "$SESSION:frontend" \
  "$ACT cd '$FRONTEND_DIR'; VITE_WS_BASE='$WS_BASE' npm run dev" C-m

tmux select-window -t "$SESSION:leader"

echo "[run_team] up. windows: registry node1 node2 node3 leader frontend"
echo "[run_team]   attach : tmux attach -t $SESSION    (switch windows: Ctrl-b <n> or Ctrl-b w)"
echo "[run_team]   stop   : $0 --stop"

if [ "$DO_ATTACH" = 1 ]; then
  # release the keepalive to the foreground attach (sudo cache already warm)
  kill "$KEEPALIVE" 2>/dev/null || true; trap - EXIT
  exec tmux attach -t "$SESSION"
fi
