# Scores every run against per-scenario beat checklists (descriptive
# and design-derived).
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

TOK = re.compile(r"^t(?P<turn>\d+)(?:-\d+)? (?P<who>[A-Z]+\d*)(?:>(?P<tgt>[A-Z*]+\d*))?"
                 r"\.(?P<verb>[A-Z_]+)"
                 r"(?:\((?P<arg>[^)]*)\))?(?:x(?P<n>\d+))?(?P<marks>(?:![a-z-]+)*)$")

def parse_strip(strip):
    out = []
    for t in strip.split(" · "):
        m = TOK.match(t.strip())
        if not m:
            continue
        d = m.groupdict()
        out.append(dict(who=d["who"], tgt=d["tgt"] or "", verb=d["verb"],
                        turn=int(d["turn"]),
                        args=set((d["arg"] or "").split(",")) - {""},
                        n=int(d["n"] or 1),
                        marks=set((d["marks"] or "").strip("!").split("!")) - {""}))
    return out

def _first(toks, pred):
    for i, t in enumerate(toks):
        if pred(t):
            return i
    return None

IMPL = ("EXEC", "FULL")
WORKY = {"workspace", "workspace/tests", "spec"}

def is_work(t):
    return (t["who"].startswith(IMPL)
            and ((t["verb"] == "WRITE" and t["args"] & WORKY)
                 or (t["verb"] == "RUN" and "test" in t["args"])))

def is_attest(t):
    return (t["verb"] == "WRITE" and "attestation" in t["args"]
            and t["who"].startswith(("VER", "FULL")))

def backbone(toks):
    i_work = _first(toks, is_work)
    i_att = _first(toks, is_attest)
    attester = toks[i_att]["who"] if i_att is not None else ""
    beats = {
        "announced": any(t["verb"] == "CREATE_TASKS" for t in toks),
        "planned": any((t["who"].startswith("PLAN") and t["verb"] == "MSG"
                        and t["args"] & {"M", "L", "XL"})
                       or (t["who"].startswith("PLAN") and "executed" in t["marks"])
                       for t in toks),
        "worked": i_work is not None,
        "reported": any(t["who"].startswith(IMPL)
                        and (t["verb"] == "DONE" or "reported" in t["marks"])
                        for t in toks),
        "attested": i_att is not None or any("verified" in t["marks"] for t in toks),
    }

    ver_ran = any(t["who"].startswith("VER") and t["verb"] == "RUN" for t in toks)
    order = {}
    if i_att is not None and i_work is not None:
        order["work-before-attest"] = i_work < i_att
    if i_att is not None:
        i_ran = _first(toks, lambda t: t["who"] == attester and t["verb"] == "RUN")
        order["ran-before-attest"] = i_ran is not None and i_ran < i_att
    return beats, order, attester, ver_ran

def scenario_beats(rec, stages, lanes):
    scen = rec["scenario"]
    if scen == "S3":
        return {s: (s in stages) for s in ("encountered", "raised", "rerouted", "recovered")}
    if scen == "S4":

        return {"seam-engaged": bool({"probed", "asked"} & stages),
                "crossed": "crossed" in stages}
    if scen == "S5":
        named = stages.get("named", 0)
        total = stages.get("_s5_total", 0)
        return {"named-majority": total > 0 and named * 2 >= total,
                "disposed": stages.get("disposed", 0) > 0}
    if scen == "S2":
        work_lanes = [l for l, ts in lanes.items()
                      if l != "-" and any(is_work(t) for t in ts)]
        att_lanes = [l for l, ts in lanes.items() if l != "-" and any(is_attest(t) for t in ts)]
        return {"both-lanes-worked": len(work_lanes) >= 2,
                "any-lane-attested": len(att_lanes) >= 1}
    return {}

def violations(rec, toks, beats, order, attester, units_flags):
    v = []
    if order.get("work-before-attest") is False:
        v.append("attest-before-work")
    if rec["scenario"] != "S3" or rec["dose"] != "full":
        if any(t["who"] == "LEAD" and t["verb"] == "WRITE" and t["args"] & WORKY
               for t in toks):
            v.append("leader-does-work")
    return v

def load_all():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    strips = defaultdict(dict)
    for r in rix.read_tsv(os.path.join(OUT, "canon_strips.tsv")):
        strips[r["run_id"]][r["lane"]] = r["strip"]
    stages = defaultdict(set)
    s5 = Counter()
    with io.open(os.path.join(OUT, "events.csv"), encoding="utf-8") as f:
        for e in csv.DictReader(f):
            if e["unit_type"] == "ablated-requirement":
                s5[(e["run_id"], e["stage"])] += 1
            else:
                stages[e["run_id"]].add(e["stage"])
    import json
    s3cls = {}
    p3 = os.path.join(OUT, "s3_classification.json")
    if os.path.isfile(p3):
        s3cls = {r.get("run_id", ""): r.get("primary", "")
                 for r in json.load(io.open(p3, encoding="utf-8"))}
    s5_overruled = set()
    with io.open(os.path.join(OUT, "events.csv"), encoding="utf-8") as f:
        for e in csv.DictReader(f):
            if (e["unit_type"] == "ablated-requirement" and e["stage"] == "disposed"
                    and e["channel"] == "downgraded-in-pass"):
                s5_overruled.add(e["run_id"])
    units_flags = defaultdict(lambda: Counter())
    for u in rix.read_tsv(os.path.join(OUT, "trajectory_units.tsv")):
        if u["unit_type"] != "assignment":
            continue
        sp = u["stage_path"].split(">")
        if "reported" in sp and "executed" not in sp and "claimed" in sp:
            units_flags[u["run_id"]]["report_no_work"] += 1
    return idx, strips, stages, s5, units_flags, s3cls, s5_overruled

def normative(rec, beats, order, ver_ran, st, stx, lanes, uf, s3cls, s5ov, toks):
    nb = dict(beats)
    nb["verified-independently"] = bool(beats.get("attested")) and ver_ran
    scen = rec["scenario"]
    if scen == "S3":
        nb.update({"encountered": "encountered" in st, "raised": "raised" in st,
                   "resolved-as-designed": ("recovered" in st)
                   or s3cls.get(rec["run_id"], "") == "honest-report"})
    elif scen == "S4":
        nb.update({"seam-engaged": bool({"probed", "asked"} & st),
                   "crossed": "crossed" in st, "integrated": "integrated" in st})
    elif scen == "S5":
        named, total = stx.get("named", 0), stx.get("_s5_total", 0)
        nb.update({"named-majority": total > 0 and named * 2 >= total,
                   "verdict-carries-findings": stx.get("disposed", 0) > 0
                   and rec["run_id"] not in s5ov})
    elif scen == "S2":
        nb.update({"both-lanes-worked":
                   len([l for l, ts in lanes.items() if l != "-"
                        and any(is_work(t) for t in ts)]) >= 2,
                   "any-lane-attested":
                   any(any(is_attest(t) for t in ts) for l, ts in lanes.items()
                       if l != "-")})
    nv = []
    if beats.get("attested") and not ver_ran:
        nv.append("attest-without-own-evidence")
    if order.get("work-before-attest") is False:
        nv.append("attest-before-work")
    n_rnw = uf.get(rec["run_id"], {}).get("report_no_work", 0)
    if n_rnw:
        nv.append("report-without-work(%d)" % n_rnw)
    if any(t["who"] == "LEAD" and t["verb"] == "WRITE" and t["args"] & WORKY for t in toks):
        nv.append("leader-does-work")
    if rec["run_id"] in s5ov:
        nv.append("named-gap-overruled")
    reached = sum(1 for v in nb.values() if v)
    conf = round(reached / len(nb), 3) if nb else 0.0
    return conf, ";".join(sorted(k for k, v in nb.items() if not v)), ";".join(nv),         int(conf >= 0.9 and not nv)

def score_run(rec, strips, stages, s5, units_flags, s3cls=None, s5ov=None):
    toks = parse_strip(strips.get(rec["run_id"], {}).get("*", ""))
    lanes = {l: parse_strip(s) for l, s in strips.get(rec["run_id"], {}).items() if l != "*"}
    beats, order, attester, ver_ran = backbone(toks)
    st = dict.fromkeys(stages.get(rec["run_id"], set()), True)
    st = set(stages.get(rec["run_id"], set()))
    stx = {}
    if rec["scenario"] == "S5":
        stx = {"named": s5[(rec["run_id"], "named")],
               "disposed": s5[(rec["run_id"], "disposed")],
               "_s5_total": s5[(rec["run_id"], "ablated")]}
        sb = scenario_beats(rec, stx, lanes)
    else:
        sb = scenario_beats(rec, st, lanes)
    allbeats = dict(beats, **sb)
    vio = violations(rec, toks, beats, order, attester, units_flags.get(rec["run_id"], {}))
    bonus = []
    if rec["scenario"] == "S4" and "integrated" in st:
        bonus.append("integrated")
    nconf, nmiss, nviol, meets = normative(rec, beats, order, ver_ran, st, stx, lanes,
                                           units_flags, s3cls or {}, s5ov or set(), toks)
    reached = sum(1 for v in allbeats.values() if v)
    conf = round(reached / len(allbeats), 3) if allbeats else 0.0
    verdict = ("accepted" if conf >= 0.8 and not vio else
               "degraded" if conf >= 0.5 and (conf >= 0.8 or not vio) else "bad")
    return dict(run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],
                dose=rec["dose"], task=rec["task"],
                beats_expected=len(allbeats), beats_reached=reached, conformance=conf,
                missing=";".join(sorted(k for k, v in allbeats.items() if not v)),
                orderings=";".join("%s=%s" % (k, "ok" if v else "VIOLATED")
                                   for k, v in sorted(order.items())),
                violations=";".join(vio), verdict=verdict,
                verifier_executed=int(ver_ran),
                n_report_no_work=units_flags.get(rec["run_id"], {}).get("report_no_work", 0)
                if hasattr(units_flags, "get") else 0, bonus=";".join(bonus),
                normative_conformance=nconf, normative_missing=nmiss,
                normative_violations=nviol, meets_design=meets,
                regrade_score=rec["regrade_score"], regrade_pass=rec["regrade_pass"])

# build the output tables from the raw streams
def build():
    idx, strips, stages, s5, uf, s3cls, s5ov = load_all()
    rows = [score_run(r, strips, stages, s5, uf, s3cls, s5ov) for r in idx]
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "conformance.tsv"), "w", encoding="utf-8",
                 newline="") as f:
        w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("wrote out/conformance.tsv (%d runs)" % len(rows))
    report(rows)
    return rows

# print the human-readable summary
def report(rows):
    print("\n=== verdicts by scenario ===")
    print("%-5s %9s %9s %5s %14s" % ("scen", "accepted", "degraded", "bad", "mean conf"))
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc]
        c = Counter(r["verdict"] for r in rs)
        print("%-5s %9d %9d %5d %14.3f" % (sc, c["accepted"], c["degraded"], c["bad"],
                                           sum(r["conformance"] for r in rs) / len(rs)))
    print("\nmost common violations: %s" % dict(Counter(
        v.split("(")[0] for r in rows for v in r["violations"].split(";") if v).most_common()))
    print("most common missing beats: %s" % dict(Counter(
        m for r in rows for m in r["missing"].split(";") if m).most_common(8)))

    print("\n=== NORMATIVE reference (REFERENCE_TRAJECTORIES.md — PROVISIONAL pending "
          "user sign-off) ===")
    print("%-5s %12s %11s %8s %11s" % ("scen", "descriptive", "normative", "gap", "meets"))
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc]
        d = sum(r["conformance"] for r in rs) / len(rs)
        n = sum(r["normative_conformance"] for r in rs) / len(rs)
        print("%-5s %12.3f %11.3f %8.3f %8d/%d" % (sc, d, n, d - n,
                                                   sum(r["meets_design"] for r in rs),
                                                   len(rs)))
    print("meets_design corpus-wide: %d/%d" % (sum(r["meets_design"] for r in rows),
                                               len(rows)))
    print("normative violations: %s" % dict(Counter(
        x.split("(")[0] for r in rows for x in r["normative_violations"].split(";")
        if x).most_common()))
    print("normative missing beats: %s" % dict(Counter(
        m for r in rows for m in r["normative_missing"].split(";") if m).most_common(6)))

    lib_p = os.path.join(OUT, "library_index.tsv")
    if not os.path.isfile(lib_p):
        return
    lib = {r["run_id"]: r["cls"] for r in rix.read_tsv(lib_p)}
    by = {r["run_id"]: r for r in rows}
    print("\n=== validation against the Phase-5 library (held-out oracle) ===")
    print("%-5s %-9s %-44s %5s %-9s %s" % ("scen", "class", "run", "conf", "verdict",
                                           "violations / missing"))
    for rid, cls in sorted(lib.items(), key=lambda kv: (by[kv[0]]["scenario"], kv[1])):
        r = by.get(rid)
        if not r:
            continue
        det = r["violations"] or ("missing: " + r["missing"] if r["missing"] else "-")
        print("%-5s %-9s %-44s %5.2f %-9s %s" % (r["scenario"], cls, rid[:44],
                                                 r["conformance"], r["verdict"], det[:60]))
    g = [by[k]["conformance"] for k, c in lib.items() if c == "gold" and k in by]
    f = [by[k]["conformance"] for k, c in lib.items() if c == "failure" and k in by]
    ga = sum(1 for k, c in lib.items() if c == "gold" and by[k]["verdict"] == "accepted")
    fa = sum(1 for k, c in lib.items() if c == "failure" and by[k]["verdict"] == "accepted")
    print("\ngold: mean conf %.3f, %d/%d accepted | failure: mean conf %.3f, %d/%d accepted"
          % (sum(g) / len(g), ga, len(g), sum(f) / len(f), fa, len(f)))

def show(run_id):
    idx, strips, stages, s5, uf, s3cls, s5ov = load_all()
    rec = next((r for r in idx if r["run_id"] == run_id), None)
    if rec is None:
        sys.exit("unknown run_id: " + run_id)
    r = score_run(rec, strips, stages, s5, uf, s3cls, s5ov)
    print("\n=== %s (%s, score %s) ===" % (run_id, rec["scenario"], rec["regrade_score"]))
    print("conformance %s (%d/%d)  verdict %s" % (r["conformance"], r["beats_reached"],
                                                  r["beats_expected"], r["verdict"]))
    print("missing:    %s" % (r["missing"] or "-"))
    print("orderings:  %s" % (r["orderings"] or "-"))
    print("violations: %s" % (r["violations"] or "-"))

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx, strips, stages, s5, uf, s3cls, s5ov = load_all()
    by = {}
    for rec in idx:
        by[rec["run_id"]] = score_run(rec, strips, stages, s5, uf, s3cls, s5ov)
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-64s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    r = by["crypto1_s3partial-20260808-211436"]
    check("S3 gold: full conformance, accepted", r["conformance"] >= 0.9
          and r["verdict"] == "accepted", "conf=%s verdict=%s" % (r["conformance"], r["verdict"]))
    r = by["p5_s3partial-20260808-204549"]
    check("S3 anti-exemplar: `recovered` missing, not accepted",
          "recovered" in r["missing"] and r["verdict"] != "accepted",
          "missing=%s verdict=%s" % (r["missing"], r["verdict"]))

    r = by["P6_enforced-20260808-143229"]
    check("P6 (no trajectory at all) is `bad`", r["verdict"] == "bad",
          "conf=%s" % r["conformance"])
    lib = {x["run_id"]: x["cls"] for x in rix.read_tsv(os.path.join(OUT, "library_index.tsv"))}
    g = {k: by[k] for k, c in lib.items() if c == "gold" and k in by}
    f = {k: by[k] for k, c in lib.items() if c == "failure" and k in by}
    check("library golds outrank failures on mean conformance",
          sum(x["conformance"] for x in g.values()) / len(g)
          > sum(x["conformance"] for x in f.values()) / len(f),
          "gold %.3f vs failure %.3f" % (sum(x["conformance"] for x in g.values()) / len(g),
                                         sum(x["conformance"] for x in f.values()) / len(f)))
    ng = sum(1 for x in g.values() if x["verdict"] == "accepted")
    check("every library gold is `accepted`", ng == len(g), "%d/%d" % (ng, len(g)))

    fn = ["cr4_enforced-20260808-114309", "ir2_prompt-only-20260810-100536",
          "P3_enforced-20260808-134613", "test1_enforced-20260808-125124"]
    ok_fn = [k for k in fn if by[k]["verdict"] == "accepted"]
    check("known content-defect failures stay accepted (documented false negatives)",
          len(ok_fn) == len(fn), "%d/%d accepted" % (len(ok_fn), len(fn)))

    bf = ["crypto1_s3full-20260808-230358", "p5_s3partial-20260808-204549",
          "lh5_s4-20260809-081250", "P6_enforced-20260808-143229"]
    ok_bf = [k for k in bf if by[k]["verdict"] != "accepted"]
    check("behavioural failures are not accepted", len(ok_bf) == len(bf),
          "%d/%d flagged" % (len(ok_bf), len(bf)))

    r = by["cr4_enforced-20260808-114309"]
    check("NORM: cr4's laundering is now visible (attest-without-own-evidence)",
          "attest-without-own-evidence" in r["normative_violations"],
          r["normative_violations"])
    r = by["spec5_s5partial-20260809-154345"]
    check("NORM: spec5's disposition failure is now visible (named-gap-overruled)",
          "named-gap-overruled" in r["normative_violations"], r["normative_violations"])
    r = by["P10_prompt-only-20260808-055135"]
    check("NORM: the S2 exemplar meets the design outright", r["meets_design"] == 1,
          "norm=%s" % r["normative_conformance"])
    n_meets = sum(1 for x in by.values() if x["meets_design"])
    check("NORM: meeting the design is rare (the shallow-verification finding)",
          n_meets < 40, "%d/168 meet" % n_meets)
    return 1 if bad else 0

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg:
        show(arg)
    else:
        build()
