#!/usr/bin/env bash
# leader_acl.sh — per-SCENARIO ACL profile for the jw_leader OS user on run_current.
# Run AFTER configure_task_pool.sh --acls (that script rebuilds resource ACLs).
# run_team.sh calls this automatically when JW_LEADER_USER is set (profile from
# JW_LEADER_ACL, default: full).
#
#   Usage: leader_acl.sh <full|informed|coordination|none> [--root DIR] [--dry-run]
#
# Profiles (data-plane only — the coordination plane is ALWAYS granted, because a
# leader that cannot reach the shared task DB cannot create_task and the run is dead):
#   full          rwX everywhere            = today's exempt/cz776-owner behavior
#   informed      read-only everywhere      = observer-orchestrator (sees spec+workspace)
#   coordination  brief+attestation r only  = delegation-contract boundary
#                 (spec/workspace/reports ---)
#   none          all data resources ---    = leader-blockage probe (scenario 3 variant)
#
# Always granted regardless of profile:
#   team_shared.db rw + its dir rwx (sqlite WAL/SHM), messages rX (except none: ---).
set -euo pipefail

U=jw_leader
ROOT=/srv/jwteam_clone/shared/run_current
DB=/srv/jwteam_clone/shared/team_shared.db
DRY=0
PROFILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --root) ROOT="$2"; shift 2;;
    --dry-run) DRY=1; shift;;
    full|informed|coordination|none) PROFILE="$1"; shift;;
    *) echo "usage: $0 <full|informed|coordination|none> [--root DIR] [--dry-run]" >&2; exit 2;;
  esac
done
[ -n "$PROFILE" ] || { echo "usage: $0 <full|informed|coordination|none> [--root DIR] [--dry-run]" >&2; exit 2; }
if [ $DRY = 0 ]; then
  getent passwd "$U" >/dev/null || { echo "ERROR: user $U missing — run: sudo bash ~/jwclone/setup_leader_system.sh" >&2; exit 1; }
fi
[ -d "$ROOT" ] || { echo "ERROR: resource root missing: $ROOT" >&2; exit 1; }

case "$PROFILE" in
  full)          SPEC=rX;  BRIEF=r;   WS=rwX; REPORTS=rwX; ATT=rw;  MSG=rX;  ROOTP=rwx;;
  informed)      SPEC=rX;  BRIEF=r;   WS=rX;  REPORTS=rX;  ATT=r;   MSG=rX;  ROOTP=r-x;;
  coordination)  SPEC=---; BRIEF=r;   WS=---; REPORTS=---; ATT=r;   MSG=rX;  ROOTP=--x;;
  none)          SPEC=---; BRIEF=---; WS=---; REPORTS=---; ATT=---; MSG=---; ROOTP=--x;;
esac

grant() {  # grant <acl-spec> <path...>  (skips missing paths; -R for dirs + default ACL)
  local spec="$1"; shift
  local p
  for p in "$@"; do
    [ -e "$p" ] || continue
    if [ $DRY = 1 ]; then
      echo "  DRY: setfacl -R -m u:$U:$spec $p"
      if [ -d "$p" ]; then echo "  DRY: setfacl -R -d -m u:$U:$spec $p"; fi
    else
      sudo setfacl -R -m "u:$U:$spec" "$p"
      if [ -d "$p" ]; then sudo setfacl -R -d -m "u:$U:$spec" "$p"; fi
    fi
  done
}

echo "== leader_acl: profile=$PROFILE root=$ROOT user=$U =="
# root: traversal level only, non-recursive, no default entry (children set explicitly;
# attestation.json is created later by a verifier — give ROOT a default entry so the
# new file inherits the leader's attestation permission)
if [ $DRY = 1 ]; then
  echo "  DRY: setfacl -m u:$U:$ROOTP $ROOT"
  echo "  DRY: setfacl -d -m u:$U:$ATT $ROOT"
else
  sudo setfacl -m "u:$U:$ROOTP" "$ROOT"
  sudo setfacl -d -m "u:$U:$ATT" "$ROOT"
fi
grant "$SPEC"    "$ROOT/spec"
grant "$BRIEF"   "$ROOT/brief.md"
grant "$WS"      "$ROOT/workspace"
grant "$REPORTS" "$ROOT/reports"
grant "$ATT"     "$ROOT/attestation.json"
grant "$MSG"     "$ROOT/messages"

# coordination plane — always on (task board = sqlite; WAL/SHM need dir write)
if [ $DRY = 1 ]; then
  echo "  DRY: setfacl -m u:$U:rwx $(dirname "$DB")"
  echo "  DRY: setfacl -m u:$U:rw  $DB"
else
  sudo setfacl -m "u:$U:rwx" "$(dirname "$DB")"
  if [ -f "$DB" ]; then sudo setfacl -m "u:$U:rw" "$DB"; fi
fi
echo "== leader_acl: done =="
