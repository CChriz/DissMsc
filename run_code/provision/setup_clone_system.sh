#!/usr/bin/env bash
# setup_clone_system.sh — ONE-TIME privileged setup for the jwclone stack.
# Creates the isolated node users/group and the /srv/jwteam_clone runtime tree,
# mirroring the original /srv/jwteam layout but under new identities. Idempotent.
#
#   Run once:   sudo bash ~/jwclone/setup_clone_system.sh
#
# Mirrors original:  jw_node1/2/3 : jw_team : /srv/jwteam
#           clone ->  jw_cnode1/2/3: jw_cteam: /srv/jwteam_clone
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "run with sudo: sudo bash $0" >&2; exit 1; }

GRP=jw_cteam
BASE=/srv/jwteam_clone
DESKTOP_USER="${SUDO_USER:-cz776}"   # the human who will run configure_task/run_team

echo "== group =="
getent group "$GRP" >/dev/null || groupadd "$GRP"
echo "  $GRP: $(getent group "$GRP")"

echo "== node users (system, nologin, primary group $GRP) =="
for n in 1 2 3; do
  u="jw_cnode$n"; home="$BASE/cnode$n"
  if getent passwd "$u" >/dev/null; then
    echo "  $u exists"
  else
    useradd -r -g "$GRP" -d "$home" -s /usr/sbin/nologin -M "$u"
    echo "  created $u (home $home)"
  fi
done

echo "== add $DESKTOP_USER to $GRP (for group access to shared/) =="
id -nG "$DESKTOP_USER" | tr ' ' '\n' | grep -qx "$GRP" || usermod -aG "$GRP" "$DESKTOP_USER"
echo "  $DESKTOP_USER groups: $(id -nG "$DESKTOP_USER")"
echo "  NOTE: $DESKTOP_USER must open a NEW shell for the new group to take effect."

echo "== runtime tree $BASE =="
mkdir -p "$BASE/shared" "$BASE/cnode1" "$BASE/cnode2" "$BASE/cnode3"
chown root:root "$BASE";           chmod 755  "$BASE"
for n in 1 2 3; do
  chown "jw_cnode$n:$GRP" "$BASE/cnode$n"; chmod 750 "$BASE/cnode$n"
  # pre-create the log dir run_one.sh truncates (app creates the rest)
  install -d -o "jw_cnode$n" -g "$GRP" -m 750 "$BASE/cnode$n/logs/logs"
done
# shared: group-writable + setgid so new files inherit the group (mirrors original)
chown root:"$GRP" "$BASE/shared"; chmod 2770 "$BASE/shared"
# seed the DB file (configure_task.sh resets it each run; this makes first launch clean)
[ -e "$BASE/shared/team_shared.db" ] || : > "$BASE/shared/team_shared.db"
chown root:"$GRP" "$BASE/shared/team_shared.db"; chmod 664 "$BASE/shared/team_shared.db"

echo
echo "== layout =="
ls -la "$BASE"; echo "--- shared ---"; ls -la "$BASE/shared"

echo
echo "== passwordless sudo -u jw_cnodeN (nodes launch in tmux panes w/o a tty ticket) =="
RULE=/etc/sudoers.d/jwclone_nodes
cat > "$RULE" <<EOF
# Allow $DESKTOP_USER to launch the clone nodes as their isolated users without a
# password. The nodes start in tmux panes (separate ttys) that don't inherit the
# run_team.sh sudo ticket, so this rule is required for an unattended launch.
$DESKTOP_USER ALL=(jw_cnode1,jw_cnode2,jw_cnode3) NOPASSWD: ALL
EOF
chmod 440 "$RULE"
if visudo -cf "$RULE" >/dev/null 2>&1; then echo "  $RULE installed + validated"; else
  echo "  ERROR: sudoers rule failed validation — removing"; rm -f "$RULE"; fi

echo
echo "== provision clone node configs (registry 8100 / clone DB / +100 transport) =="
SELFDIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SELFDIR/fix_node_configs.sh" ]; then
  bash "$SELFDIR/fix_node_configs.sh"
else
  echo "  WARN: fix_node_configs.sh not found next to this script — run it manually."
fi

echo
echo "== acl tooling present? (enforced arm needs setfacl) =="
command -v setfacl >/dev/null && echo "  setfacl OK" || echo "  MISSING: sudo apt-get install -y acl"

echo
echo "DONE. Next (as $DESKTOP_USER, in a NEW shell so group membership applies):"
echo "  ~/jwclone/jwrun/run_one.sh \"<task_0_team dir>\" --arm enforced"
