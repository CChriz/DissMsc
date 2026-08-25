#!/usr/bin/env bash
# s5_personas.sh <on|off> — swap spec paths in the lnode member-catalog personas.
#  on : planner1/planner2 personas spec/spec.md -> spec/p_spec.md
#       verifier1/verifier2 personas spec/spec.md -> spec/v_spec.md
#       (each still reads "FULL specification" — non-disclosure preserved)
#  off: restore from backup taken by 'on'
set -uo pipefail
CFG=/srv/jwteam_clone/lnode/.jiuwenswarm/config/config.yaml
BK=/srv/jwteam_clone/lnode/.jiuwenswarm/config/config.yaml.pre_s5
case "${1:-}" in
  on)
    sudo -n -u jw_leader test -f "$BK" && { echo "already ON (backup exists)"; exit 0; }
    sudo -n -u jw_leader cp "$CFG" "$BK"
    sudo -n -u jw_leader python3 - "$CFG" <<'PYEOF'
import io, re, sys
p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()
def swap(s, member, new):
    # operate only inside the member's catalog entry (member_name .. next member_name)
    pat = re.compile(r"(member_name: %s\b.*?persona: '[^']*')" % member, re.S)
    m = pat.search(s)
    assert m, "no persona entry for " + member
    seg = m.group(1)
    assert "spec/spec.md" in seg, member + " persona lacks spec/spec.md"
    return s[:m.start(1)] + seg.replace("spec/spec.md", new) + s[m.end(1):]
for member in ("planner1", "planner2"):
    s = swap(s, member, "spec/p_spec.md")
for member in ("verifier1", "verifier2"):
    s = swap(s, member, "spec/v_spec.md")
io.open(p, "w", encoding="utf-8").write(s)
print("personas: S5 paths installed")
PYEOF
    # hard no-execute for verifier NODES (framework permission rail):
    for k in 7 8; do
      C=/srv/jwteam_clone/pnode$k/.jiuwenswarm/config/config.yaml
      sudo -n -u jw_cpool$k cp "$C" "$C.pre_s5"
      sudo -n -u jw_cpool$k python3 - "$C" <<'PYE2'
import io, sys
p = sys.argv[1]
s = io.open(p, encoding='utf-8').read()
n = 0
for tool in ('bash', 'mcp_exec_command', 'create_terminal'):
    old, new = '    %s: ask' % tool, '    %s: deny' % tool
    if old in s:
        s = s.replace(old, new); n += 1
io.open(p, 'w', encoding='utf-8').write(s)
print('  pnode verifier exec-deny: %d tools' % n)
PYE2
    done
    ;;
  off)
    sudo -n -u jw_leader test -f "$BK" || { echo "no backup — already OFF?"; exit 0; }
    sudo -n -u jw_leader cp "$BK" "$CFG"
    sudo -n -u jw_leader rm "$BK"
    for k in 7 8; do
      C=/srv/jwteam_clone/pnode$k/.jiuwenswarm/config/config.yaml
      sudo -n -u jw_cpool$k test -f "$C.pre_s5" && { sudo -n -u jw_cpool$k cp "$C.pre_s5" "$C"; sudo -n -u jw_cpool$k rm "$C.pre_s5"; }
    done
    echo "personas: restored"
    ;;
  *) echo "usage: $0 <on|off>" >&2; exit 2;;
esac
