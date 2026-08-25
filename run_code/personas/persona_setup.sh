#!/usr/bin/env bash
# persona_setup.sh <task_key> <stock|generated> [--specsplit]
#
# SINGLE authority for the OS-pool leader catalog personas
# (/srv/jwteam_clone/lnode/.jiuwenswarm/config/config.yaml, jw_leader-owned).
# Called PER TASK by the scenario batch runners, AFTER configure+scenario-hook,
# BEFORE launch. Idempotent: always resets from config.stock.yaml first.
#
#   arm generated : install personas_arm2.json specialist set for <task_key>
#                   (display name + profile only; member_name pins untouched;
#                    authority-probe clone/title preserved verbatim).
#   arm stock     : leave the stock role personas.
#   --specsplit   : (S5) after the arm is set, swap the spec path inside the
#                   planner/verifier personas: planner1/2 -> spec/p_spec.md,
#                   verifier1/2 -> spec/v_spec.md. Applied ON TOP of whichever
#                   arm, so ordering is correct for arm-2 (specialist text first,
#                   path swap second).
#
# Ordering contract (S5 x arm2): apply_personas(arm2) -> path swap, all here in
# one call, so s5's spec-path swap can never clobber the arm and vice-versa.
# This REPLACES s5_personas.sh's persona-swap role; s5 exec-deny stays separate.
set -uo pipefail
KEY="${1:-}"; ARM="${2:-}"; shift 2 2>/dev/null || true
SPECSPLIT=0; [ "${1:-}" = "--specsplit" ] && SPECSPLIT=1
case "$ARM" in stock|generated) ;; *) echo "usage: $0 <key> <stock|generated> [--specsplit]" >&2; exit 2;; esac
CFG="${JW_PERSONA_CFG:-/srv/jwteam_clone/lnode/.jiuwenswarm/config/config.yaml}"
STOCK="${CFG%/*}/config.stock.yaml"
APPLY=/mnt/c/Users/cz776/Downloads/benchmark7/personas/apply_personas.py
case "$CFG" in /srv/*) L="sudo -n -u jw_leader";; *) L="";; esac

$L test -f "$STOCK" || { echo "ERROR: no stock snapshot $STOCK (create from a clean lnode first)" >&2; exit 1; }

# 1. arm
if [ "$ARM" = generated ]; then
  $L python3 "$APPLY" "$KEY" --arm generated --config "$CFG" || { echo "persona_setup: apply_personas FAILED" >&2; exit 1; }
else
  $L cp "$STOCK" "$CFG"    # stock baseline
  $L rm -f /tmp/jw_roster.txt   # clear any arm-2 roster so stock runs stay clean
fi

# 2. optional S5 spec-path swap (on top of the arm)
if [ "$SPECSPLIT" = 1 ]; then
  $L python3 - "$CFG" <<'PYE' || { echo "persona_setup: specsplit swap FAILED" >&2; exit 1; }
import io, re, sys
p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()
def swap(s, member, newpath):
    pat = re.compile(r"(member_name:\s*['\"]?%s['\"]?.*?persona:\s*['\"])" % re.escape(member), re.S)
    m = pat.search(s)
    assert m, "no persona entry for " + member
    # replace spec/spec.md only within this member's persona scalar (to end of that item)
    start = m.end(1)
    end = s.find("member_name:", start)
    end = end if end != -1 else len(s)
    seg = s[start:end]
    assert "spec/spec.md" in seg, member + " persona lacks spec/spec.md"
    return s[:start] + seg.replace("spec/spec.md", newpath) + s[end:]
for mb in ("planner1", "planner2"):
    s = swap(s, mb, "spec/p_spec.md")
for mb in ("verifier1", "verifier2"):
    s = swap(s, mb, "spec/v_spec.md")
io.open(p, "w", encoding="utf-8").write(s)
print("  specsplit: planner->p_spec, verifier->v_spec")
PYE
fi
# 3. optional TEAM ROSTER (transactive-memory index): build member->specialist+
#    capability list, append to every teammate persona, and emit roster.txt for the
#    runner to fold into the leader kickoff. Only meaningful for the generated arm.
ROSTER="${JW_ROSTER:-1}"
if [ "$ARM" = generated ] && [ "$ROSTER" = 1 ]; then
  $L python3 - "$CFG" "$APPLY" "$KEY" "/tmp/jw_roster.txt" <<'PYE' || { echo "persona_setup: roster FAILED" >&2; exit 1; }
import io, json, re, sys
cfg, apply_py, key, rosterfile = sys.argv[1:5]
personas = json.loads(io.open(str(__import__("pathlib").Path(apply_py).parent / "personas_arm2.json"), encoding="utf-8").read())
team = personas[key]
MEMBERS = ["planner1","planner2","executor1","executor2","executor3","verifier1","verifier2","fullstack1"]
def cap(persona):
    m = re.search(r"Specialties:\s*([^.]*)", persona)
    if not m: return "general specialist"
    parts = [p.strip() for p in m.group(1).split(",") if p.strip()]
    return ", ".join(parts[:3])
lines = ["TEAM ROSTER — your teammates (call by the bracketed name via send_message(to_member_name=...)):"]
for m in MEMBERS:
    if m in team:
        lines.append("- %s [%s]: %s" % (m, team[m]["name"], cap(team[m]["persona"])))
roster = "\n".join(lines)
io.open(rosterfile, "w", encoding="utf-8").write(roster + "\n")
# append roster into each teammate persona scalar (before its closing quote)
s = io.open(cfg, encoding="utf-8").read()
esc = "\\n\\n" + roster.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
for m in MEMBERS:
    pat = re.compile(r'(member_name:\s*[\'"]?%s[\'"]?.*?persona:\s*")((?:[^"\\]|\\.)*)(")' % re.escape(m), re.S)
    def repl(g): return g.group(1) + g.group(2) + esc + g.group(3)
    s2, n = pat.subn(repl, s, count=1)
    if n: s = s2
io.open(cfg, "w", encoding="utf-8").write(s)
print("  roster: %d members listed, appended to personas + %s" % (len([m for m in MEMBERS if m in team]), rosterfile))
PYE
fi
# optional (JW_NO_LEADER_ESCALATION=1): rewrite the escalation clause so members
# ask the relevant TEAMMATE directly instead of raising to the leader.
if [ "${JW_NO_LEADER_ESCALATION:-0}" = 1 ]; then
  $L python3 - "$CFG" <<PYE2
import io,sys
p=sys.argv[1]; s=io.open(p,encoding="utf-8").read()
old="report specific access problem to the leader via send_message and ask a teammate who may have access"
new="directly ask the relevant teammate(s) who own or can access that file via send_message and resolve it with them"
n=s.count(old); s=s.replace(old,new)
io.open(p,"w",encoding="utf-8").write(s); print("  escalation->peer rewritten in %d personas"%n)
PYE2
fi

echo "persona_setup ok: key=$KEY arm=$ARM specsplit=$SPECSPLIT roster=$([ "$ARM" = generated ] && echo $ROSTER || echo n/a)"
