# Cost and score deltas of each stress run against the same task in
# the arm's own measured base.
import io, os, sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace
import run_index as rix

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
ROLES = ["planner", "executor", "verifier", "fullstack", "leader"]
PHASE = {"planner": "planning", "executor": "executing", "verifier": "verifying",
         "fullstack": "generalist", "leader": "coordination"}

BASE_OF = {
    ("S3", "enforced"): ("S1A", "enforced"),
    ("S4", "enforced"): ("S1A", "enforced"),
    ("S5", "enforced"): ("S1A", "enforced"),
    ("S2", "enforced"): ("S1A", "enforced"),
    ("S2", "prompt-only"): ("S1A", "prompt-only"),
}

def f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d

def load():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    mem = []
    with io.open(os.path.join(OUT, "member_metrics.csv"), encoding="utf-8") as fh:
        import csv
        mem = list(csv.DictReader(fh))
    return idx, mem

def stuck_spend(rec):
    run = teamtrace.load_run(rec["archive_path"])
    blocked_tok = retry_tok = total = 0
    for m in run["members"]:
        seen = set()
        for t in m["turns"]:
            tok = (t["usage"] or {}).get("output_tokens", 0) or 0
            total += tok
            tgts = {(a["path"] or (a["args_text"] or "")[:60]) for a in t["actions"]
                    if a["blocked"]}
            if tgts:
                blocked_tok += tok
                if tgts & seen:
                    retry_tok += tok
                seen |= tgts
    stall_s = sum(e - s for s, e in teamtrace.stall_windows(run))
    active_s = sum(e - s for m in run["members"]
                   for s, e, _ in teamtrace.member_intervals(m))
    return blocked_tok, retry_tok, total, round(stall_s, 1), round(active_s, 1)

# build the output tables from the raw streams
def build():
    idx, mem = load()

    per_run = defaultdict(lambda: defaultdict(float))
    for m in mem:
        k = m["run_id"]
        r = m["role_group"]
        per_run[k]["out"] += f(m["output_tokens"])
        per_run[k]["in"] += f(m["input_tokens"])
        per_run[k]["turns"] += f(m["turns"])
        per_run[k]["msgs"] += f(m["act_comms"])
        per_run[k]["comms_tok"] += f(m["comms_token_est"])
        per_run[k]["out_" + r] += f(m["output_tokens"])
        per_run[k]["turns_" + r] += f(m["turns"])
        per_run[k]["comms_" + r] += f(m["comms_token_est"])
    for rid, rec in idx.items():
        b, rt, tot, stall, active = stuck_spend(rec)
        per_run[rid]["stuck_tok"] = b
        per_run[rid]["retry_tok"] = rt
        per_run[rid]["stall_s"] = stall
        per_run[rid]["active_s"] = active

    trows = []
    for rid, rec in sorted(idx.items()):
        p = per_run[rid]
        if not p["out"]:
            continue
        span = f(rec["span_s"])
        row = dict(run_id=rid, scenario=rec["scenario"], arm=rec["arm"],
                   condition=rec["condition"], dose=rec["dose"], task=rec["task"],
                   out_tokens=int(p["out"]), turns=int(p["turns"]),
                   messages=int(p["msgs"]),
                   span_s=span, stall_s=p["stall_s"],
                   time_s=round(max(span - p["stall_s"], 0), 1),
                   active_s=p["active_s"],
                   score=f(rec["regrade_score"], ""), rpass=rec["regrade_pass"],
                   comms_tokens_est=int(p["comms_tok"]),
                   comms_pct=round(100 * p["comms_tok"] / p["out"], 1),
                   stuck_tokens=int(p["stuck_tok"]),
                   stuck_pct=round(100 * p["stuck_tok"] / p["out"], 1),
                   retry_tokens=int(p["retry_tok"]))
        for r in ROLES:
            row["pct_" + PHASE[r]] = round(100 * p["out_" + r] / p["out"], 1)
            row["tok_" + PHASE[r]] = int(p["out_" + r])
            row["turns_" + PHASE[r]] = int(p["turns_" + r])
        trows.append(row)
    _write(os.path.join(OUT, "task_role_split.tsv"), trows)

    base = defaultdict(dict)
    for r in trows:
        base[(r["scenario"], r["condition"], r["dose"], r["arm"])][r["task"]] = r

    drows = []
    for (sc, cond, dose, arm), tasks in sorted(base.items()):
        if sc == "S1A" or (sc, cond) not in BASE_OF:
            continue
        if arm == "2":
            bt = base.get(("S1A", "prompt-only", "control", "2"))
        else:
            bsc, bcond = BASE_OF[(sc, cond)]
            bt = base.get((bsc, bcond, "control", "1"))
        if not bt:
            continue
        for task, row in sorted(tasks.items()):
            if sc == "S2":
                continue
            b = bt.get(task)
            if not b:
                continue
            drows.append(dict(
                scenario=sc, dose=row["dose"], arm=arm, task=task, run_id=row["run_id"],
                base_run=b["run_id"],
                base_out=b["out_tokens"], out=row["out_tokens"],
                d_out=int(row["out_tokens"] - b["out_tokens"]),
                d_out_pct=round(100 * (row["out_tokens"] - b["out_tokens"])
                                / b["out_tokens"], 1),
                base_turns=b["turns"], turns=row["turns"],
                d_turns=round(row["turns"] - b["turns"], 1),
                d_msgs=round(row["messages"] - b["messages"], 1),
                base_time_s=b["time_s"], time_s=row["time_s"],
                d_time_s=round(row["time_s"] - b["time_s"], 1),
                d_span_s=round(row["span_s"] - b["span_s"], 1),
                base_score=b["score"], score=row["score"],
                d_score=(round(row["score"] - b["score"], 3)
                         if b["score"] != "" and row["score"] != "" else ""),
                score_base_run=b["run_id"],
                d_stuck_tok=int(row["stuck_tokens"] - b["stuck_tokens"]),
                **{("d_tok_" + ph): int(row["tok_" + ph] - b["tok_" + ph])
                   for ph in ("planning", "executing", "verifying", "generalist",
                              "coordination")},
                **{("d_turns_" + ph): round(row["turns_" + ph] - b["turns_" + ph], 1)
                   for ph in ("planning", "executing", "verifying", "generalist",
                              "coordination")},
                stuck_pct=row["stuck_pct"], base_stuck_pct=b["stuck_pct"]))
    _write(os.path.join(OUT, "stress_delta.tsv"), drows)
    prows = persona_stress(base)
    _write(os.path.join(OUT, "persona_stress_delta.tsv"), prows)
    report(trows, drows, base, prows)
    overview(base)
    return trows, drows

PHASES = ("planning", "executing", "verifying", "generalist", "coordination")

def overview_rows(base):
    a1b = base.get(("S1A", "enforced", "control", "1"), {})
    a2p = base.get(("S1A", "prompt-only", "control", "2"), {})

    def base_of(arm, task):
        b = (a1b if arm == "1" else a2p).get(task)
        if not b:
            return None
        return dict(out=b["out_tokens"], turns=b["turns"],
                    msgs=b["messages"], time=b["time_s"],
                    score=b["score"], run=b["run_id"],
                    tok_ph={ph: b["tok_" + ph] for ph in PHASES},
                    turns_ph={ph: b["turns_" + ph] for ph in PHASES})

    out = {"1": [], "2": []}
    for (sc, cond, dose, arm), tasks in sorted(base.items()):
        if sc in ("S1A", "S1B", "S2") or (sc, cond) not in BASE_OF:
            continue
        for task, r in sorted(tasks.items()):
            b = base_of(arm, task)
            if not b:
                continue
            out[arm].append(dict(
                scenario=sc, dose=dose, task=task, run_id=r["run_id"],
                base_run=b["run"],
                base_out=int(b["out"]), out=r["out_tokens"],
                d_out=int(r["out_tokens"] - b["out"]),
                d_pct=round(100 * (r["out_tokens"] - b["out"]) / b["out"], 1),
                d_turns=round(r["turns"] - b["turns"], 1),
                d_msgs=round(r["messages"] - b["msgs"], 1),
                d_time=round(r["time_s"] - b["time"], 1),
                base_score=b["score"], score=r["score"],
                d_score=(round(r["score"] - b["score"], 3)
                         if b["score"] != "" and r["score"] != "" else ""),
                d_tok_ph={ph: int(r["tok_" + ph] - b["tok_ph"][ph]) for ph in PHASES},
                d_turns_ph={ph: round(r["turns_" + ph] - b["turns_ph"][ph], 1)
                            for ph in PHASES}))
    return out

def _cell_line(rs):
    n = len(rs)
    ds = [r["d_score"] for r in rs if r["d_score"] != ""]
    return dict(
        n=n, d_out=sum(r["d_out"] for r in rs) / n,
        d_pct=sum(r["d_pct"] for r in rs) / n,
        d_turns=sum(r["d_turns"] for r in rs) / n,
        d_time=sum(r["d_time"] for r in rs) / n,
        d_score=(sum(ds) / len(ds)) if ds else None,
        worse=sum(1 for d in ds if d < -0.05),
        same=sum(1 for d in ds if abs(d) <= 0.05),
        better=sum(1 for d in ds if d > 0.05))

def _cell_key(r):
    return (r["scenario"], "" if r["scenario"] == "S5" else r["dose"])

def _cell_label(k):
    return "%s-%s" % k if k[1] else k[0]

def overview(base):
    orows = overview_rows(base)
    ARM_NOTE = {
        "1": "Base = S1A enforced arm-1: same task, same enforcement, no manipulation — "
             "every column is measured on both sides.",
        "2": "Base = the MEASURED S1A prompt-only arm-2 runs, unscaled on every "
             "dimension — the specialist arm's own control. One caveat: the base ran "
             "prompt-only while the stress cells are enforced; that condition offset "
             "is shared by every arm-2 cell, so cross-cell comparison is unaffected, "
             "and S1A scores measured arm/condition-insensitive."}
    for arm in ("1", "2"):
        rows = orows[arm]
        if not rows:
            continue
        L = ["# Stress overview — arm-%s (%s personas)" % (
                arm, "base" if arm == "1" else "specialist"),
             "", "Auto-generated by stress_vs_base.py. " + ARM_NOTE[arm],
             "Time = wall-clock span minus framework stall windows. Score = grade.sh "
             "regrade partial score (never attestation).", ""]
        cells = defaultdict(list)
        for r in rows:
            cells[_cell_key(r)].append(r)

        L += ["## Cell summary", "",
              "(S5 pools partial+minimal — the split is not a dose contrast; per-task "
              "dose tags below.)", "",
              "| condition | pairs | Δtok/run | Δ% | Δturns | Δtime (s) | Δscore | "
              "score worse / same / better |", "|---|---|---|---|---|---|---|---|"]
        for k in sorted(cells):
            c = _cell_line(cells[k])
            L.append("| %s | %d | %+d | %+.1f%% | %+.1f | %+.0f | %s | %d / %d / %d |"
                     % (_cell_label(k), c["n"], c["d_out"], c["d_pct"], c["d_turns"],
                        c["d_time"],
                        ("%+.3f" % c["d_score"]) if c["d_score"] is not None else "—",
                        c["worse"], c["same"], c["better"]))
        L.append("")

        for k in sorted(cells):
            rs = sorted(cells[k], key=lambda r: r["task"])
            n = len(rs)
            L += ["## %s (arm-%s, %d pairs)" % (_cell_label(k), arm, n), "",
                  "| task | tok base→stress | Δ% | Δturns | Δtime (s) | score "
                  "base→stress | Δscore |", "|---|---|---|---|---|---|---|"]
            for r in rs:
                tname = r["task"][:22] + (
                    " [%s]" % r["dose"][:4] if r["scenario"] == "S5" else "")
                L.append("| %s | %s → %s | %+.1f%% | %+.1f | %+.0f | %s → %s | %s |" % (
                    tname, "{:,}".format(r["base_out"]),
                    "{:,}".format(r["out"]), r["d_pct"], r["d_turns"], r["d_time"],
                    r["base_score"], r["score"],
                    ("%+.3f" % r["d_score"]) if r["d_score"] != "" else "—"))
            L += ["", "Per-phase deltas (mean over the %d pairs): %s" % (
                      n, " · ".join("%s %+dtok / %+.1f turns" % (
                          ph[:5], sum(r["d_tok_ph"][ph] for r in rs) / n,
                          sum(r["d_turns_ph"][ph] for r in rs) / n) for ph in PHASES)),
                  ""]
        p = os.path.join(OUT, "stress_overview_arm%s.md" % arm)
        io.open(p, "w", encoding="utf-8").write("\n".join(L) + "\n")

    print("\n=== 5. PER-ARM OVERVIEW (full tables: out/stress_overview_arm{1,2}.md) ===")
    for arm in ("1", "2"):
        if not orows[arm]:
            continue
        print("  arm-%s (%s personas)%s" % (
            arm, "base" if arm == "1" else "specialist",
            "" if arm == "1" else "  [base: measured S1A prompt-only arm-2, unscaled]"))
        cells = defaultdict(list)
        for r in orows[arm]:
            cells[_cell_key(r)].append(r)
        print("    %-14s %6s %9s %8s %9s %9s %8s %22s" % (
            "condition", "pairs", "Δtok", "Δ%", "Δturns", "Δtime_s", "Δscore",
            "score worse/same/better"))
        for k in sorted(cells):
            c = _cell_line(cells[k])
            print("    %-14s %6d %9d %8.1f %9.1f %+9.0f %8s %15d/%2d/%2d" % (
                _cell_label(k), c["n"], c["d_out"], c["d_pct"], c["d_turns"], c["d_time"],
                ("%+.3f" % c["d_score"]) if c["d_score"] is not None else "—",
                c["worse"], c["same"], c["better"]))

def two_tables(base):
    a1b = base.get(("S1A", "enforced", "control", "1"), {})
    a2p = base.get(("S1A", "prompt-only", "control", "2"), {})
    tables = {}
    for arm, bt in (("1", a1b), ("2", a2p)):
        rows = []
        for (sc, cond, dose, a), tasks in sorted(base.items()):
            if a != arm or sc in ("S1A", "S1B", "S2"):
                continue
            pairs = [(bt[t], r) for t, r in sorted(tasks.items()) if t in bt]
            if not pairs:
                continue
            n = len(pairs)
            rows.append(dict(
                condition="%s %s" % (sc, dose), pairs=n,
                base_tok=int(sum(b["out_tokens"] for b, _ in pairs) / n),
                stress_tok=int(sum(r["out_tokens"] for _, r in pairs) / n),
                d_tok=int(sum(r["out_tokens"] - b["out_tokens"] for b, r in pairs) / n),
                d_pct=round(100 * sum((r["out_tokens"] - b["out_tokens"]) / b["out_tokens"]
                                      for b, r in pairs) / n, 1),
                base_turns=round(sum(b["turns"] for b, _ in pairs) / n, 1),
                d_turns=round(sum(r["turns"] - b["turns"] for b, r in pairs) / n, 1),
                base_msgs=round(sum(b["messages"] for b, _ in pairs) / n, 1),
                d_msgs=round(sum(r["messages"] - b["messages"] for b, r in pairs) / n, 1),
                base_stuck_pct=round(sum(b["stuck_pct"] for b, _ in pairs) / n, 1),
                stress_stuck_pct=round(sum(r["stuck_pct"] for _, r in pairs) / n, 1)))
        tables[arm] = rows
    return tables

def persona_stress(base):
    fac = base_persona_ratio(base)
    rows = []
    for (sc, cond, dose, arm), tasks in sorted(base.items()):
        if arm != "1" or sc in ("S1A", "S1B", "S2"):
            continue
        a2 = base.get((sc, cond, dose, "2"))
        if not a2:
            continue
        bsc, bcond = BASE_OF.get((sc, cond), (None, None))
        b1 = base.get((bsc, bcond, "control", "1"), {})
        b2 = base.get(("S1A", "prompt-only", "control", "2"), {})
        for task, r1 in sorted(tasks.items()):
            r2, b = a2.get(task), b1.get(task)
            bb2 = b2.get(task)
            if not (r2 and b and bb2):
                continue
            rows.append(dict(
                scenario=sc, dose=dose, task=task,
                base_arm1=b["out_tokens"], base_arm2=bb2["out_tokens"],
                stress_arm1=r1["out_tokens"], stress_arm2=r2["out_tokens"],
                d_stress_arm1=r1["out_tokens"] - b["out_tokens"],
                d_stress_arm2=r2["out_tokens"] - bb2["out_tokens"],
                d_persona_under_stress=r2["out_tokens"] - r1["out_tokens"],
                persona_ratio=round(r2["out_tokens"] / r1["out_tokens"], 2),
                base_persona_ratio=round(fac, 2),
                interaction=round(r2["out_tokens"] / r1["out_tokens"] - fac, 2),
                turns_arm1=r1["turns"], turns_arm2=r2["turns"],
                d_turns_persona=r2["turns"] - r1["turns"],
                base_turns=b["turns"],
                d_turns_stress_arm1=r1["turns"] - b["turns"],
                msgs_arm1=r1["messages"], msgs_arm2=r2["messages"],
                d_msgs_persona=r2["messages"] - r1["messages"],
                stuck_pct_arm1=r1["stuck_pct"], stuck_pct_arm2=r2["stuck_pct"]))
    return rows

def base_persona_ratio(base):
    a1 = base.get(("S1A", "prompt-only", "control", "1"), {})
    a2 = base.get(("S1A", "prompt-only", "control", "2"), {})
    common = set(a1) & set(a2)
    if not common:
        return 1.0
    return (sum(a2[t]["out_tokens"] for t in common)
            / sum(a1[t]["out_tokens"] for t in common))

def _write(path, rows):
    if not rows:
        return
    cols = list(rows[0].keys())
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")

# print the human-readable summary
def report(trows, drows, base, prows=None):
    L = []
    def out(s=""):
        print(s)
        L.append(s)

    out("=== 1. SPEND SPLIT by agent group (mean of per-task shares, % of team output) ===")
    out("%-26s %4s %5s %9s %9s %9s %10s %12s %7s" % (
        "condition", "arm", "runs", "planning", "executing", "verifying", "generalist",
        "coordination", "comms"))
    cells = defaultdict(list)
    for r in trows:
        cells[(r["scenario"], r["dose"], r["condition"], r["arm"])].append(r)
    for k in sorted(cells):
        rs = cells[k]
        n = len(rs)
        out("%-26s %4s %5d %9.1f %9.1f %9.1f %10.1f %12.1f %7.1f" % (
            "%s/%s/%s" % (k[0], k[1], k[2]), k[3], n,
            sum(r["pct_planning"] for r in rs) / n,
            sum(r["pct_executing"] for r in rs) / n,
            sum(r["pct_verifying"] for r in rs) / n,
            sum(r["pct_generalist"] for r in rs) / n,
            sum(r["pct_coordination"] for r in rs) / n,
            sum(r["comms_pct"] for r in rs) / n))

    out("\n=== 2. STRESS DELTA vs the same task in S1A (paired) ===")
    out("%-22s %4s %5s %11s %8s %8s %8s   %s" % (
        "condition", "arm", "pairs", "Δ out tok", "Δ %", "Δ turns", "Δ msgs",
        "Δ by phase: plan / exec / verify / gen / coord"))
    dcells = defaultdict(list)
    for r in drows:
        dcells[(r["scenario"], r["dose"], r["arm"])].append(r)
    for k in sorted(dcells):
        rs = dcells[k]
        n = len(rs)
        ph = " / ".join("%+d" % (sum(r["d_tok_" + x] for r in rs) / n)
                        for x in ("planning", "executing", "verifying", "generalist",
                                  "coordination"))
        out("%-22s %4s %5d %11d %8.1f %8.1f %8.1f   %s" % (
            "%s/%s" % (k[0], k[1]), k[2], n,
            sum(r["d_out"] for r in rs) / n,
            sum(r["d_out_pct"] for r in rs) / n,
            sum(r["d_turns"] for r in rs) / n,
            sum(r["d_msgs"] for r in rs) / n, ph))
    out("\n  every base is MEASURED: arm-1 vs S1A enforced arm-1, arm-2 vs S1A "
        "prompt-only arm-2 (the specialist arm's own control).")

    out("\n=== 3. TOKENS SPENT STUCK (output tokens in turns containing a denial) ===")
    out("%-26s %4s %5s %12s %8s %12s" % ("condition", "arm", "runs", "stuck tok/run",
                                         "% of out", "retry tok/run"))
    for k in sorted(cells):
        rs = cells[k]
        n = len(rs)
        out("%-26s %4s %5d %12d %8.1f %12d" % (
            "%s/%s/%s" % (k[0], k[1], k[2]), k[3], n,
            sum(r["stuck_tokens"] for r in rs) / n,
            sum(r["stuck_pct"] for r in rs) / n,
            sum(r["retry_tokens"] for r in rs) / n))

    if prows:
        out("\n=== 4. PERSONA x STRESS decomposition (per task, measured pairs) ===")
        out("%-16s %5s %13s %13s %13s %8s %8s %9s" % (
            "condition", "tasks", "Δstress arm1", "Δstress arm2", "Δpersona", "ratio",
            "base r", "interact"))
        cells = defaultdict(list)
        for r in prows:
            cells[(r["scenario"], r["dose"])].append(r)
        for k in sorted(cells):
            rs = cells[k]
            n = len(rs)
            out("%-16s %5d %13d %13d %13d %8.2f %8.2f %+9.2f" % (
                "%s/%s" % k, n,
                sum(r["d_stress_arm1"] for r in rs) / n,
                sum(r["d_stress_arm2"] for r in rs) / n,
                sum(r["d_persona_under_stress"] for r in rs) / n,
                sum(r["persona_ratio"] for r in rs) / n,
                rs[0]["base_persona_ratio"],
                sum(r["interaction"] for r in rs) / n))
        out("\n  Δstress arm1  = stress(arm1) - base(arm1: S1A enforced)     [measured]")
        out("  Δstress arm2  = stress(arm2) - base(arm2: S1A prompt-only)  [measured]")
        out("  Δpersona      = stress(arm2) - stress(arm1)          [both measured, paired]")
        out("  interaction   = persona ratio under stress - the base persona ratio")
        out("\n  turns and messages, same pairs:")
        out("%-16s %13s %13s %13s %13s" % ("condition", "Δturns arm1", "Δturns persona",
                                           "msgs arm1", "Δmsgs persona"))
        for k in sorted(cells):
            rs = cells[k]
            n = len(rs)
            out("%-16s %13.1f %13.1f %13.1f %13.1f" % (
                "%s/%s" % k,
                sum(r["d_turns_stress_arm1"] for r in rs) / n,
                sum(r["d_turns_persona"] for r in rs) / n,
                sum(r["msgs_arm1"] for r in rs) / n,
                sum(r["d_msgs_persona"] for r in rs) / n))

    tabs = two_tables(base)
    for arm, title, basename in (("1", "TABLE A — BASE personas (arm-1)",
                                  "S1A enforced arm-1, measured"),
                                 ("2", "TABLE B — SPECIALIST personas (arm-2)",
                                  "S1A prompt-only arm-2, measured")):
        out("\n=== %s ===   base = %s, paired by task" % (title, basename))
        out("%-16s %6s %10s %10s %9s %7s %9s %8s %9s %8s" % (
            "condition", "pairs", "base tok", "stress tok", "Δ tok", "Δ %",
            "Δ turns", "Δ msgs", "stuck% b", "stuck% s"))
        for r in tabs[arm]:
            out("%-16s %6d %10d %10d %9d %7.1f %9.1f %8.1f %9.1f %8.1f" % (
                r["condition"], r["pairs"], r["base_tok"], r["stress_tok"], r["d_tok"],
                r["d_pct"], r["d_turns"], r["d_msgs"], r["base_stuck_pct"],
                r["stress_stuck_pct"]))
    out("\n  Both tables are measured on both sides. Table B's one caveat: its base ran "
        "prompt-only while the stress cells are enforced; the offset is shared by every "
        "arm-2 cell, so cross-cell comparison is unaffected.")
    _write(os.path.join(OUT, "stress_delta_arm1.tsv"), tabs["1"])
    _write(os.path.join(OUT, "stress_delta_arm2.tsv"), tabs["2"])

    p = os.path.join(OUT, "stress_summary.md")
    io.open(p, "w", encoding="utf-8").write(
        "# Stress vs base — generated by stress_vs_base.py\n\n```\n"
        + "\n".join(L) + "\n```\n")
    print("\nwrote out/task_role_split.tsv, out/stress_delta.tsv, out/stress_summary.md")

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx, mem = load()
    trows, drows = build_quiet()
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-56s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    worst = max(abs(sum(r["pct_" + PHASE[x]] for x in ROLES) - 100) for r in trows)
    check("role shares sum to 100% on every run", worst < 0.5, "max drift %.2f pp" % worst)

    need = [r for r in trows if r["scenario"] in ("S3", "S4", "S5")]
    have = {(r["scenario"], r["dose"], r["arm"], r["task"]) for r in drows}
    miss = [r["run_id"] for r in need
            if (r["scenario"], r["dose"], r["arm"], r["task"]) not in have]
    check("every S3/S4/S5 run is paired to an S1A task twin", not miss,
          "unpaired=%d %s" % (len(miss), miss[:3]))

    base = defaultdict(dict)
    for r in trows:
        base[(r["scenario"], r["condition"], r["dose"], r["arm"])][r["task"]] = r
    ghost = [r["run_id"] for r in drows if r["base_run"] not in idx]
    check("every base is a real measured run (no synthesis)", not ghost,
          "ghost bases=%s" % (ghost[:3] or "none"))

    over = [r["run_id"] for r in trows if r["stuck_tokens"] > r["out_tokens"]]
    check("stuck tokens <= team output on every run", not over, "violations=%s" % (over or "none"))

    cr4 = [r for r in drows if r["arm"] == "1" and r["task"] == "cr4"]
    check("arm-1 cr4 base score is the annotated 0.94",
          cr4 and all(r["base_score"] == 0.94 for r in cr4),
          sorted({r["base_score"] for r in cr4}))

    bad_score = [r for r in drows if r["d_score"] != "" and (
        abs(r["d_score"] - (r["score"] - r["base_score"])) > 1e-9
        or abs(r["d_score"]) > 1.0
        or r["score_base_run"] not in idx
        or f(idx[r["score_base_run"]]["regrade_score"], None) != r["base_score"])]
    check("every d_score = measured stress score - measured base score",
          not bad_score, "violations=%d %s" % (len(bad_score),
                                               [r["run_id"] for r in bad_score[:2]]))

    a2bad = [r for r in drows if r["arm"] == "2" and r["score_base_run"]
             and (idx[r["score_base_run"]]["arm"] != "2"
                  or idx[r["score_base_run"]]["scenario"] != "S1A")]
    check("arm-2 score/time bases are measured S1A arm-2 runs", not a2bad,
          "violations=%s" % ([r["run_id"] for r in a2bad[:3]] or "none"))

    tmiss = [r["run_id"] for r in drows if r["d_time_s"] == ""]
    check("stall-free time delta present for every pair", not tmiss,
          "missing=%s" % (tmiss[:3] or "none"))

    orows = overview_rows(base)
    tabs = two_tables(base)
    o2 = defaultdict(list)
    for r in orows["2"]:
        o2["%s %s" % (r["scenario"], r["dose"])].append(r["d_pct"])
    drift = max(abs(sum(v) / len(v) - t["d_pct"])
                for t in tabs["2"] for k, v in o2.items() if k == t["condition"])
    check("overview arm-2 token deltas match Table B (one estimator)", drift < 0.15,
          "max drift %.2f pp" % drift)
    return 1 if bad else 0

def build_quiet():
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return build()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
