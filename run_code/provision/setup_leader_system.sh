#!/usr/bin/env bash
# setup_leader_system.sh — ONE-TIME privileged setup for the LEADER OS user
# (mirrors setup_pool_system.sh for the 10-node pool). Idempotent.
#
#   Run once:   sudo bash ~/jwclone/setup_leader_system.sh
#
# Creates:
#   user   jw_leader   (system, nologin, primary group jw_cteam)
#   home   /srv/jwteam_clone/lnode   (750, owner jw_leader:jw_cteam)
#          config copied from leader_home_dynamic (canonical catalog config)
#   sudoers /etc/sudoers.d/jwclone_leader   (cz776 -> jw_leader NOPASSWD)
#   ACL    cz776:rX over the home (archiver/watchdog read, same as pool nodes)
#
# Why: the leader has always run as cz776 = OWNER of run_current, so it was
# structurally exempt from ACL enforcement (manifest exempt=true). A separate
# uid makes leader access per-scenario controllable via jwrun/leader_acl.sh.
#
# After setup, an OS-leader dynamic run is:
#   JW_LEADER_USER=jw_leader JW_LEADER_ACL=coordination \
#     ~/jwclone/jwrun/run_one.sh "<task_0_team>" --roster dynamic --arm enforced
# Leave JW_LEADER_USER unset for the legacy cz776 leader (default, unchanged).
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0" >&2; exit 1; }

GRP=jw_cteam
U=jw_leader
HOME_DIR=/srv/jwteam_clone/lnode
TEMPLATE=/home/cz776/jwclone/leader_home_dynamic
DESKTOP_USER="${SUDO_USER:-cz776}"

getent group "$GRP" >/dev/null || { echo "ERROR: group $GRP missing (run setup_clone_system.sh first)" >&2; exit 1; }
[ -f "$TEMPLATE/.jiuwenswarm/config/config.yaml" ] || { echo "ERROR: template config missing: $TEMPLATE/.jiuwenswarm/config/config.yaml" >&2; exit 1; }

echo "== leader user + home =="
getent passwd "$U" >/dev/null || useradd -r -g "$GRP" -d "$HOME_DIR" -s /usr/sbin/nologin -M "$U"
mkdir -p "$HOME_DIR"
chown "$U:$GRP" "$HOME_DIR"; chmod 750 "$HOME_DIR"
echo "  $U -> $HOME_DIR"

echo "== config (from $TEMPLATE; re-copied on every setup run) =="
install -d -o "$U" -g "$GRP" -m 750 "$HOME_DIR/.jiuwenswarm/config"
cp "$TEMPLATE/.jiuwenswarm/config/config.yaml" "$HOME_DIR/.jiuwenswarm/config/config.yaml"
chown "$U:$GRP" "$HOME_DIR/.jiuwenswarm/config/config.yaml"
chmod 640 "$HOME_DIR/.jiuwenswarm/config/config.yaml"

# The leader creates .agent_teams/, agent/sessions/, etc. UNDER .jiuwenswarm at
# runtime — so the WHOLE home must be owned by the leader user, not root. `install -d`
# above creates .jiuwenswarm as root; without this the leader hits [Errno 13] on
# .agent_teams (2026-08-08). Seed agent/ dirs + chown the tree, then cz776:rX for
# the archiver/watchdog (cz776 reads leader traces to archive them).
install -d -o "$U" -g "$GRP" -m 750 \
  "$HOME_DIR/.jiuwenswarm/agent/sessions" \
  "$HOME_DIR/.jiuwenswarm/agent/.logs"
chown -R "$U:$GRP" "$HOME_DIR/.jiuwenswarm"
chmod 750 "$HOME_DIR/.jiuwenswarm"
setfacl -R  -m u:"$DESKTOP_USER":rX "$HOME_DIR/.jiuwenswarm" 2>/dev/null || true
setfacl -R -d -m u:"$DESKTOP_USER":rX "$HOME_DIR/.jiuwenswarm" 2>/dev/null || true
echo "  home owned by $U (leader creates .agent_teams/sessions at runtime); $DESKTOP_USER:rX for archiver"
echo "  NOTE: catalog/persona edits go in the TEMPLATE ($TEMPLATE), then re-run this script."

echo "== sudoers (passwordless sudo -u $U for $DESKTOP_USER) =="
RULE=/etc/sudoers.d/jwclone_leader
cat > "$RULE" <<EOF
# Leader launches in a tmux pane without a tty sudo ticket (same as jwclone_pool).
$DESKTOP_USER ALL=($U) NOPASSWD: ALL
EOF
chmod 440 "$RULE"
visudo -cf "$RULE" >/dev/null 2>&1 && echo "  $RULE installed + validated" \
  || { echo "  ERROR: sudoers rule failed validation — removing"; rm -f "$RULE"; exit 1; }

echo "== harness read ACL (cz776:rX; archiver + watchdog tail the leader traces) =="
setfacl -R  -m "u:$DESKTOP_USER:rX" "$HOME_DIR"
setfacl -R -d -m "u:$DESKTOP_USER:rX" "$HOME_DIR"

echo
echo "DONE. Leader OS user ready."
echo "Per-run leader permissions: jwrun/leader_acl.sh <full|informed|coordination|none>"
echo "(run_team.sh applies it automatically after configure when JW_LEADER_USER is set;"
echo " profile from JW_LEADER_ACL, default full = today's exempt-equivalent behavior)."
echo "If the leader fails to boot as $U, it may need more template state copied from"
echo "$TEMPLATE into $HOME_DIR (config.yaml alone matched the pool-node pattern)."
