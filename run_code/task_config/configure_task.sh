#!/usr/bin/env bash
# configure_task.sh — auto-configure the run_current resource root from a task folder.
#
# Usage:
#   ./configure_task.sh <task_team_folder> [--acls] [--root DIR]
#
# Example:
#   ./configure_task.sh "/mnt/c/Users/cz776/Downloads/000000.NEWEVALS/taskxteam/d6_0_team"
#   ./configure_task.sh ".../d6_0_team" --acls          # also apply pre-run role ACLs
#
# Generic task format expected (discovered from the 10 examples):
#   <task>_0_team/<TASKNAME>(_|__)seed_0/{ spec.md, brief.md, workspace/ }
#
# What it does:
#   1. locate the single inner task dir (handles _seed_0 and __seed_0)
#   2. validate spec.md + brief.md + workspace/ are present
#   3. wipe + rebuild /srv/jwteam_clone/shared/run_current with spec/ brief.md workspace/ reports/ messages/
#   4. copy task files in; fix ownership (cz776:jw_cteam) + perms (2770)
#   5. reset the shared DB
#   6. optional: apply the per-role pre-run ACLs (--acls), then verify
set -euo pipefail

# ---- pinned identities (match the role->node pin) ----
P=jw_cnode1   # planner
E=jw_cnode2   # executor
V=jw_cnode3   # verifier
GRP=jw_cteam
DB=/srv/jwteam_clone/shared/team_shared.db
ROOT=/srv/jwteam_clone/shared/run_current
DO_ACLS=0

# ---- parse args ----
TASK_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --acls) DO_ACLS=1; shift;;
    --root) ROOT="$2"; shift 2;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) TASK_DIR="$1"; shift;;
  esac
done
[ -n "$TASK_DIR" ] || { echo "usage: $0 <task_team_folder> [--acls] [--root DIR]" >&2; exit 2; }
[ -d "$TASK_DIR" ] || { echo "ERROR: not a directory: $TASK_DIR" >&2; exit 1; }

echo "== configure_task =="
echo "task folder : $TASK_DIR"
echo "resource root: $ROOT"
echo "apply ACLs  : $([ $DO_ACLS = 1 ] && echo yes || echo no)"

# ---- 1. locate the single inner task dir ----
shopt -s nullglob
inner_dirs=( "$TASK_DIR"/*/ )
shopt -u nullglob
if [ "${#inner_dirs[@]}" -ne 1 ]; then
  echo "ERROR: expected exactly ONE inner task dir under $TASK_DIR, found ${#inner_dirs[@]}:" >&2
  printf '   %s\n' "${inner_dirs[@]}" >&2
  exit 1
fi
SRC="${inner_dirs[0]%/}"
echo "inner task  : $(basename "$SRC")"

# ---- 2. validate the generic format ----
miss=0
[ -f "$SRC/spec.md" ]      || { echo "  MISSING: spec.md"  >&2; miss=1; }
[ -f "$SRC/brief.md" ]     || { echo "  MISSING: brief.md" >&2; miss=1; }
[ -d "$SRC/workspace" ]    || { echo "  MISSING: workspace/" >&2; miss=1; }
[ "$miss" = 0 ] || { echo "ERROR: task folder does not match the expected format." >&2; exit 1; }
ws_items=$(find "$SRC/workspace" -mindepth 1 -maxdepth 1 | wc -l)
echo "validated   : spec.md + brief.md + workspace/ ($ws_items top-level items)"

# ---- 3. stop any running team, rebuild the resource root ----
pkill -9 -f jiuwenswarm 2>/dev/null || true
pkill -9 -f a2x-registry 2>/dev/null || true
sleep 1

# ---- 3b. PURGE all past-run state so NO prior-run data is accessible to agents ----
#      (anti-cheat: stops an agent reading a previous run's workspace/messages/checkpoints;
#       also guarantees determinism). Preserves each home's .jiuwenswarm/config/.
for n in 1 2 3; do
  H="/srv/jwteam_clone/cnode$n"
  sudo rm -rf "$H/.jiuwenswarm/.agent_teams" \
              "$H/.jiuwenswarm/agent/.checkpoint" \
              "$H/.jiuwenswarm/agent/sessions" \
              "$H/.a2x_registry_client" \
              "$H/.team" \
              "$H/.openjiuwen" 2>/dev/null || true
done
# Purge the ACTIVE leader home (default = predefined; JW_LEADER_HOME = dynamic profile).
LEADER_HOME="${JW_LEADER_HOME:-/home/cz776/jwclone/leader_home}"
sudo rm -rf "$LEADER_HOME/.jiuwenswarm/.agent_teams" \
            "$LEADER_HOME/.jiuwenswarm/.openjiuwen" \
            "$LEADER_HOME/.openjiuwen" 2>/dev/null || true
# clear stale registry service registrations so no cross-run blank-teammate adoption
rm -rf /home/cz776/.a2x_registry/database/team_pool 2>/dev/null || true
echo "purged      : node+leader .agent_teams/checkpoints/sessions + registry team_pool (no past-run state)"

# ---- 3c. isolate node homes so NO agent can read another agent's private workspace
#      (verifier grading the executor's private files = false pass). Base 700 blocks the
#      other node users; an ACL keeps the HARNESS (cz776) able to read the team logs
#      (wait_for_done) and archive. Nodes still reach the shared DB + run_current via the
#      jw_cteam group / per-uid ACLs (separate paths, unaffected).
for n in 1 2 3; do
  H="/srv/jwteam_clone/cnode$n"
  sudo chmod 700 "$H" 2>/dev/null || true
  sudo setfacl -R  -m u:cz776:rX "$H" 2>/dev/null || true   # existing content
  sudo setfacl -R -d -m u:cz776:rX "$H" 2>/dev/null || true   # per-run content (logs, workspaces)
done
echo "isolated    : node homes owner-only + cz776:rX (no cross-node reads; harness reads logs)"

sudo rm -rf "$ROOT"
sudo mkdir -p "$ROOT/spec" "$ROOT/workspace" "$ROOT/reports" "$ROOT/messages"

# ---- 4. copy task files in ----
sudo cp "$SRC/spec.md"  "$ROOT/spec/spec.md"
sudo cp "$SRC/brief.md" "$ROOT/brief.md"
# copy entire workspace contents (preserves nested dirs: tests/, corpus/, app/, data/, mqueue/, ...)
sudo cp -a "$SRC/workspace/." "$ROOT/workspace/"

# ---- ownership + perms (cp from /mnt/c lands as root) ----
sudo chown -R cz776:"$GRP" "$ROOT"
sudo chmod -R 2770 "$ROOT"
echo "populated   : $ROOT  (owner cz776:$GRP, mode 2770)"

# ---- 5. reset the shared DB ----
sudo rm -f "$DB" "$DB-wal" "$DB-shm" "$DB-journal"
sudo touch "$DB"
sudo chgrp "$GRP" "$DB"
sudo chmod 664 "$DB"
echo "db reset    : $DB"

# ---- 6. optional ACLs (pre-run, fixed uids — pinning guarantees the mapping) ----
if [ "$DO_ACLS" = 1 ]; then
  R="$ROOT"
  sudo setfacl -b "$R/spec"
  sudo setfacl -m u:$P:rx,u:$V:rx,u:$E:---,g::---,o::--- "$R/spec"
  sudo setfacl -b "$R/spec/spec.md"
  sudo setfacl -m u:$P:r,u:$V:r,u:$E:---,g::---,o::--- "$R/spec/spec.md"

  sudo setfacl -b "$R/brief.md"
  sudo setfacl -m u:$P:r,u:$E:r,u:$V:---,g::---,o::--- "$R/brief.md"

  sudo setfacl -R -b "$R/workspace"
  sudo setfacl -R -m   u:$E:rwx,u:$V:rx,u:$P:---,g::---,o::--- "$R/workspace"
  sudo setfacl -R -d -m u:$E:rwx,u:$V:rx,u:$P:--- "$R/workspace"

  sudo setfacl -R -b "$R/reports"
  sudo setfacl -R -m   u:$E:rwx,u:$V:rx,u:$P:---,g::---,o::--- "$R/reports"
  sudo setfacl -R -d -m u:$E:rwx,u:$V:rx,u:$P:--- "$R/reports"

  sudo setfacl -R -b "$R/messages"
  sudo setfacl -R -m   u:$P:rx,u:$E:rx,u:$V:rx,g::---,o::--- "$R/messages"
  sudo setfacl -R -d -m u:$P:rx,u:$E:rx,u:$V:rx "$R/messages"

  sudo touch "$R/attestation.json"
  sudo setfacl -b "$R/attestation.json"
  sudo setfacl -m u:$V:rw,u:$P:r,u:$E:r,g::---,o::--- "$R/attestation.json"

  # lock down the ROOT itself: nodes may TRAVERSE (--x) to reach their permitted
  # subdirs, but cannot create/delete files at the root. This closes the group-writable
  # scratch-space channel (previously agents could write output/ or stray deliverables
  # at run_current root). The verifier still writes attestation.json because that is a
  # MODIFY of a pre-existing file via the file's own rw ACL, which does not require
  # root-directory write. Validated: attestation write + subdir ops + traverse all OK.
  sudo setfacl -m u:$P:--x,u:$E:--x,u:$V:--x,g::---,o::--- "$R"

  echo "acls applied: enforced arm"
  echo "  spec  (executor must be ---):"; sudo getfacl -p "$R/spec" 2>/dev/null | grep -E "^user:$E|^other"
  echo "  brief (verifier must be ---):"; sudo getfacl -p "$R/brief.md" 2>/dev/null | grep -E "^user:$V|^other"
  echo "  workspace (planner ---):";      sudo getfacl -p "$R/workspace" 2>/dev/null | grep -E "^user:$P|^default:user:$P"
else
  echo "acls        : SKIPPED (prompt-only arm). Re-run with --acls for the enforced arm."
fi

echo
echo "== layout =="
ls -R "$ROOT" | head -40
echo
echo "DONE. Resource root ready at $ROOT"
echo "Next: launch registry + nodes + leader, then the thin D-prompt."
