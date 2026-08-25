# Builds the master run index: one row per run with outcome, size and
# timing columns, plus per-member rows.
import csv, io, json, os, re, sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RUNS_ROOT = r"C:\Users\cz776\Downloads\Runs"

BATCHES = {
    "S1A_team_dyn_pro":         ("S1A", 1, "prompt-only", "control"),
    "S1A_team_dyn_pro_arm2":    ("S1A", 2, "prompt-only", "control"),
    "S1A_team_enf_pro":         ("S1A", 1, "enforced",    "control"),
    "S1B_team_dyn_pro":         ("S1B", 1, "prompt-only", "control"),
    "S1B_team_enf_pro":         ("S1B", 1, "enforced",    "control"),
    "S1B_team_enf_pro_arm2":    ("S1B", 2, "enforced",    "control"),
    "S2_pairs_pro":             ("S2",  1, "prompt-only", "pairs"),
    "S2_pairs_enf_pro":         ("S2",  1, "enforced",    "pairs"),
    "S2_pairs_enf_pro_arm2":    ("S2",  2, "enforced",    "pairs"),
    "S3_full_enf_pro":          ("S3",  1, "enforced",    "full"),
    "S3_full_enf_pro_arm2":     ("S3",  2, "enforced",    "full"),
    "S3_partial_enf_pro":       ("S3",  1, "enforced",    "partial"),
    "S3_partial_enf_pro_arm2":  ("S3",  2, "enforced",    "partial"),
    "S4_enf_pro":               ("S4",  1, "enforced",    "closed"),
    "S4_enf_pro_arm2":          ("S4",  2, "enforced",    "closed"),
    "S5_partial_enf_pro":       ("S5",  1, "enforced",    "partial"),
    "S5_partial_enf_pro_arm2":  ("S5",  2, "enforced",    "partial"),
    "S5_minimal_enf_pro":       ("S5",  1, "enforced",    "minimal"),
    "S5_minimal_enf_pro_arm2":  ("S5",  2, "enforced",    "minimal"),
}
EXPECTED = {"S1A_team_dyn_pro": 12, "S1A_team_dyn_pro_arm2": 12, "S1A_team_enf_pro": 12,
            "S1B_team_dyn_pro": 8, "S1B_team_enf_pro": 8, "S1B_team_enf_pro_arm2": 8,
            "S2_pairs_pro": 10, "S2_pairs_enf_pro": 10, "S2_pairs_enf_pro_arm2": 10,
            "S3_full_enf_pro": 12, "S3_full_enf_pro_arm2": 12,
            "S3_partial_enf_pro": 12, "S3_partial_enf_pro_arm2": 12,
            "S4_enf_pro": 12, "S4_enf_pro_arm2": 12,
            "S5_partial_enf_pro": 6, "S5_partial_enf_pro_arm2": 6,
            "S5_minimal_enf_pro": 6, "S5_minimal_enf_pro_arm2": 6}

KNOWN_GAPS = {
    "P1_prompt-only-20260808-042501":
        "no batch_results row (tsv starts at P2); run is real and graded in s2_regrade",
}

ROLE_GROUP = [(re.compile(r"^planner"), "planner"), (re.compile(r"^executor"), "executor"),
              (re.compile(r"^verifier"), "verifier"), (re.compile(r"^fullstack"), "fullstack"),
              (re.compile(r"^team_leader$"), "leader")]

def role_group(member):
    for pat, grp in ROLE_GROUP:
        if pat.match(member):
            return grp
    return "unknown"

def read_tsv(path):
    if not os.path.isfile(path):
        return []
    with io.open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter="\t"))

def load_joins():
    audit = {r["archive"]: r for r in read_tsv(os.path.join(OUT, "trace_audit.tsv"))}
    tags = {r["archive"]: r for r in read_tsv(os.path.join(OUT, "run_tags.tsv"))}
    return audit, tags

def batch_rows(batch):
    d = os.path.join(RUNS_ROOT, batch)
    out = {}
    for r in read_tsv(os.path.join(d, "batch_results.tsv")):
        arc = os.path.basename(r.get("archive", "").rstrip("/"))
        if arc:
            out[arc] = r
    return out

def regrade_rows(batch):
    d = os.path.join(RUNS_ROOT, batch)
    s1 = read_tsv(os.path.join(d, "scenario1_regrade.tsv"))
    if s1:
        return {r["task"]: r for r in s1}, None
    s2 = read_tsv(os.path.join(d, "s2_regrade.tsv"))
    if s2:
        by_bundle = defaultdict(list)
        for r in s2:
            by_bundle[r["bundle"]].append(r)
        return None, by_bundle
    return {}, None

def fnum(x, default=""):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def trace_stats(archive_path):
    run = teamtrace.load_run(archive_path)
    sums = [teamtrace.member_summary(m) for m in run["members"]]
    starts, ends = [], []
    for m in run["members"]:
        iv = teamtrace.member_intervals(m)
        if iv:
            starts.append(iv[0][0])
            ends.append(iv[-1][1])
    stalls = teamtrace.stall_windows(run)
    return {
        "members": len(sums),
        "turns": sum(len(m["turns"]) for m in run["members"]),
        "actions": sum(s["actions"] for s in sums),
        "blocked_actions": sum(s["blocked"] for s in sums),
        "failed_actions": sum(s["failed"] for s in sums),
        "input_tokens": sum(s["input_tokens"] for s in sums),
        "output_tokens": sum(s["output_tokens"] for s in sums),
        "cache_tokens": sum(s["cache_tokens"] for s in sums),
        "messages": len(run["messages"]),
        "span_s": round(max(ends) - min(starts), 1) if starts else "",
        "active_member_s": round(sum(s["active_s"] for s in sums), 1),
        "stall_windows": len(stalls),
        "stall_s": round(sum(e - s for s, e in stalls), 1) if stalls else 0.0,
    }, sums

INDEX_COLS = ["run_id", "batch", "scenario", "arm", "condition", "dose", "task",
              "phase", "survivor", "timestamp", "framework_outcome",
              "regrade_pass", "regrade_score", "checks_passed", "checks_total",
              "grader_failure_modes", "subtask_scores",
              "trace_status", "streams", "members", "turns", "actions",
              "blocked_actions", "messages", "span_s", "stall_windows",
              "input_tokens", "output_tokens", "cache_tokens",
              "annotated", "behavioral_families", "behavioral_tags",
              "grader_artifact_only", "notes", "archive_path"]

# build the output tables from the raw streams
def build(do_trace=True):
    audit, tags = load_joins()
    rows, members_rows, problems, notes = [], [], [], []
    for batch, (scen, arm, cond, dose) in BATCHES.items():
        bdir = os.path.join(RUNS_ROOT, batch)
        if not os.path.isdir(bdir):
            problems.append("missing batch dir: " + batch)
            continue
        arcs = sorted(d for d in os.listdir(bdir) if os.path.isdir(os.path.join(bdir, d)))
        br = batch_rows(batch)
        rg, rg_s2 = regrade_rows(batch)
        for arc in arcs:
            b = br.get(arc, {})
            task = b.get("task", arc.split("_")[0])
            rec = {c: "" for c in INDEX_COLS}

            outcome_raw = b.get("outcome", "")
            outcome = re.split(r"\s+[—-]\s+", outcome_raw, 1)[0].strip()
            rec.update(run_id=arc, batch=batch, scenario=scen, arm=arm, condition=cond,
                       dose=dose, task=task, phase=b.get("phase", ""),
                       survivor=b.get("survivor", ""), timestamp=b.get("timestamp", ""),
                       framework_outcome=outcome,
                       archive_path=os.path.join(bdir, arc))
            if outcome != outcome_raw:
                rec["notes"] = "batch_results outcome cell had trailing prose: " + outcome_raw
            if arc in KNOWN_GAPS:
                rec["notes"] = KNOWN_GAPS[arc]
            elif arc not in br:
                problems.append("archive with no batch_results row: %s/%s" % (batch, arc))
            if rg is not None:
                r = rg.get(task)
                if r is None:
                    problems.append("no regrade row: %s/%s (task %s)" % (batch, arc, task))
                else:
                    rec.update(regrade_pass=r.get("pass", ""),
                               regrade_score=r.get("partial_score", ""),
                               checks_passed=r.get("checks_passed", ""),
                               checks_total=r.get("checks_total", ""),
                               grader_failure_modes=r.get("failure_modes", ""))
            else:
                bundle = task if task in (rg_s2 or {}) else arc.split("_")[0]
                subs = (rg_s2 or {}).get(bundle, [])
                if not subs:
                    problems.append("no s2 regrade rows: %s/%s" % (batch, arc))
                else:
                    scores = [fnum(s["partial_score"], 0.0) for s in subs]
                    rec.update(regrade_pass=str(all(s.get("pass") == "True" for s in subs)),
                               regrade_score=round(sum(scores) / len(scores), 4),
                               checks_passed=sum(int(s["checks_passed"] or 0) for s in subs),
                               checks_total=sum(int(s["checks_total"] or 0) for s in subs),
                               grader_failure_modes=";".join(
                                   s["failure_modes"] for s in subs if s["failure_modes"]),
                               subtask_scores=";".join(
                                   "%s=%s" % (s["subtask"], s["partial_score"]) for s in subs))
            a = audit.get(arc)
            if a is None:
                problems.append("no trace_audit row: %s/%s" % (batch, arc))
            else:
                rec.update(trace_status=a["status"], streams=a["live_streams"])
                if a["status"] != "OK":
                    problems.append("trace audit not OK: %s/%s -> %s" % (batch, arc, a["status"]))
            t = tags.get(arc)
            rec["annotated"] = "yes" if t else "no"
            if t:
                rec.update(behavioral_families=t["behavioral_families"],
                           behavioral_tags=t["behavioral_tags"],
                           grader_artifact_only=t["grader_artifact_only"])
            if do_trace:
                try:
                    stats, sums = trace_stats(rec["archive_path"])
                except Exception as e:
                    problems.append("teamtrace failed: %s/%s -> %s" % (batch, arc, e))
                    stats, sums = {}, []
                rec.update(stats)
                for s in sums:
                    members_rows.append(dict(
                        run_id=arc, batch=batch, scenario=scen, arm=arm, condition=cond,
                        dose=dose, task=task, member=s["member"], node=s["node"],
                        role_group=role_group(s["member"]), llm_calls=s["llm_calls"],
                        input_tokens=s["input_tokens"], output_tokens=s["output_tokens"],
                        cache_tokens=s["cache_tokens"], actions=s["actions"],
                        blocked=s["blocked"], failed=s["failed"], active_s=s["active_s"]))
            rows.append(rec)
        if len(arcs) != EXPECTED.get(batch):
            problems.append("archive count %d != expected %d for %s"
                            % (len(arcs), EXPECTED.get(batch), batch))

        for arc_name, brow in br.items():
            if arc_name not in arcs:
                notes.append("%s: superseded rerun row in batch_results (%s, %s)"
                             % (batch, arc_name, brow.get("outcome", "")))

        dup = [t for t, n in Counter(r["task"] for r in rows
                                     if r["batch"] == batch).items() if n > 1]
        if dup:
            problems.append("duplicate task in %s (regrade join ambiguous): %s"
                            % (batch, ", ".join(dup)))

    indexed = {r["run_id"] for r in rows}
    for arc in tags:
        if arc not in indexed:
            problems.append("annotated run not in index: " + arc)
    return rows, members_rows, problems, notes

def write(rows, members_rows):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "run_index.tsv")
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, INDEX_COLS, delimiter="\t", extrasaction="ignore",
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    p2 = os.path.join(OUT, "runs.csv")
    with io.open(p2, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, INDEX_COLS, extrasaction="ignore", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    p3 = os.path.join(OUT, "members.csv")
    if members_rows:
        cols = list(members_rows[0].keys())
        with io.open(p3, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, cols, lineterminator="\n")
            w.writeheader()
            w.writerows(members_rows)
    return p, p2, p3

def summarize(rows, members_rows):
    print("\nruns by scenario x arm:")
    c = Counter((r["scenario"], r["arm"]) for r in rows)
    for k in sorted(c):
        print("  %-4s arm-%s  %3d" % (k[0], k[1], c[k]))
    ann = sum(1 for r in rows if r["annotated"] == "yes")
    grd = sum(1 for r in rows if r["grader_artifact_only"] == "yes")
    print("\ntotal runs %d | annotated %d | grader-artifact-only %d | "
          "behavioural findings %d" % (len(rows), ann, grd, ann - grd))
    if members_rows:
        g = Counter(m["role_group"] for m in members_rows)
        print("member rows %d by role group: %s" % (len(members_rows), dict(g)))
    out = Counter(r["framework_outcome"] for r in rows)
    print("framework outcomes:", dict(out))

if __name__ == "__main__":
    only_verify = len(sys.argv) > 1 and sys.argv[1] == "verify"
    rows, members_rows, problems, notes = build(do_trace=not only_verify)
    if problems:
        print("RECONCILIATION PROBLEMS (%d):" % len(problems))
        for p in problems:
            print("  " + p)
    else:
        print("reconciliation clean: batch_results, regrade, trace_audit and annotation "
              "joins all complete for %d runs" % len(rows))
    if notes:
        print("\ndata-hygiene notes (%d, non-fatal):" % len(notes))
        for n in notes:
            print("  " + n)
    if not only_verify:
        paths = write(rows, members_rows)
        print("wrote:\n  " + "\n  ".join(paths))
        summarize(rows, members_rows)
    sys.exit(1 if problems else 0)
