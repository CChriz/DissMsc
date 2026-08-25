#!/usr/bin/env bash
# apply_specsplit.sh <task> [--root DIR] [--dry-run]
# S5 spec split, on top of enforced base ACLs (run AFTER configure + leader_acl):
#  - installs spec/p_spec.md (planner view) + spec/v_spec.md (full), REMOVES spec/spec.md
#  - ACLs: p_spec r for jw_cpool1,2 + jw_leader; --- for cpool7,8,9
#          v_spec r for jw_cpool7,8;            --- for cpool1,2,9 AND jw_leader
#    (leader must NOT read v_spec — it would become a full-knowledge relay)
#  - replaces spec-duplicating workspace docs with the planner-dose version
#    (spec6: protocol_spec.txt, crypto1: CRYPTO_SPEC.md, api1: compat_matrix.md,
#     p5: corpus/audit_policy.txt) — the in-repo doc is the stale/incomplete one
#  - GATE: ablated canaries absent from p_spec+brief(+workspace, distinctive ones),
#    present in v_spec; ACL readback; spec.md gone. exit 1 aborts the run.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT=/srv/jwteam_clone/shared/run_current
TASK="${1:-}"; shift 2>/dev/null || true
DRY=0
while [ $# -gt 0 ]; do case "$1" in
  --root) ROOT="$2"; shift 2;; --dry-run) DRY=1; shift;;
  *) echo "unknown: $1" >&2; exit 2;; esac; done
SP="$HERE/specs/$TASK"
[ -f "$SP/p_spec.md" ] && [ -f "$SP/v_spec.md" ] || { echo "ERROR: no spec pair for $TASK" >&2; exit 2; }
SD="$ROOT/spec"
[ -d "$SD" ] || [ "$DRY" = 1 ] || { echo "ERROR: no spec dir at $SD" >&2; exit 2; }

declare -A WSDOC=( [spec6]=protocol_spec.txt [crypto1]=CRYPTO_SPEC.md \
                   [api1]=compat_matrix.md [p5]=corpus/audit_policy.txt )

if [ "$DRY" = 1 ]; then
  echo "DRY: install p_spec.md+v_spec.md -> $SD, rm spec.md, ACLs, wsdoc=${WSDOC[$TASK]:-none}"
  exit 0
fi
sudo cp "$SP/p_spec.md" "$SD/p_spec.md" || exit 1
sudo cp "$SP/v_spec.md" "$SD/v_spec.md" || exit 1
sudo rm -f "$SD/spec.md" || exit 1
sudo chown cz776:jw_cteam "$SD/p_spec.md" "$SD/v_spec.md"
sudo chmod 640 "$SD/p_spec.md" "$SD/v_spec.md"
# p_spec: planners + leader; deny verifiers + generic
for u in jw_cpool1 jw_cpool2 jw_leader; do sudo setfacl -m "u:$u:r" "$SD/p_spec.md" || exit 1; done
for u in jw_cpool7 jw_cpool8 jw_cpool9; do sudo setfacl -m "u:$u:---" "$SD/p_spec.md" || exit 1; done
# v_spec: verifiers only; deny planners + generic + LEADER
for u in jw_cpool7 jw_cpool8; do sudo setfacl -m "u:$u:r" "$SD/v_spec.md" || exit 1; done
for u in jw_cpool1 jw_cpool2 jw_cpool9 jw_leader; do sudo setfacl -m "u:$u:---" "$SD/v_spec.md" || exit 1; done
# executors keep baseline no-spec; generic (cpool9) denied on both above
# dose-aligned brief (7 tasks have one; others keep the bundle brief)
if [ -f "$SP/brief.md" ]; then
  sudo cp "$SP/brief.md" "$ROOT/brief.md" || exit 1
  echo "  installed dose-aligned brief.md"
fi

# spec DIR: traverse-only for members (no listing — personas name the exact path;
# prevents filename-based disclosure of the other role's spec)
for u in jw_cpool1 jw_cpool2 jw_cpool7 jw_cpool8 jw_cpool9; do sudo setfacl -m "u:$u:--x" "$SD" || exit 1; done

# workspace de-dup
if [ -n "${WSDOC[$TASK]:-}" ] && [ -e "$ROOT/workspace/${WSDOC[$TASK]}" ]; then
  sudo cp "$SP/p_spec.md" "$ROOT/workspace/${WSDOC[$TASK]}" || exit 1
  echo "  replaced workspace/${WSDOC[$TASK]} with planner-dose version"
fi

# ---- GATE (python: fact_map-driven canary + ACL assertions) -----------------
python3 - "$HERE/fact_map.json" "$TASK" "$ROOT" <<'PYEOF' || { echo "SPECSPLIT GATE FAILED" >&2; exit 1; }
import io, json, os, subprocess, sys
fm = json.load(io.open(sys.argv[1], encoding="utf-8"))
task, root = sys.argv[2], sys.argv[3]
ent = fm[task]
p = io.open(os.path.join(root, "spec", "p_spec.md"), encoding="utf-8", errors="replace").read()
v = io.open(os.path.join(root, "spec", "v_spec.md"), encoding="utf-8", errors="replace").read()
try:
    b = io.open(os.path.join(root, "brief.md"), encoding="utf-8", errors="replace").read()
except Exception:
    b = ""
fail = 0
for u in ent["ablated"]:
    key = u["canary"]  # verbatim v_spec substring (validated offline)
    if key in p:
        print(f"GATE: canary {key!r} present in p_spec"); fail = 1
    if key not in v:
        print(f"GATE: canary {key!r} MISSING from v_spec"); fail = 1
    if key in b:
        print(f"GATE: canary {key!r} present in brief.md"); fail = 1
if os.path.exists(os.path.join(root, "spec", "spec.md")):
    print("GATE: spec.md still present"); fail = 1
def eff(uid, path):
    out = subprocess.run(["sudo", "getfacl", "-p", path], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith(f"user:{uid}:"):
            return line.split(":")[2]
    return ""
ps, vs = os.path.join(root, "spec", "p_spec.md"), os.path.join(root, "spec", "v_spec.md")
for uid, path, want in [("jw_cpool1", ps, "r"), ("jw_leader", ps, "r"), ("jw_cpool7", ps, "-"),
                        ("jw_cpool7", vs, "r"), ("jw_leader", vs, "-"), ("jw_cpool1", vs, "-"),
                        ("jw_cpool9", vs, "-")]:
    e = eff(uid, path)
    ok = ("r" in e) if want == "r" else ("r" not in e)
    if not ok:
        print(f"GATE: ACL {uid} on {os.path.basename(path)} = {e!r}, want {want}"); fail = 1
print("gate:", "PASS" if fail == 0 else "FAIL")
sys.exit(fail)
PYEOF
echo "specsplit applied+verified: task=$TASK"
