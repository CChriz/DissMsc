#!/usr/bin/env bash
# apply_split.sh <task> <open|closed> [--root DIR] [--dry-run]
#
# Scenario-4 complementary-access delta: on top of the enforced baseline
# (configure_task_pool --acls must have run first), refine the exec-band's
# workspace rwx into two ownership zones per s4/maps/<task>.split.json.
#   Zone A owners: jw_cpool4 jw_cpool5 (executor1, executor2)
#   Zone B owners: jw_cpool6 jw_cpool9 (executor3, fullstack1)
# dose open   -> non-owner side keeps rX on the other zone
# dose closed -> non-owner side gets --- on the other zone
# shared_rwx  -> all four rwX;  ro_all -> all four rX (also enforces spec
# do-not-modify files);  stubs -> pre-created empty owner-ACL'd files.
# Additionally strips fullstack1's baseline spec rX (S4 default; skip with
# JW_S4_KEEP_GENERIC_SPEC=1). Planners/verifiers/leader untouched.
# HARD-VERIFIES every applied (uid,path) and exits 1 on mismatch so the
# run_team hook aborts rather than run a soft split.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT=/srv/jwteam_clone/shared/run_current
TASK="${1:-}"; DOSE="${2:-}"; shift 2 2>/dev/null || true
DRY=0
while [ $# -gt 0 ]; do case "$1" in
  --root) ROOT="$2"; shift 2;; --dry-run) DRY=1; shift;;
  *) echo "unknown: $1" >&2; exit 2;; esac; done
case "$DOSE" in open|closed) : ;; *) echo "usage: $0 <task> <open|closed> [--root DIR] [--dry-run]" >&2; exit 2;; esac
MAP="$HERE/maps/${TASK}.split.json"
[ -f "$MAP" ] || { echo "ERROR: no split map $MAP" >&2; exit 2; }
W="$ROOT/workspace"
[ -d "$W" ] || { echo "ERROR: no workspace at $W" >&2; exit 2; }

# Flatten JSON -> "OP<TAB>path" directives (paths relative to workspace)
DIRECTIVES="$(python3 - "$MAP" <<'PYEOF'
import json, sys
m = json.load(open(sys.argv[1]))
for s in m.get("stubs", []):
    print("STUB%s\t%s" % (s["zone"], s["path"]))
for p in m["zoneA"]["paths"]:
    print("ZONEA\t%s" % p)
for p in m["zoneB"]["paths"]:
    print("ZONEB\t%s" % p)
for p in m.get("shared_rwx", []):
    print("SHARED\t%s" % p)
for p in m.get("ro_all", []):
    print("RO\t%s" % p)
PYEOF
)" || { echo "ERROR: split map parse failed" >&2; exit 2; }

A_UIDS="jw_cpool4 jw_cpool5"
B_UIDS="jw_cpool6 jw_cpool9"
ALL_UIDS="$A_UIDS $B_UIDS"
NONOWNER_PERM="rX"; [ "$DOSE" = closed ] && NONOWNER_PERM="-"
VERIFY=()   # "uid|path|expect" expect in {w, r, none}

facl(){ # facl <perm> <uid> <path>   perm in rwX|rX|-
  local perm="$1" uid="$2" p="$3" spec
  case "$perm" in rwX) spec="u:$uid:rwX";; rX) spec="u:$uid:rX";; -) spec="u:$uid:---";; esac
  if [ "$DRY" = 1 ]; then echo "  SETFACL $spec $p"; return 0; fi
  sudo setfacl -R -m "$spec" "$p" || { echo "  setfacl FAILED $spec $p" >&2; return 1; }
  if [ -d "$p" ]; then
    sudo setfacl -R -d -m "$spec" "$p" || { echo "  setfacl(default) FAILED $spec $p" >&2; return 1; }
  fi
  case "$perm" in rwX) VERIFY+=("$uid|$p|w");; rX) VERIFY+=("$uid|$p|r");; -) VERIFY+=("$uid|$p|none");; esac
}

echo "== apply_split: task=$TASK dose=$DOSE root=$ROOT dry=$DRY =="
fail=0
while IFS=$'\t' read -r op rel; do
  [ -n "$op" ] || continue
  p="$W/$rel"
  case "$op" in
    STUBA|STUBB)
      if [ ! -e "$p" ]; then
        if [ "$DRY" = 1 ]; then echo "  STUB create $p"; else { sudo touch "$p" && sudo chown cz776:jw_cteam "$p" && sudo chmod 660 "$p"; } || fail=1; fi
      fi ;;
  esac
done <<< "$DIRECTIVES"
while IFS=$'\t' read -r op rel; do
  [ -n "$op" ] || continue
  p="$W/$rel"
  case "$op" in
    STUBA) p="$W/$rel"; for u in $A_UIDS; do facl rwX "$u" "$p" || fail=1; done
           for u in $B_UIDS; do facl "$NONOWNER_PERM" "$u" "$p" || fail=1; done ;;
    STUBB) for u in $B_UIDS; do facl rwX "$u" "$p" || fail=1; done
           for u in $A_UIDS; do facl "$NONOWNER_PERM" "$u" "$p" || fail=1; done ;;
    ZONEA) [ -e "$p" ] || { echo "  MISSING zone path $p" >&2; fail=1; continue; }
           for u in $A_UIDS; do facl rwX "$u" "$p" || fail=1; done
           for u in $B_UIDS; do facl "$NONOWNER_PERM" "$u" "$p" || fail=1; done ;;
    ZONEB) [ -e "$p" ] || { echo "  MISSING zone path $p" >&2; fail=1; continue; }
           for u in $B_UIDS; do facl rwX "$u" "$p" || fail=1; done
           for u in $A_UIDS; do facl "$NONOWNER_PERM" "$u" "$p" || fail=1; done ;;
    SHARED) [ -e "$p" ] || { echo "  MISSING shared path $p" >&2; fail=1; continue; }
           for u in $ALL_UIDS; do facl rwX "$u" "$p" || fail=1; done ;;
    RO)    [ -e "$p" ] || { echo "  MISSING ro path $p" >&2; fail=1; continue; }
           for u in $ALL_UIDS; do facl rX "$u" "$p" || fail=1; done ;;
  esac
done <<< "$DIRECTIVES"

# workspace ROOT default: new root-level files are shared scratch for all four
if [ "$DRY" = 1 ]; then echo "  SETFACL(default,root) all-four rwX $W"
else
  for u in $ALL_UIDS; do sudo setfacl -d -m "u:$u:rwX" "$W" || fail=1; done
fi

# S4 default: strip generic (fullstack1) baseline spec read so requirements flow
# through planner relay + seams. Skip with JW_S4_KEEP_GENERIC_SPEC=1.
if [ "${JW_S4_KEEP_GENERIC_SPEC:-0}" != 1 ] && [ -d "$ROOT/spec" ]; then
  if [ "$DRY" = 1 ]; then echo "  SETFACL u:jw_cpool9:--- $ROOT/spec"
  else
    sudo setfacl -R -m u:jw_cpool9:--- "$ROOT/spec" || fail=1
    sudo setfacl -R -d -m u:jw_cpool9:--- "$ROOT/spec" || fail=1
    VERIFY+=("jw_cpool9|$ROOT/spec|none")
  fi
fi

# ---- HARD VERIFY ------------------------------------------------------------
if [ "$DRY" = 0 ]; then
  for v in "${VERIFY[@]}"; do
    uid="${v%%|*}"; rest="${v#*|}"; p="${rest%|*}"; expect="${rest##*|}"
    eff="$(sudo getfacl -p "$p" 2>/dev/null | awk -F: -v U="$uid" '$1=="user" && $2==U {print $3; exit}')"
    ok=0
    case "$expect" in
      w)    case "$eff" in *w*) ok=1;; esac ;;
      r)    case "$eff" in *r*) case "$eff" in *w*) ok=0;; *) ok=1;; esac ;; esac ;;
      none) [ "$eff" = "---" ] && ok=1 ;;
    esac
    if [ "$ok" != 1 ]; then
      echo "  VERIFY FAIL: $uid on $p = '${eff:-MISSING}' (expected $expect)" >&2; fail=1
    fi
  done
  [ "$fail" = 0 ] || { echo "SPLIT VERIFY FAILED — aborting (run would be unsplit/soft)" >&2; exit 1; }
  echo "split VERIFIED: ${#VERIFY[@]} (uid,path) assertions hold (task=$TASK dose=$DOSE)"
else
  [ "$fail" = 0 ] || exit 1
fi
