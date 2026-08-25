# One event table over all runs: assignment, blocked-capability,
# cross-edge and ablated-requirement stage automata.
import csv, io, json, os, re, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace
import run_index as rix
import stuck_reroute as SR
import s4_seams as S4

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

AUTOMATA = {
    "assignment":          ["announced", "claimed", "executed", "reported", "verified"],
    "blocked-capability":  ["encountered", "raised", "rerouted", "recovered"],
    "cross-edge":          ["probed", "asked", "crossed", "integrated"],
    "ablated-requirement": ["ablated", "named", "disposed"],
}
STAGE_IDX = {ut: {s: i for i, s in enumerate(st)} for ut, st in AUTOMATA.items()}

EVENT_COLS = ["run_id", "scenario", "arm", "dose", "task", "unit_type", "unit",
              "stage", "stage_idx", "ts_rel", "agent", "role", "channel", "evidence_ref"]

BOARD_CLAIM = ("claim_task", "update_task", "complete_task")

RELAY_CHARS = 400

_READONLY = {"find", "ls", "cat", "head", "tail", "grep", "wc", "tree", "pwd", "echo",
             "which", "stat", "du", "getfacl", "id", "whoami", "env", "printenv", "file",
             "sort", "uniq", "diff", "date", "cd", "true", "sudo"}
_SEG = re.compile(r"&&|\|\||[;|]")

def _is_readonly_cmd(cmd):
    segs = [s.strip() for s in _SEG.split(cmd or "") if s.strip()]
    if not segs:
        return True
    return all(re.split(r"\s+", s)[0].split("/")[-1] in _READONLY for s in segs)

def deliverable_action(role, a):
    if not ok_action(a):
        return False
    p = (a["path"] or "").replace("\\", "/")
    tool = a["tool"]
    if role == "planner":
        if tool == "send_message":
            return len(a["args_text"] or "") >= RELAY_CHARS
        return tool in ("write_file", "edit_file") and re.search(r"spec|plan|brief", p, re.I)
    if role == "verifier":
        return (tool in ("write_file", "edit_file") and "attestation" in p) or (
            tool == "bash" and not _is_readonly_cmd(p))
    if role in ("executor", "fullstack"):
        return (tool in ("write_file", "edit_file") and "workspace/" in p) or (
            tool == "bash" and not _is_readonly_cmd(p))
    return tool in ("write_file", "edit_file") or (
        tool == "bash" and not _is_readonly_cmd(p))

def ok_action(a):
    return not a["blocked"] and not a["failed"]

def run_t0(run):
    return min((t["start_ts"] for m in run["members"] for t in m["turns"]), default=0)

def ev(rec, unit_type, unit, stage, ts_rel, agent, channel="", evidence=""):
    return dict(run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],
                dose=rec["dose"], task=rec["task"], unit_type=unit_type, unit=unit,
                stage=stage, stage_idx=STAGE_IDX[unit_type][stage],
                ts_rel=("" if ts_rel is None else round(ts_rel, 1)), agent=agent,
                role=rix.role_group(agent) if agent else "", channel=channel,
                evidence_ref=str(evidence)[:120])

def assignment_events(rec, run=None):
    run = run or teamtrace.load_run(rec["archive_path"])
    t0 = run_t0(run)
    out = []
    announced = {}
    claims = {}
    completed = {}

    for m in run["members"]:
        for t in m["turns"]:
            for a in t["actions"]:
                if a["tool"] == "create_task":
                    try:
                        j = json.loads(a["args_text"] or "{}")
                    except Exception:
                        continue
                    tasks = j.get("tasks")
                    tasks = tasks if isinstance(tasks, list) else [j]
                    for spec in tasks:
                        tid = str(spec.get("task_id") or "").strip()
                        if not tid or tid in announced:
                            continue
                        announced[tid] = a["ts"]
                        out.append(ev(rec, "assignment", tid, "announced", a["ts"] - t0,
                                      m["member"], "board",
                                      "create_task %s" % (spec.get("title", "")[:40])))
                elif a["tool"] in BOARD_CLAIM:
                    tr = teamtrace._TRANSITION_PAT.search(a["result_excerpt"] or "")
                    if not tr:
                        continue
                    tid, frm, to = tr.group(1), tr.group(2), tr.group(3)

                    if to == "claimed" and tid not in claims:
                        claims[tid] = (a["ts"], m["member"])
                    elif to == "completed" and tid not in completed:
                        completed[tid] = (a["ts"], m["member"])

    for tid, (ts, who) in sorted(claims.items(), key=lambda kv: kv[1][0]):
        out.append(ev(rec, "assignment", tid, "claimed", ts - t0, who, "board",
                      "pending->claimed"))

    exec_ts = {}
    for tid, (cts, who) in claims.items():
        mem = next((m for m in run["members"] if m["member"] == who), None)
        if not mem:
            continue
        role = rix.role_group(who)
        first = None
        for t in mem["turns"]:
            for a in t["actions"]:
                if a["ts"] >= cts and deliverable_action(role, a):
                    if first is None or a["ts"] < first[0]:
                        first = (a["ts"], a["tool"], a["path"] or "")
        if first:
            exec_ts[tid] = first[0]
            out.append(ev(rec, "assignment", tid, "executed", first[0] - t0, who, "workspace",
                          "%s %s" % (first[1], (first[2] or "")[-60:])))

    rep_ts = {}
    for tid, (cts, who) in claims.items():
        cand = completed.get(tid)
        if cand:
            rep_ts[tid] = cand[0]
            out.append(ev(rec, "assignment", tid, "reported", cand[0] - t0, cand[1], "board",
                          "claimed->completed"))
            continue
        base = exec_ts.get(tid)
        if base is None:
            continue
        mem = next((m for m in run["members"] if m["member"] == who), None)
        msg = None
        for t in (mem["turns"] if mem else []):
            for a in t["actions"]:
                if a["tool"] == "send_message" and a["ts"] >= base:
                    if msg is None or a["ts"] < msg:
                        msg = a["ts"]
        if msg is not None:
            rep_ts[tid] = msg
            out.append(ev(rec, "assignment", tid, "reported", msg - t0, who, "message",
                          "first message after executing"))

    for tid, (ts, who) in completed.items():
        if tid not in claims and tid in announced:
            rep_ts[tid] = ts
            out.append(ev(rec, "assignment", tid, "reported", ts - t0, who, "board",
                          "claimed->completed (no claim event recorded)"))

    att = None
    for m in run["members"]:
        if rix.role_group(m["member"]) not in ("verifier", "fullstack"):
            continue
        for t in m["turns"]:
            for a in t["actions"]:
                p = (a["path"] or "").replace("\\", "/")
                if (a["tool"] in ("write_file", "edit_file") and "attestation" in p
                        and ok_action(a) and (att is None or a["ts"] < att[0])):
                    att = (a["ts"], m["member"], p)
    if att:
        for tid, rts in rep_ts.items():
            if att[0] >= rts:
                out.append(ev(rec, "assignment", tid, "verified", att[0] - t0, att[1],
                              "attestation", "run-level: " + att[2][-50:]))
    return out

def s3_events(rec):
    f = SR.s3_funnel(rec)
    unit = "%s-capability" % f["phase"]
    out = []
    for stage, key, agent, chan in (
            ("encountered", "encountered_s", f["encountered_by"], "denial"),
            ("raised", "raised_s", f["encountered_by"], "message"),
            ("rerouted", "decided_s", "team_leader", "board"),
            ("recovered", "landed_s", "", f["landed_by"] or "")):
        v = f.get(key, "")
        if v == "":
            continue
        who = agent
        if stage == "recovered":
            who = {"leader": "team_leader", "leader-relay": "team_leader"}.get(
                f["landed_by"], f["survivor"] or "")
        out.append(ev(rec, "blocked-capability", unit, stage, float(v), who, chan,
                      "s3_funnel.%s" % key))
    return out

def s4_events(rec, tm_cache={}):
    task = rec["task"]
    if not os.path.isfile(os.path.join(S4.MAPS, task + ".split.json")):
        return [], "no split map for task %s" % task
    res = S4.analyze(task, rec["archive_path"])
    tm = res["_tm"]
    run = teamtrace.load_run(rec["archive_path"])
    t0 = run_t0(run)

    msgs, denials = [], []
    for m in run["members"]:
        name = m["member"]
        for t in m["turns"]:
            for a in t["actions"]:
                if a["tool"] == "send_message":
                    try:
                        j = json.loads(a["args_text"] or "{}")
                    except Exception:
                        continue
                    msgs.append((a["ts"], name, str(j.get("to", "")),
                                 str(j.get("content", ""))))
                elif a["blocked"]:
                    p = (a["path"] or "").replace("\\", "/")
                    rel = p.split("workspace/")[-1] if "workspace/" in p else p
                    denials.append((a["ts"], name, rel, a["tool"]))
    msgs.sort()
    denials.sort()

    out = []
    for i, e in enumerate(res["edges"]):
        src, dst = e["edge"].split(" -> ")
        unit = "e%d:%s->%s" % (i, src, dst)
        home = tm.zone_of_path(src)
        if home not in ("A", "B"):
            home = tm.zone_of_path(dst)
        needer = "B" if home == "A" else "A"
        eps = [p for p in (src, dst) if tm.zone_of_path(p) in ("A", "B")]

        for ts, who, rel, tool in denials:
            if tm.member_zone(who) not in ("A", "B") or tm.member_zone(who) == home:
                continue
            if any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in eps):
                out.append(ev(rec, "cross-edge", unit, "probed", ts - t0, who, tool, rel))
                break

        home_paths = [p for p in tm.map["zone" + home]["paths"]]
        refs = [p for p in home_paths] + [os.path.basename(p.rstrip("/")) for p in home_paths]
        for ts, who, to, content in msgs:
            if tm.member_zone(who) != needer:
                continue
            if any(r and r in content for r in refs):
                out.append(ev(rec, "cross-edge", unit, "asked", ts - t0, who, "message",
                              "to=%s" % to[:20]))
                break

        delivered = sorted((c for c in e["crossings"] if c["mode"] == "delivered"),
                           key=lambda c: c["ts"])
        if delivered:
            c = delivered[0]
            out.append(ev(rec, "cross-edge", unit, "crossed", c["ts"] - t0, c["from"],
                          c["channel"], "%s (%s)" % (c["symbol"], c["prov"])))

        t_end = max((t["end_ts"] for m in run["members"] for t in m["turns"]), default=t0)
        hit = None
        for sym, meta in S4._edge_symbols(tm, e):
            if meta["prov"] not in ("pristine", "emergent"):
                continue
            nz = "B" if meta["home"] == "A" else "A"
            for p in tm.map["zone" + nz]["paths"]:
                for frel, text in S4.files_under(res["_final_ws"], p):
                    if S4.word_in(sym, text):
                        hit = (sym, frel)
                        break
                if hit:
                    break
            if hit:
                break
        if hit:
            out.append(ev(rec, "cross-edge", unit, "integrated", t_end - t0, "", "artifact",
                          "%s in %s" % hit))
    return out, ""

def s5_events(rec, units_by_run):
    out = []
    for u in units_by_run.get(rec["run_id"], []):

        unit = "%s :: %s" % ((u["section"] or "")[:40], (u["canaries"] or u["unit"])[:40])
        ts = u["t_first_mention_rel"]
        ts = float(ts) if ts not in ("", None) else None
        det, who = u["detected_by"], u["first_namer"]

        out.append(ev(rec, "ablated-requirement", unit, "ablated", None, "",
                      u["stratum"], u["canaries"][:60]))
        if det != "none":
            verifier_caught = u["named_by_verifier"] == "1"
            out.append(ev(rec, "ablated-requirement", unit, "named", ts, who,
                          "at-verify" if verifier_caught else "at-plan",
                          "first=%s%s" % (who or det,
                                          "; verifier also named" if verifier_caught
                                          and rix.role_group(who) != "verifier" else "")))
        if det != "none" and u["disposition"] in ("hard-fail-emitted", "downgraded-in-pass"):
            out.append(ev(rec, "ablated-requirement", unit, "disposed", None, "",
                          u["disposition"], "verdict=%s" % u["attestation_verdict"]))
    return out

def s5_units():
    p = os.path.join(OUT, "s5_funnel_units.tsv")
    if not os.path.isfile(p):
        return {}
    by = defaultdict(list)
    for r in rix.read_tsv(p):
        by[r["run_id"]].append(r)
    return by

def build_events(index=None, quiet=False):
    idx = index or rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    s5u = s5_units()
    events, notes = [], []
    for n, rec in enumerate(idx, 1):
        if not quiet and n % 20 == 0:
            print("  ... %d/%d runs" % (n, len(idx)), file=sys.stderr)
        try:
            events += assignment_events(rec)
        except Exception as e:
            notes.append("%s: assignment failed: %s" % (rec["run_id"], e))
        if rec["scenario"] == "S3" and rec["phase"]:
            try:
                events += s3_events(rec)
            except Exception as e:
                notes.append("%s: s3 adapter failed: %s" % (rec["run_id"], e))
        elif rec["scenario"] == "S4":
            try:
                rows, why = s4_events(rec)
                events += rows
                if why:
                    notes.append("%s: %s" % (rec["run_id"], why))
            except Exception as e:
                notes.append("%s: s4 adapter failed: %s" % (rec["run_id"], e))
        elif rec["scenario"] == "S5":
            events += s5_events(rec, s5u)
    return events, notes

def units_table(events):
    by = defaultdict(list)
    for e in events:
        by[(e["run_id"], e["unit_type"], e["unit"])].append(e)
    rows = []
    for (rid, ut, unit), evs in by.items():
        evs.sort(key=lambda e: (e["stage_idx"], e["ts_rel"] if e["ts_rel"] != "" else 0))
        deepest = max(e["stage_idx"] for e in evs)
        first, last = evs[0], evs[-1]
        ts = [e["ts_rel"] for e in evs if e["ts_rel"] != ""]
        rows.append(dict(
            run_id=rid, scenario=first["scenario"], arm=first["arm"], dose=first["dose"],
            task=first["task"], unit_type=ut, unit=unit,
            deepest_stage=AUTOMATA[ut][deepest], deepest_idx=deepest,

            completion=round((deepest + 1) / len(AUTOMATA[ut]), 3),
            stages_observed=len({e["stage_idx"] for e in evs}),
            complete=int(deepest == len(AUTOMATA[ut]) - 1),
            stage_path=">".join(e["stage"] for e in evs),
            skipped=int(len({e["stage_idx"] for e in evs}) != deepest + 1),
            t_first=(min(ts) if ts else ""), t_last=(max(ts) if ts else ""),
            span_s=(round(max(ts) - min(ts), 1) if len(ts) > 1 else ""),
            agents=";".join(sorted({e["agent"] for e in evs if e["agent"]})),
            channels=";".join(sorted({e["channel"] for e in evs if e["channel"]}))))
    rows.sort(key=lambda r: (r["run_id"], r["unit_type"], r["unit"]))
    return rows

def runs_table(urows, index):
    meta = {r["run_id"]: r for r in index}
    by = defaultdict(list)
    for r in urows:
        by[(r["run_id"], r["unit_type"])].append(r)
    rows = []
    for (rid, ut), rs in sorted(by.items()):
        m = meta.get(rid, {})
        att = Counter(r["deepest_stage"] for r in rs)
        rows.append(dict(
            run_id=rid, scenario=rs[0]["scenario"], arm=rs[0]["arm"], dose=rs[0]["dose"],
            task=rs[0]["task"], unit_type=ut, units=len(rs),
            funnel_completion=round(sum(r["completion"] for r in rs) / len(rs), 3),
            complete_units=sum(r["complete"] for r in rs),
            **{"died_at_" + s: att.get(s, 0) for s in AUTOMATA[ut]},
            signature=" | ".join(sorted({r["stage_path"] for r in rs})),
            regrade_score=m.get("regrade_score", ""), regrade_pass=m.get("regrade_pass", ""),
            framework_outcome=m.get("framework_outcome", "")))
    return rows

def _write(path, rows, delim="\t"):
    if not rows:
        return
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, cols, delimiter=delim, extrasaction="ignore",
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

# build the output tables from the raw streams
def build():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    if not idx:
        sys.exit("out/run_index.tsv missing — run `python run_index.py` first")
    events, notes = build_events(idx)
    events.sort(key=lambda e: (e["run_id"], e["unit_type"], e["unit"], e["stage_idx"]))
    _write(os.path.join(OUT, "events.csv"), events, delim=",")
    urows = units_table(events)
    rrows = runs_table(urows, idx)
    _write(os.path.join(OUT, "trajectory_units.tsv"), urows)
    _write(os.path.join(OUT, "trajectory_runs.tsv"), rrows)
    print("wrote out/events.csv (%d events), out/trajectory_units.tsv (%d units), "
          "out/trajectory_runs.tsv (%d rows)" % (len(events), len(urows), len(rrows)))
    idx_by_unit = defaultdict(dict)
    for e in events:
        if e["unit_type"] == "assignment":
            idx_by_unit[(e["run_id"], e["unit"])][e["stage"]] = e
    report._events_by_unit = idx_by_unit
    if notes:
        print("\nnotes (%d):" % len(notes))
        for n in notes:
            print("  " + n)
    report(urows, rrows)
    return events, urows, rrows

def v_role(stages):
    return (stages.get("claimed") or {}).get("role", "")

# print the human-readable summary
def report(urows, rrows):
    print("\n=== FUNNEL ATTRITION by unit type (units, %% dying at each stage) ===")
    for ut, stages in AUTOMATA.items():
        rs = [r for r in urows if r["unit_type"] == ut]
        if not rs:
            continue
        att = Counter(r["deepest_stage"] for r in rs)
        n = len(rs)
        print("\n%-20s n=%d  mean completion %.3f" % (
            ut, n, sum(r["completion"] for r in rs) / n))
        for i, s in enumerate(stages):

            reached = sum(1 for r in rs if s in r["stage_path"].split(">"))

            tail = ("complete" if i == len(stages) - 1 else "died here")
            print("   %-18s reached %4d (%3.0f%%)   %-9s %4d (%3.0f%%)"
                  % (s, reached, 100.0 * reached / n, tail, att.get(s, 0),
                     100.0 * att.get(s, 0) / n))
        sk = sum(1 for r in rs if r["skipped"])
        print("   (%d of %d units skip a stage — entering mid-automaton is legal: a "
              "survivor can recover with no leader decision, a verifier can catch a unit "
              "the plan side never flagged)" % (sk, n))

    ev_by_unit = getattr(report, "_events_by_unit", None)
    if ev_by_unit:
        rep = [k for k, v in ev_by_unit.items() if "reported" in v]
        vv = [k for k in rep if v_role(ev_by_unit[k]) == "verifier"]
        oo = [k for k in rep if v_role(ev_by_unit[k]) != "verifier"]
        def _sh(ks):
            n = sum(1 for k in ks if "verified" in ev_by_unit[k])
            return "%d/%d (%.0f%%)" % (n, len(ks), 100.0 * n / len(ks)) if ks else "-"
        print("\n   `verified` by claimant: non-verifier %s | verifier's own verify task %s"
              " (structurally unreachable — its attestation IS the deliverable)"
              % (_sh(oo), _sh(vv)))

    print("\n=== assignment funnel by scenario ===")
    print("%-6s %6s %6s %11s %9s %9s %9s" % ("scen", "runs", "units", "completion",
                                             "claimed", "executed", "reported"))
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        rs = [r for r in urows if r["unit_type"] == "assignment" and r["scenario"] == sc]
        if not rs:
            continue
        runs = len({r["run_id"] for r in rs})
        n = len(rs)
        print("%-6s %6d %6d %11.3f %9.0f%% %9.0f%% %9.0f%%" % (
            sc, runs, n, sum(r["completion"] for r in rs) / n,
            100.0 * sum(1 for r in rs if "claimed" in r["stage_path"].split(">")) / n,
            100.0 * sum(1 for r in rs if "executed" in r["stage_path"].split(">")) / n,
            100.0 * sum(1 for r in rs if "reported" in r["stage_path"].split(">")) / n))

    print("\n=== most common stage paths per unit type ===")
    for ut in AUTOMATA:
        rs = [r for r in urows if r["unit_type"] == ut]
        if not rs:
            continue
        print("  %s:" % ut)
        for path, k in Counter(r["stage_path"] for r in rs).most_common(4):
            print("     %4d  %s" % (k, path))

    print("\n=== funnel completion x outcome (assignment units, regraded runs) ===")
    rows = [r for r in rrows if r["unit_type"] == "assignment" and r["regrade_score"]
            not in ("", None)]
    buckets = defaultdict(list)
    for r in rows:
        try:
            s = float(r["regrade_score"])
        except ValueError:
            continue
        buckets["pass (>=1.0)" if s >= 1.0 else
                "partial (0.5-1)" if s >= 0.5 else "low (<0.5)"].append(r)
    for k in ("pass (>=1.0)", "partial (0.5-1)", "low (<0.5)"):
        rs = buckets.get(k, [])
        if rs:
            print("  %-16s n=%3d  mean assignment completion %.3f" % (
                k, len(rs), sum(float(r["funnel_completion"]) for r in rs) / len(rs)))

def show(run_id):
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    rec = next((r for r in idx if r["run_id"] == run_id), None)
    if rec is None:
        sys.exit("unknown run_id: " + run_id)
    events, notes = build_events([rec], quiet=True)
    print("\n=== %s (%s arm-%s %s, task %s) ===" % (rec["run_id"], rec["scenario"],
                                                    rec["arm"], rec["dose"], rec["task"]))
    for n in notes:
        print("  note: " + n)
    print("%9s  %-20s %-26s %-18s %-12s %s" % ("ts", "unit_type", "unit", "stage",
                                               "agent", "evidence"))
    for e in sorted(events, key=lambda e: (e["ts_rel"] if e["ts_rel"] != "" else 1e9,
                                           e["unit_type"], e["stage_idx"])):
        print("%9s  %-20s %-26s %-18s %-12s %s" % (
            e["ts_rel"], e["unit_type"], e["unit"][:26], e["stage"], e["agent"][:12],
            e["evidence_ref"][:44]))
    for r in units_table(events):
        print("  unit %-26s %-20s deepest=%-16s %s" % (
            r["unit"][:26], r["unit_type"], r["deepest_stage"], r["stage_path"]))

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    by_id = {r["run_id"]: r for r in idx}
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-62s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    def units_of(rid, ut=None):
        rec = by_id[rid]
        evs, _ = build_events([rec], quiet=True)
        return [u for u in units_table(evs) if ut is None or u["unit_type"] == ut]

    p5 = units_of("p5_s3partial-20260808-204549", "blocked-capability")
    check("p5_s3partial: the reroute unit never reaches `recovered`",
          p5 and all(u["deepest_stage"] != "recovered" for u in p5),
          "deepest=%s" % [u["deepest_stage"] for u in p5])
    cr = units_of("crypto1_s3full-20260808-230358", "blocked-capability")
    check("crypto1_s3full: encountered and raised are both emitted",
          cr and cr[0]["deepest_idx"] >= 1, "path=%s" % (cr[0]["stage_path"] if cr else "-"))

    pipe = units_of("pipe3_stream_processing_s4-20260809-091434", "cross-edge")
    check("S4 pipe3: no cross-edge unit reaches `crossed`",
          pipe and all(u["deepest_idx"] < 2 for u in pipe),
          "n=%d deepest=%s" % (len(pipe), sorted({u["deepest_stage"] for u in pipe})))

    s5 = units_of("spec5_s5partial-20260809-154345", "ablated-requirement")
    check("S5 spec5 arm-1: every unit is named, and by a verifier",
          s5 and all("named" in u["stage_path"].split(">") and "at-verify" in u["channels"]
                     for u in s5),
          "%d/%d units named at-verify"
          % (sum(1 for u in s5 if "at-verify" in u["channels"]), len(s5)))

    asg = units_of("crypto1_s3full-20260808-230358", "assignment")
    plan = next((u for u in asg if u["unit"] == "plan"), None)
    impl = next((u for u in asg if u["unit"] == "implement"), None)
    check("crypto1_s3full: `plan` is announced, claimed by planner1, reported",
          plan and "claimed" in plan["stage_path"] and "reported" in plan["stage_path"]
          and "planner1" in plan["agents"], "path=%s agents=%s"
          % (plan["stage_path"] if plan else "-", plan["agents"] if plan else "-"))
    check("crypto1_s3full: `implement` has exactly one claimant (3 races lost)",
          impl and impl["agents"].count(";") <= 1,
          "agents=%s" % (impl["agents"] if impl else "-"))

    events, notes = build_events(idx)
    urows = units_table(events)
    check("no adapter failed on any of the 168 runs", not notes,
          "%d notes%s" % (len(notes), (": " + notes[0]) if notes else ""))
    s3u = [u for u in urows if u["unit_type"] == "blocked-capability"]
    check("every S3 run emits its capability unit and every one is `encountered`",
          len(s3u) == 48 and all(u["stage_path"].startswith("encountered") for u in s3u),
          "%d units, all start encountered=%s"
          % (len(s3u), all(u["stage_path"].startswith("encountered") for u in s3u)))

    rec_n = sum(1 for u in s3u if u["deepest_stage"] == "recovered")
    check("S3 recovered-unit count reproduces the frozen 44/48 landing count",
          rec_n == 44, "%d/48 recovered" % rec_n)

    ann = {u["run_id"] for u in urows if u["unit_type"] == "assignment"}
    missing = sorted({r["run_id"] for r in idx} - ann)
    check("every run announces an assignment, bar the known P6-enforced stall",
          missing == ["P6_enforced-20260808-143229"], "runs with none: %s" % (missing or "-"))

    fu = s5_units()
    measurable = sum(len(rs) for rs in fu.values())
    named = sum(1 for rs in fu.values() for r in rs if r["detected_by"] != "none")
    su = [u for u in urows if u["unit_type"] == "ablated-requirement"]
    check("S5 units match s5_funnel's measurable units one-for-one",
          len({(u["run_id"], u["unit"]) for u in su}) == measurable,
          "trajectory %d vs s5_funnel %d" % (len(su), measurable))
    got_named = sum(1 for u in su if "named" in u["stage_path"].split(">"))
    check("S5 named units match s5_funnel's detection count", got_named == named,
          "trajectory %d vs s5_funnel %d" % (got_named, named))

    sfa = sum(1 for u in su if u["deepest_stage"] == "ablated" and "silent" in u["channels"])
    check("silent-stratum units that die at `ablated` reproduce the 3 silent-false-accepts",
          sfa == 3, "%d never-named silent units" % sfa)
    return 1 if bad else 0

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg:
        show(arg)
    else:
        build()
