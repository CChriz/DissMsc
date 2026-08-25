# Churn bursts, verbatim retries, terminal loops and cross-actor redo.
import io, os, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace
import run_index as rix
import generic_metrics as GM
import canon

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

MERGE_TURNS = 4
BURST_MIN = 3
DOOM_LEN = 8
REDO_CLASSES = {"workspace", "workspace/tests", "attestation", "spec", "brief"}

def norm_path(p):
    p = (p or "").replace("\\", "/")
    return p.split("run_current/", 1)[-1] if "run_current/" in p else p

def norm_cmd(c):
    return " ".join((c or "").split())[:200]

def member_work(mem):
    seq = []
    for t in mem["turns"]:
        for a in t["actions"]:
            if a["blocked"]:
                continue
            if a["tool"] in GM.WRITE_TOOLS:
                seq.append((t["turn"], a["ts"], "W", norm_path(a["path"]),
                            canon.path_class(a["path"]), False,
                            "success=False" not in (a["result_excerpt"] or "")))
            elif a["tool"] == "bash":
                cc = canon.cmd_class(a["path"] or "")
                seq.append((t["turn"], a["ts"], "R", norm_cmd(a["path"]), cc,
                            cc == "test", True))
    return seq

def bursts_of(seq):
    out, cur = [], []
    for step in seq:
        if step[2] != "R":
            if cur:
                out.append(cur)
            cur = []
            continue
        if cur and step[0] - cur[-1][0] > MERGE_TURNS:
            out.append(cur)
            cur = []
        cur.append(step)
    if cur:
        out.append(cur)
    flagged = []
    for b in out:
        terminal = bool(seq) and b[-1] is seq[-1]
        flagged.append((b, terminal))
    return flagged

def verbatim_streak(steps):
    best, best_cmd, run, prev = 1, "", 1, None
    for s in steps:
        if prev is not None and s[3] == prev:
            run += 1
            if run > best:
                best, best_cmd = run, prev
        else:
            run = 1
        prev = s[3]
    return (best, best_cmd) if best > 1 else (1, "")

def analyze_run(rec):
    run = teamtrace.load_run(rec["archive_path"])
    ctx = dict(run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],
               dose=rec["dose"], task=rec["task"])
    mrows, brows = [], []
    writes_by_path = defaultdict(list)
    churn = defaultdict(Counter)
    leader_ws = 0
    for mem in run["members"]:
        member = mem["member"]
        role = rix.role_group(member)

        if role == "leader":
            leader_ws += sum(1 for t in mem["turns"] for a in t["actions"]
                             if a["tool"] in GM.WRITE_TOOLS
                             and GM.path_class(a["path"]) == "workspace")
        seq = member_work(mem)
        for s in seq:
            if s[2] == "W":
                churn[member][s[3]] += 1
                if s[6] and s[4] in REDO_CLASSES:
                    writes_by_path[s[3]].append((s[1], member, role))
        bs = bursts_of(seq)
        max_burst = max((len(b) for b, _t in bs), default=0)
        max_vs = 0
        term_len = 0
        for b, terminal in bs:
            vs, vcmd = verbatim_streak(b)
            max_vs = max(max_vs, vs)
            if terminal:
                term_len = len(b)
            if len(b) >= BURST_MIN:
                classes = Counter(s[4] for s in b)
                brows.append(dict(ctx, member=member, role_group=role, len=len(b),
                                  n_test=sum(1 for s in b if s[5]),
                                  verbatim_streak=vs, verbatim_cmd=vcmd[:60],
                                  classes=";".join("%s=%d" % kv
                                                   for kv in classes.most_common()),
                                  turn_start=b[0][0], turn_end=b[-1][0],
                                  span_s=round(b[-1][1] - b[0][1], 1),
                                  terminal=int(terminal)))
        mrows.append(dict(ctx, member=member, role_group=role,
                          work_actions=len(seq),
                          bash_actions=sum(1 for s in seq if s[2] == "R"),
                          write_actions=sum(1 for s in seq if s[2] == "W"),
                          test_runs=sum(1 for s in seq if s[5]),
                          bursts=sum(1 for b, _t in bs if len(b) >= BURST_MIN),
                          max_burst=max_burst, verbatim_streak=max_vs,
                          terminal_burst_len=term_len,
                          paths_written=len(churn[member]),
                          max_path_writes=max(churn[member].values(), default=0),
                          redo_made=0, redone_by_others=0))
    by_member = {r["member"]: r for r in mrows}
    rrows = []
    for path, ws in writes_by_path.items():
        ws.sort()
        t0, first, first_role = ws[0]
        seen = set()
        for ts, member, role in ws[1:]:
            if member == first or member in seen:
                continue
            seen.add(member)
            n = sum(1 for x in ws if x[1] == member)
            rrows.append(dict(ctx, path=path[:70], path_class=canon.path_class(path),
                              first_writer=first, first_role=first_role,
                              rewriter=member, rewriter_role=role, n_rewrites=n,
                              ts_first=round(t0, 1), ts_redo=round(ts, 1),
                              gap_s=round(ts - t0, 1)))
            by_member[member]["redo_made"] += 1
            by_member[first]["redone_by_others"] += 1
    return mrows, brows, rrows, leader_ws

def _write(path, rows):
    if not rows:
        return
    cols = list(rows[0].keys())
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")

# build the output tables from the raw streams
def build():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    mrows, brows, rrows = [], [], []
    leader_ws = {}
    for n, rec in enumerate(idx, 1):
        if n % 25 == 0:
            print("  ... %d/%d" % (n, len(idx)), file=sys.stderr)
        a, b, c, lw = analyze_run(rec)
        mrows += a
        brows += b
        rrows += c
        leader_ws[rec["run_id"]] = lw
    _write(os.path.join(OUT, "repetition_members.tsv"), mrows)
    _write(os.path.join(OUT, "repetition_bursts.tsv"), brows)
    _write(os.path.join(OUT, "redo_writes.tsv"), rrows)
    print("wrote out/repetition_members.tsv (%d), out/repetition_bursts.tsv (%d), "
          "out/redo_writes.tsv (%d)\n" % (len(mrows), len(brows), len(rrows)))
    lines = report(mrows, brows, rrows, leader_ws,
                   {r["run_id"]: r for r in idx})
    with io.open(os.path.join(OUT, "repetition_summary.md"), "w",
                 encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\nwrote out/repetition_summary.md")

def enf_only_arm1(rows, idx):
    return [r for r in rows
            if not (r["arm"] == "1"
                    and idx.get(r["run_id"], {}).get("condition") == "prompt-only")]

# print the human-readable summary
def report(mrows, brows, rrows, leader_ws, idx):
    mrows = enf_only_arm1(mrows, idx)
    brows = enf_only_arm1(brows, idx)
    rrows = enf_only_arm1(rrows, idx)
    L = []

    def p(s=""):
        L.append(s)
        print(s)

    scens = ("S1A", "S1B", "S2", "S3", "S4", "S5")
    p("# Step repetition, doom-loops, and cross-actor redo")
    p()
    p("## Churn bursts by scenario (burst = consecutive bash, no intervening write/edit)")
    p()
    p("| scen | members | w/ burst>=%d | bursts | med len | max len | terminal>=%d "
      "(doom) | verbatim>=3 |" % (BURST_MIN, DOOM_LEN))
    p("|---|---|---|---|---|---|---|---|")
    for sc in scens:
        ms = [r for r in mrows if r["scenario"] == sc]
        bs = [r for r in brows if r["scenario"] == sc]
        if not ms:
            continue
        lens = sorted(b["len"] for b in bs)
        p("| %s | %d | %d | %d | %s | %s | %d | %d |" % (
            sc, len(ms), sum(1 for r in ms if r["bursts"]), len(bs),
            lens[len(lens) // 2] if lens else "-", lens[-1] if lens else "-",
            sum(1 for b in bs if b["terminal"] and b["len"] >= DOOM_LEN),
            sum(1 for b in bs if b["verbatim_streak"] >= 3)))
    p()
    p("## Who re-runs the tests (test-class bash actions by role)")
    p()
    p("| scen | planner | executor | verifier | fullstack | leader | verifier share |")
    p("|---|---|---|---|---|---|---|")
    for sc in scens:
        ms = [r for r in mrows if r["scenario"] == sc]
        if not ms:
            continue
        by = Counter()
        for r in ms:
            by[r["role_group"]] += r["test_runs"]
        tot = sum(by.values()) or 1
        p("| %s | %d | %d | %d | %d | %d | %.2f |" % (
            sc, by["planner"], by["executor"], by["verifier"], by["fullstack"],
            by["leader"], by["verifier"] / tot))
    p()
    p("## Doom-loops: terminal bursts >= %d (churned, then never acted again)" % DOOM_LEN)
    p()
    for b in sorted([b for b in brows if b["terminal"] and b["len"] >= DOOM_LEN],
                    key=lambda x: -x["len"]):
        p("- `%s` %s **%d steps** (%d test) t%d-%d, %.0fs — %s%s" % (
            b["run_id"], b["member"], b["len"], b["n_test"], b["turn_start"],
            b["turn_end"], b["span_s"], b["classes"],
            (" — verbatim x%d `%s`" % (b["verbatim_streak"], b["verbatim_cmd"])
             if b["verbatim_streak"] >= 3 else "")))
    p()
    p("## Verbatim retries (same command >= 3x, nothing changed in between)")
    p()
    for b in sorted([b for b in brows if b["verbatim_streak"] >= 3],
                    key=lambda x: -x["verbatim_streak"])[:15]:
        p("- `%s` %s x%d: `%s`" % (b["run_id"], b["member"], b["verbatim_streak"],
                                   b["verbatim_cmd"]))
    p()
    p("## Cross-actor redo (deliverable-surface path rewritten by a different member)")
    p()
    ws = [r for r in rrows if r["path_class"] != "attestation"]
    at = [r for r in rrows if r["path_class"] == "attestation"]
    p("| scen | redo events (non-attest) | runs w/ redo | top role pairs | "
      "attestation shared-writes |")
    p("|---|---|---|---|---|")
    for sc in scens:
        rs = [r for r in ws if r["scenario"] == sc]
        ats = [r for r in at if r["scenario"] == sc]
        n_runs = len({(r["run_id"]) for r in rs})
        pairs = Counter("%s->%s" % (r["first_role"], r["rewriter_role"]) for r in rs)
        p("| %s | %d | %d | %s | %d |" % (
            sc, len(rs), n_runs,
            ", ".join("%s x%d" % kv for kv in pairs.most_common(3)) or "-", len(ats)))
    p()
    p("## Leader substitute work (generic_metrics' leader workspace writes, recomputed)")
    p()
    by_cell = Counter()
    for rid, n in leader_ws.items():
        rec = idx[rid]
        by_cell["%s-%s" % (rec["scenario"], rec["dose"])] += n
    p("leader workspace writes by cell: %s"
      % (dict(sorted(by_cell.items())) if by_cell else "{}"))
    p()
    p("Read: redo is PATH-level (S4 duplication lands in different files by construction —"
      " see s4_seams); S2 bundles are file-disjoint by the collision gate, so S2 redo ~0"
      " is a design check, not a finding. Attestation shared-writes are the dual-verifier"
      " protocol working, EXCEPT when the second writer clobbers the verdict"
      " (multi4's attestation-merge-clobber).")
    return L

def show(run_id):
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    if run_id not in idx:
        sys.exit("unknown run_id: " + run_id)
    mrows, brows, rrows, lw = analyze_run(idx[run_id])
    print("\n=== %s ===" % run_id)
    for r in mrows:
        print("%-14s work=%d bash=%d writes=%d tests=%d max_burst=%d verbatim=%d "
              "terminal=%d churn_max=%d" % (
                  r["member"], r["work_actions"], r["bash_actions"], r["write_actions"],
                  r["test_runs"], r["max_burst"], r["verbatim_streak"],
                  r["terminal_burst_len"], r["max_path_writes"]))
    print("\nbursts >= %d:" % BURST_MIN)
    for b in brows:
        print("  %-14s len=%-3d test=%-2d verbatim=%d %s t%d-%d %s" % (
            b["member"], b["len"], b["n_test"], b["verbatim_streak"],
            "TERMINAL" if b["terminal"] else "        ", b["turn_start"], b["turn_end"],
            b["classes"]))
    print("\nredo events:")
    for r in rrows:
        print("  %s: %s(%s) -> %s(%s) x%d after %.0fs  [%s]" % (
            r["path_class"], r["first_writer"], r["first_role"], r["rewriter"],
            r["rewriter_role"], r["n_rewrites"], r["gap_s"], r["path"]))
    print("\nleader workspace writes: %d" % lw)

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-64s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    m, b, _r, _lw = analyze_run(idx["cr4_enforced-20260808-114309"])
    ex = [x for x in b if x["role_group"] == "executor"]
    big = max(ex, key=lambda x: x["len"]) if ex else None
    check("cr4-enforced: the annotated ~16-attempt debug burst is found",
          big is not None and 12 <= big["len"] <= 20 and big["n_test"] >= 1,
          "len=%s test=%s span=%ss" % (big and big["len"], big and big["n_test"],
                                       big and big["span_s"]))

    m2, _b2, _r2, _lw2 = analyze_run(idx["cr4_s5partial_arm2-20260809-195057"])
    t = {r["member"]: r["test_runs"] for r in m2}
    check("cr4_s5partial_arm2: verifiers 0 test runs, executor1 dominant (>=10)",
          t.get("executor1", 0) >= 10 and 1 <= t.get("executor2", 0) <= 2
          and t.get("verifier1", 0) == 0 and t.get("verifier2", 0) == 0
          and t["executor1"] == max(t.values()),
          "e1=%s e2=%s v1=%s v2=%s" % (t.get("executor1"), t.get("executor2"),
                                       t.get("verifier1", 0), t.get("verifier2", 0)))

    tot = Counter()
    for rid, rec in idx.items():
        _m, _b, _r, lw = analyze_run(rec)
        key = ("S3-full" if (rec["scenario"], rec["dose"]) == ("S3", "full") else
               "S3-partial" if rec["scenario"] == "S3" else "non-S3")
        tot[key] += lw

        _CACHE[rid] = (_m, _b, _r)
    check("leader workspace writes: S3-full=24, non-S3=0, S3-partial<=4",
          tot["S3-full"] == 24 and tot["non-S3"] == 0 and tot["S3-partial"] <= 4,
          dict(tot))

    run = teamtrace.load_run(idx["test9_s4-20260809-083623"]["archive_path"])
    n_blocked = sum(1 for mm in run["members"] for tt in mm["turns"]
                    for a in tt["actions"] if a["blocked"])
    m4, b4, _r4 = _CACHE["test9_s4-20260809-083623"]
    n_work = sum(r["work_actions"] for r in m4)
    n_all = sum(1 for mm in run["members"] for tt in mm["turns"] for a in tt["actions"]
                if not a["blocked"] and (a["tool"] in GM.WRITE_TOOLS or a["tool"] == "bash"))
    check("test9_s4: denials excluded (probe loop is stuck_reroute's, not ours)",
          n_blocked >= 2 and n_work == n_all,
          "denials=%d work=%d nonblocked-work=%d" % (n_blocked, n_work, n_all))

    _m5, _b5, r5 = _CACHE["multi4_s5minimal-20260809-165336"]
    hit = [r for r in r5 if r["path_class"] == "attestation"
           and r["first_writer"] == "verifier2" and r["rewriter"] == "verifier1"]
    check("multi4_s5minimal: attestation merge-clobber shows as v2->v1 redo",
          bool(hit), hit[0] if hit else [r for r in r5
                                         if r["path_class"] == "attestation"])
    return 1 if bad else 0

_CACHE = {}

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg:
        show(arg)
    else:
        build()
