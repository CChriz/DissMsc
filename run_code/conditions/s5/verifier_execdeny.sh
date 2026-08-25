#!/usr/bin/env bash
# verifier_execdeny.sh <on|off> — batch-level verifier no-execute for S5.
# Sets tools bash/mcp_exec_command/create_terminal to 'deny' on verifier nodes
# pnode7/pnode8 (persona boundary is the primary guarantee; this is defense in
# depth — note the rail was observed non-enforcing once, treat as best-effort).
# Extracted from s5_personas.sh so persona_setup.sh owns the leader catalog alone.
set -uo pipefail
case "${1:-}" in
  on)
    for k in 7 8; do
      C=/srv/jwteam_clone/pnode$k/.jiuwenswarm/config/config.yaml
      sudo -n -u jw_cpool$k test -f "$C.pre_s5" && continue
      sudo -n -u jw_cpool$k cp "$C" "$C.pre_s5"
      sudo -n -u jw_cpool$k python3 - "$C" <<'PYE'
import io, sys
p = sys.argv[1]; s = io.open(p, encoding="utf-8").read(); n = 0
for t in ("bash", "mcp_exec_command", "create_terminal"):
    if "    %s: ask" % t in s:
        s = s.replace("    %s: ask" % t, "    %s: deny" % t); n += 1
io.open(p, "w", encoding="utf-8").write(s); print("  %s exec-deny: %d tools" % (p.split("/")[3], n))
PYE
    done ;;
  off)
    for k in 7 8; do
      C=/srv/jwteam_clone/pnode$k/.jiuwenswarm/config/config.yaml
      sudo -n -u jw_cpool$k test -f "$C.pre_s5" && { sudo -n -u jw_cpool$k cp "$C.pre_s5" "$C"; sudo -n -u jw_cpool$k rm "$C.pre_s5"; }
    done
    echo "verifier exec-deny restored" ;;
  *) echo "usage: $0 <on|off>" >&2; exit 2;;
esac
