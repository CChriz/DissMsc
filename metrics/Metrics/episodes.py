# Question-and-answer episodes across the seam and their resolution.
import csv, io, os, sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix
from conformance import parse_strip
from chains import strips_by_run

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

MILESTONES = {
    "S1A": ["plan-delivered", "work", "attested"],
    "S1B": ["plan-delivered", "work", "attested"],
    "S2":  ["both-lanes-working", "work-reported", "attested"],
    "S3":  ["block-encountered", "raised", "recovered"],
    "S4":  ["seam-engaged", "crossed", "integrated"],
    "S5":  ["hidden-unit-named", "attested", "authority-held"],
}

WINDOW = {
    "S3": ({"encountered"}, {"recovered"}),
    "S4": ({"probed", "asked"}, {"integrated", "crossed"}),
    "S5": (set(), {"named"}),
}
KEEP_VERBS = {"DENIED", "REASSIGN", "WRITE", "CLAIM", "READ"}
SCEN_MARKS = {"encountered", "raised", "rerouted", "recovered",
              "probed", "asked", "crossed", "integrated", "named"}

def _keep(t):
    if t["verb"] in KEEP_VERBS:
        return True
    if t["verb"] in ("MSG", "BROADCAST"):
        return bool(t["args"] & {"S", "M", "L", "XL"}) or bool(t["marks"])
    if t["verb"] == "RUN":
        return bool(t["args"] & {"acl", "test"})
    return bool(t["marks"] & SCEN_MARKS)

def episode(rec, strips):
    toks = parse_strip(strips.get(rec["run_id"], {}).get("*", ""))
    sc = rec["scenario"]
    if sc not in WINDOW:
        return None
    smarks, emarks = WINDOW[sc]
    i0 = i1 = None
    for i, t in enumerate(toks):
        if i0 is None and (t["marks"] & smarks
                           or (sc == "S5" and t["who"].startswith("VER")
                               and t["verb"] == "READ" and "spec" in t["args"])):
            i0 = i
        if t["marks"] & emarks:
            i1 = i
    resolved = i1 is not None and (i0 is None or i1 >= i0)
    if i0 is None and i1 is None:
        return dict(run_id=rec["run_id"], scenario=sc, arm=rec["arm"], dose=rec["dose"],
                    task=rec["task"], resolved="no-episode", beats=0, episode="",
                    regrade_score=rec["regrade_score"])
    if i0 is None:
        i0 = max(0, (i1 or 0) - 8)
    end = (i1 + 1) if resolved else len(toks)
    win = toks[i0:end]

    denied_actors = {t["who"] for t in win if t["verb"] == "DENIED"}
    resolver = toks[i1]["who"] if i1 is not None else ""
    cast = denied_actors | {"LEAD", resolver}
    cut = [t for t in win if _keep(t)
           and (t["who"] in cast or t["marks"] & SCEN_MARKS
                or (t["verb"] in ("MSG", "BROADCAST") and t["tgt"] in cast))]
    if not resolved:
        cut = cut[:10]
    def fmt(t):
        return "%s.%s(%s)%s%s" % (
            t["who"], t["verb"], ",".join(sorted(t["args"])),
            (">" + t["tgt"]) if t["tgt"] else "",
            ("!" + "!".join(sorted(t["marks"]))) if t["marks"] else "")

    if len(cut) > 14:
        parts = [fmt(t) for t in cut[:8]] + ["…(%d beats)…" % (len(cut) - 13)] +                 [fmt(t) for t in cut[-5:]]
    else:
        parts = [fmt(t) for t in cut]
    return dict(run_id=rec["run_id"], scenario=sc, arm=rec["arm"], dose=rec["dose"],
                task=rec["task"],
                resolved=("resolved" if resolved else "UNRESOLVED"),
                beats=len(cut), episode=" -> ".join(parts),
                regrade_score=rec["regrade_score"])

def nav_verdicts():
    import walk
    ev = walk.load_evidence()
    over = {}
    for r in rix.read_tsv(os.path.join(OUT, "s5_funnel_runs.tsv")):
        over[r["run_id"]] = int(r.get("disp_downgraded-in-pass", 0) or 0) > 0
    out = {}
    for rec in rix.read_tsv(os.path.join(OUT, "run_index.tsv")):
        ms = MILESTONES[rec["scenario"]]
        have = ev.get(rec["run_id"], {})
        reached = []
        for m in ms:
            if m == "authority-held":
                ok = ("hidden-unit-named" in have
                      and not over.get(rec["run_id"], True))
            else:
                ok = m in have
            if ok:
                reached.append(m)
        verdict = ("navigated" if ms[-1] in reached else
                   "partial" if reached else "not")
        out[rec["run_id"]] = (reached, verdict)
    return out

# build the output tables from the raw streams
def build():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    strips = strips_by_run()
    nav = nav_verdicts()
    rows = []
    for r in idx:
        e = episode(r, strips) or dict(
            run_id=r["run_id"], scenario=r["scenario"], arm=r["arm"], dose=r["dose"],
            task=r["task"], resolved="", beats=0, episode="",
            regrade_score=r["regrade_score"])
        reached, verdict = nav[r["run_id"]]
        e["milestones"] = ",".join(reached)
        e["navigation"] = verdict
        rows.append(e)
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "episodes.tsv"), "w", encoding="utf-8",
                 newline="") as f:
        w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("wrote out/episodes.tsv (%d rows, all 168 runs)" % len(rows))
    print("\n=== THE TABLE: did the team navigate past its collaboration stress? ===")
    print("%-5s %10s %8s %5s   (milestones: %s)" % ("scen", "navigated", "partial",
                                                    "not", "3 per scenario"))
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc]
        c = Counter(r["navigation"] for r in rs)
        print("%-5s %10d %8d %5d   %s" % (sc, c["navigated"], c["partial"], c["not"],
                                          " -> ".join(MILESTONES[sc])))
    for sc in ("S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc]
        c = Counter(r["resolved"] for r in rs)
        b = sorted(r["beats"] for r in rs if r["beats"])
        print("  %-3s %s · median episode length %d beats"
              % (sc, dict(c.most_common()), b[len(b) // 2] if b else 0))
    return rows

def show(arg):
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    strips = strips_by_run()
    for rec in idx:
        if rec["run_id"] == arg or rec["scenario"] == arg:
            e = episode(rec, strips)
            if not e:
                continue
            print("\n%s  [%s, score %s]" % (e["run_id"], e["resolved"],
                                            e["regrade_score"]))
            for p in e["episode"].split(" -> "):
                print("   " + p)

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    strips = strips_by_run()
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-58s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    e = episode(idx["crypto1_s3partial-20260808-211436"], strips)
    check("S3 gold episode: starts at the block, ends resolved",
          e["resolved"] == "resolved" and "DENIED" in e["episode"]
          and "recovered" in e["episode"], "%d beats" % e["beats"])
    e = episode(idx["p5_s3partial-20260808-204549"], strips)
    check("p5_s3partial episode: UNRESOLVED (the annotated non-recovery)",
          e["resolved"] == "UNRESOLVED", e["resolved"])
    lens = [episode(idx[r], strips)["beats"] for r in idx
            if idx[r]["scenario"] == "S3"]
    lens = sorted(x for x in lens if x)
    check("episodes are compact (median <= 30 beats; S3 stories are honestly ~23)",
          lens[len(lens) // 2] <= 30, "median %d" % lens[len(lens) // 2])

    nav = nav_verdicts()
    from collections import Counter as _C
    per = {}
    for rec in rix.read_tsv(os.path.join(OUT, "run_index.tsv")):
        per.setdefault(rec["scenario"], _C())[nav[rec["run_id"]][1]] += 1
    check("S3 navigated == 44 (the frozen 44/48 landing count)",
          per["S3"]["navigated"] == 44, "%d" % per["S3"]["navigated"])
    check("S4 navigated <= 3 (only the integrating runs)",
          per["S4"]["navigated"] <= 3, "%d" % per["S4"]["navigated"])
    check("S5 navigated == 2 (the corpus's two hard-fail dispositions)",
          per["S5"]["navigated"] == 2, "%d" % per["S5"]["navigated"])
    return 1 if bad else 0

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg:
        show(arg)
    else:
        build()
