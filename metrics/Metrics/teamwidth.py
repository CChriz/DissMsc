# The team-width funnel per run: pool, engaged, assigned by the leader,
# and contributing to a deliverable.
import csv, io, os, sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
ENGAGED_TOK = 2000

def build_rows():
    with io.open(os.path.join(OUT, "member_metrics.csv"), encoding="utf-8") as f:
        mm = list(csv.DictReader(f))
    bt = rix.read_tsv(os.path.join(OUT, "board_tasks.tsv"))
    back = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "backtrace.tsv"))}
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}

    pool = defaultdict(int)
    engaged = defaultdict(int)
    for m in mm:
        pool[m["run_id"]] += 1
        if int(m["output_tokens"]) > ENGAGED_TOK:
            engaged[m["run_id"]] += 1
    assigned = defaultdict(set)
    for t in bt:
        if t["preassignee"]:
            assigned[t["run_id"]].add(t["preassignee"])

    rows = []
    for rid, rec in sorted(idx.items()):
        b = back.get(rid, {})
        rows.append(dict(
            run_id=rid, scenario=rec["scenario"], arm=rec["arm"], dose=rec["dose"],
            task=rec["task"], pool=pool[rid], engaged=engaged[rid],
            assigned=len(assigned[rid]),
            contributing=int(b["contributing"]) if b.get("contributing") else "",
            active_bt=int(b["active"]) if b.get("active") else ""))
    return rows

def _mean(vs):
    vs = [v for v in vs if v != ""]
    return sum(vs) / len(vs) if vs else 0

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

    p("# Team width: pool → engaged → assigned → contributing (mean members per run)")
    p()
    p("engaged = >%d output tokens; assigned = distinct board assignees named by the "
      "leader; contributing = in a deliverable's ancestry (backtrace)." % ENGAGED_TOK)
    p()
    for arm in ("1", "2"):
        p("## Arm-%s (%s personas)" % (arm, "base" if arm == "1" else "specialist"))
        p()
        p("| scen | runs | pool | engaged | assigned | contributing | contributing/engaged |")
        p("|---|---|---|---|---|---|---|")
        for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
            rs = [r for r in rows if r["scenario"] == sc and r["arm"] == arm]
            if not rs:
                continue
            e, a, c = _mean([r["engaged"] for r in rs]), \
                _mean([r["assigned"] for r in rs]), \
                _mean([r["contributing"] for r in rs])
            p("| %s | %d | %.1f | %.1f | %.1f | %.1f | %.0f%% |" % (
                sc, len(rs), _mean([r["pool"] for r in rs]), e, a, c,
                100 * c / e if e else 0))
        p()
    p("Read: the pool is constant (9) but the effective team is not — the leader "
      "assigns ~3-5, most of the pool engages anyway, and only a fraction of engaged "
      "members' work reaches a deliverable. The engaged→contributing drop is the "
      "spend that buys no artifact.")
    return L

# build the output tables from the raw streams
def build():
    rows = build_rows()
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "teamwidth.tsv"), "w", encoding="utf-8",
                 newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")
    print("wrote out/teamwidth.tsv (%d runs)\n" % len(rows))
    L = report(rows)
    io.open(os.path.join(OUT, "teamwidth_summary.md"), "w", encoding="utf-8").write(
        "\n".join(L) + "\n")
    print("\nwrote out/teamwidth_summary.md")
    return rows

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    rows = build_rows()
    by = {r["run_id"]: r for r in rows}
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-66s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    off = [r["run_id"] for r in rows if r["pool"] != 9]
    check("pool = 9 on every run except the P6 SPOF",
          off == ["P6_enforced-20260808-143229"]
          and by["P6_enforced-20260808-143229"]["pool"] == 1,
          "exceptions=%s" % off)

    check("cr4-S5-arm2: 3 distinct assignees (annotated pinning triple)",
          by["cr4_s5partial_arm2-20260809-195057"]["assigned"] == 3,
          by["cr4_s5partial_arm2-20260809-195057"]["assigned"])
    check("test9-S5-arm2: 4 distinct assignees (hand-read board story)",
          by["test9_s5minimal_arm2-20260809-220537"]["assigned"] == 4,
          by["test9_s5minimal_arm2-20260809-220537"]["assigned"])

    pairs = [(r["contributing"], r["active_bt"]) for r in rows
             if r["contributing"] != "" and r["active_bt"]]
    share = sum(c for c, a in pairs) / sum(a for c, a in pairs)
    check("contributing/active reconciles with current backtrace (~59%)",
          0.55 <= share <= 0.63, "%.2f" % share)

    viol = [r["run_id"] for r in rows
            if r["engaged"] > r["pool"] or r["assigned"] > r["pool"]
            or (r["contributing"] != "" and r["contributing"] > r["pool"])]
    check("engaged/assigned/contributing never exceed the pool", not viol,
          "violations=%s" % (viol[:3] or "none"))
    return 1 if bad else 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
