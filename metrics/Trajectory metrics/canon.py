# Canonical strips: serialises each run into a compact token sequence (actor,
# action class, turn number, milestone anchors). The walk uses the milestone turn
# anchors; the strips are also the human-readable trajectory view.

import csv, io, json, os, re, sys

from collections import Counter, defaultdict


try:

    sys.stdout.reconfigure(encoding="utf-8")

except Exception:

    pass


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import teamtrace

import run_index as rix


HERE = os.path.dirname(os.path.abspath(__file__))

OUT = os.path.join(HERE, "out")


ROLE_TOKEN = [(re.compile(r"^team_leader$"), "LEAD"),

              (re.compile(r"^planner(\d*)"), "PLAN"), (re.compile(r"^executor(\d*)"), "EXEC"),

              (re.compile(r"^verifier(\d*)"), "VER"), (re.compile(r"^fullstack(\d*)"), "FULL")]


READ_TOOLS = {"read_file", "list_files", "glob", "view_task", "list_members", "workspace_meta"}

SCRATCH_TOOLS = {"todo_create", "todo_modify"}

BOARD_TOOLS = {"create_task", "claim_task", "update_task", "complete_task"}


SIZE_BUCKETS = ((200, "XS"), (600, "S"), (2000, "M"), (6000, "L"))


CMD_CLASS = [(re.compile(r"\bpytest\b|\bunittest\b|python -m pytest"), "test"),

             (re.compile(r"\bpip install|\bnpm i(nstall)?\b|apt-get"), "install"),

             (re.compile(r"getfacl|setfacl|\bchmod\b|\bid\b|whoami|namei"), "acl"),

             (re.compile(r"^\s*(ls|cat|head|tail|find|grep|wc|tree|stat|du|file)\b"), "look"),

             (re.compile(r"\bpython\b|\bnode\b|\bgo run\b"), "run"),

             (re.compile(r"\bgit\b"), "git")]


def actor(member):

    for pat, tok in ROLE_TOKEN:

        m = pat.match(member or "")

        if m:

            return tok + (m.group(1) if m.groups() and m.group(1) else "")

    return "OTHER"


def path_class(p):

    p = (p or "").replace("\\", "/")

    if not p:

        return "-"

    tail = p.split("run_current/", 1)[-1]

    if "attestation" in tail:

        return "attestation"

    if re.search(r"(^|/)spec(/|\.)|spec\.md", tail):

        return "spec"

    if "brief" in tail:

        return "brief"

    if "/workspaces/" in p or re.search(r"_workspace", p):

        return "own-scratch"

    if tail.startswith("workspace/tests/") or "/tests/" in tail:

        return "workspace/tests"

    if tail.startswith("workspace"):

        return "workspace"

    if tail.startswith(".team") or "jiuwen_team_sess" in tail:

        return "team-meta"

    return "other"


def cmd_class(cmd):

    for pat, tok in CMD_CLASS:

        if pat.search(cmd or ""):

            return tok

    return "sh"


PHASE_ID = [(re.compile(r"plan"), "plan"), (re.compile(r"impl|fix|build|write|code"), "impl"),

            (re.compile(r"verif|test|review|check"), "verify")]


def phase_of(task_id):

    t = (task_id or "").lower()

    for pat, tok in PHASE_ID:

        if pat.search(t):

            return tok

    return "other" if t else ""


def size_bucket(n):

    for lim, tok in SIZE_BUCKETS:

        if n < lim:

            return tok

    return "XL"


KEY_VERBS = {"CREATE_TASKS", "CLAIM", "DONE", "REASSIGN", "CANCEL", "BUILD_TEAM", "DENIED"}

KEY_WRITE = {"workspace", "workspace/tests", "attestation", "spec"}

KEY_RUN = {"test", "acl"}

KEY_MSG_SIZES = {"M", "L", "XL"}


MERGE_TURNS = 4

MULTI_ARG_VERBS = {"DENIED", "RUN", "WRITE"}


def is_key(c):

    if c["marks"]:

        return True

    v, args = c["verb"], c.get("args") or {c["arg"]}

    if v in KEY_VERBS:

        return True

    if v == "WRITE":

        return bool(args & KEY_WRITE)

    if v == "RUN":

        return bool(args & KEY_RUN)

    if v in ("MSG", "BROADCAST"):

        return bool(args & KEY_MSG_SIZES)

    return False


def main_thread(coll):

    holders = {c["who"] for c in coll if c["verb"] in ("CLAIM", "DONE")} | {"LEAD"}

    out, seen_kick = [], False

    for c in coll:

        v = c["verb"]

        if c["marks"]:

            out.append(c)

            continue

        if v == "CLAIM_LOST":

            continue

        if v == "REASSIGN":

            continue

        if v in ("BUILD_TEAM", "CREATE_TASKS", "CLAIM", "DONE", "CANCEL"):

            out.append(c)

            continue

        if c["who"] not in holders:

            continue

        if v == "BROADCAST":

            if not seen_kick:

                out.append(c)

                seen_kick = True

            continue

        if v == "DENIED":

            out.append(c)

        elif v == "WRITE" and (c.get("args") or {c["arg"]}) & KEY_WRITE:

            out.append(c)

        elif v == "RUN" and (c.get("args") or {c["arg"]}) & KEY_RUN:

            out.append(c)

        elif v == "MSG" and (c.get("args") or {c["arg"]}) & KEY_MSG_SIZES:

            out.append(c)

    return out


# One beat per action/message, normalised: paths and commands to classes,
# message sizes to buckets.
def raw_beats(run):

    beats = []

    for m in run["members"]:

        who = actor(m["member"])

        for t in m["turns"]:

            for a in t["actions"]:

                tool, p = a["tool"], (a["path"] or "")

                blocked = bool(a["blocked"])

                key = (a["ts"], m["member"], t["turn"], tool)

                if tool in SCRATCH_TOOLS:

                    continue

                if blocked:

                    beats.append((key, who, "DENIED", path_class(p), "", t["turn"],

                                  a["ts"], True, None))

                    continue

                if tool in READ_TOOLS:


                    cls = path_class(p)

                    if (tool == "read_file"

                            and ((who.startswith("PLAN") and cls == "spec")

                                 or (who.startswith("VER")

                                     and cls in ("workspace", "workspace/tests", "spec")))):


                        beats.append((key, who, "READ", cls, "", t["turn"], a["ts"],

                                      False, None))

                    continue

                if tool == "send_message":

                    try:

                        j = json.loads(a["args_text"] or "{}")

                        to, body = str(j.get("to", "")), str(j.get("content", ""))

                    except Exception:

                        to, body = "", (a["args_text"] or "")

                    tgt = "*" if to in ("*", "") else actor(to)

                    verb = "BROADCAST" if tgt == "*" else "MSG"

                    beats.append((key, who, verb, size_bucket(len(body)), tgt, t["turn"],

                                  a["ts"], False, None))

                elif tool in BOARD_TOOLS:

                    tr = teamtrace._TRANSITION_PAT.search(a["result_excerpt"] or "")

                    tid = None

                    try:

                        j = json.loads(a["args_text"] or "{}")

                        tid = j.get("task_id")

                        if not tid and isinstance(j.get("tasks"), list):

                            tid = "+%d" % len(j["tasks"])

                    except Exception:

                        pass

                    if tool == "create_task":

                        beats.append((key, who, "CREATE_TASKS", tid or "?", "", t["turn"],

                                      a["ts"], False, None))

                    elif tr:

                        to_ = tr.group(3)

                        verb = {"claimed": "CLAIM", "completed": "DONE",

                                "cancelled": "CANCEL"}.get(to_, "BOARD")

                        beats.append((key, who, verb, phase_of(tr.group(1)), "", t["turn"],

                                      a["ts"], False, tr.group(1)))

                    elif tool == "update_task":


                        beats.append((key, who, "REASSIGN", phase_of(tid), "", t["turn"],

                                      a["ts"], False, tid))

                    else:

                        beats.append((key, who, "CLAIM_LOST", phase_of(tid), "", t["turn"],

                                      a["ts"], False, tid))

                elif tool in ("write_file", "edit_file"):

                    cls = path_class(p)

                    if cls in ("own-scratch", "team-meta"):

                        continue

                    beats.append((key, who, "WRITE", cls, "", t["turn"], a["ts"],

                                  False, None))

                elif tool == "bash":

                    beats.append((key, who, "RUN", cmd_class(p), "", t["turn"], a["ts"],

                                  False, None))

                elif tool == "build_team":

                    beats.append((key, who, "BUILD_TEAM", "", "", t["turn"], a["ts"],

                                  False, None))

                else:

                    beats.append((key, who, tool.upper(), "", "", t["turn"], a["ts"],

                                  False, None))

    beats.sort(key=lambda b: b[0])

    return beats


def lanes_of(beats):

    holding, out = {}, []

    for b in beats:

        _key, who, verb, _arg, _tgt, _turn, _ts, _blk, tid = b

        lane = holding.get(who, "-")

        if verb == "CLAIM" and tid:

            holding[who] = tid

            lane = tid

        elif verb in ("DONE", "CANCEL") and tid:

            lane = tid

            if holding.get(who) == tid:

                holding.pop(who, None)

        elif verb == "CREATE_TASKS":

            lane = "-"

        out.append(lane)

    return out


def anchors_for(run_id, events_index):

    out = defaultdict(list)

    for e in events_index.get(run_id, []):

        if e["ts_rel"] == "":

            continue

        out[(actor(e["agent"]), round(float(e["ts_rel"]), 1))].append(e["stage"])

    return out


def token(actor_, verb, arg, tgt, turn, n, turn_end, marks):

    body = verb

    if tgt and tgt != "":

        body = "%s>%s.%s" % (actor_, tgt, verb)

    else:

        body = "%s.%s" % (actor_, verb)

    if arg:

        body += "(%s)" % arg

    if n > 1:

        body += "x%d" % n

    tt = "t%d" % turn if n == 1 else "t%d-%d" % (turn, turn_end)

    if marks:

        body += "!" + "!".join(sorted(set(marks)))

    return "%s %s" % (tt, body)


# The full strip for one run, with milestone anchors.
def strip_for(rec, events_index):

    run = teamtrace.load_run(rec["archive_path"])

    t0 = min((t["start_ts"] for m in run["members"] for t in m["turns"]), default=0)

    beats = raw_beats(run)

    lanes = lanes_of(beats)

    anch = anchors_for(rec["run_id"], events_index)


    per_actor = defaultdict(list)

    for b, lane in zip(beats, lanes):

        _key, who, verb, arg, tgt, turn, ts, blk, _tid = b

        marks = anch.get((who, round(ts - t0, 1)), [])

        prev = per_actor[who][-1] if per_actor[who] else None

        mergeable = (prev is not None and prev["verb"] == verb and prev["tgt"] == tgt

                     and prev["lane"] == lane and turn - prev["turn_end"] <= MERGE_TURNS

                     and (prev["arg"] == arg or verb in MULTI_ARG_VERBS))

        if mergeable:

            prev["n"] += 1

            prev["turn_end"] = turn

            prev["ts_end"] = ts

            prev["args"].add(arg)

            prev["marks"] += marks

            continue

        per_actor[who].append(dict(who=who, verb=verb, arg=arg, args={arg}, tgt=tgt,

                                   lane=lane, n=1, turn=turn, turn_end=turn, ts=ts,

                                   ts_end=ts, marks=list(marks)))

    coll = sorted((c for v in per_actor.values() for c in v), key=lambda c: (c["ts"], c["who"]))

    for c in coll:

        if len(c["args"]) > 1:

            a = sorted(x for x in c["args"] if x)

            c["arg"] = ",".join(a[:2]) + ("+" if len(a) > 2 else "")


    toks = [token(c["who"], c["verb"], c["arg"], c["tgt"], c["turn"], c["n"],

                  c["turn_end"], c["marks"]) for c in coll]

    by_lane = defaultdict(list)

    for c, tk in zip(coll, toks):

        by_lane[c["lane"]].append(tk)

    key = " · ".join(tk for c, tk in zip(coll, toks) if is_key(c))

    return (" · ".join(toks), {k: " · ".join(v) for k, v in by_lane.items()}, coll, key)


def tok_list(strip):

    return [t.split(" ", 1)[1] if " " in t else t for t in strip.split(" · ") if t]


_ORD = re.compile(r"^(LEAD|PLAN|EXEC|VER|FULL|OTHER)\d*")

_CNT = re.compile(r"x\d+")


def cmp_tokens(strip):

    out = []

    for t in tok_list(strip):

        t = _CNT.sub("", t)

        head, _, rest = t.partition(".")

        if ">" in head:

            a, _, b = head.partition(">")

            head = "%s>%s" % (_ORD.sub(lambda m: m.group(1), a),

                              _ORD.sub(lambda m: m.group(1), b))

        else:

            head = _ORD.sub(lambda m: m.group(1), head)

        m = re.match(r"([A-Z_]+)(?:\(([^)]*)\))?(.*)$", rest)

        if m:

            verb, arg, marks = m.group(1), (m.group(2) or ""), (m.group(3) or "")

            arg = arg.split(",")[0].rstrip("+")

            rest = verb + (("(%s)" % arg) if arg else "") + marks

        out.append(head + "." + rest)

    return out


def edit_sim(a, b):

    a, b = cmp_tokens(a), cmp_tokens(b)

    if not a and not b:

        return 1.0

    if not a or not b:

        return 0.0

    prev = list(range(len(b) + 1))

    for i, x in enumerate(a, 1):

        cur = [i] + [0] * len(b)

        for j, y in enumerate(b, 1):

            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))

        prev = cur

    return round(1 - prev[-1] / max(len(a), len(b)), 3)


def anchored(strip):

    return " · ".join(t for t in strip.split(" · ") if "!" in t)


def beat_set(strip):

    return {t.split("!", 1)[1] for t in cmp_tokens(strip) if "!" in t}


def jaccard(a, b):

    A, B = beat_set(a), beat_set(b)

    return round(len(A & B) / len(A | B), 3) if (A | B) else 1.0


def events_by_run():

    p = os.path.join(OUT, "events.csv")

    if not os.path.isfile(p):

        sys.exit("out/events.csv missing — run `python trajectory.py` first")

    out = defaultdict(list)

    with io.open(p, encoding="utf-8") as f:

        for r in csv.DictReader(f):

            out[r["run_id"]].append(r)

    return out


def _write(path, rows):

    if not rows:

        return

    cols = []

    for r in rows:

        for k in r:

            if k not in cols:

                cols.append(k)

    with io.open(path, "w", encoding="utf-8", newline="") as f:

        w = csv.DictWriter(f, cols, delimiter="\t", extrasaction="ignore",

                           lineterminator="\n")

        w.writeheader()

        w.writerows(rows)


def build():

    idx = rix.read_tsv(os.path.join(OUT, "run_index.tsv"))

    ev = events_by_run()

    rows = []

    for n, rec in enumerate(idx, 1):

        if n % 25 == 0:

            print("  ... %d/%d" % (n, len(idx)), file=sys.stderr)

        g, lanes, coll, key = strip_for(rec, ev)

        mt = main_thread(coll)

        mts = " · ".join(token(c["who"], c["verb"], c["arg"], c["tgt"], c["turn"], c["n"],

                               c["turn_end"], c["marks"]) for c in mt)

        rows.append(dict(run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],

                         dose=rec["dose"], task=rec["task"], lane="*",

                         tokens=len(tok_list(g)), key_tokens=len(tok_list(key)),

                         main_tokens=len(mt), main_strip=mts, key_strip=key, strip=g))

        for lane, s in sorted(lanes.items()):

            rows.append(dict(run_id=rec["run_id"], scenario=rec["scenario"], arm=rec["arm"],

                             dose=rec["dose"], task=rec["task"], lane=lane,

                             tokens=len(tok_list(s)), key_tokens="", main_tokens="",

                             main_strip="", key_strip="", strip=s))

    _write(os.path.join(OUT, "canon_strips.tsv"), rows)

    glob_rows = [r for r in rows if r["lane"] == "*"]

    tl = sorted(r["tokens"] for r in glob_rows)

    kl = sorted(r["key_tokens"] for r in glob_rows)

    print("wrote out/canon_strips.tsv (%d rows: %d global + %d lane strips)"

          % (len(rows), len(glob_rows), len(rows) - len(glob_rows)))

    print("full strip: min %d / median %d / max %d tokens   key strip: min %d / median %d "

          "/ max %d" % (tl[0], tl[len(tl) // 2], tl[-1], kl[0], kl[len(kl) // 2], kl[-1]))

    separation(glob_rows)

    return rows


def separation(glob_rows):

    p = os.path.join(OUT, "library_index.tsv")

    if not os.path.isfile(p):

        print("\n(no library_index.tsv — run library.py for the separation check)")

        return []

    lib = rix.read_tsv(p)

    strip = {r["run_id"]: r["key_strip"] for r in glob_rows}

    rows = []

    for scen in sorted({r["scenario"] for r in lib}):

        ents = [r for r in lib if r["scenario"] == scen and r["run_id"] in strip]

        for i, a in enumerate(ents):

            for b in ents[i + 1:]:

                rows.append(dict(scenario=scen, a=a["run_id"], b=b["run_id"],

                                 a_cls=a["cls"], b_cls=b["cls"],

                                 pair=("same" if a["cls"] == b["cls"] else "cross"),

                                 kind="%s-%s" % tuple(sorted([a["cls"], b["cls"]])),

                                 sim=edit_sim(strip[a["run_id"]], strip[b["run_id"]]),

                                 sim_anchored=edit_sim(anchored(strip[a["run_id"]]),

                                                       anchored(strip[b["run_id"]])),

                                 sim_beats=jaccard(strip[a["run_id"]], strip[b["run_id"]])))

    _write(os.path.join(OUT, "canon_similarity.tsv"), rows)

    print("\n=== does the strip separate gold from failure? (Phase-5 library pairs) ===")

    print("  %-27s %-15s %-15s %-8s %s" % ("comparison", "gold-gold", "gold-failure",

                                           "separat.", "fail-fail"))

    for name, col in (("full-sequence edit", "sim"),

                      ("anchored-skeleton edit", "sim_anchored"),

                      ("beat SET overlap (jaccard)", "sim_beats")):

        gg = [r[col] for r in rows if r["kind"] == "gold-gold"]

        gf = [r[col] for r in rows if r["kind"] == "failure-gold"]

        ff = [r[col] for r in rows if r["kind"] == "failure-failure"]

        mg, mf, mff = (sum(v) / len(v) if v else 0 for v in (gg, gf, ff))

        print("  %-27s %.3f (n=%-2d)   %.3f (n=%-2d)   %+.3f   %.3f"

              % (name, mg, len(gg), mf, len(gf), mg - mf, mff))

    print("""
  Read: ORDER is noise here, PRESENCE is signal. Whole-sequence edit distance does not
  separate the classes; the order-free repertoire of anchored beats does, and
  failure-failure is the lowest of the three — golds share a beat repertoire while
  failures each miss a different part of it. On 4 gold pairs this is a direction, not a
  result. It is enough to settle the Phase-6 design: ask a judge WHICH BEATS OCCURRED,
  including paraphrases the deterministic tests missed — never how similar two sequences
  look.""")

    print("\nwrote out/canon_similarity.tsv")

    return rows


def show(run_id):

    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}

    if run_id not in idx:

        sys.exit("unknown run_id: " + run_id)

    rec = idx[run_id]

    g, lanes, coll, key = strip_for(rec, events_by_run())

    print("\n=== %s (%s arm-%s %s, task %s, score %s) ==="

          % (run_id, rec["scenario"], rec["arm"], rec["dose"], rec["task"],

             rec["regrade_score"]))

    mt = main_thread(coll)

    mts = " · ".join(token(c["who"], c["verb"], c["arg"], c["tgt"], c["turn"], c["n"],

                           c["turn_end"], c["marks"]) for c in mt)

    print("\nMAIN THREAD — the interaction sequence (%d beats)" % len(mt))

    for t in mts.split(" · "):

        print("   " + t)

    print("\nKEY STRIP — the judge-facing form (%d tokens)" % len(tok_list(key)))

    for t in key.split(" · "):

        print("   " + t)

    print("\nFULL STRIP (%d tokens)" % len(tok_list(g)))

    for t in g.split(" · "):

        print("   " + t)

    print("\nLANES")

    for lane, s in sorted(lanes.items()):

        print("   [%s] %s" % (lane, s))


# Oracle gate.
def verify():

    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}

    ev = events_by_run()

    bad = 0


    def check(label, ok, detail):

        nonlocal bad

        print("  %-5s %-60s %s" % ("OK" if ok else "FLAG", label, detail))

        if not ok:

            bad += 1


    r = idx["crypto1_s3partial-20260808-211436"]

    a, _l1, _c1, _k1 = strip_for(r, ev)

    b, _l2, _c2, _k2 = strip_for(r, ev)

    check("serialisation is deterministic (byte-identical on re-run)", a == b,

          "%d tokens" % len(tok_list(a)))


    lens = []

    for rid in ("crypto1_s3partial-20260808-211436", "p5_s3partial-20260808-204549",

                "P10_prompt-only-20260808-055135", "cr4_enforced-20260808-114309",

                "lh5_s4-20260809-081250", "spec5_s5partial-20260809-154345"):

        _s, _l, _c, k = strip_for(idx[rid], ev)

        lens.append(len(tok_list(k)))

    check("key strips stay compact (<=60 tokens on the library sample)", max(lens) <= 60,

          "max %d, mean %.0f" % (max(lens), sum(lens) / len(lens)))


    run = teamtrace.load_run(idx["crypto1_s3partial-20260808-211436"]["archive_path"])

    beats = raw_beats(run)

    n_reads = sum(1 for m in run["members"] for t in m["turns"] for x in t["actions"]

                  if x["tool"] in READ_TOOLS and not x["blocked"])

    n_denied = sum(1 for m in run["members"] for t in m["turns"] for x in t["actions"]

                   if x["blocked"])

    reads = [b for b in beats if b[2] == "READ"]

    plan_reads = [b for b in reads if b[1].startswith("PLAN")]

    ok_cls = {"spec", "workspace", "workspace/tests"}

    check("policy holds: only exception reads kept, every denial kept",

          len(reads) == 27

          and [(b[3], b[5]) for b in plan_reads] == [("spec", 1), ("spec", 3)]

          and all(b[1].startswith(("PLAN", "VER")) and b[3] in ok_cls for b in reads)

          and sum(1 for b in beats if b[2] == "DENIED") == n_denied,

          "kept %d/%d reads (%d planner-spec), kept %d/%d denials"

          % (len(reads), n_reads, len(plan_reads),

             sum(1 for b in beats if b[2] == "DENIED"), n_denied))


    s, _l, coll, _k = strip_for(idx["crypto1_s3partial-20260808-211436"], ev)

    marks = {m for c in coll for m in c["marks"]}

    check("frozen Phase-4 stages appear as anchors on the S3 gold",

          {"raised", "recovered"} <= marks, sorted(marks))


    _s2, _l2, coll2, _k2 = strip_for(idx["p5_s3partial-20260808-204549"], ev)

    m2 = {m for c in coll2 for m in c["marks"]}

    check("p5_s3partial carries no `recovered` anchor (frozen anti-exemplar)",

          "recovered" not in m2, sorted(m2))


    leaky = [t for t in tok_list(s) if re.search(r"cpool|node\d|/srv/|\.py\b|\d{4,}", t)]

    check("strips carry no personas, absolute paths or raw timestamps", not leaky,

          leaky[:3] or "-")


    g, lanes, coll, _k = strip_for(idx["P10_prompt-only-20260808-055135"], ev)

    check("lane strips partition the global strip (no token lost or duplicated)",

          sum(len(tok_list(v)) for v in lanes.values()) == len(tok_list(g)),

          "%d lanes, %d lane tokens vs %d global"

          % (len(lanes), sum(len(tok_list(v)) for v in lanes.values()), len(tok_list(g))))


    check("edit similarity is 1.0 on identity and 0.0 on disjoint",

          edit_sim(g, g) == 1.0 and edit_sim("t1 A.WRITE(x)", "t1 B.RUN(y)") == 0.0,

          "identity=%.1f disjoint=%.1f" % (edit_sim(g, g),

                                           edit_sim("t1 A.WRITE(x)", "t1 B.RUN(y)")))

    return 1 if bad else 0


if __name__ == "__main__":

    arg = sys.argv[1] if len(sys.argv) > 1 else ""

    if arg == "verify":

        sys.exit(verify())

    elif arg:

        show(arg)

    else:

        build()
