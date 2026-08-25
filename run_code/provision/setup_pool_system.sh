#!/usr/bin/env bash
# setup_pool_system.sh — ONE-TIME privileged setup for the 10-node DYNAMIC pool with
# per-node OS users (mirrors setup_clone_system.sh for the 3-agent stack). Idempotent.
#
#   Run once:   sudo bash ~/jwclone/setup_pool_system.sh
#
# Creates:
#   users  jw_cpool1..10  (system, nologin, primary group jw_cteam)
#   homes  /srv/jwteam_clone/pnode1..10   (750, owner jw_cpoolK:jw_cteam)
#   sudoers /etc/sudoers.d/jwclone_pool   (cz776 -> jw_cpoolK NOPASSWD, for tmux launches)
#   per-node config.yaml + .env  (from the cnode1 template; distinct direct_addr; per-role
#   max_iterations caps; real creds) owned by the node user.
#
# Role layout (fixed; matches launch_leader.sh JW_CATALOG_PINS + provision_pool.sh):
#   pnode1-3 = planner | pnode4-6 = executor | pnode7-8 = verifier | pnode9-10 = generic
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0" >&2; exit 1; }

GRP=jw_cteam
BASE=/srv/jwteam_clone
DESKTOP_USER="${SUDO_USER:-cz776}"
SRC=/srv/jwteam_clone/cnode1/.jiuwenswarm/config/config.yaml
TEAMENV=/home/cz776/jwclone/jwrun/team.env
N=10

[ -f "$SRC" ]     || { echo "ERROR: template node config missing: $SRC (run setup_clone_system.sh first)" >&2; exit 1; }
[ -f "$TEAMENV" ] || { echo "ERROR: creds file missing: $TEAMENV" >&2; exit 1; }
getent group "$GRP" >/dev/null || { echo "ERROR: group $GRP missing (run setup_clone_system.sh first)" >&2; exit 1; }

# per-role max_iterations caps (same defaults as provision_pool.sh; override via env)
CAP_PLANNER="${JW_CAP_PLANNER:-30}"; CAP_EXECUTOR="${JW_CAP_EXECUTOR:-40}"
CAP_VERIFIER="${JW_CAP_VERIFIER:-20}"; CAP_GENERIC="${JW_CAP_GENERIC:-50}"

echo "== pool users + homes =="
for k in $(seq 1 $N); do
  u="jw_cpool$k"; home="$BASE/pnode$k"
  getent passwd "$u" >/dev/null || useradd -r -g "$GRP" -d "$home" -s /usr/sbin/nologin -M "$u"
  mkdir -p "$home"
  chown "$u:$GRP" "$home"; chmod 750 "$home"
  install -d -o "$u" -g "$GRP" -m 750 "$home/logs/logs"
  echo "  $u  -> $home"
done

echo "== sudoers (passwordless sudo -u jw_cpoolK for $DESKTOP_USER) =="
RULE=/etc/sudoers.d/jwclone_pool
USERS=$(seq -f "jw_cpool%g" 1 $N | paste -sd, -)
cat > "$RULE" <<EOF
# Pool nodes launch in tmux panes without a tty sudo ticket (same as jwclone_nodes).
$DESKTOP_USER ALL=($USERS) NOPASSWD: ALL
EOF
chmod 440 "$RULE"
visudo -cf "$RULE" >/dev/null 2>&1 && echo "  $RULE installed + validated" \
  || { echo "  ERROR: sudoers rule failed validation — removing"; rm -f "$RULE"; exit 1; }

echo "== per-node configs (template: cnode1; distinct direct_addr; role caps; real creds) =="
for k in $(seq 1 $N); do
  u="jw_cpool$k"; home="$BASE/pnode$k"; cfgdir="$home/.jiuwenswarm/config"
  direct=$((28700 + k*10 + 1))
  if   [ "$k" -le 3 ]; then cap="$CAP_PLANNER";  role=planner
  elif [ "$k" -le 6 ]; then cap="$CAP_EXECUTOR"; role=executor
  elif [ "$k" -le 8 ]; then cap="$CAP_VERIFIER"; role=verifier
  else                      cap="$CAP_GENERIC";  role=generic; fi
  mkdir -p "$cfgdir"
  sed -E "s#tcp://0\.0\.0\.0:28711#tcp://0.0.0.0:${direct}#g" "$SRC" > "$cfgdir/config.yaml"
  sed -i -E "s/^([[:space:]]*max_iterations:[[:space:]]*)(100|200)[[:space:]]*\$/\1${cap}/" "$cfgdir/config.yaml"
  printf '\nteam_teammate_max_iterations: %s\n' "$cap" >> "$cfgdir/config.yaml"
  sed -E 's/^[[:space:]]*export[[:space:]]+//' "$TEAMENV" > "$cfgdir/.env"
  chown -R "$u:$GRP" "$home/.jiuwenswarm"
  chmod 640 "$cfgdir/config.yaml"; chmod 640 "$cfgdir/.env"
  echo "  pnode$k: role=$role cap=$cap direct=$direct owner=$u"
done

echo
echo "DONE. Pool now has OS-user isolation (jw_cpool1..10 @ /srv/jwteam_clone/pnodeK)."
echo "Dynamic runs will auto-detect this and launch nodes via sudo -u (passwordless)."
echo "Enforced-arm dynamic runs become available: run_one.sh <task> --roster dynamic --arm enforced"
