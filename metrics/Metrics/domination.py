# Workload concentration per run: effective contributors by turns,
# actions, tokens and deliverable writes.
import csv, io, json, os, sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
DIMS = ("turns", "actions", "tokens", "writes")

def load():
    with io.open(os.path.join(OUT, "member_metrics.csv"), encoding="utf-8") as f:
        mm = list(csv.DictReader(f))
    part = rix.read_tsv(os.path.join(OUT, "participation.tsv"))
    writes = {(r["run_id"], r["member"]): int(r["deliver_writes"]) for r in part}
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    per_run = defaultdict(list)
    for m in mm:
        per_run[m["run_id"]].append(dict(
            member=m["member"], role=m["role_group"],
            turns=int(m["turns"]), actions=int(m["actions"]),
            tokens=int(m["output_tokens"]),
            writes=writes.get((m["run_id"], m["member"]), 0)))
    return per_run, idx

def concentration(vals):
    tot = sum(vals)
    if not tot:
        return "", "", ""
    shares = [v / tot for v in vals]
    hhi = sum(s * s for s in shares)
    return round(max(shares), 3), round(hhi, 3), round(1.0 / hhi, 2)

def build_rows(per_run, idx):
    rows = []
    for rid, members in sorted(per_run.items()):
        rec = idx.get(rid)
        if not rec:
            continue
        row = dict(run_id=rid, scenario=rec["scenario"], arm=rec["arm"],
                   dose=rec["dose"], task=rec["task"], members=len(members),
                   score=rec["regrade_score"])
        for dim in DIMS:
            vals = [m[dim] for m in members]
            top, hhi, eff = concentration(vals)
            top_m = max(members, key=lambda m: m[dim]) if sum(vals) else None
            row["top_" + dim] = top_m["member"] if top_m else ""
            row["top_%s_role" % dim] = top_m["role"] if top_m else ""
            row["top_%s_share" % dim] = top
            row["hhi_" + dim] = hhi
            row["eff_" + dim] = eff
        rows.append(row)
    return rows

def _write(path, rows):
    cols = list(rows[0].keys())
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")

def enf_only_arm1(rows):
    cond = {r["run_id"]: r["condition"]
            for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    return [r for r in rows
            if not (r["arm"] == "1" and cond.get(r["run_id"]) == "prompt-only")]

# print the human-readable summary
def report(rows):
    rows = enf_only_arm1(rows)
    L = []

    def p(s=""):
        L.append(s)
        print(s)

    scens = ("S1A", "S1B", "S2", "S3", "S4", "S5")
    p("# Workload domination (concentration per run; leader included)")
    p()
    p("eff = effective contributors (1/HHI): 9 = spread over the whole pool, 1 = solo.")
    p()
    for arm in ("1", "2"):
        p("## Arm-%s (%s personas)" % (arm, "base" if arm == "1" else "specialist"))
        p()
        p("| scen | runs | top turn share | eff (turns) | eff (actions) | eff (tokens) "
          "| top WRITER share | eff (writes) | leader is top writer |")
        p("|---|---|---|---|---|---|---|---|---|")
        for sc in scens:
            rs = [r for r in rows if r["scenario"] == sc and r["arm"] == arm]
            if not rs:
                continue
            n = len(rs)

            def mean(k):
                vs = [r[k] for r in rs if r[k] != ""]
                return sum(vs) / len(vs) if vs else 0

            p("| %s | %d | %.2f | %.1f | %.1f | %.1f | %.2f | %.1f | %d |" % (
                sc, n, mean("top_turns_share"), mean("eff_turns"), mean("eff_actions"),
                mean("eff_tokens"), mean("top_writes_share"), mean("eff_writes"),
                sum(1 for r in rs if r["top_writes_role"] == "leader")))
        p()
    p("## Who dominates, by currency (corpus-wide top-member role)")
    p()
    p("| currency | planner | executor | verifier | fullstack | leader |")
    p("|---|---|---|---|---|---|")
    from collections import Counter
    for dim in DIMS:
        c = Counter(r["top_%s_role" % dim] for r in rows if r["top_%s_role" % dim])
        p("| %s | %s |" % (dim, " | ".join(str(c.get(g, 0)) for g in
                                           ("planner", "executor", "verifier",
                                            "fullstack", "leader"))))
    p()
    p("Read: ACTIVITY concentration is scenario-invariant (turns spread to ~8 of 9 "
      "members everywhere — stress never concentrates effort), while AUTHORSHIP is "
      "always concentrated (~2 effective writers of 9) and is the currency where the "
      "treatments show: S2 has the most authors (two deliverables), S4 next (the write "
      "partition forces two), S3 the fewest (blocking writers concentrates authorship "
      "onto the survivor or leader). Leader-as-top-writer clusters in S3's "
      "leader-intervened class.")
    return L

# build the output tables from the raw streams
def build():
    per_run, idx = load()
    rows = build_rows(per_run, idx)
    _write(os.path.join(OUT, "domination.tsv"), rows)
    print("wrote out/domination.tsv (%d runs)\n" % len(rows))
    L = report(rows)
    io.open(os.path.join(OUT, "domination_summary.md"), "w", encoding="utf-8").write(
        "\n".join(L) + "\n")
    print("\nwrote out/domination_summary.md")
    return rows

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    per_run, idx = load()
    rows = build_rows(per_run, idx)
    by = {r["run_id"]: r for r in rows}
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-66s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    a = by["cr4_s5partial_arm2-20260809-195057"]
    b = by["test9_s5minimal_arm2-20260809-220537"]
    check("cr4-S5-arm2 more concentrated than test9-S5-arm2 (annotated rosters)",
          a["hhi_actions"] > b["hhi_actions"] and a["hhi_turns"] > b["hhi_turns"],
          "hhi_actions %.3f vs %.3f, hhi_turns %.3f vs %.3f"
          % (a["hhi_actions"], b["hhi_actions"], a["hhi_turns"], b["hhi_turns"]))

    check("cr4-S5-arm2: executor1 dominates actions (annotated 54 tools)",
          a["top_actions"] == "executor1", a["top_actions"])

    eff = {}
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        vs = [r["eff_writes"] for r in rows if r["scenario"] == sc and r["eff_writes"] != ""]
        eff[sc] = sum(vs) / len(vs)
    check("effective AUTHORS: S2 max; S3 min among stress scenarios (S4, S5)",
          max(eff, key=eff.get) == "S2" and eff["S3"] < eff["S4"] and eff["S3"] < eff["S5"],
          {k: round(v, 2) for k, v in sorted(eff.items())})

    cls = {r.get("run_id", ""): r.get("primary", "") for r in
           json.load(io.open(os.path.join(OUT, "s3_classification.json"),
                             encoding="utf-8"))}
    li = [by[k] for k, v in cls.items() if v == "leader-intervened" and k in by]
    sv = [by[k] for k, v in cls.items() if v == "survivor-path" and k in by]
    r_li = sum(1 for r in li if r["top_writes_role"] == "leader") / len(li)
    r_sv = sum(1 for r in sv if r["top_writes_role"] == "leader") / len(sv)
    check("leader tops writes more often in leader-intervened than survivor-path",
          r_li > r_sv, "%.2f (n=%d) vs %.2f (n=%d)" % (r_li, len(li), r_sv, len(sv)))

    okv = all(0 < r["top_%s_share" % d] <= 1 and 1.0 / r["members"] - 1e-9 <= r["hhi_" + d] <= 1
              and r["eff_" + d] <= r["members"] + 1e-9
              for r in rows for d in DIMS if r["hhi_" + d] != "")
    check("concentration invariants hold on all runs x currencies", okv, "168 runs x 4")
    return 1 if bad else 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
