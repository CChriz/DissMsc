# Per-run flow graph over the canonical strips with content grades.
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
IMPL = ("EXEC", "FULL")

def flows_of(toks):
    spec_reads = [(i, t) for i, t in enumerate(toks)
                  if t["who"].startswith("PLAN") and t["verb"] == "READ"
                  and "spec" in t["args"]]
    spec_denied = [(i, t) for i, t in enumerate(toks)
                   if t["who"].startswith("PLAN") and t["verb"] == "DENIED"
                   and t["args"] & {"spec", "brief"}]
    plan_msgs = [(i, t) for i, t in enumerate(toks)
                 if t["who"].startswith("PLAN") and t["verb"] in ("MSG", "BROADCAST")
                 and t["args"] & {"M", "L", "XL"}
                 and (t["tgt"] == "*" or t["tgt"].startswith(IMPL) or t["verb"] == "BROADCAST")]
    work_writes = [(i, t) for i, t in enumerate(toks)
                   if t["who"].startswith(IMPL) and t["verb"] == "WRITE"
                   and t["args"] & {"workspace", "workspace/tests"}]
    reports = [(i, t) for i, t in enumerate(toks)
               if t["who"].startswith(IMPL)
               and ((t["verb"] == "MSG" and (t["tgt"].startswith("VER")
                                             or t["tgt"] == "LEAD" or t["tgt"] == "*"))
                    or t["verb"] == "DONE")]
    ver_ev = [(i, t) for i, t in enumerate(toks)
              if t["who"].startswith("VER")
              and ((t["verb"] == "READ" and t["args"] & {"workspace", "workspace/tests"})
                   or (t["verb"] == "RUN"
                       and t["args"] & {"test", "run", "sh", "install", "git"}))]
    attests = [(i, t) for i, t in enumerate(toks)
               if t["who"].startswith(("VER", "FULL")) and t["verb"] == "WRITE"
               and "attestation" in t["args"]]

    f1 = "absent"
    for i, m in plan_msgs:
        if any(j < i and r["who"] == m["who"] for j, r in spec_reads):
            f1 = "realised"
            break
        if any(j < i and r["who"] == m["who"] for j, r in spec_denied):
            f1 = "attempted"
    if not plan_msgs and (spec_reads or spec_denied):
        f1 = "no-plan-msg"

    f2 = "absent"
    for i, w in work_writes:
        if any(j < i and (m["tgt"] == "*" or m["tgt"] == w["who"] or
                          m["verb"] == "BROADCAST")
               for j, m in plan_msgs):
            f2 = "realised"
            break

    f3 = "absent"
    if work_writes:
        first_w = work_writes[0][0]
        if any(j > first_w for j, _ in ver_ev):
            f3 = "realised(artifact)"
        elif any(j > first_w and t["verb"] == "MSG" and t["tgt"].startswith("VER")
                 for j, t in reports):
            f3 = "realised(report)"
        elif any(j > first_w for j, _ in reports):
            f3 = "realised(report-indirect)"

    f4 = "absent"
    if attests:
        signers = {t["who"] for _, t in attests}
        last = attests[-1][0]
        if any(j < last and t["who"] in signers for j, t in ver_ev):
            f4 = "realised"
        else:
            f4 = "no-evidence"
    return {"F1_spec_to_plan": f1, "F2_plan_to_work": f2,
            "F3_work_to_verify": f3, "F4_verify_to_attest": f4}

def load_routes():
    import json
    R = {"s3_class": {}, "s3_lane": {}, "s4_chan": {}, "s5_disp": {}, "src": {}}
    p3 = os.path.join(OUT, "s3_classification.json")
    if os.path.isfile(p3):
        R["s3_class"] = {r.get("run_id", ""): r.get("primary", "")
                         for r in json.load(io.open(p3, encoding="utf-8"))}
    for r in rix.read_tsv(os.path.join(OUT, "s3_reroute_funnel.tsv")):
        R["s3_lane"][r["run_id"]] = r.get("landed_by", "")
    p4 = os.path.join(OUT, "s4_congruence.json")
    if os.path.isfile(p4):
        for r in json.load(io.open(p4, encoding="utf-8")):
            ch = sorted({c for e in r.get("edges", []) for c in e.get("channels", [])})
            R["s4_chan"][r.get("archive", "")] = ",".join(ch) or "none"
    for r in rix.read_tsv(os.path.join(OUT, "s5_funnel_runs.tsv")):
        over = int(r.get("disp_downgraded-in-pass", 0) or 0)
        hard = int(r.get("disp_hard-fail-emitted", 0) or 0)
        R["s5_disp"][r["run_id"]] = ("overruled" if over else
                                     "authority-held" if hard else "no-named-units")
    for r in rix.read_tsv(os.path.join(OUT, "backtrace.tsv")):
        mix = r.get("source_mix", "")
        R["src"][r["run_id"]] = mix.split(";")[0].split("=")[0] if mix else ""
    return R

def scenario_flow(rec, R):
    rid, sc = rec["run_id"], rec["scenario"]
    if sc == "S3":
        lane = R["s3_lane"].get(rid, "")
        cls = R["s3_class"].get(rid, "")
        if lane:
            return "realised", {"survivor": "survivor", "leader": "leader-did-it",
                                "leader-relay": "leader-relay"}.get(lane, lane)
        if cls == "honest-report":
            return "realised", "honest-report"
        return "absent", "none"
    if sc == "S4":
        ch = R["s4_chan"].get(rid, "")
        if ch and ch != "none":
            return "realised", ch

        return ("unmeasured", "no-channel-data") if not ch else ("absent", "none")
    if sc == "S5":
        d = R["s5_disp"].get(rid, "")
        if d == "authority-held":
            return "realised", d
        if d == "overruled":
            return "realised-overruled", d
        return ("absent", d or "no-data")
    return "", ""

def score_run(rec, strips, R=None):
    toks = parse_strip(strips.get(rec["run_id"], {}).get("*", ""))
    fl = flows_of(toks)
    realised = sum(1 for v in fl.values() if v.startswith(("realised", "attempted")))
    n_flows = 4
    srow = dict(run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],
                dose=rec["dose"], task=rec["task"], **fl)
    if R is not None:
        sf, route = scenario_flow(rec, R)
        srow["F5_scenario_flow"] = sf
        srow["route"] = route
        srow["F2_route"] = R["src"].get(rec["run_id"], "")
        if sf:
            n_flows = 5
            realised += int(sf.startswith("realised"))
    srow.update(flows_realised=realised, flow_score=round(realised / n_flows, 2),
                regrade_score=rec["regrade_score"])
    return srow

# build the output tables from the raw streams
def build():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    strips = strips_by_run()
    R = load_routes()
    rows = [score_run(r, strips, R) for r in idx]
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "flowgraph.tsv"), "w", encoding="utf-8",
                 newline="") as f:
        w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("wrote out/flowgraph.tsv (%d runs)" % len(rows))
    report(rows)
    return rows

# print the human-readable summary
def report(rows):
    print("\n=== flow realisation per scenario (share of runs) ===")
    print("%-5s %8s %8s %8s %8s %11s" % ("scen", "F1", "F2", "F3", "F4", "mean score"))
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc]
        if not rs:
            continue
        n = len(rs)
        f = [100.0 * sum(1 for r in rs
                         if r[k].startswith(("realised", "attempted"))) / n
             for k in ("F1_spec_to_plan", "F2_plan_to_work", "F3_work_to_verify",
                       "F4_verify_to_attest")]
        print("%-5s %7.0f%% %7.0f%% %7.0f%% %7.0f%% %11.2f"
              % (sc, f[0], f[1], f[2], f[3],
                 sum(r["flow_score"] for r in rs) / n))

    print("\n=== ROUTING PATTERNS (how each scenario's flow was realised) ===")
    for sc in ("S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc and "route" in r]
        c = Counter(r["route"] for r in rs)
        print("  %-4s %s" % (sc, dict(c.most_common())))
    c = Counter(r.get("F2_route", "") for r in rows if r.get("F2_route"))
    print("  F2 (plan->work) route mix: %s" % dict(c.most_common()))

    lib_p = os.path.join(OUT, "library_index.tsv")
    if not os.path.isfile(lib_p):
        return
    lib = {r["run_id"]: r["cls"] for r in rix.read_tsv(lib_p)}
    by = {r["run_id"]: r for r in rows}
    print("\n=== the SUBSET PROOF: the 24 annotated library exemplars ===")
    print("%-5s %-9s %-40s %5s  %s" % ("scen", "class", "run", "score", "missing flows"))
    for rid, cls in sorted(lib.items(), key=lambda kv: (by[kv[0]]["scenario"], kv[1])):
        r = by.get(rid)
        if not r:
            continue
        miss = [k[:2] for k in ("F1_spec_to_plan", "F2_plan_to_work",
                                "F3_work_to_verify", "F4_verify_to_attest")
                if not r[k.replace(k[:2], k[:2])].startswith(("realised", "attempted"))
                or True]
        miss = [k.split("_")[0] for k in ("F1_spec_to_plan", "F2_plan_to_work",
                                          "F3_work_to_verify", "F4_verify_to_attest")
                if not r[k].startswith(("realised", "attempted"))]
        print("%-5s %-9s %-40s %5s  %s" % (r["scenario"], cls, rid[:40],
                                           r["flow_score"], ",".join(miss) or "-"))
    g = [by[k]["flow_score"] for k, c in lib.items() if c == "gold" and k in by]
    f = [by[k]["flow_score"] for k, c in lib.items() if c == "failure" and k in by]
    print("\ngold mean %.2f vs failure mean %.2f (n=%d/%d)"
          % (sum(g) / len(g), sum(f) / len(f), len(g), len(f)))

def show(run_id):
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    if run_id not in idx:
        sys.exit("unknown run_id: " + run_id)
    r = score_run(idx[run_id], strips_by_run())
    for k, v in r.items():
        print("%-22s %s" % (k, v))

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    strips = strips_by_run()

    def one(rid):
        return score_run(idx[rid], strips)

    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-60s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    r = one("crypto1_enforced-20260808-114845")
    check("S1A gold realises all four flows", r["flows_realised"] == 4,
          "%s" % {k: v for k, v in r.items() if k.startswith("F")})
    r = one("p5_s3partial-20260808-204549")
    check("p5_s3partial: work never happens -> F2/F3/F4 cannot realise",
          r["flows_realised"] <= 1, "score=%s" % r["flow_score"])
    r = one("P6_enforced-20260808-143229")
    check("P6: zero flows", r["flows_realised"] == 0, "score=%s" % r["flow_score"])
    r = one("cr4_enforced-20260808-114309")
    check("cr4: F4 realised via reads (static verification — annotated)",
          r["F4_verify_to_attest"] == "realised", r["F4_verify_to_attest"])
    return 1 if bad else 0

def robustness(n_perm=10000, seed=7):
    import random
    rnd = random.Random(seed)
    rows = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "flowgraph.tsv"))}
    lib = [(r["run_id"], r["cls"], r["scenario"]) for r in
           rix.read_tsv(os.path.join(OUT, "library_index.tsv"))
           if r["cls"] in ("gold", "failure") and r["run_id"] in rows]
    FL = ("F1_spec_to_plan", "F2_plan_to_work", "F3_work_to_verify",
          "F4_verify_to_attest", "F5_scenario_flow")

    def score(rid, drop=None):
        r = rows[rid]
        ks = [k for k in FL if k != drop and r.get(k, "")]
        got = sum(1 for k in ks if r[k].startswith(("realised", "attempted")))
        return got / len(ks) if ks else 0.0

    def gap(labels, drop=None):
        g = [score(rid, drop) for (rid, _c, _s), lab in zip(lib, labels) if lab == "gold"]
        f = [score(rid, drop) for (rid, _c, _s), lab in zip(lib, labels)
             if lab == "failure"]
        return (sum(g) / len(g) - sum(f) / len(f)) if g and f else 0.0

    true_labels = [c for _r, c, _s in lib]
    obs = gap(true_labels)
    print("=== 1. permutation test (labels shuffled within scenario, n=%d) ===" % n_perm)
    by_scen = {}
    for k, (_r, c, sc) in enumerate(lib):
        by_scen.setdefault(sc, []).append(k)
    hits = 0
    for _ in range(n_perm):
        lab = list(true_labels)
        for sc, idxs in by_scen.items():
            vals = [lab[k] for k in idxs]
            rnd.shuffle(vals)
            for k, v in zip(idxs, vals):
                lab[k] = v
        if gap(lab) >= obs - 1e-12:
            hits += 1
    print("  observed gold-failure gap %.3f, permuted >= observed in %d/%d  ->  p = %.4f"
          % (obs, hits, n_perm, hits / n_perm))

    print("\n=== 2. negative control: arm-1 vs arm-2 on the four GENERIC flows ===")
    def arm_mean(a):
        rs = [r for r in rows.values() if r["arm"] == a]
        return sum(sum(1 for k in FL[:4] if r[k].startswith(("realised", "attempted")))
                   / 4.0 for r in rs) / len(rs), len(rs)
    m1, n1 = arm_mean("1")
    m2, n2 = arm_mean("2")
    print("  arm-1 %.3f (n=%d) vs arm-2 %.3f (n=%d), diff %.3f  ->  %s"
          % (m1, n1, m2, n2, abs(m1 - m2),
             "PASS (no separation)" if abs(m1 - m2) < 0.05 else "FLAG"))

    print("\n=== 3. ablation: gold-failure gap with each flow dropped ===")
    print("  full gap: %.3f" % obs)
    for k in FL:
        print("  without %-22s %.3f" % (k + ":", gap(true_labels, drop=k)))

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg == "robustness":
        robustness()
    elif arg:
        show(arg)
    else:
        build()
