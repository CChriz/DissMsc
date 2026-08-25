#!/usr/bin/env bash
# configure_task_dynamic.sh <task_team_folder> [--root DIR]
#
# NO-SUDO task setup for the DYNAMIC (prompt-only) pool. run_current lives under the
# group-writable /srv/jwteam_clone/shared (mode 2770, group jw_cteam, setgid), and cz776
# is a jw_cteam member, so the resource root + DB can be rebuilt without root. This is the
# dynamic-arm counterpart to configure_task.sh; it deliberately SKIPS the enforced-arm
# per-uid ACLs and the jw_cnode home isolation (dynamic runs are prompt-only, and the pool
# nodes run as cz776). Task layout matches configure_task.sh so archiving/analysis are unchanged.
set -euo pipefail

GRP=jw_cteam
DB=/srv/jwteam_clone/shared/team_shared.db
ROOT=/srv/jwteam_clone/shared/run_current
LEADER_HOME="${JW_LEADER_HOME:-/home/cz776/jwclone/leader_home_dynamic}"
POOL=/home/cz776/jwclone/pool

TASK_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2;;
    -*) echo "unknown option: $1" >&2; exit 2;;
    *) TASK_DIR="$1"; shift;;
  esac
done
[ -n "$TASK_DIR" ] && [ -d "$TASK_DIR" ] || { echo "usage: $0 <task_team_folder> [--root DIR]" >&2; exit 2; }

echo "== configure_task_dynamic (no-sudo, prompt-only) =="
echo "task folder : $TASK_DIR"
echo "resource root: $ROOT"

# ---- 1. locate the single inner task dir ----
shopt -s nullglob; inner=( "$TASK_DIR"/*/ ); shopt -u nullglob
[ "${#inner[@]}" -eq 1 ] || { echo "ERROR: expected exactly ONE inner task dir under $TASK_DIR, found ${#inner[@]}" >&2; exit 1; }
SRC="${inner[0]%/}"
echo "inner task  : $(basename "$SRC")"

# ---- 2. validate the generic format ----
[ -f "$SRC/spec.md" ] && [ -f "$SRC/brief.md" ] && [ -d "$SRC/workspace" ] \
  || { echo "ERROR: task folder must contain spec.md + brief.md + workspace/" >&2; exit 1; }

# ---- 3. stop any running (cz776) stack ----
pkill -9 -f jiuwenswarm 2>/dev/null || true
pkill -9 -f a2x-registry 2>/dev/null || true
sleep 1

# ---- 3b. purge past-run state (all cz776-owned; anti-cheat + determinism) ----
rm -rf "$LEADER_HOME/.jiuwenswarm/.agent_teams" \
       "$LEADER_HOME/.jiuwenswarm/.openjiuwen" \
       "$LEADER_HOME/.openjiuwen" 2>/dev/null || true
rm -rf "$POOL"/node*/.jiuwenswarm/.agent_teams \
       "$POOL"/node*/.jiuwenswarm/.openjiuwen \
       "$POOL"/node*/.jiuwenswarm/agent/.checkpoint \
       "$POOL"/node*/.jiuwenswarm/agent/sessions \
       "$POOL"/node*/.a2x_registry_client \
       "$POOL"/node*/.team 2>/dev/null || true
rm -rf /home/cz776/.a2x_registry/database/team_pool 2>/dev/null || true
echo "purged      : dynamic leader + pool nodes .agent_teams/checkpoints/sessions + registry team_pool"

# ---- 4. rebuild run_current (group-writable shared dir; no sudo) ----
# cz776 owns run_current's own dirs, but a prior ENFORCED run leaves agent-created
# subdirs owned by jw_cnode users with restrictive ACLs that block a no-sudo rm. So:
# try rm; if anything survives, MOVE the tree aside (rename only needs write on the
# group-writable shared/ parent) so the fresh mkdir always succeeds.
rm -rf "$ROOT" 2>/dev/null || true
if [ -e "$ROOT" ]; then
  if mv "$ROOT" "${ROOT}.stale.$$" 2>/dev/null; then
    echo "note: prior run_current not fully removable (enforced-run leftovers); moved aside -> ${ROOT}.stale.$$" >&2
  else
    echo "ERROR: cannot clear or move $ROOT — run the sudo configure_task.sh once to reset it." >&2
    exit 1
  fi
fi
mkdir -p "$ROOT/spec" "$ROOT/workspace" "$ROOT/reports" "$ROOT/messages"
cp "$SRC/spec.md"  "$ROOT/spec/spec.md"
cp "$SRC/brief.md" "$ROOT/brief.md"
cp -a "$SRC/workspace/." "$ROOT/workspace/"
chgrp -R "$GRP" "$ROOT" 2>/dev/null || true
chmod -R 2770 "$ROOT" 2>/dev/null || true
echo "populated   : $ROOT (group $GRP, mode 2770)"

# ---- 5. reset the shared DB ----
rm -f "$DB" "$DB-wal" "$DB-shm" "$DB-journal" 2>/dev/null || true
: > "$DB"
chgrp "$GRP" "$DB" 2>/dev/null || true
chmod 664 "$DB"
echo "db reset    : $DB"

echo
echo "== layout =="
ls -R "$ROOT" | head -40
echo
echo "DONE (dynamic, no ACLs). Resource root ready at $ROOT"
