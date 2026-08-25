# Traces the plan-work-verify baton through connected hands and censuses
# everything that happens off-chain.
import csv, io, os, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix
from conformance import parse_strip

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

IMPL = ("EXEC", "FULL")

def _first(toks, pred, start=0):
    for i in range(start, len(toks)):
        if pred(toks[i]):
            return i
    return None

def trace_chain(toks):
    links, consumed = {}, set()

    def take(name, i):
        if i is not None:
            links[name] = i
            consumed.add(i)
        return i

    i_board = take("board", _first(toks, lambda t: t["verb"] == "CREATE_TASKS"))
    take("kickoff", _first(toks, lambda t: t["who"] == "LEAD"
                           and t["verb"] in ("MSG", "BROADCAST"),
                           (i_board or 0)))
    take("spec-consult", _first(toks, lambda t: t["who"].startswith("PLAN")
                                and ((t["verb"] == "READ" and "spec" in t["args"])
                                     or (t["verb"] == "DENIED"
                                         and t["args"] & {"spec", "brief"}))))
    i_hand = take("plan-handoff", _first(
        toks, lambda t: t["who"].startswith("PLAN") and t["verb"] in ("MSG", "BROADCAST")
        and t["args"] & {"M", "L", "XL"}
        and (t["tgt"] == "*" or t["tgt"].startswith(IMPL)), (i_board or 0)))
    carrier = toks[i_hand]["tgt"] if i_hand is not None else None
    if carrier == "*":
        carrier = None

    i_work = take("work", _first(
        toks, lambda t: t["who"].startswith(IMPL)
        and ((t["verb"] == "WRITE" and t["args"] & {"workspace", "workspace/tests", "spec"})
             or (t["verb"] == "RUN" and "test" in t["args"])),
        (i_hand if i_hand is not None else 0)))
    worker = toks[i_work]["who"] if i_work is not None else None
    work_intact = (i_work is not None and (carrier is None or worker == carrier))

    i_wh = take("work-handoff", _first(
        toks, lambda t: t["who"] == worker
        and ((t["verb"] == "MSG" and (t["tgt"].startswith("VER") or t["tgt"] == "LEAD"))
             or t["verb"] == "DONE"),
        (i_work if i_work is not None else 0)) if worker else None)
    designate = (toks[i_wh]["tgt"] if i_wh is not None
                 and toks[i_wh]["verb"] == "MSG" else None)
    if designate is not None and not designate.startswith("VER"):
        designate = None

    i_att = take("attest", _first(
        toks, lambda t: t["who"].startswith(("VER", "FULL"))
        and t["verb"] == "WRITE" and "attestation" in t["args"],
        (i_wh if i_wh is not None else (i_work if i_work is not None else 0))))
    att_intact = (i_att is not None
                  and (designate is None or toks[i_att]["who"] == designate))

    complete = all(k in links for k in ("board", "plan-handoff", "work",
                                        "work-handoff", "attest"))
    return links, consumed, dict(carrier=carrier or "", worker=worker or "",
                                 designate=designate or "",
                                 work_link=("intact" if work_intact else
                                            "broken" if i_work is not None else "absent"),
                                 attest_link=("intact" if att_intact else
                                              "broken" if i_att is not None else "absent"),
                                 complete=int(complete))

def branches(toks, consumed, links):
    link_at = sorted((i, name) for name, i in links.items())
    chain_actors = {toks[i]["who"] for i in consumed}
    segs = []
    per_actor = defaultdict(list)
    for i, t in enumerate(toks):
        if i not in consumed:
            per_actor[t["who"]].append(i)
    for who, idxs in per_actor.items():
        seg = [idxs[0]]
        for a, b in zip(idxs, idxs[1:]):
            if b - a <= 3:
                seg.append(b)
            else:
                segs.append((who, seg))
                seg = [b]
        segs.append((who, seg))
    out = []
    for who, seg in segs:
        fork = ""
        for i, name in link_at:
            if i <= seg[0]:
                fork = name
        comp = Counter()
        merges = False
        for i in seg:
            t = toks[i]
            comp[t["verb"]] += t["n"]
            if t["verb"] in ("MSG", "BROADCAST") and (
                    t["tgt"] == "*" or t["tgt"] in chain_actors):
                after = [j for j in consumed if j > i and toks[j]["who"] ==
                         (None if t["tgt"] == "*" else t["tgt"])]
                if t["tgt"] == "*" or after:
                    merges = True
        out.append(dict(actor=who, beats=sum(comp.values()), after=fork or "start",
                        composition=";".join("%s=%d" % kv for kv in comp.most_common(4)),
                        fate="merges" if merges else "dies"))
    return out

def strips_by_run():
    out = defaultdict(dict)
    for r in rix.read_tsv(os.path.join(OUT, "canon_strips.tsv")):
        out[r["run_id"]][r["lane"]] = r["strip"]
    return out

def trace_run(rec, strips):
    rows = []
    all_lanes = strips.get(rec["run_id"], {})
    if rec["scenario"] == "S2":
        subs = sorted({l.split("-")[0] for l in all_lanes
                       if l not in ("*", "-") and "-" in l})
        lanes = subs or ["*"]
    else:
        lanes = ["*"]
    for lane in lanes:
        if rec["scenario"] == "S2" and lane != "*":
            parts = [all_lanes.get("-", "")]
            for ph in ("plan", "impl", "implement", "verify"):
                for l, st in sorted(all_lanes.items()):
                    if l.startswith(lane + "-") and ph in l:
                        parts.append(st)
            toks = parse_strip(" · ".join(x for x in parts if x))
        else:
            toks = parse_strip(all_lanes.get(lane, ""))
        links, consumed, flags = trace_chain(toks)
        brs = branches(toks, consumed, links)
        rows.append(dict(
            run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],
            dose=rec["dose"], task=rec["task"], lane=lane,
            chain=" > ".join("%s@%d" % (k, links[k]) for k in
                             ("board", "kickoff", "spec-consult", "plan-handoff",
                              "work", "work-handoff", "attest") if k in links),
            missing=";".join(k for k in ("board", "plan-handoff", "work",
                                         "work-handoff", "attest") if k not in links),
            **flags,
            n_branches=len(brs), branch_beats=sum(b["beats"] for b in brs),
            chain_beats=len(consumed),
            branches=" | ".join("%s after %s: %s -> %s" % (
                b["actor"], b["after"], b["composition"], b["fate"])
                for b in sorted(brs, key=lambda x: -x["beats"])[:6])))
    return rows

# build the output tables from the raw streams
def build():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    strips = strips_by_run()
    rows = []
    for rec in idx:
        rows += trace_run(rec, strips)
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "chains.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("wrote out/chains.tsv (%d chains over %d runs)"
          % (len(rows), len({r['run_id'] for r in rows})))
    report(rows)
    return rows

# print the human-readable summary
def report(rows):
    print("\n=== HANDOFF CHAIN completion and connectivity, per scenario ===")
    print("%-5s %7s %9s %13s %13s %11s" % ("scen", "chains", "complete", "work-intact",
                                           "attest-intact", "brk/absent"))
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc]
        if not rs:
            continue
        print("%-5s %7d %9d %13d %13d %11d" % (
            sc, len(rs), sum(r["complete"] for r in rs),
            sum(1 for r in rs if r["work_link"] == "intact"),
            sum(1 for r in rs if r["attest_link"] == "intact"),
            sum(1 for r in rs if "broken" in (r["work_link"], r["attest_link"]))))

    print("\n=== the BRANCH CENSUS: what lives off the main chain ===")
    comp = Counter()
    fates = Counter()
    n_br = 0
    for r in rows:
        n_br += r["n_branches"]
        for b in r["branches"].split(" | "):
            if not b:
                continue
            fates[b.rsplit("-> ", 1)[-1]] += 1
            for kv in b.split(": ", 1)[-1].split(" -> ")[0].split(";"):
                if "=" in kv:
                    k, v = kv.split("=")
                    try:
                        comp[k] += int(v)
                    except ValueError:
                        pass
    tot_branch = sum(r["branch_beats"] for r in rows)
    tot_chain = sum(r["chain_beats"] for r in rows)
    print("branches: %d · branch beats %d vs chain beats %d (%.0f%% of activity is "
          "off-chain)" % (n_br, tot_branch, tot_chain,
                          100.0 * tot_branch / (tot_branch + tot_chain)))
    print("branch composition (top): %s" % dict(comp.most_common(8)))
    print("branch fates (of the largest-6 per run): %s" % dict(fates))

    missing = Counter(m for r in rows for m in r["missing"].split(";") if m)
    print("\nmissing chain links: %s" % dict(missing.most_common()))

def show(run_id):
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    if run_id not in idx:
        sys.exit("unknown run_id: " + run_id)
    for r in trace_run(idx[run_id], strips_by_run()):
        print("\n=== %s lane=%s (%s) ===" % (run_id, r["lane"], r["scenario"]))
        print("chain:    %s" % r["chain"])
        print("carrier=%s worker=%s designate=%s | work_link=%s attest_link=%s complete=%d"
              % (r["carrier"], r["worker"], r["designate"], r["work_link"],
                 r["attest_link"], r["complete"]))
        if r["missing"]:
            print("missing:  %s" % r["missing"])
        print("branches (%d, %d beats vs %d chain beats):"
              % (r["n_branches"], r["branch_beats"], r["chain_beats"]))
        for b in r["branches"].split(" | "):
            if b:
                print("   " + b)

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    strips = strips_by_run()

    def one(rid):
        return trace_run(idx[rid], strips)[0]

    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-62s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    r = one("crypto1_enforced-20260808-114845")
    check("S1A gold: complete chain, work by the plan recipient",
          r["complete"] == 1 and r["work_link"] == "intact",
          "work=%s attest=%s carrier=%s worker=%s"
          % (r["work_link"], r["attest_link"], r["carrier"], r["worker"]))
    r = one("cr4_enforced-20260808-114309")
    check("cr4: chain completes; the annotated 16-attempt debug episode is a branch",
          r["complete"] == 1 and any("RUN=1" in b and "dies" in b
                                     for b in r["branches"].split(" | ")),
          "attest_link=%s branches=%s" % (r["attest_link"], r["branches"][:60]))
    r = one("p5_s3partial-20260808-204549")
    check("p5_s3partial: the baton never reaches `work`",
          "work" in r["missing"] or r["work_link"] == "absent", "missing=%s" % r["missing"])
    r = one("P6_enforced-20260808-143229")
    check("P6: no chain at all", r["complete"] == 0 and r["chain_beats"] <= 1,
          "chain=%s" % r["chain"])
    rows = trace_run(idx["P10_prompt-only-20260808-055135"], strips)
    check("P10 traces per lane (two chains by design)", len(rows) >= 2,
          "%d lanes: %s" % (len(rows), [r["lane"] for r in rows]))
    return 1 if bad else 0

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg:
        show(arg)
    else:
        build()
