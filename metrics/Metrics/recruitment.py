# Board allocation: who held tasks, who lost claim races, who worked
# without a task, and the fate of leader pins.
import io, json, os, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace
import run_index as rix
import canon

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

DELIVER_CLASSES = {"workspace", "workspace/tests", "attestation", "spec", "brief"}
ACTIVE_TOK = 2000
ADVISOR_CHARS = 1000

def _tid(x):
    return (x or "").lstrip("#").strip()

def board_story(run):
    acts = []
    for m in run["members"]:
        for t in m["turns"]:
            for a in t["actions"]:
                if a["tool"] in ("create_task", "claim_task", "update_task",
                                 "complete_task"):
                    acts.append((a["ts"], m["member"], a))
    acts.sort(key=lambda x: x[0])
    tasks = {}
    mev = defaultdict(Counter)

    def task(tid):
        return tasks.setdefault(tid, dict(
            task_id=tid, creator="", preassignee="", pre_by="", holders=[], losers=[],
            completer=""))

    for ts, member, a in acts:
        if a["blocked"]:
            continue
        try:
            j = json.loads(a["args_text"] or "{}")
        except Exception:
            j = {}
        tr = teamtrace._TRANSITION_PAT.search(a["result_excerpt"] or "")
        tool = a["tool"]
        if tool == "create_task":
            for td in (j.get("tasks") or ([j] if j.get("task_id") else [])):
                t = task(_tid(td.get("task_id")))
                if not t["creator"]:
                    t["creator"] = member
                asg = td.get("assignee")
                if asg and not t["preassignee"]:
                    t["preassignee"], t["pre_by"] = asg, member
                    mev[asg]["assigned"] += 1
        elif tool == "update_task":
            t = task(_tid(j.get("task_id")) or (_tid(tr.group(1)) if tr else ""))
            asg = j.get("assignee")
            if asg and not t["preassignee"]:
                t["preassignee"], t["pre_by"] = asg, member
                mev[asg]["assigned"] += 1
        elif tool == "claim_task":
            tid = _tid(j.get("task_id")) or (_tid(tr.group(1)) if tr else "")
            if not tid:
                continue
            t = task(tid)
            if tr and tr.group(3) == "claimed":
                t["holders"].append(member)
                mev[member]["held"] += 1
            elif tr and tr.group(3) == "completed":

                t["completer"] = member
                mev[member]["completed"] += 1
            elif not tr:
                t["losers"].append(member)
                mev[member]["lost"] += 1
        elif tool == "complete_task":
            if tr and tr.group(3) == "completed":
                t = task(_tid(tr.group(1)))
                t["completer"] = member
                mev[member]["completed"] += 1
    return tasks, mev

def honored_of(t):
    if not t["preassignee"]:
        return ""
    cands = [m for m in t["holders"] if m != t["pre_by"]]
    if t["completer"] and t["completer"] != t["pre_by"]:
        cands.append(t["completer"])
    if not cands:
        return "unresolved"
    return "honored" if cands[-1] == t["preassignee"] else "overridden"

def classify_members(run, mev):
    rows = []
    for m in run["members"]:
        member = m["member"]
        s = teamtrace.member_summary(m)
        writes = msgs_chars = 0
        reads = 0
        for t in m["turns"]:
            for a in t["actions"]:
                if a["blocked"]:
                    continue
                if a["tool"] in ("write_file", "edit_file") and \
                        canon.path_class(a["path"]) in DELIVER_CLASSES and \
                        "success=False" not in (a["result_excerpt"] or ""):
                    writes += 1
                elif a["tool"] == "send_message":
                    msgs_chars += len(a["args_text"] or "")
                elif a["tool"] in canon.READ_TOOLS or a["tool"] == "bash":
                    reads += 1
        e = mev.get(member, Counter())
        if rix.role_group(member) == "leader":
            cls = "leader"
        elif e["held"] or e["assigned"] or e["completed"]:
            cls = "holder"
        elif e["lost"]:
            cls = "contender"
        elif s["output_tokens"] > ACTIVE_TOK:
            cls = ("shadow-worker" if writes else
                   "shadow-advisor" if msgs_chars >= ADVISOR_CHARS else
                   "shadow-watcher")
        else:
            cls = "minimal"
        rows.append(dict(member=member, role_group=rix.role_group(member), cls=cls,
                         out_tokens=s["output_tokens"], deliver_writes=writes,
                         msg_chars=msgs_chars, held=e["held"], lost=e["lost"],
                         assigned=e["assigned"], completed=e["completed"]))
    return rows

def analyze_run(rec):
    run = teamtrace.load_run(rec["archive_path"])
    ctx = dict(run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],
               dose=rec["dose"], task=rec["task"])
    tasks, mev = board_story(run)
    trows = [dict(ctx, task_id=t["task_id"], phase=canon.phase_of(t["task_id"]),
                  creator=t["creator"], preassignee=t["preassignee"],
                  first_holder=(t["holders"][0] if t["holders"] else ""),
                  last_holder=(t["holders"][-1] if t["holders"] else ""),
                  completer=t["completer"], n_lost=len(t["losers"]),
                  losers=";".join(t["losers"]), honored=honored_of(t))
             for t in tasks.values()]
    prows = [dict(ctx, **r) for r in classify_members(run, mev)]
    return trows, prows

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
    trows, prows = [], []
    for n, rec in enumerate(idx, 1):
        if n % 25 == 0:
            print("  ... %d/%d" % (n, len(idx)), file=sys.stderr)
        a, b = analyze_run(rec)
        trows += a
        prows += b
    _write(os.path.join(OUT, "board_tasks.tsv"), trows)
    _write(os.path.join(OUT, "participation.tsv"), prows)
    print("wrote out/board_tasks.tsv (%d tasks), out/participation.tsv (%d members)\n"
          % (len(trows), len(prows)))
    lines = report(trows, prows)
    io.open(os.path.join(OUT, "recruitment_summary.md"), "w", encoding="utf-8").write(
        "\n".join(lines) + "\n")
    print("\nwrote out/recruitment_summary.md")

def _cell(prows, key):
    out = defaultdict(list)
    for r in prows:
        out[key(r)].append(r)
    return out

def enf_only_arm1(rows):
    cond = {r["run_id"]: r["condition"]
            for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    return [r for r in rows
            if not (r["arm"] == "1" and cond.get(r["run_id"]) == "prompt-only")]

# print the human-readable summary
def report(trows, prows):
    trows, prows = enf_only_arm1(trows), enf_only_arm1(prows)
    L = []

    def p(s=""):
        L.append(s)
        print(s)

    scens = ("S1A", "S1B", "S2", "S3", "S4", "S5")
    CLS = ("holder", "contender", "shadow-worker", "shadow-advisor", "shadow-watcher",
           "minimal")
    p("# Recruitment, claim races, and shadow participation")
    for arm in ("1", "2"):
        p()
        p("## Arm-%s (%s personas)" % (arm, "base" if arm == "1" else "specialist"))
        p()
        p("### Participation classes (non-leader members, share of pool)")
        p()
        p("| scen | " + " | ".join(CLS) + " | shadow tok share |")
        p("|" + "---|" * (len(CLS) + 2))
        for sc in scens:
            rs = [r for r in prows if r["scenario"] == sc and r["arm"] == arm
                  and r["cls"] != "leader"]
            if not rs:
                continue
            n = len(rs)
            tot = sum(r["out_tokens"] for r in rs) or 1
            sh_tok = sum(r["out_tokens"] for r in rs if r["cls"].startswith("shadow"))
            p("| %s | %s | %.1f%% |" % (
                sc, " | ".join("%.0f%%" % (100.0 * sum(1 for r in rs if r["cls"] == c) / n)
                               for c in CLS), 100.0 * sh_tok / tot))
        p()
        p("### Board pinning (tasks the leader pre-assigned an assignee)")
        p()
        p("| scen | tasks | pre-assigned | honored | overridden | unresolved |")
        p("|---|---|---|---|---|---|")
        for sc in scens:
            ts = [t for t in trows if t["scenario"] == sc and t["arm"] == arm]
            if not ts:
                continue
            pa = [t for t in ts if t["preassignee"]]
            h = Counter(t["honored"] for t in pa)
            p("| %s | %d | %d | %d | %d | %d |" % (
                sc, len(ts), len(pa), h["honored"], h["overridden"], h["unresolved"]))
        p()
        p("### Claim races")
        p()
        p("| scen | lost claims | contested tasks | peak contenders | winner roles |")
        p("|---|---|---|---|---|")
        for sc in scens:
            ts = [t for t in trows if t["scenario"] == sc and t["arm"] == arm]
            if not ts:
                continue
            contested = [t for t in ts if t["n_lost"] > 0]
            winners = Counter(rix.role_group(t["first_holder"]) for t in contested
                              if t["first_holder"])
            p("| %s | %d | %d/%d | %d | %s |" % (
                sc, sum(t["n_lost"] for t in ts), len(contested), len(ts),
                max((t["n_lost"] for t in ts), default=0),
                ", ".join("%s x%d" % kv for kv in winners.most_common(3)) or "-"))
        p()
    p("## Utilization by role (holder rate, arm-1 vs arm-2)")
    p()
    p("| role | arm-1 holders | arm-2 holders | arm-1 shadow | arm-2 shadow |")
    p("|---|---|---|---|---|")
    for role in ("planner", "executor", "verifier", "fullstack"):
        row = []
        for arm in ("1", "2"):
            rs = [r for r in prows if r["role_group"] == role and r["arm"] == arm]
            n = len(rs) or 1
            row.append("%.0f%%" % (100.0 * sum(1 for r in rs if r["cls"] == "holder") / n))
        for arm in ("1", "2"):
            rs = [r for r in prows if r["role_group"] == role and r["arm"] == arm]
            n = len(rs) or 1
            row.append("%.0f%%" % (100.0 * sum(1 for r in rs
                                               if r["cls"].startswith("shadow")) / n))
        p("| %s | %s |" % (role, " | ".join(row)))
    p()
    p("Read: `holder` needs an actual hold (claim-with-transition, assignment, or "
      "completion) — Phase 2's `recruited` flag also counts members who lost every race. "
      "Board pinning is update_task/create_task `assignee`; kickoff-message pinning is "
      "free text and out of scope. Shadows are boardless-but-active members; their token "
      "share is spend the board never sanctioned — the annotations show both rescuers "
      "(cr4-S5-arm-2 executor2) and spectators there.")
    return L

def show(run_id):
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    if run_id not in idx:
        sys.exit("unknown run_id: " + run_id)
    trows, prows = analyze_run(idx[run_id])
    print("\n=== %s — board tasks ===" % run_id)
    for t in trows:
        print("  %-18s pre=%s%-11s holders=%-30s lost=%d %s %s" % (
            t["task_id"][:18], t["preassignee"] or "-",
            (" (%s)" % t["honored"]) if t["honored"] else "",
            ",".join(filter(None, [t["first_holder"],
                                   t["last_holder"] if t["last_holder"] != t["first_holder"]
                                   else ""])) or "-",
            t["n_lost"], ("losers=" + t["losers"]) if t["losers"] else "",
            ("done=" + t["completer"]) if t["completer"] else ""))
    print("\n=== members ===")
    for r in sorted(prows, key=lambda x: x["cls"]):
        print("  %-12s %-10s %-15s tok=%-7d writes=%-3d msg_chars=%-6d held=%d lost=%d"
              % (r["member"], r["role_group"], r["cls"], r["out_tokens"],
                 r["deliver_writes"], r["msg_chars"], r["held"], r["lost"]))

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-66s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    t1, p1 = analyze_run(idx["cr4_enforced-20260808-114309"])
    imp = [t for t in t1 if t["phase"] == "impl"]
    check("cr4-enforced: 3-way race on #implement, an executor holds it",
          imp and imp[0]["n_lost"] >= 2
          and rix.role_group(imp[0]["first_holder"]) == "executor",
          imp and "lost=%d holder=%s" % (imp[0]["n_lost"], imp[0]["first_holder"]))

    t2, p2 = analyze_run(idx["cr4_s5partial_arm2-20260809-195057"])
    ti = {t["task_id"]: t for t in t2}
    check("cr4_s5partial_arm2: implement pinned to executor3, overridden",
          ti.get("implement", {}).get("preassignee") == "executor3"
          and ti["implement"]["honored"] == "overridden",
          "%s -> %s (%s)" % (ti.get("implement", {}).get("preassignee"),
                             ti.get("implement", {}).get("completer")
                             or ti.get("implement", {}).get("last_holder"),
                             ti.get("implement", {}).get("honored")))
    check("cr4_s5partial_arm2: planner2 holds #plan",
          ti.get("plan", {}).get("first_holder") == "planner2",
          ti.get("plan", {}).get("first_holder"))

    e2 = [r for r in p2 if r["member"] == "executor2"]
    check("cr4_s5partial_arm2: executor2 is a shadow advisor/worker",
          e2 and e2[0]["cls"] in ("shadow-advisor", "shadow-worker"),
          e2 and "%s tok=%d msg=%d" % (e2[0]["cls"], e2[0]["out_tokens"],
                                       e2[0]["msg_chars"]))

    both = p1 + p2
    okp = all(r["cls"] in ("leader", "holder", "contender", "shadow-worker",
                           "shadow-advisor", "shadow-watcher", "minimal") for r in both)
    okh = all(r["held"] or r["assigned"] or r["completed"]
              for r in both if r["cls"] == "holder")
    okc = all(r["lost"] and not (r["held"] or r["assigned"] or r["completed"])
              for r in both if r["cls"] == "contender")
    check("partition invariants hold (holder/contender definitions)",
          okp and okh and okc, "classes=%s" % dict(Counter(r["cls"] for r in both)))

    t6, _p6 = analyze_run(idx["test9_s5minimal_arm2-20260809-220537"])
    ti6 = {t["task_id"]: t for t in t6}
    done = {tid for tid, t in ti6.items() if t["completer"]}
    check("test9_s5minimal_arm2: 5 tasks completed, reverify claimed-never-completed",
          done == {"plan", "implement", "verify", "fix_service", "add_timeout_test"}
          and ti6.get("reverify", {}).get("first_holder")
          and not ti6.get("reverify", {}).get("completer"),
          "completed=%s reverify_holder=%s" % (sorted(done),
                                               ti6.get("reverify", {}).get("first_holder")))
    return 1 if bad else 0

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg:
        show(arg)
    else:
        build()
