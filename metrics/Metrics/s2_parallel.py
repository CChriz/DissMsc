# S2 bundles vs their single-task runs: overlap, speedup, token cost,
# and why slow bundles were slow.
import io, os, re, sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace
import run_index as rix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RUNS_ROOT = rix.RUNS_ROOT

TASK_ROW = re.compile(r"\('([^']+)',\s*'([^']*)',\s*'([^']*)'\)")

BASELINE = {"S2_pairs_pro": "S1A_team_dyn_pro", "S2_pairs_enf_pro": "S1A_team_enf_pro",
            "S2_pairs_enf_pro_arm2": "S1A_team_dyn_pro_arm2"}

def bundle_subtasks(batch):
    out = defaultdict(list)
    for r in rix.read_tsv(os.path.join(RUNS_ROOT, batch, "s2_regrade.tsv")):
        out[r["bundle"]].append(r["subtask"])
    return out

def task_table(archive):
    p = os.path.join(archive, "task_table.txt")
    if not os.path.isfile(p):
        return []
    txt = io.open(p, encoding="utf-8", errors="replace").read()
    return TASK_ROW.findall(txt)

def id_matches(task_id, subtask):
    alias = subtask.split("_")[0]
    for name in {subtask, alias}:
        if re.search(r"(?:^|[^a-z0-9])%s(?:[^a-z0-9]|$)" % re.escape(name),
                     task_id, re.I):
            return True
    return False

def span_of(intervals):
    return (min(s for s, _e, _t in intervals), max(e for _s, e, _t in intervals))

def overlap_ratio(a, b):
    if not a or not b:
        return ""
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return round(inter / union, 3) if union > 0 else ""

def analyse(rec, subtasks, singles):
    run = teamtrace.load_run(rec["archive_path"])
    ivs = {m["member"]: teamtrace.member_intervals(m) for m in run["members"]
           if m["member"] != "team_leader"}
    active = {m: sum(e - s for s, e, _ in v) for m, v in ivs.items() if v}
    rows = task_table(rec["archive_path"])

    members_of = {t: set() for t in subtasks}
    for task_id, member, _status in rows:
        for t in subtasks:
            if id_matches(task_id, t):
                members_of[t].add(member)
    shared = set.intersection(*members_of.values()) if len(members_of) > 1 else set()
    spans, engaged = {}, {}
    for t in subtasks:
        excl = [m for m in members_of[t] - shared if ivs.get(m)]
        engaged[t] = len(members_of[t])
        spans[t] = span_of([iv for m in excl for iv in ivs[m]]) if excl else None

    a, b = (subtasks + ["", ""])[:2]
    ov = overlap_ratio(spans.get(a), spans.get(b))

    prof = teamtrace.concurrency_profile(run)
    team_active = sum(prof.values())
    concurrent = sum(v for k, v in prof.items() if k >= 2)
    conc_share = round(concurrent / team_active, 3) if team_active else ""

    gaps = teamtrace.classify_gaps(run)
    dep_wait = round(sum(g["dur_s"] for g in gaps if g["kind"] == "dependency_wait"), 1)
    stall_s = round(sum(g["dur_s"] for g in gaps if g["kind"] == "stall"), 1)
    lead_gap = ""
    if spans.get(a) and spans.get(b):
        lead_gap = round(abs(spans[a][0] - spans[b][0]), 1)

    base = [singles.get(t) for t in subtasks]
    speedup = ""
    if all(base) and rix.fnum(rec["span_s"], 0):
        tot = sum(rix.fnum(s["span"], 0) for s in base)
        speedup = round(tot / rix.fnum(rec["span_s"]), 2)

    token_ratio = turn_ratio = ""
    if all(base):
        s_out = sum(s["out"] for s in base)
        s_turns = sum(s["turns"] for s in base)
        if s_out:
            token_ratio = round(rix.fnum(rec["output_tokens"], 0) / s_out, 2)
        if s_turns:
            turn_ratio = round(rix.fnum(rec["turns"], 0) / s_turns, 2)

    sub_scores = {}
    for kv in (rec["subtask_scores"] or "").split(";"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            sub_scores[k] = rix.fnum(v, None)
    d_scores = {}
    for t in subtasks:
        s1 = singles.get(t)
        if s1 and s1["score"] is not None and sub_scores.get(t) is not None:
            d_scores[t] = round(sub_scores[t] - s1["score"], 3)

    no_task = [m for m in ivs if not any(m in members_of[t] for t in subtasks)]

    usable = int(bool(spans.get(a)) and bool(spans.get(b)))
    return dict(
        usable=usable,
        run_id=rec["run_id"], batch=rec["batch"], condition=rec["condition"],
        bundle=rec["task"], subtask_a=a, subtask_b=b,
        span_s=rec["span_s"], span_a=round(spans[a][1] - spans[a][0], 1) if spans.get(a) else "",
        span_b=round(spans[b][1] - spans[b][0], 1) if spans.get(b) else "",
        overlap=ov, team_concurrency=conc_share,
        single_a=(base[0] or {}).get("span", ""), single_b=(base[1] or {}).get("span", ""),
        speedup=speedup,
        token_ratio=token_ratio, turn_ratio=turn_ratio,
        d_score_a=d_scores.get(a, ""), d_score_b=d_scores.get(b, ""),
        engaged_a=engaged.get(a, 0), engaged_b=engaged.get(b, 0),
        shared_members=len(shared), members_without_task=len(no_task),
        first_assign_gap_s=lead_gap, dependency_wait_s=dep_wait, stall_s=stall_s,
        outcome=rec["framework_outcome"], score=rec["regrade_score"])

def singles_by_task(batch):
    out = {}
    for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv")):
        if r["batch"] == BASELINE.get(batch):
            out[r["task"]] = dict(span=r["span_s"],
                                  out=rix.fnum(r["output_tokens"], 0),
                                  turns=rix.fnum(r["turns"], 0),
                                  score=rix.fnum(r["regrade_score"], None))
    return out

# build the output tables from the raw streams
def build():
    idx = [r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
           if r["scenario"] == "S2"]
    rows = []
    for batch in sorted({r["batch"] for r in idx}):
        subs = bundle_subtasks(batch)
        singles = singles_by_task(batch)
        for rec in [r for r in idx if r["batch"] == batch]:
            st = subs.get(rec["task"], [])
            if len(st) != 2:
                print("  -- skip %s: %d subtasks in regrade" % (rec["run_id"], len(st)))
                continue
            rows.append(analyse(rec, st, singles))
    cols = list(rows[0].keys())
    p = os.path.join(OUT, "s2_parallel.tsv")
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    print("wrote %s (%d bundle runs)\n" % (p, len(rows)))
    report(rows)
    return rows

# print the human-readable summary
def report(rows):
    print("%-30s %-9s %7s %7s %7s %7s %7s %6s %6s" % (
        "run", "bundle", "span", "ovlp", "conc", "singles", "speedup", "eng", "notask"))
    for r in sorted(rows, key=lambda x: (x["condition"], x["bundle"])):
        singles = ""
        if r["single_a"] and r["single_b"]:
            singles = "%d+%d" % (rix.fnum(r["single_a"], 0), rix.fnum(r["single_b"], 0))
        print("%-30s %-9s %7s %7s %7s %7s %7s %3d/%-2d %6d" % (
            r["run_id"][:30], "%s+%s" % (r["subtask_a"], r["subtask_b"]),
            r["span_s"], r["overlap"], r["team_concurrency"], singles, r["speedup"],
            r["engaged_a"], r["engaged_b"], r["members_without_task"]))

    ok = [r for r in rows if r["usable"] and r["speedup"] != ""]
    if ok:
        print("\nbundles with both measures (n=%d):" % len(ok))
        print("  mean chain overlap      %.2f" % (sum(r["overlap"] for r in ok) / len(ok)))
        print("  mean team concurrency   %.2f"
              % (sum(r["team_concurrency"] for r in ok) / len(ok)))
        print("  mean speedup vs singles %.2f  (>1 = bundling finished faster)"
              % (sum(r["speedup"] for r in ok) / len(ok)))
        faster = sum(1 for r in ok if r["speedup"] > 1)
        print("  bundles faster than the two singles: %d/%d" % (faster, len(ok)))
    unusable = [r for r in rows if not r["usable"]]
    if unusable:
        print("\nexcluded (a chain never ran or was not attributed): %d" % len(unusable))
        for r in unusable:
            print("  %-30s %s  outcome=%s" % (r["run_id"][:30],
                                              "%s+%s" % (r["subtask_a"], r["subtask_b"]),
                                              r["outcome"]))
    ser = [r for r in rows if r["usable"] and r["overlap"] < 0.5]
    print("\nserialised bundles (chain overlap < 0.5): %d" % len(ser))
    for r in ser:
        print("  %-30s overlap=%.2f  first-assign gap=%ss  dependency-wait=%ss  stall=%ss"
              % (r["run_id"][:30], r["overlap"], r["first_assign_gap_s"],
                 r["dependency_wait_s"], r["stall_s"]))

    print("\n=== COST OF THE SPEEDUP + SUBTASK SCORE DELTA, per lane (2026-08-23) ===")
    print("  ratio = bundle / (single_a + single_b); <1 = bundling also cheaper")

    def lane_of(r):
        return ("enforced arm-2" if "arm2" in r["batch"] else
                "enforced arm-1" if r["condition"] == "enforced" else
                "prompt-only arm-1")
    lanes = sorted({lane_of(r) for r in rows})
    for lane in lanes:
        rs = [r for r in rows if lane_of(r) == lane and r["token_ratio"] != ""]
        ds = [d for r in rows if lane_of(r) == lane
              for d in (r["d_score_a"], r["d_score_b"]) if d != ""]
        if not rs:
            continue
        tr = [r["token_ratio"] for r in rs]
        tu = [r["turn_ratio"] for r in rs if r["turn_ratio"] != ""]
        print("  %-18s n=%2d  token ratio mean %.2f (cheaper: %d/%d)  turn ratio %.2f"
              % (lane, len(rs), sum(tr) / len(tr),
                 sum(1 for x in tr if x < 1), len(tr),
                 sum(tu) / len(tu) if tu else 0))
        if ds:
            print("  %-18s subtask Δscore vs its single: mean %+.3f  "
                  "(drop %d / same %d / gain %d of %d)"
                  % ("", sum(ds) / len(ds),
                     sum(1 for d in ds if d < -0.05),
                     sum(1 for d in ds if abs(d) <= 0.05),
                     sum(1 for d in ds if d > 0.05), len(ds)))

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = [r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
           if r["scenario"] == "S2"]
    rows = {}
    for batch in sorted({r["batch"] for r in idx}):
        subs = bundle_subtasks(batch)
        singles = singles_by_task(batch)
        for rec in [r for r in idx if r["batch"] == batch]:
            st = subs.get(rec["task"], [])
            if len(st) == 2:
                rows[rec["run_id"]] = analyse(rec, st, singles)
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-58s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    p10 = rows.get("P10_prompt-only-20260808-055135")
    check("P10: the two chains overlap substantially (annotated exemplar)",
          p10 is not None and p10["overlap"] != "" and p10["overlap"] >= 0.5,
          "" if p10 is None else "overlap=%s concurrency=%s" % (p10["overlap"],
                                                               p10["team_concurrency"]))
    check("P10: two three-member chains, with a member left without a task",
          p10 is not None and p10["engaged_a"] == 3 and p10["engaged_b"] == 3
          and p10["members_without_task"] >= 1,
          "" if p10 is None else "chains=%d/%d without-task=%d"
          % (p10["engaged_a"], p10["engaged_b"], p10["members_without_task"]))

    p6 = rows.get("P6_enforced-20260808-143229")
    check("P6: no member chain activity (leader SPOF, excluded from parallelism)",
          p6 is not None and p6["overlap"] == "",
          "" if p6 is None else "overlap=%r span_a=%r span_b=%r"
          % (p6["overlap"], p6["span_a"], p6["span_b"]))

    p3 = rows.get("P3_enforced-20260808-134613")
    check("P3: chains overlap (annotated as genuine phase-level overlap)",
          p3 is not None and p3["overlap"] != "" and p3["overlap"] > 0,
          "" if p3 is None else "overlap=%s" % p3["overlap"])

    check("every bundle run resolved to exactly 2 subtasks", len(rows) == 30,
          "resolved=%d/30" % len(rows))

    have = [r for r in rows.values() if r["single_a"] and r["single_b"]]
    okc = all(r["token_ratio"] != "" and r["token_ratio"] > 0 for r in have)
    check("token/turn cost ratios present wherever both singles exist",
          okc and have, "n=%d" % len(have))

    d3 = {p3["subtask_a"]: p3["d_score_a"], p3["subtask_b"]: p3["d_score_b"]} if p3 else {}
    check("P3-enf test9 score delta strongly negative (annotated misplacement)",
          p3 is not None and d3.get("test9", "") != "" and d3["test9"] <= -0.5,
          "d=%s" % d3.get("test9"))
    return 1 if bad else 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
