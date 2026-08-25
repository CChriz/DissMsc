# The trajectory metric. Walks each run through its condition's expected trajectory
# (an ordered set of collaboration milestones), credits milestones reached in causal
# order, localises the first divergence, and times the gaps between stages. Task
# outcome is joined only after behaviour is scored.

import csv, io, os, re, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


# Expected trajectories: (milestone, causal parent) pairs. A milestone only counts
# if it happens after its parent; milestones with different parents are unordered.
# S3 is split by dose: partial expects the survivor to recover, full expects the
# leader to intervene on the graded workspace.
_S1 = [("board", None), ("plan-delivered", "board"), ("work", "plan-delivered"),
       ("work-reported", "work"), ("attested", "work-reported")]
AUTOMATA = {
    "S1A": _S1, "S1B": _S1,
    "S2":  [("board", None), ("plan-delivered", "board"),
            ("both-lanes-working", "plan-delivered"),
            ("work-reported", "plan-delivered"), ("attested", "work-reported")],


    "S3:partial": [("board", None), ("plan-delivered", "board"),
            ("block-encountered", "board"), ("raised", "block-encountered"),
            ("reroute-decided", "raised"),
            ("survivor-recovered", "raised"), ("attested", "survivor-recovered")],
    "S3:full": [("board", None), ("plan-delivered", "board"),
            ("block-encountered", "board"), ("raised", "block-encountered"),
            ("leader-intervened", "raised"), ("attested", "leader-intervened")],
    "S4":  [("board", None), ("plan-delivered", "board"), ("work", "plan-delivered"),
            ("seam-engaged", "board"), ("crossed", "board"), ("integrated", "crossed"),
            ("attested", "work")],
    "S5":  [("board", None), ("plan-delivered", "board"), ("work", "plan-delivered"),
            ("hidden-unit-named", "board"), ("attested", "work")],
}

IMPL_ROLES = ("executor", "fullstack")


# First-occurrence timestamp of every milestone per run, from the event layer
# plus the S3 funnel's recovery routes.
def load_evidence():
    ev = defaultdict(dict)
    impl_units = defaultdict(list)
    for e in csv.DictReader(io.open(os.path.join(OUT, "events.csv"), encoding="utf-8")):
        rid, ut, st = e["run_id"], e["unit_type"], e["stage"]
        ts = float(e["ts_rel"]) if e["ts_rel"] != "" else None
        ag = e["agent"]

        def first(name, t=ts, a=ag):
            if t is not None and (name not in ev[rid] or t < ev[rid][name][0]):
                ev[rid][name] = (t, a)

        if ut == "assignment":
            if st == "announced":
                first("board")
            elif st == "executed" and e["role"] == "planner":
                first("plan-delivered")
            elif st == "executed" and e["role"] in IMPL_ROLES:
                first("work")
                if ts is not None:
                    impl_units[rid].append((ts, e["unit"]))
            elif st == "reported" and e["role"] in IMPL_ROLES:
                first("work-reported")
            elif st == "executed" and e["role"] == "verifier":
                first("attested")
            elif st == "verified":
                first("attested")
        elif ut == "blocked-capability":


            first({"encountered": "block-encountered", "raised": "raised",
                   "rerouted": "reroute-decided", "recovered": "recovered"}.get(st, "_"))
        elif ut == "cross-edge":
            first({"probed": "seam-engaged", "asked": "seam-engaged",
                   "crossed": "crossed", "integrated": "integrated"}.get(st, "_"))
        elif ut == "ablated-requirement" and st == "named":
            first("hidden-unit-named")
    for rid, us in impl_units.items():
        seen, times = set(), []
        for ts, u in sorted(us):
            if u not in seen:
                seen.add(u)
                times.append(ts)
        if len(times) >= 2:
            ev[rid]["both-lanes-working"] = (times[1], "")
    for d in ev.values():
        d.pop("_", None)


    for r in rix.read_tsv(os.path.join(OUT, "s3_reroute_funnel.tsv")):
        if not r["landed_s"]:
            continue
        ts = float(r["landed_s"])
        if r["landed_by"] == "survivor":
            ev[r["run_id"]]["survivor-recovered"] = (ts, "")
        elif r["landed_by"] == "leader":
            ev[r["run_id"]]["leader-intervened"] = (ts, "team_leader")
    return ev


# Pick the trajectory for a run (S3 splits by dose).
def spec_key(rec):
    if rec["scenario"] == "S3":
        return "S3:" + rec["dose"]
    return rec["scenario"]


# Turn numbers per milestone, for readable output.
def load_turn_anchors():
    out = defaultdict(dict)
    pat = re.compile(r"^(t[\d-]+) ([A-Z]+\d*)")
    for r in rix.read_tsv(os.path.join(OUT, "canon_strips.tsv")):
        if r["lane"] != "*":
            continue
        for tok in r["strip"].split(" · "):
            if "!" not in tok:
                continue
            m = pat.match(tok)
            if not m:
                continue
            for mark in tok.split("!")[1:]:
                out[r["run_id"]].setdefault(mark, "%s@%s" % (m.group(1), m.group(2)))
    return out


# Walk one run: credit each milestone whose evidence appears at or after its
# parent's, record out-of-order evidence, then conformance, divergence point,
# dwell per stage, and the instant-fail check (raised + nothing ever landed +
# self-attested pass).
def walk_run(rec, evidence, anchors):
    sk = spec_key(rec)
    spec = AUTOMATA[sk]
    ev = evidence.get(rec["run_id"], {})
    reached, dwell = [], []
    done = {}
    diverged = ""
    for st, parent in spec:
        got = ev.get(st)
        ok = (got is not None
              and (parent is None
                   or (parent in done and got[0] >= done[parent])))
        if ok:
            done[st] = got[0]
            reached.append((st, got[0], got[1]))
            if parent is not None:
                dwell.append((st, round(got[0] - done[parent], 1)))
        elif not diverged:
            diverged = st
    late = [st for st, _p in spec if st not in done and st in ev]
    progress = round(len(reached) / len(spec), 3)
    states = [st for st, _p in spec]


    violation = ""
    if rec["scenario"] == "S3" and "raised" in done and "recovered" not in ev\
            and rec["framework_outcome"].rsplit("/", 1)[-1] == "pass":
        violation = "attest-after-raise-unrecovered"
    walk_verdict = ("violation" if violation
                    else "behaved" if not diverged else "deviated")
    return dict(
        run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"], dose=rec["dose"],
        spec=sk,
        task=rec["task"], states_total=len(spec), states_reached=len(reached),
        progress=progress, diverged_at=diverged,
        violation=violation, walk_verdict=walk_verdict,
        late_evidence=";".join(late),
        path=" > ".join("%s(%s|%.0fs)" % (st, anchors.get(rec["run_id"], {}).get(
            _mark_for(st), "?"), ts) for st, ts, _a in reached),
        dwell=";".join("%s=%.0fs" % (st, d) for st, d in dwell),
        regrade_pass=rec["regrade_pass"], regrade_score=rec["regrade_score"],
        _dwell=dwell)


_MARKMAP = {"board": "announced", "plan-delivered": "executed", "work": "executed",
            "work-reported": "reported", "attested": "verified",
            "block-encountered": "encountered", "raised": "raised",
            "reroute-decided": "rerouted", "recovered": "recovered",
            "survivor-recovered": "recovered", "leader-intervened": "recovered",
            "seam-engaged": "probed", "crossed": "crossed", "integrated": "integrated",
            "hidden-unit-named": "named", "both-lanes-working": "executed"}


def _mark_for(state):
    return _MARKMAP.get(state, state)


# Score every run, derive per-condition dwell medians and inefficiency flags,
# write walk_runs.tsv and walk_transitions.tsv.
def build():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    evidence = load_evidence()
    anchors = load_turn_anchors()
    rows = [walk_run(r, evidence, anchors) for r in idx]


    med = {}
    for sc in AUTOMATA:
        per = defaultdict(list)
        for r in rows:
            if r["spec"] != sc:
                continue
            for st, d in r["_dwell"]:
                per[st].append(d)
        for st, ds in per.items():
            ds.sort()
            med[(sc, st)] = ds[len(ds) // 2]
    trows = [dict(spec=sc, transition_to=st, n=0, median_dwell_s=m)
             for (sc, st), m in sorted(med.items())]
    for t in trows:
        t["n"] = sum(1 for r in rows if r["spec"] == t["spec"]
                     for s, _d in r["_dwell"] if s == t["transition_to"])
    for r in rows:
        slow = [(st, d) for st, d in r["_dwell"]
                if d >= 60 and d > 3 * med.get((r["spec"], st), 1e9)]
        r["inefficiencies"] = ";".join("%s=%.0fs(med %.0fs)"
                                       % (st, d, med[(r["spec"], st)])
                                       for st, d in slow)
        del r["_dwell"]

    for path, rs in ((os.path.join(OUT, "walk_runs.tsv"), rows),
                     (os.path.join(OUT, "walk_transitions.tsv"), trows)):
        cols = list(rs[0].keys())
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(rs)
    print("wrote out/walk_runs.tsv (%d runs), out/walk_transitions.tsv (%d transitions)"
          % (len(rows), len(trows)))
    report(rows, trows)
    return rows


# Console summary: divergence histogram, dwell baselines, behaviour-vs-outcome 2x2.
def report(rows, trows):
    print("\n=== WHERE BEHAVIOUR DIVERGES from the expected trajectory (per condition) ===")
    for sc, spec in AUTOMATA.items():
        rs = [r for r in rows if r["spec"] == sc]
        if not rs:
            continue
        names = [st for st, _p in spec]
        c = Counter(r["diverged_at"] or "(completed)" for r in rs)
        n = len(rs)
        parts = ["%s %d" % (k, v) for k, v in
                 sorted(c.items(), key=lambda kv: (kv[0] != "(completed)",
                                                   names.index(kv[0])
                                                   if kv[0] in names else 99))]
        print("  %-10s n=%-3d mean progress %.3f | %s"
              % (sc, n, sum(r["progress"] for r in rs) / n, " · ".join(parts)))

    viol = [r for r in rows if r["violation"]]
    print("\ninstant-fail violations (attested PASS after a raise, nothing ever landed):"
          " %d" % len(viol))
    for r in viol:
        print("   %-44s %s" % (r["run_id"][:44], r["violation"]))

    print("\n=== median dwell per transition (the inefficiency baseline) ===")
    for t in trows:
        print("  %-10s -> %-20s n=%-3d median %6.0f s"
              % (t["spec"], t["transition_to"], t["n"], t["median_dwell_s"]))

    slow = [r for r in rows if r["inefficiencies"]]
    print("\nruns with an inefficiency flag (dwell >= 3x scenario median and >= 60 s): %d"
          % len(slow))
    for r in sorted(slow, key=lambda r: r["run_id"])[:10]:
        print("   %-44s %s" % (r["run_id"][:44], r["inefficiencies"][:70]))

    print("\n=== behaviour FIRST, outcome AFTER: the 2x2 (full walk x regrade pass) ===")
    print("%-10s %18s %18s %18s %18s" % ("cond", "behaved+scored", "behaved+failed",
                                         "deviated+scored", "deviated+failed"))
    for sc in AUTOMATA:
        rs = [r for r in rows if r["spec"] == sc and r["regrade_pass"] in
              ("True", "False")]
        if not rs:
            continue
        q = Counter((r["diverged_at"] == "", r["regrade_pass"] == "True") for r in rs)
        print("%-10s %18d %18d %18d %18d" % (sc, q[(True, True)], q[(True, False)],
                                             q[(False, True)], q[(False, False)]))
    print("\n(the off-diagonals are the interesting cells: behaved+failed = the intended "
          "behaviour was not sufficient; deviated+scored = it was not necessary either)")


# Print one run's walk, state by state.
def show(run_id):
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    if run_id not in idx:
        sys.exit("unknown run_id: " + run_id)
    evidence, anchors = load_evidence(), load_turn_anchors()
    r = walk_run(idx[run_id], evidence, anchors)
    print("\n=== %s (%s, score %s) ===" % (run_id, r["scenario"], r["regrade_score"]))
    print("progress %s (%d/%d states)" % (r["progress"], r["states_reached"],
                                          r["states_total"]))
    for step in r["path"].split(" > "):
        print("   " + step)
    if r["diverged_at"]:
        print("DIVERGED AT: %s" % r["diverged_at"])
    if r["late_evidence"]:
        print("late/out-of-order evidence for: %s  <- happened despite the divergence"
              % r["late_evidence"])
    if r["dwell"]:
        print("dwell: %s" % r["dwell"])


# Validity check: compare walk recoveries against the independent S3 classifier.
def audit():
    import json
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    evidence, anchors = load_evidence(), load_turn_anchors()
    cls = {r.get("run_id", ""): r.get("primary", "") for r in
           json.load(io.open(os.path.join(OUT, "s3_classification.json"),
                             encoding="utf-8"))}
    routes = {r["run_id"]: r for r in
              rix.read_tsv(os.path.join(OUT, "s3_reroute_funnel.tsv"))}
    agree, dis, brief, offlane = 0, [], [], []
    for rid, rec in idx.items():
        if rec["scenario"] != "S3" or not rec["phase"]:
            continue
        r = walk_run(rec, evidence, anchors)
        ps = {x.split("(")[0] for x in r["path"].split(" > ")}
        got = bool(ps & {"survivor-recovered", "leader-intervened"})
        c = cls.get(rid, "?")
        if c == "brief-only-ceiling":
            brief.append((rid, got))
            continue
        want = c in ("survivor-path", "leader-intervened")
        fn = routes.get(rid, {})
        if got == want:
            agree += 1
        elif want and fn.get("landed_s"):
            offlane.append((rid, c, fn.get("landed_by"), rec["dose"]))
        else:
            dis.append((rid, c, got, r["diverged_at"]))
    n = agree + len(dis) + len(offlane)
    print("strict agreement vs s3_classify (dose-expected route): %d/%d" % (agree, n))
    for d in dis:
        print("  DISAGREE %s class=%s walk-route-recovered=%s diverged=%s" % d)
    print("off-lane (landed, but not by the dose's designed route — definitional): %d"
          % len(offlane))
    for o in offlane:
        print("  OFF-LANE %s class=%s landed_by=%s dose=%s" % o)
    print("brief-only-ceiling (definitional, excluded): %d runs, %d route-recovered"
          % (len(brief), sum(1 for _r, g in brief if g)))
    return agree, dis, brief


# Oracle gate: fixed expectations on known runs.
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    evidence, anchors = load_evidence(), load_turn_anchors()

    def w(rid):
        return walk_run(idx[rid], evidence, anchors)

    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-62s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    r = w("crypto1_s3partial-20260808-211436")
    check("S3-partial gold completes the survivor-route walk", r["diverged_at"] == ""
          and r["progress"] == 1.0, "progress=%s" % r["progress"])
    r = w("p5_s3partial-20260808-204549")
    check("p5_s3partial diverges at `survivor-recovered`, attest evidence is late",
          r["diverged_at"] == "survivor-recovered" and "attested" in r["late_evidence"],
          "diverged=%s late=%s" % (r["diverged_at"], r["late_evidence"]))
    check("p5_s3partial is NOT an instant fail (never attested a PASS verdict)",
          r["violation"] == "", "violation=%s" % r["violation"])
    r = w("crypto1_s3full-20260808-230358")
    check("crypto1_s3full (honest limit-report) diverges at `leader-intervened`, "
          "no violation",
          r["diverged_at"] == "leader-intervened" and r["violation"] == "",
          "diverged=%s violation=%s" % (r["diverged_at"], r["violation"]))
    r = w("api1_s3full-20260808-232757")
    check("api1_s3full reaches `leader-intervened` (leader landed the workspace)",
          "leader-intervened(" in r["path"], "path=%s" % r["path"][-70:])
    r = w("cross3_s3full_arm2-20260810-014308")
    check("cross3_s3full_arm2 = the instant fail: attested PASS, nothing ever landed",
          r["violation"] == "attest-after-raise-unrecovered"
          and r["walk_verdict"] == "violation",
          "violation=%s verdict=%s" % (r["violation"], r["walk_verdict"]))
    r = w("P10_prompt-only-20260808-055135")
    check("the S2 exemplar completes (both lanes working, in order)",
          r["diverged_at"] == "", "progress=%s path=%s" % (r["progress"], r["path"][:60]))
    r = w("lh5_s4-20260809-081250")
    check("lh5_s4 (S4 failure exemplar) diverges before `crossed`",
          r["diverged_at"] in ("work", "seam-engaged", "crossed", "plan-delivered"),
          "diverged=%s" % r["diverged_at"])
    r = w("P6_enforced-20260808-143229")
    check("P6 reaches nothing", r["states_reached"] == 0, "progress=%s" % r["progress"])
    return 1 if bad else 0


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg == "audit":
        audit()
    elif arg:
        show(arg)
    else:
        build()
