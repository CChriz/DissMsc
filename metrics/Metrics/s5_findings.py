# Remaining S5 results over the gated funnel tables.
import csv, io, json, os, re, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace
import run_index as rix
import s5_splits as S5
import s5_funnel as F

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")

def spec_touches(run):
    out = []
    for mem in run["members"]:
        role = rix.role_group(mem["member"])
        for t in mem["turns"]:
            for a in t["actions"]:
                hay = "%s %s" % (a["path"] or "", a["args_text"] or "")
                for f in ("v_spec", "p_spec"):
                    if f in hay:
                        out.append((mem["member"], role, f, a["tool"],
                                    int(bool(a["blocked"])), a["ts"]))
                        break
    return out

# entry point
def main():
    idx = [r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
           if r["scenario"] == "S5"]
    units = F.units_by_run()
    splits = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "s5_splits.tsv"))}

    read_v, read_p = Counter(), Counter()
    leader_v_ok = leader_v_blocked = 0
    first_v_read = []
    per_run = {}
    for rec in idx:
        run = teamtrace.load_run(rec["archive_path"])
        t0 = min((t["start_ts"] for m in run["members"] for t in m["turns"]), default=0)
        touches = spec_touches(run)
        vs = [x for x in touches if x[2] == "v_spec" and x[3] == "read_file"]
        ok_v = [x for x in vs if not x[4]]
        for _m, role, f, _tool, blocked, _ts in touches:
            if f == "v_spec":
                read_v[(role, "blocked" if blocked else "ok")] += 1
            else:
                read_p[(role, "blocked" if blocked else "ok")] += 1
        leader_v_ok += sum(1 for x in ok_v if x[1] == "leader")
        leader_v_blocked += sum(1 for x in vs if x[1] == "leader" and x[4])
        if ok_v:
            first_v_read.append((rec["run_id"], round(min(x[5] for x in ok_v) - t0, 1),
                                 sorted({x[0] for x in ok_v})))
        per_run[rec["run_id"]] = dict(rec=rec, run=run, t0=t0)

    print("=== A. v_spec access (verifier-only by design) ===")
    print("  reads by role:", {k: v for k, v in sorted(read_v.items())})
    print("  leader successful v_spec reads: %d   leader denials on v_spec: %d"
          % (leader_v_ok, leader_v_blocked))
    print("  runs where a verifier actually opened v_spec: %d/%d"
          % (len(first_v_read), len(idx)))
    if first_v_read:
        lat = sorted(x[1] for x in first_v_read)
        print("  first v_spec read, seconds after first event: min %.0f med %.0f max %.0f"
              % (lat[0], lat[len(lat) // 2], lat[-1]))

    print("\n=== B. p_spec reach (planners + leader only by design) ===")
    print("  touches by role:", {k: v for k, v in sorted(read_p.items())})

    print("\n=== C/D. naming latency, repair and re-verification ===")
    urows = []
    for rec in idx:
        us = units.get(rec["run_id"], [])
        if us:
            urows += F.score_run(rec, us)
    named = [r for r in urows if r["t_first_mention_rel"] != ""]
    silent_named = [r for r in named if r["stratum"] == "silent"]
    if named:
        lat = sorted(float(r["t_first_mention_rel"]) for r in named)
        print("  first naming of an ablated unit: min %.0f med %.0f max %.0f s"
              % (lat[0], lat[len(lat) // 2], lat[-1]))
    if silent_named:
        lat = sorted(float(r["t_first_mention_rel"]) for r in silent_named)
        print("  silent units only: min %.0f med %.0f max %.0f s"
              % (lat[0], lat[len(lat) // 2], lat[-1]))
    print("  first namer by role:", dict(Counter(
        rix.role_group(r["first_namer"]) for r in named)))

    repaired = after_write = 0
    for rec in idx:
        d = per_run[rec["run_id"]]
        rs = [r for r in urows if r["run_id"] == rec["run_id"]
              and r["t_first_mention_rel"] != ""]
        if not rs:
            continue
        first = min(float(r["t_first_mention_rel"]) for r in rs)
        writes = [a["ts"] - d["t0"] for m in d["run"]["members"] for t in m["turns"]
                  for a in t["actions"]
                  if a["tool"] in ("write_file", "edit_file") and not a["blocked"]
                  and "workspace" in (a["path"] or "")]
        if any(w > first for w in writes):
            after_write += 1
        repaired += 1
    print("  runs where a workspace write follows the first naming: %d/%d"
          % (after_write, repaired))

    print("\n=== E. verdict discipline ===")
    verds = Counter()
    for rec in idx:
        _txt, v = F.attestation(rec["archive_path"])
        verds[v or "(none)"] += 1
    print("  attestation verdicts across the 24 S5 runs:", dict(verds))

    print("\n=== F. ablation dose vs outcome (descriptive, n=24) ===")
    print("  %-26s %-4s %6s %6s %8s" % ("task", "arm", "abl", "ratio", "score"))
    for rec in sorted(idx, key=lambda r: (r["task"], r["arm"])):
        s = splits.get(rec["run_id"])
        if not s:
            continue
        a, ret = int(s["req_subunits_ablated"]), int(s["req_subunits_retained"])
        ratio = a / (a + ret) if a + ret else 0
        print("  %-26s %-4s %6d %6.2f %8s" % (rec["task"], rec["arm"], a, ratio,
                                              rec["regrade_score"]))

if __name__ == "__main__":
    main()
