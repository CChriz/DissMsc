#!/usr/bin/env bash
# configure_task_pool.sh <task_team_folder> [--acls] [--root DIR]
#
# Task setup for the 10-node OS-USER pool (jw_cpool1..10 @ /srv/jwteam_clone/pnodeK) —
# the dynamic-roster counterpart of configure_task.sh. Needs sudo (root) like the 3-agent
# path: purge crosses uids, and --acls applies the enforced arm.
#
# Role->uid layout (fixed; matches setup_pool_system.sh + JW_CATALOG_PINS):
#   PLANNERS  jw_cpool1-3   EXECUTORS jw_cpool4-6
#   VERIFIERS jw_cpool7-8   GENERIC   jw_cpool9-10   (generic = union of all role perms)
#
# Per-role enforced ACLs mirror configure_task.sh:
#   spec:        planners+verifiers+generic r  | executors ---
#   brief.md:    planners+executors+generic r  | verifiers ---
#   workspace:   executors+generic rwx | verifiers rx | planners ---
#   reports:     executors+generic rwx | verifiers rx | planners ---
#   messages:    all rx
#   attestation: verifiers+generic rw | planners+executors r
#   root:        all --x (traverse only; no scratch writes at run_current root)
set -euo pipefail

GRP=jw_cteam
DB=/srv/jwteam_clone/shared/team_shared.db
ROOT=/srv/jwteam_clone/shared/run_current
LEADER_HOME="${JW_LEADER_HOME:-/home/cz776/jwclone/leader_home_dynamic}"
DO_ACLS=0

P="u:jw_cpool1,u:jw_cpool2,u:jw_cpool3"          # planners
E="u:jw_cpool4,u:jw_cpool5,u:jw_cpool6"          # executors
V="u:jw_cpool7,u:jw_cpool8"                       # verifiers
G="u:jw_cpool9,u:jw_cpool10"                      # generic (union)

TASK_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --acls) DO_ACLS=1; shift;;
    --root) ROOT="$2"; shift 2;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) TASK_DIR="$1"; shift;;
  esac
done
[ -n "$TASK_DIR" ] && [ -d "$TASK_DIR" ] || { echo "usage: $0 <task_team_folder> [--acls] [--root DIR]" >&2; exit 2; }

echo "== configure_task_pool (OS-user pool) =="
echo "task folder : $TASK_DIR"
echo "resource root: $ROOT"
echo "apply ACLs  : $([ $DO_ACLS = 1 ] && echo yes || echo no)"

# ---- 1. locate + validate the inner task dir ----
shopt -s nullglob; inner=( "$TASK_DIR"/*/ ); shopt -u nullglob
[ "${#inner[@]}" -eq 1 ] || { echo "ERROR: expected exactly ONE inner task dir, found ${#inner[@]}" >&2; exit 1; }
SRC="${inner[0]%/}"
[ -f "$SRC/spec.md" ] && [ -f "$SRC/brief.md" ] && [ -d "$SRC/workspace" ] \
  || { echo "ERROR: task folder must contain spec.md + brief.md + workspace/" >&2; exit 1; }
echo "inner task  : $(basename "$SRC")"

# ---- 2. stop any running stack ----
# per-uid kills instead of root pkill: root pkill isn't in the NOPASSWD whitelist,
# but cz776 -> jw_* NOPASSWD:ALL is, and cz776 can signal its own processes directly.
pkill -9 -f jiuwenswarm 2>/dev/null || true
pkill -9 -f a2x-registry 2>/dev/null || true
for _u in jw_cpool1 jw_cpool2 jw_cpool3 jw_cpool4 jw_cpool5 jw_cpool6 jw_cpool7 jw_cpool8 jw_cpool9 jw_cpool10 jw_leader jw_cnode1 jw_cnode2 jw_cnode3; do
  sudo -n -u "$_u" pkill -9 -u "$_u" -f jiuwenswarm 2>/dev/null || true
done
sleep 1

# ---- 3. purge past-run state (anti-cheat + determinism; preserves config/) ----
for k in $(seq 1 10); do
  H="/srv/jwteam_clone/pnode$k"
  sudo rm -rf "$H/.jiuwenswarm/.agent_teams" \
              "$H/.jiuwenswarm/.openjiuwen" \
              "$H/.jiuwenswarm/agent/.checkpoint" \
              "$H/.jiuwenswarm/agent/sessions" \
              "$H/.a2x_registry_client" \
              "$H/.team" \
              "$H/.openjiuwen" 2>/dev/null || true
  sudo find "$H/logs/logs" -maxdepth 2 -name '*.log' -exec truncate -s 0 {} + 2>/dev/null || true
done
sudo rm -rf "$LEADER_HOME/.jiuwenswarm/.agent_teams" \
            "$LEADER_HOME/.jiuwenswarm/.openjiuwen" \
            "$LEADER_HOME/.openjiuwen" 2>/dev/null || true
rm -rf /home/cz776/.a2x_registry/database/team_pool 2>/dev/null || true
echo "purged      : pool homes + dynamic leader + registry team_pool"

# ---- 4. pool-home isolation: owner-only + harness read (same as cnodes) ----
for k in $(seq 1 10); do
  H="/srv/jwteam_clone/pnode$k"
  sudo chmod 700 "$H" 2>/dev/null || true
  sudo setfacl -R  -m u:cz776:rX "$H" 2>/dev/null || true
  sudo setfacl -R -d -m u:cz776:rX "$H" 2>/dev/null || true
done
echo "isolated    : pnode homes 700 + cz776:rX (no cross-node reads; harness reads logs)"

# ---- 5. rebuild run_current ----
sudo rm -rf "$ROOT"
# artifacts/skills/trajectories = LEADER scratch dirs it creates at runtime. A
# jw_leader leader (read-only root under the informed/blockage profile) can't
# create them → Errno 13 on boot. Pre-create them group-writable (2770, group
# jw_cteam ∋ jw_leader) so the leader writes INTO them via group perms (2026-08-08).
sudo mkdir -p "$ROOT/spec" "$ROOT/workspace" "$ROOT/reports" "$ROOT/messages" \
              "$ROOT/artifacts" "$ROOT/skills" "$ROOT/trajectories"
sudo cp "$SRC/spec.md"  "$ROOT/spec/spec.md"
sudo cp "$SRC/brief.md" "$ROOT/brief.md"
sudo cp -a "$SRC/workspace/." "$ROOT/workspace/"
sudo chown -R cz776:"$GRP" "$ROOT"
# dirs 2770, files 660: shipped files must NOT carry exec bits, or setfacl's
# capital-X (verifier read-only) degenerates to rx on them (2026-08-08).
# Executors still execute via their explicit rwx ACL; files they create are
# their own (they can chmod +x build outputs).
sudo find "$ROOT" -type d -exec chmod 2770 {} +
sudo find "$ROOT" -type f -exec chmod 660 {} +
echo "populated   : $ROOT (owner cz776:$GRP, dirs 2770 / files 660)"

# ---- 6. reset the shared DB ----
sudo rm -f "$DB" "$DB-wal" "$DB-shm" "$DB-journal"
sudo touch "$DB"; sudo chgrp "$GRP" "$DB"; sudo chmod 664 "$DB"
echo "db reset    : $DB"

# ---- 7. enforced-arm per-role ACLs (pool uids) ----
if [ "$DO_ACLS" = 1 ]; then
  R="$ROOT"
  grant(){ sudo setfacl "$@"; }   # thin wrapper for readability

  # whole spec/ tree, recursive + default ACLs (rX: read + dir-traverse only),
  # so ANY file under spec/ is covered — not just spec.md (2026-08-08)
  grant -R -b "$R/spec"
  grant -R -m   u:jw_cpool1:rX,u:jw_cpool2:rX,u:jw_cpool3:rX,u:jw_cpool7:rX,u:jw_cpool8:rX,u:jw_cpool9:rX,u:jw_cpool10:rX,u:jw_cpool4:---,u:jw_cpool5:---,u:jw_cpool6:---,g::---,o::--- "$R/spec"
  grant -R -d -m u:jw_cpool1:rX,u:jw_cpool2:rX,u:jw_cpool3:rX,u:jw_cpool7:rX,u:jw_cpool8:rX,u:jw_cpool9:rX,u:jw_cpool10:rX,u:jw_cpool4:---,u:jw_cpool5:---,u:jw_cpool6:---,g::---,o::--- "$R/spec"

  grant -b "$R/brief.md"
  grant -m u:jw_cpool1:r,u:jw_cpool2:r,u:jw_cpool3:r,u:jw_cpool4:r,u:jw_cpool5:r,u:jw_cpool6:r,u:jw_cpool9:r,u:jw_cpool10:r,u:jw_cpool7:---,u:jw_cpool8:---,g::---,o::--- "$R/brief.md"

  grant -R -b "$R/workspace"
  # verifier rX MUST be granted in a SEPARATE call BEFORE executor rwx: setfacl's
  # capital-X grants x if any entry IN THE SAME command carries x (2026-08-08)
  grant -R -m   u:jw_cpool7:rX,u:jw_cpool8:rX,u:jw_cpool1:---,u:jw_cpool2:---,u:jw_cpool3:---,g::---,o::--- "$R/workspace"
  grant -R -m   u:jw_cpool4:rwx,u:jw_cpool5:rwx,u:jw_cpool6:rwx,u:jw_cpool9:rwx,u:jw_cpool10:rwx,u:cz776:rwX "$R/workspace"
  # default ACLs must list ALL denied uids AND g::---/o::--- — an executor-created
  # file with missing entries falls back to the GROUP class (jw_cteam = everyone),
  # leaking run work-products to planners (found in pre-batch audit 2026-08-08)
  grant -R -d -m u:jw_cpool7:rX,u:jw_cpool8:rX,u:jw_cpool1:---,u:jw_cpool2:---,u:jw_cpool3:---,g::---,o::--- "$R/workspace"
  grant -R -d -m u:jw_cpool4:rwx,u:jw_cpool5:rwx,u:jw_cpool6:rwx,u:jw_cpool9:rwx,u:jw_cpool10:rwx,u:cz776:rwX "$R/workspace"

  grant -R -b "$R/reports"
  grant -R -m   u:jw_cpool7:rX,u:jw_cpool8:rX,u:jw_cpool1:---,u:jw_cpool2:---,u:jw_cpool3:---,g::---,o::--- "$R/reports"
  grant -R -m   u:jw_cpool4:rwx,u:jw_cpool5:rwx,u:jw_cpool6:rwx,u:jw_cpool9:rwx,u:jw_cpool10:rwx,u:cz776:rwX "$R/reports"
  grant -R -d -m u:jw_cpool7:rX,u:jw_cpool8:rX,u:jw_cpool1:---,u:jw_cpool2:---,u:jw_cpool3:---,g::---,o::--- "$R/reports"
  grant -R -d -m u:jw_cpool4:rwx,u:jw_cpool5:rwx,u:jw_cpool6:rwx,u:jw_cpool9:rwx,u:jw_cpool10:rwx,u:cz776:rwX "$R/reports"

  # messages: read+write for ALL roles (2026-08-08, per the 3-role capability
  # table — was rx; note substantive messaging travels via the team DB anyway)
  grant -R -b "$R/messages"
  grant -R -m   u:jw_cpool1:rwx,u:jw_cpool2:rwx,u:jw_cpool3:rwx,u:jw_cpool4:rwx,u:jw_cpool5:rwx,u:jw_cpool6:rwx,u:jw_cpool7:rwx,u:jw_cpool8:rwx,u:jw_cpool9:rwx,u:jw_cpool10:rwx,g::---,o::--- "$R/messages"
  grant -R -d -m u:jw_cpool1:rwx,u:jw_cpool2:rwx,u:jw_cpool3:rwx,u:jw_cpool4:rwx,u:jw_cpool5:rwx,u:jw_cpool6:rwx,u:jw_cpool7:rwx,u:jw_cpool8:rwx,u:jw_cpool9:rwx,u:jw_cpool10:rwx,g::---,o::--- "$R/messages"

  sudo touch "$R/attestation.json"
  sudo chown cz776:"$GRP" "$R/attestation.json"
  grant -b "$R/attestation.json"
  grant -m u:cz776:rw,u:jw_cpool7:rw,u:jw_cpool8:rw,u:jw_cpool9:rw,u:jw_cpool10:rw,u:jw_cpool1:r,u:jw_cpool2:r,u:jw_cpool3:r,u:jw_cpool4:r,u:jw_cpool5:r,u:jw_cpool6:r,g::---,o::--- "$R/attestation.json"

  # root: traverse only (no scratch writes at run_current root)
  grant -m u:jw_cpool1:--x,u:jw_cpool2:--x,u:jw_cpool3:--x,u:jw_cpool4:--x,u:jw_cpool5:--x,u:jw_cpool6:--x,u:jw_cpool7:--x,u:jw_cpool8:--x,u:jw_cpool9:--x,u:jw_cpool10:--x,g::---,o::--- "$R"

  echo "acls applied: enforced arm (pool uids)"
  echo "  spec (executor jw_cpool4 must be ---):"; sudo getfacl -p "$R/spec" 2>/dev/null | grep -E "^user:jw_cpool4|^other"
  echo "  brief (verifier jw_cpool7 must be ---):"; sudo getfacl -p "$R/brief.md" 2>/dev/null | grep -E "^user:jw_cpool7|^other"
  echo "  workspace (planner jw_cpool1 ---):"; sudo getfacl -p "$R/workspace" 2>/dev/null | grep -E "^user:jw_cpool1"
else
  echo "acls        : SKIPPED (prompt-only arm). Re-run with --acls for enforced."
fi

echo
echo "DONE. Resource root ready at $ROOT"
