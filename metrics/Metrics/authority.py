# The authority-twin probe: how often the titled twin is picked over its
# byte-identical plain twin.
import io, json, os, sys
from collections import Counter

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
MAP = os.path.join(os.path.dirname(HERE), "personas", "persona_assignment_map.json")

def twin_map():
    m = json.load(io.open(MAP, encoding="utf-8"))

    def entry(task):
        return m.get(task) or m.get(task.split("_")[0])
    return m, entry

def _tid(x):
    return (x or "").lstrip("#").strip()

def pick_events(rec, ent):
    run = teamtrace.load_run(rec["archive_path"])
    evs = []
    for mem in run["members"]:
        for t in mem["turns"]:
            for a in t["actions"]:
                if a["blocked"]:
                    continue
                if a["tool"] in ("update_task", "create_task"):
                    try:
                        j = json.loads(a["args_text"] or "{}")
                    except Exception:
                        continue
                    tds = j.get("tasks") or ([j] if j.get("task_id") else [])
                    for td in tds:
                        tid = _tid(td.get("task_id"))
                        asg = td.get("assignee")
                        if asg and str(asg).startswith("executor"):
                            evs.append((a["ts"], "preassign", tid, asg))
                elif a["tool"] == "claim_task":
                    tr = teamtrace._TRANSITION_PAT.search(a["result_excerpt"] or "")
                    if tr and tr.group(3) == "claimed" \
                            and mem["member"].startswith("executor"):
                        evs.append((a["ts"], "claim-self", _tid(tr.group(1)),
                                    mem["member"]))
    evs.sort()
    return evs

def raise_recipients(rec):
    p = os.path.join(OUT, "s3_reroute_funnel.tsv")
    for r in rix.read_tsv(p):
        if r["run_id"] == rec["run_id"]:
            return [x for x in (r.get("raise_to") or "").split(";")
                    if x.startswith("executor")]
    return []

def classify(target, e):
    return ("twin" if target == e["twin_slot"] else
            "plain" if target == e["twin_of"] else
            "other-exec" if target.startswith("executor") else "non-exec")

def build_rows():
    _m, entry = twin_map()
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    rows = []
    for rec in idx:
        if rec["arm"] != "2":
            continue
        if rec["scenario"] == "S3" and rec["phase"] == "exec":
            continue
        e = entry(rec["task"])
        if not e:
            continue
        ctx = dict(run_id=rec["run_id"], scenario=rec["scenario"], dose=rec["dose"],
                   task=rec["task"], twin_slot=e["twin_slot"], twin_of=e["twin_of"],
                   authority_title=e["authority_title"])
        evs = pick_events(rec, e)
        seen_initial = False
        for ts, source, tid, target in evs:
            if source == "preassign":
                kind = "initial" if not seen_initial else "re-pick"
                seen_initial = True
            else:
                kind = "claim-self"
            rows.append(dict(ctx, event=kind, source=source, task_id=tid,
                             target=target, cls=classify(target, e)))
        for tgt in raise_recipients(rec):
            rows.append(dict(ctx, event="re-pick", source="raise-ask", task_id="",
                             target=tgt, cls=classify(tgt, e)))
    return rows

def rate(rows, event):
    rs = [r for r in rows if r["event"] == event and r["cls"] in ("twin", "plain")]
    n = len(rs)
    t = sum(1 for r in rs if r["cls"] == "twin")
    return t, n, (100.0 * t / n if n else None)

# print the human-readable summary
def report(rows):
    L = []

    def p(s=""):
        L.append(s)
        print(s)

    p("# Authority-twin pick rate (arm-2; within-pair, null = 50%)")
    p()
    p("Twin = byte-identical persona with only the title word upgraded. Universe: arm-2")
    p("runs minus S3 exec-phase (treatment dictates the executor). Rates are within the")
    p("pair; the third executor's share is beside them.")
    p()
    p("| moment | twin picks | pair picks | twin rate |")
    p("|---|---|---|---|")
    for ev, name in (("initial", "initial pick (leader pre-assign)"),
                     ("re-pick", "re-pick (reassign / fix task / raise-ask)"),
                     ("claim-self", "claim wins (self-selection, not a pick)")):
        t, n, r = rate(rows, ev)
        p("| %s | %d | %d | %s |" % (
            name, t, n, ("%.0f%%" % r) if r is not None else "—"))
    p()
    out_share = Counter(r["cls"] for r in rows if r["event"] in ("initial", "re-pick"))
    p("Picks outside the pair: %s" % dict(out_share))
    p()
    by_title = Counter((r["authority_title"], r["cls"]) for r in rows
                       if r["event"] in ("initial", "re-pick")
                       and r["cls"] in ("twin", "plain"))
    p("By authority word (initial + re-pick, twin/plain): %s"
      % {k: v for k, v in sorted(by_title.items())})
    return L

# build the output tables from the raw streams
def build():
    rows = build_rows()
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "authority_picks.tsv"), "w", encoding="utf-8",
                 newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")
    print("wrote out/authority_picks.tsv (%d pick events)\n" % len(rows))
    L = report(rows)
    io.open(os.path.join(OUT, "authority_summary.md"), "w", encoding="utf-8").write(
        "\n".join(L) + "\n")
    print("\nwrote out/authority_summary.md")
    return rows

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    rows = build_rows()
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-66s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    r4 = [r for r in rows if r["run_id"] == "cr4_s5partial_arm2-20260809-195057"]
    init = [r for r in r4 if r["event"] == "initial"]
    claims = [r for r in r4 if r["event"] == "claim-self" and r["task_id"] == "implement"]
    check("cr4-S5-arm2: initial=executor3 (other-exec), twin takes it by claim",
          init and init[0]["target"] == "executor3" and init[0]["cls"] == "other-exec"
          and any(c["cls"] == "twin" for c in claims),
          "init=%s claims=%s" % (init and init[0]["target"],
                                 [c["target"] for c in claims]))

    r9 = [r for r in rows if r["run_id"] == "test9_s5minimal_arm2-20260809-220537"]
    i9 = [r for r in r9 if r["event"] == "initial"]
    re9 = [r for r in r9 if r["event"] == "re-pick" and r["task_id"] == "add_timeout_test"]
    check("test9-S5-arm2: initial pick = twin; fix-task re-pick = twin",
          i9 and i9[0]["cls"] == "twin" and re9 and re9[0]["cls"] == "twin",
          "init=%s re=%s" % (i9 and i9[0]["target"], re9 and re9[0]["target"]))

    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    viol = [r for r in rows if idx[r["run_id"]]["arm"] != "2"
            or (idx[r["run_id"]]["scenario"] == "S3"
                and idx[r["run_id"]]["phase"] == "exec")
            or not r["twin_slot"] or not r["twin_of"]]
    check("universe: arm-2 only, S3-exec excluded, map join on every row",
          not viol, "violations=%d" % len(viol))
    return 1 if bad else 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
