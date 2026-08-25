# Walks backwards from each deliverable: whose work fed it, and what
# evidence the attestor personally held.
import csv, io, os, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix
from conformance import parse_strip
from chains import strips_by_run

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
IMPL = ("EXEC", "FULL")

def last_inbound(toks, actor, before, substantive=False):
    for j in range(before - 1, -1, -1):
        t = toks[j]
        if t["verb"] in ("MSG", "BROADCAST") and (t["tgt"] == actor or t["tgt"] == "*"):
            if substantive and not (t["args"] & {"M", "L", "XL"}):
                continue
            return j
    return None

def _support(toks, who, before):
    for j in range(before - 1, -1, -1):
        t = toks[j]
        if t["who"] != who:
            continue
        if (t["verb"] == "WRITE" and t["args"] & {"workspace", "workspace/tests",
                                                  "attestation"})                 or (t["verb"] == "RUN" and t["args"] & {"test", "run", "sh"})                 or (t["verb"] == "READ" and "spec" in t["args"]):
            return j
    return None

def trace_spine(toks, i_root):
    def pick(actor, before):
        best = {}
        for j in range(before - 1, -1, -1):
            t = toks[j]
            if t["verb"] not in ("MSG", "BROADCAST") or not (
                    t["tgt"] == actor or t["tgt"] == "*"):
                continue
            lead = t["who"] == "LEAD"
            sub = bool(t["args"] & {"M", "L", "XL"})
            key = ("nonlead-sub" if not lead and sub else
                   "nonlead" if not lead else "lead")
            best.setdefault(key, j)
        return best.get("nonlead-sub", best.get("nonlead", best.get("lead")))

    chain, i = [i_root], i_root
    actor = toks[i_root]["who"]
    origin = "run-start"
    for _hop in range(24):
        i_trig = pick(actor, i)
        lead_only = i_trig is not None and toks[i_trig]["who"] == "LEAD"

        if i_trig is None or lead_only:
            i_read = None
            for j in range(i - 1, -1, -1):
                t = toks[j]
                if (t["who"] == actor and t["verb"] == "READ"
                        and t["args"] & {"workspace", "workspace/tests"}):
                    i_read = j
                    break
            if i_read is not None:
                i_write = None
                for j in range(i_read - 1, -1, -1):
                    t = toks[j]
                    if (t["who"].startswith(IMPL) and t["verb"] == "WRITE"
                            and t["args"] & {"workspace", "workspace/tests"}):
                        i_write = j
                        break
                if i_write is not None:
                    chain += [i_read, i_write]
                    i, actor = i_write, toks[i_write]["who"]
                    continue
        if i_trig is None:

            claimed = any(t["who"] == actor and t["verb"] == "CLAIM"
                          for t in toks[:i])
            origin = "board-claim" if claimed else "unprompted"
            break
        chain.append(i_trig)
        sender = toks[i_trig]["who"]
        if sender == "LEAD" and toks[i_trig]["verb"] == "BROADCAST":
            origin = "kickoff"
            break
        j = _support(toks, sender, i_trig)
        if j is not None:
            chain.append(j)
            i = j
        else:
            i = i_trig
        actor = sender
    return chain, origin

def backtrace_run(rec, strips):
    toks = parse_strip(strips.get(rec["run_id"], {}).get("*", ""))
    marked, tree = set(), []

    def mark(i, why):
        if i is not None and i not in marked:
            marked.add(i)
            t = toks[i]
            tree.append("%s.%s(%s)%s <- %s" % (
                t["who"], t["verb"], ",".join(sorted(t["args"])),
                (">" + t["tgt"]) if t["tgt"] else "", why))

    att = [i for i, t in enumerate(toks) if t["verb"] == "WRITE"
           and "attestation" in t["args"] and t["who"].startswith(("VER", "FULL"))]
    ver_basis, attestor, reporter = "no-attestation", "", ""
    if att:
        i_att = att[-1]
        attestor = toks[i_att]["who"]
        mark(i_att, "ROOT deliverable")

        signers = {toks[i]["who"] for i in att}

        ran = [i for i, t in enumerate(toks) if t["who"] in signers
               and t["verb"] == "RUN"
               and t["args"] & {"test", "run", "sh", "install", "git"}]
        red = [i for i, t in enumerate(toks) if t["who"] in signers and i < i_att
               and t["verb"] == "READ"
               and t["args"] & {"workspace", "workspace/tests"}]
        for i in ran[-1:]:
            mark(i, "attestor's own execution")
        for i in red[-1:]:
            mark(i, "attestor's own workspace read")
        i_trig = last_inbound(toks, attestor, i_att)
        if i_trig is not None:
            mark(i_trig, "message that triggered the attestation")
            reporter = toks[i_trig]["who"]
        ver_basis = ("ran" if ran else "read-only" if red else
                     "message-only" if i_trig is not None else "unprompted")

    writers = {}
    for i, t in enumerate(toks):
        if (t["verb"] == "WRITE" and t["args"] & {"workspace", "workspace/tests"}
                and t["who"].startswith(IMPL) and t["who"] not in writers):
            writers[t["who"]] = i
    sources = {}
    for w, i_w in sorted(writers.items(), key=lambda kv: kv[1]):
        mark(i_w, "ROOT deliverable (first workspace write by %s)" % w)
        i_src = last_inbound(toks, w, i_w, substantive=True)
        if i_src is None:
            i_src = last_inbound(toks, w, i_w)
        if i_src is None:
            sources[w] = "self-started"
            continue
        mark(i_src, "message that kicked off %s's work" % w)
        s = toks[i_src]["who"]
        sources[w] = ("plan-fed" if s.startswith("PLAN") else
                      "peer-fed" if s.startswith(IMPL) else
                      "leader-fed" if s == "LEAD" else "other-fed")
        if s.startswith("PLAN"):
            i_spec = None
            for j in range(i_src - 1, -1, -1):
                t = toks[j]
                if t["who"] == s and ((t["verb"] == "READ" and "spec" in t["args"])
                                      or (t["verb"] == "DENIED"
                                          and t["args"] & {"spec", "brief"})):
                    i_spec = j
                    break
            if i_spec is not None:
                mark(i_spec, "%s's spec consultation" % s)
            i_asg = last_inbound(toks, s, i_src)
            if i_asg is not None and toks[i_asg]["who"] == "LEAD":
                mark(i_asg, "leader engaged %s" % s)

    spine_str, spine_origin, spine_depth = "", "no-deliverable", 0
    root = att[-1] if att else (max(writers.values()) if writers else None)
    if root is not None:
        sp, spine_origin = trace_spine(toks, root)
        for i in sp:
            mark(i, "on the realised spine")
        spine_depth = len(sp)
        parts = []
        for i in reversed(sp):
            t = toks[i]
            parts.append("%s.%s(%s)%s" % (t["who"], t["verb"],
                                          ",".join(sorted(t["args"])),
                                          (">" + t["tgt"]) if t["tgt"] else ""))
        spine_str = " -> ".join(parts)

    active = {t["who"] for t in toks}
    contributing = {toks[i]["who"] for i in marked}
    total_beats = sum(t["n"] for t in toks)
    marked_beats = sum(toks[i]["n"] for i in marked)
    return dict(
        run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"], dose=rec["dose"],
        task=rec["task"], attestor=attestor, verifier_basis=ver_basis, reporter=reporter,
        n_writers=len(writers),
        work_sources=";".join("%s=%s" % kv for kv in sorted(sources.items())),
        source_mix=";".join("%s=%d" % kv for kv in
                            sorted(Counter(sources.values()).items())),
        contributing=len(contributing), active=len(active),
        idle_contributors=";".join(sorted(active - contributing)),
        ancestry_beat_share=round(marked_beats / total_beats, 3) if total_beats else 0.0,
        spine=spine_str, spine_depth=spine_depth, spine_origin=spine_origin,
        grounded=int(spine_origin == "kickoff"),
        tree=" | ".join(tree))

_ROLE2MEM = {"PLAN": "planner", "EXEC": "executor", "VER": "verifier",
             "FULL": "fullstack", "LEAD": "team_leader"}

def _member_of(tok_who):
    import re as _re
    m = _re.match(r"([A-Z]+)(\d*)", tok_who)
    base = _ROLE2MEM.get(m.group(1), "")
    return base + m.group(2) if base != "team_leader" else "team_leader"

def content_verify(rec, strips):
    import json
    import teamtrace
    import s4_seams as S4S
    toks = parse_strip(strips.get(rec["run_id"], {}).get("*", ""))
    att = [i for i, t in enumerate(toks) if t["verb"] == "WRITE"
           and "attestation" in t["args"] and t["who"].startswith(("VER", "FULL"))]
    writers = [i for i, t in enumerate(toks)
               if t["verb"] == "WRITE" and t["args"] & {"workspace", "workspace/tests"}
               and t["who"].startswith(IMPL)]
    root = att[-1] if att else (writers[-1] if writers else None)
    if root is None:
        return dict(run_id=rec["run_id"], scenario=rec["scenario"], hops=0, verified=0,
                    proximity=0, artifact_ok=0, detail="")
    sp, _origin = trace_spine(toks, root)

    run = teamtrace.load_run(rec["archive_path"])
    acts = {}
    for m in run["members"]:
        d = acts.setdefault(m["member"], {})
        for t in m["turns"]:
            d.setdefault(t["turn"], []).extend(t["actions"])

    def raw(tok, tools, want_to=None):
        mem = _member_of(tok["who"])
        for tt in range(tok["turn"], tok["turn"] + 7):
            for a in acts.get(mem, {}).get(tt, []):
                if a["tool"] not in tools or not a["args_text"]:
                    continue
                try:
                    j = json.loads(a["args_text"])
                except Exception:
                    continue
                if want_to is not None:
                    to = str(j.get("to", "*"))
                    if want_to != "*" and _member_of(want_to) != to and to != "*":
                        continue
                return j
        return None

    def text_of(tok):
        if tok["verb"] == "WRITE":
            j = raw(tok, ("write_file", "edit_file"))
            body = (str(j.get("content", "")) or str(j.get("new_string", ""))
                    or str(j.get("new_str", ""))) if j else ""
            return (body, os.path.basename(str(j.get("file_path", ""))) if j else "")
        if tok["verb"] == "RUN":
            j = raw(tok, ("bash",))
            return (str(j.get("command", "")) if j else "", "")
        if tok["verb"] in ("MSG", "BROADCAST"):
            j = raw(tok, ("send_message",))
            return (str(j.get("content", "")) if j else "", "")
        return ("", "")

    hops = ver = prox = art_ok = 0
    detail = []
    for k in range(1, len(sp)):
        trig = toks[sp[k]]
        contrib = toks[sp[k - 1]]
        if trig["verb"] in ("MSG", "BROADCAST"):
            hops += 1
            j = raw(trig, ("send_message",), want_to=trig["tgt"] or "*")
            msg = str(j.get("content", "")) if j else ""
            ctext, cbase = text_of(contrib)
            ok = why = False
            if msg and cbase and cbase in msg:
                ok, why = True, "path"
            elif msg and ctext:

                syms = S4S.idents(ctext)
                hit = sum(1 for t in list(syms)[:200] if S4S.word_in(t, msg))
                ok, why = hit >= 2, "sym%d" % hit
            elif not msg:
                why = "no-msg-found"
            elif not ctext:
                why = "no-content-found"
            ver += bool(ok)
            prox += (not ok)
            detail.append("%s->%s:%s" % (trig["who"], contrib["who"],
                                         why if ok or why else "prox"))
        elif trig["verb"] == "READ" and k + 1 < len(sp)                 and toks[sp[k + 1]]["verb"] == "WRITE":
            jr = raw(trig, ("read_file",))
            jw = raw(toks[sp[k + 1]], ("write_file", "edit_file"))
            if jr and jw and os.path.basename(str(jr.get("file_path", ""))) ==                     os.path.basename(str(jw.get("file_path", ""))):
                art_ok += 1
    return dict(run_id=rec["run_id"], scenario=rec["scenario"], hops=hops, verified=ver,
                proximity=prox, artifact_ok=art_ok, detail=";".join(detail))

def content_all():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    strips = strips_by_run()
    rows = []
    for n, rec in enumerate(idx, 1):
        if n % 25 == 0:
            print("  ... %d/%d" % (n, len(idx)), file=sys.stderr)
        rows.append(content_verify(rec, strips))
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "spine_content.tsv"), "w", encoding="utf-8",
                 newline="") as f:
        w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    H = sum(r["hops"] for r in rows)
    V = sum(r["verified"] for r in rows)
    print("wrote out/spine_content.tsv")
    print("\nmessage hops on spines: %d — content-verified %d (%.0f%%), "
          "proximity-only %d" % (H, V, 100.0 * V / H if H else 0, H - V))
    full = sum(1 for r in rows if r["hops"] and r["verified"] == r["hops"])
    print("runs whose EVERY spine hop content-verifies: %d/%d (of %d with hops)"
          % (full, len(rows), sum(1 for r in rows if r["hops"])))
    return rows

# build the output tables from the raw streams
def build():
    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
    strips = strips_by_run()
    rows = [backtrace_run(r, strips) for r in idx]
    cols = list(rows[0].keys())
    with io.open(os.path.join(OUT, "backtrace.tsv"), "w", encoding="utf-8",
                 newline="") as f:
        w = csv.DictWriter(f, cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print("wrote out/backtrace.tsv (%d runs)" % len(rows))
    report(rows)
    return rows

# print the human-readable summary
def report(rows):
    print("\n=== WORK PROVENANCE: what kicked off each workspace-writer ===")
    mix = Counter()
    for r in rows:
        for kv in r["source_mix"].split(";"):
            if "=" in kv:
                k, v = kv.split("=")
                mix[k] += int(v)
    tot = sum(mix.values())
    for k, v in mix.most_common():
        print("  %-14s %4d  (%3.0f%%)" % (k, v, 100.0 * v / tot))

    print("\n=== VERIFIER BASIS: the attestor's own evidence before signing ===")
    for sc in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        rs = [r for r in rows if r["scenario"] == sc]
        c = Counter(r["verifier_basis"] for r in rs)
        print("  %-4s %s" % (sc, dict(c.most_common())))

    print("\n=== CONTRIBUTION ===")
    contrib = sum(r["contributing"] for r in rows)
    act = sum(r["active"] for r in rows)
    print("  agents in a deliverable's ancestry: %d of %d active (%.0f%%)"
          % (contrib, act, 100.0 * contrib / act))
    idle = Counter(a for r in rows for a in r["idle_contributors"].split(";") if a)
    print("  most often active-but-feeding-nothing: %s" % dict(idle.most_common(6)))
    sh = sorted(r["ancestry_beat_share"] for r in rows)
    print("  ancestry beats as share of all beats: median %.2f (min %.2f max %.2f)"
          % (sh[len(sh) // 2], sh[0], sh[-1]))

def show(run_id):
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    if run_id not in idx:
        sys.exit("unknown run_id: " + run_id)
    r = backtrace_run(idx[run_id], strips_by_run())
    print("\n=== %s (%s) ===" % (run_id, r["scenario"]))
    print("attestor=%s basis=%s reporter=%s" % (r["attestor"], r["verifier_basis"],
                                                r["reporter"]))
    print("work sources: %s" % r["work_sources"])
    print("contributing %d/%d active · idle: %s" % (r["contributing"], r["active"],
                                                    r["idle_contributors"] or "-"))
    print("\nREALISED PATH (traced end->start, shown start->end; origin=%s, %d beats):"
          % (r["spine_origin"], r["spine_depth"]))
    for step in r["spine"].split(" -> "):
        print("   " + step)
    print("\nprovenance tree (marked backwards from the deliverables):")
    for line in r["tree"].split(" | "):
        print("   " + line)

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    strips = strips_by_run()

    def one(rid):
        return backtrace_run(idx[rid], strips)

    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-62s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    r = one("crypto1_enforced-20260808-114845")
    check("S1A gold: attestor's basis is its own READS (static review, annotated)",
          r["verifier_basis"] == "read-only", "basis=%s" % r["verifier_basis"])
    check("S1A gold: all three executors plan-fed",
          r["source_mix"].startswith("plan-fed=3"), r["source_mix"])

    r = one("p5_s3partial_arm2-20260810-035018")
    check("arm-2 exemplar: peer-fed work appears in the provenance",
          "peer-fed" in r["source_mix"] or "peer-fed" in r["work_sources"],
          r["work_sources"][:70])

    r = one("P6_enforced-20260808-143229")
    check("P6: no attestation, no writers", r["verifier_basis"] == "no-attestation"
          and r["n_writers"] == 0, "basis=%s writers=%d"
          % (r["verifier_basis"], r["n_writers"]))

    r = one("crypto1_s3partial-20260808-211436")
    check("S3 gold spine: kickoff-grounded, spec-read and attestation on it",
          r["grounded"] == 1 and "READ(spec)" in r["spine"]
          and "WRITE(attestation)" in r["spine"],
          "origin=%s depth=%s" % (r["spine_origin"], r["spine_depth"]))

    r = one("p5_s3partial_arm2-20260810-035018")
    import re as _re
    check("arm-2 exemplar spine carries the peer relay (EXEC->EXEC)",
          bool(_re.search(r"EXEC\d*\.MSG\([^)]*\)>EXEC", r["spine"])),
          r["spine"][:90])
    return 1 if bad else 0

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "verify":
        sys.exit(verify())
    elif arg == "content":
        content_all()
    elif arg:
        show(arg)
    else:
        build()
