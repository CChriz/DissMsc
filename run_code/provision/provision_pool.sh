#!/usr/bin/env bash
# provision_pool.sh [N]  — create N cz776-owned blank-node homes for the DYNAMIC pool.
#
# No sudo. Each pool node runs as cz776 (dynamic runs are prompt-only, so the per-uid
# ACL isolation the jw_cnode users provide is not needed). Homes live under
# ~/jwclone/pool/nodeK, each with a config templated from cnode1 with a DISTINCT
# direct_addr port (the one per-node bind); bootstrap/server ports come from env at
# launch (launch_pool_node.sh). Registry (:8100) + shared DB are reached via the
# jw_cteam group, same as the fixed nodes.
#
#   ~/jwclone/jwrun/provision_pool.sh 10
#
# Port scheme (node k):  bootstrap 28700+10k   direct 28700+10k+1   server 18192+k
#   node1 -> 28710/28711/18193   ...   node10 -> 28800/28801/18202
set -euo pipefail

N="${1:-${JW_POOL_SIZE:-10}}"
POOL=/home/cz776/jwclone/pool
SRC=/srv/jwteam_clone/cnode1/.jiuwenswarm/config/config.yaml
TEAMENV=/home/cz776/jwclone/jwrun/team.env

[ -f "$SRC" ]     || { echo "ERROR: template node config missing: $SRC (run the 3-node stack setup first)" >&2; exit 1; }
[ -f "$TEAMENV" ] || { echo "ERROR: creds file missing: $TEAMENV" >&2; exit 1; }
case "$N" in ''|*[!0-9]*) echo "ERROR: N must be a positive integer" >&2; exit 2;; esac
[ "$N" -ge 1 ] || { echo "ERROR: N must be >= 1" >&2; exit 2; }

# Per-role max_iterations caps, matching the DETERMINISTIC catalog pin layout (launch_leader.sh):
#   node1-3 = planner (default 15) | node4-6 = executor (25) | node7-8 = verifier (10) | node9-10 = generic (25)
# Paper-compliant defaults; override via JW_CAP_* env.
CAP_PLANNER="${JW_CAP_PLANNER:-30}"; CAP_EXECUTOR="${JW_CAP_EXECUTOR:-40}"
CAP_VERIFIER="${JW_CAP_VERIFIER:-20}"; CAP_GENERIC="${JW_CAP_GENERIC:-50}"

mkdir -p "$POOL"
for k in $(seq 1 "$N"); do
  direct=$((28700 + k*10 + 1))
  home="$POOL/node$k"
  cfgdir="$home/.jiuwenswarm/config"
  mkdir -p "$cfgdir" "$home/logs/logs"
  # only per-node divergence: the direct_addr bind port (literal, no interpolation).
  sed -E "s#tcp://0\.0\.0\.0:28711#tcp://0.0.0.0:${direct}#g" "$SRC" > "$cfgdir/config.yaml"
  # per-node max_iterations cap by role group (node K bootstrap = 28700+10K)
  if   [ "$k" -le 3 ]; then cap="$CAP_PLANNER";  role=planner
  elif [ "$k" -le 6 ]; then cap="$CAP_EXECUTOR"; role=executor
  elif [ "$k" -le 8 ]; then cap="$CAP_VERIFIER"; role=verifier
  else                      cap="$CAP_GENERIC";  role=generic; fi
  # rewrite the react + agents.* max_iterations (100/200) to the role cap; leave commented lines alone
  sed -i -E "s/^([[:space:]]*max_iterations:[[:space:]]*)(100|200)[[:space:]]*\$/\1${cap}/" "$cfgdir/config.yaml"
  # AUTHORITATIVE per-node teammate cap: interface_deep.py prefers this node-local value over the
  # serialized team-spec max_iterations. Deterministic pinning => one member per node => per-role cap.
  printf '\nteam_teammate_max_iterations: %s\n' "$cap" >> "$cfgdir/config.yaml"
  chmod 640 "$cfgdir/config.yaml"
  # real creds as plain dotenv (strip any leading 'export ')
  sed -E 's/^[[:space:]]*export[[:space:]]+//' "$TEAMENV" > "$cfgdir/.env"
  chmod 600 "$cfgdir/.env"
  echo "  node$k: role=$role cap=$cap direct=$direct"
done

echo "provisioned $N pool node homes under $POOL (node1..node$N; caps planner=$CAP_PLANNER executor=$CAP_EXECUTOR verifier=$CAP_VERIFIER generic=$CAP_GENERIC)"
