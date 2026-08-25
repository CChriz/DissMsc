# Reconciles the S5 ablation design against the shipped archives: which spec units
# were actually hidden in each run, detected via distinctive canary strings.

import difflib, io, json, os, re, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
MATCH = 0.82

ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*\S)\s*$")
HEAD = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
NUMBERED = re.compile(r"^\s*(\d+)\.\s+")
BACKTICK = re.compile(r"`([^`\n]{2,60})`")
RANGE = re.compile(r"\[\s*-?\d+\s*,\s*-?\d+\s*\]")
QUOTED = re.compile(r"'([^'\n]{2,40})'|\"([^\"\n]{2,40})\"")


DESIGN_ABLATED = {
    "spec5": "validation ranges/coercion for 5 keys (port, request_timeout, "
             "max_connections, log_level enum, debug bool-coercion)",
    "spec6": "M6 EXISTS, M9 ERR unknown_command, M10-M12 limits, S4 SETEX, S5 APPEND",
    "p5": "payment_initiated fields, config_changed fields, tamper-evidence rule",
    "api1": "E4 must-NOT-shim, E5 remove-shim, E3 rename detail",
    "cr4": "G3 pagination, G4 status codes, G6 error schema",
    "cross3": "req 3 oneof, req 4 enum name->int, req 6 429->8",
    "crypto1": "planner keeps ONLY the PBKDF2 iteration rule",
    "pipe3": "planner keeps ONLY the ISO-8601 producer rule",
    "multi4": "planner keeps ONLY the core>=1.2 version pin",
    "test9": "planner keeps ONLY 'mock tests covering the 3 API calls'",
    "lh5": "planner keeps ONLY the CSV->JSONL transform",
    "ir2": "planner keeps ONLY 'answer into answer.json {answer, evidence[]}'",
}


def parse_items(text):
    items, stack = [], []
    for line in text.splitlines():
        h = HEAD.match(line)
        if h:
            depth = len(h.group(1))
            stack = stack[:depth - 1] + [h.group(2)]
            continue
        m = ITEM.match(line)
        if m and len(m.group(1)) > 8:
            items.append((" / ".join(stack[1:]) or "(top)", norm(m.group(1)), m.group(1)))
    return items


def norm(s):
    s = re.sub(r"\*\*|__|\*|`", "", s)
    return re.sub(r"\s+", " ", s).strip()


CONTEXT_SEC = re.compile(r"background|supporting document|fix strategy|hidden complexity"
                         r"|overview|^goal|notes?$|the \d+ bugs?|dependency management",
                         re.I)


GENERIC = {"true", "false", "on", "off", "yes", "no", "int", "bool", "string", "enum",
           "float", "null", "none", "list", "dict", "error", "pass", "fail", "data"}

IDENT = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b|\b[a-z_]+\(\)")
CODE_N = re.compile(r"\b[1-5]\d{2}\b")
PIN = re.compile(r"\b[A-Za-z_][\w.-]*\s*(?:==|>=|<=|~=)\s*[\d.]+")
FILE = re.compile(r"\b[\w./-]+\.(?:py|cfg|json|md|txt|jsonl|csv|toml|ini)\b")


def canaries(text):
    out = []
    for m in BACKTICK.finditer(text):
        c = m.group(1).strip()
        if len(c) >= 3 and not c.isdigit():
            out.append(c)
    out += RANGE.findall(text)
    for a, b in QUOTED.findall(text):
        c = (a or b).strip()
        if len(c) >= 3:
            out.append(c)
    out += [m.group(0).replace(" ", "") for m in PIN.finditer(text)]
    if not out:
        out += FILE.findall(text)
        out += [m.group(0) for m in IDENT.finditer(text)]
        out += CODE_N.findall(text)
    seen, uniq = set(), []
    for c in out:
        cl = c.lower()


        if cl in GENERIC or cl not in seen and len(cl) < 3:
            continue
        if cl not in seen:
            seen.add(cl)
            uniq.append(c)
    return uniq[:6]


def canary_hit(canary, text):
    if not canary or not text:
        return False
    nums = re.findall(r"-?\d+", canary)
    if RANGE.fullmatch(canary.strip()) and len(nums) == 2:
        return re.search(r"%s\D{0,16}%s" % (re.escape(nums[0]), re.escape(nums[1])),
                         text) is not None
    c = canary.strip()
    if c.endswith("()"):
        c = c[:-2]
    return c.lower() in text.lower()


def workspace_text(archive):
    parts = []
    ws = os.path.join(archive, "run_current", "workspace")
    for root, _dirs, files in os.walk(ws):
        if "__pycache__" in root:
            continue
        for fn in files:
            if os.path.splitext(fn)[1].lower() in (".pyc", ".png", ".jpg", ".gz", ".zip"):
                continue
            try:
                parts.append(io.open(os.path.join(root, fn), encoding="utf-8",
                                     errors="replace").read())
            except Exception:
                pass
    return "\n".join(parts)


def numbering_gaps(text):
    gaps, run = [], []
    for line in text.splitlines():
        m = NUMBERED.match(line)
        if m:
            run.append(int(m.group(1)))
        else:
            if len(run) >= 2 and run != list(range(run[0], run[0] + len(run))):
                gaps.append(run[:])
            if not NUMBERED.match(line) and line.strip() == "":
                run = []
    if len(run) >= 2 and run != list(range(run[0], run[0] + len(run))):
        gaps.append(run)
    return gaps


def count_claims(text):
    out = []
    for m in re.finditer(r"\b(?:Fix|The)\s+(\d+)\s+([a-z][a-z ]{2,24}?)(?:s\b|\b)", text):
        out.append((int(m.group(1)), m.group(0)))
    return out


def analyse(rec):
    arc = rec["archive_path"]
    sp = os.path.join(arc, "run_current", "spec")
    pf, vf = os.path.join(sp, "p_spec.md"), os.path.join(sp, "v_spec.md")
    if not (os.path.isfile(pf) and os.path.isfile(vf)):
        return None, []
    ptext = io.open(pf, encoding="utf-8", errors="replace").read()
    vtext = io.open(vf, encoding="utf-8", errors="replace").read()
    brief = ""
    bp = os.path.join(arc, "run_current", "brief.md")
    if os.path.isfile(bp):
        brief = io.open(bp, encoding="utf-8", errors="replace").read()
    ws = workspace_text(arc)
    pitems = parse_items(ptext)
    vitems = parse_items(vtext)
    ptexts = [t for _s, t, _r in pitems]


    sides = []
    for section, t, raw in vitems:
        best = max((difflib.SequenceMatcher(None, t, q).ratio() for q in ptexts),
                   default=0.0)
        sides.append(("retained" if best >= MATCH else "ablated", round(best, 2)))


    urows = []
    ablated = 0
    for (side, best), (section, t, raw) in zip(sides, vitems):


        cans = canaries(raw)
        surviving = [c for c in cans if canary_hit(c, ptext)]
        silent = [c for c in cans if c not in surviving]
        in_b = any(canary_hit(c, brief) for c in silent)
        in_w = any(canary_hit(c, ws) for c in silent)
        if side == "ablated":
            ablated += 1
        urows.append(dict(task=rec["task"], arm=rec["arm"], dose=rec["dose"],
                          run_id=rec["run_id"], section=section, side=side,
                          match_ratio=round(best, 2), text=t[:220],
                          canaries_silent="; ".join(silent),
                          canaries_surviving="; ".join(surviving),
                          partial_ablation=int(side == "ablated" and bool(surviving)
                                               and bool(silent)),
                          not_hidden=int(side == "ablated" and bool(cans) and not silent),
                          canary_in_brief=int(in_b), canary_in_workspace=int(in_w),
                          artifact_recoverable=int(side == "ablated" and (in_w or in_b))))

    vtexts = [t for _s, t, _r in vitems]
    p_only = [t for _s, t, _r in pitems
              if max((difflib.SequenceMatcher(None, t, q).ratio() for q in vtexts),
                     default=0.0) < MATCH]


    sec = defaultdict(Counter)
    for u in urows:
        sec[u["section"]][u["side"]] += 1
    units = []
    for name, c in sec.items():
        if CONTEXT_SEC.search(name):
            continue
        n = c["ablated"] + c["retained"]
        units.append((name, "ablated" if c["retained"] == 0 else
                      "retained" if c["ablated"] == 0 else "partial", n, c["ablated"]))


    req_ret = sum(c["retained"] for n, c in sec.items() if not CONTEXT_SEC.search(n))
    req_abl = sum(c["ablated"] for n, c in sec.items() if not CONTEXT_SEC.search(n))
    u_abl = sum(1 for _n, s, _t, _a in units if s == "ablated")
    u_part = sum(1 for _n, s, _t, _a in units if s == "partial")
    u_ret = sum(1 for _n, s, _t, _a in units if s == "retained")

    abl_rows = [u for u in urows if u["side"] == "ablated"]
    recov = sum(u["artifact_recoverable"] for u in abl_rows)
    part_abl = sum(u["partial_ablation"] for u in abl_rows)
    not_hidden = sum(u["not_hidden"] for u in abl_rows)
    gaps = numbering_gaps(ptext)
    claims = count_claims(ptext)
    retained = len(urows) - ablated
    srow = dict(
        task=rec["task"], arm=rec["arm"], dose=rec["dose"], run_id=rec["run_id"],
        units_ablated=u_abl, units_partial=u_part, units_retained=u_ret,
        req_subunits_retained=req_ret, req_subunits_ablated=req_abl,
        subunits_v=len(vitems), subunits_p=len(pitems),
        subunits_retained=retained, subunits_ablated=ablated,
        ablated_recoverable=recov, ablated_silent=ablated - recov,
        partial_ablation=part_abl, not_hidden=not_hidden, p_only_items=len(p_only),
        numbering_gaps=";".join(",".join(map(str, g)) for g in gaps),
        count_claims=";".join("%d:%s" % (n, p) for n, p in claims[:3]),
        clean_minimal=int(rec["dose"] == "minimal" and req_ret <= 1),
        design_says=DESIGN_ABLATED.get(rec["task"], ""),
        ablated_units=";".join(sorted(n for n, s, _t, _a in units if s == "ablated")[:5]),
        retained_units=";".join(sorted(n for n, s, _t, _a in units
                                       if s in ("retained", "partial"))[:5]))
    return srow, urows


def load():
    idx = [r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
           if r["scenario"] == "S5"]
    if not idx:
        sys.exit("run_index.tsv missing or has no S5 rows — run run_index.py first")
    return idx


def build():
    srows, urows = [], []
    for rec in load():
        s, u = analyse(rec)
        if s is None:
            print("  !! no p_spec/v_spec pair: " + rec["run_id"])
            continue
        srows.append(s)
        urows += u
    _write(os.path.join(OUT, "s5_splits.tsv"), srows)
    _write(os.path.join(OUT, "s5_units.tsv"), urows)
    print("wrote out/s5_splits.tsv (%d runs) and out/s5_units.tsv (%d units)"
          % (len(srows), len(urows)))
    report(srows, urows)
    return srows, urows


def _write(path, rows):
    if not rows:
        return
    cols = list(rows[0].keys())
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")


def report(srows, urows):
    print("\nper-task reconciliation (both arms; * = arms disagree)")
    print("%-24s %-8s %6s %6s %6s %7s %7s %10s %7s %5s" % (
        "task", "dose", "u_abl", "u_par", "u_ret", "sub_abl", "sub_ret",
        "recoverbl", "nothidden", "gaps"))
    by_task = defaultdict(list)
    for s in srows:
        by_task[s["task"]].append(s)
    for task in sorted(by_task):
        rs = by_task[task]
        star = "" if len({(r["subunits_retained"], r["subunits_ablated"])
                          for r in rs}) == 1 else " *"
        r = rs[0]
        print("%-24s %-8s %6d %6d %6d %7d %7d %10d %7d %5s%s" % (
            task, r["dose"], r["units_ablated"], r["units_partial"], r["units_retained"],
            r["subunits_ablated"], r["subunits_retained"], r["ablated_recoverable"],
            r["not_hidden"], "yes" if r["numbering_gaps"] else "no", star))
    mins = [s for s in srows if s["dose"] == "minimal"]
    bad_min = sorted({s["task"] for s in mins if not s["clean_minimal"]})
    print("\nminimal cells that are NOT skeleton+one (retained > 1): %s" % (bad_min or "none"))
    leaky = sorted({s["task"] for s in srows if s["not_hidden"]})
    print("tasks with 'ablated' units whose literals all survive in p_spec: %s"
          % (leaky or "none"))
    part = sorted({s["task"] for s in srows if s["partial_ablation"]})
    print("tasks with partially-ablated units (some literals survive): %s" % (part or "none"))
    recov = sorted({s["task"] for s in srows if s["ablated_recoverable"]})
    print("tasks with artifact-recoverable ablated units (outside the denominator): %s"
          % (recov or "none"))
    gaps = sorted({s["task"] for s in srows if s["numbering_gaps"]})
    print("tasks with a visible numbering seam in p_spec: %s" % (gaps or "none"))


def verify():
    bad = 0
    srows, urows = [], []
    for rec in load():
        s, u = analyse(rec)
        if s:
            srows.append(s)
            urows += u
    by_task = defaultdict(list)
    for s in srows:
        by_task[s["task"]].append(s)

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-58s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1


    m4 = [u for u in urows if u["task"] == "multi4" and u["side"] == "ablated"]
    pin = [u for u in m4 if "core>=1.2" in u["text"] or "version pin" in u["text"].lower()]
    check("multi4 ablated unit is the stale version pin (design says kept)",
          bool(pin), pin[0]["text"][:70] if pin else "not found")
    check("multi4 is NOT a clean minimal cell (>1 requirement unit retained)",
          all(not s["clean_minimal"] for s in by_task["multi4"]),
          "requirement sub-units retained=%d"
          % by_task["multi4"][0]["req_subunits_retained"])

    check("multi4 canary is recoverable from the shipped workspace (craft gate 1)",
          any(u["canary_in_workspace"] for u in m4),
          "recoverable=%d/%d" % (sum(u["artifact_recoverable"] for u in m4), len(m4)))
    check("multi4 p_spec has a visible numbering seam (craft gate 4)",
          bool(by_task["multi4"][0]["numbering_gaps"]),
          by_task["multi4"][0]["numbering_gaps"] or "none")

    s5 = by_task.get("spec5", [])
    check("spec5 ablates MORE than the design's 5 units",
          bool(s5) and s5[0]["subunits_ablated"] > 5,
          "sub-units ablated=%d" % (s5[0]["subunits_ablated"] if s5 else -1))
    ka = [u for u in urows if u["task"] == "spec5" and u["side"] == "ablated"
          and "keep_alive_timeout" in u["text"]]
    check("spec5's 6th unit keep_alive_timeout [1, 300] is ablated",
          bool(ka), ka[0]["text"][:60] if ka else "not found")

    cr4 = [u for u in urows if u["task"] == "cr4" and u["side"] == "ablated"]
    check("cr4 ablated units are artifact-recoverable (denominator inflated)",
          sum(u["artifact_recoverable"] for u in cr4) >= 1,
          "recoverable=%d/%d" % (sum(u["artifact_recoverable"] for u in cr4), len(cr4)))

    mismatched = [t for t, rs in by_task.items()
                  if len({(r["subunits_retained"], r["subunits_ablated"])
                          for r in rs}) > 1]
    check("arm-1 and arm-2 ship identical splits per task",
          not mismatched, "mismatched=%s" % (mismatched or "none"))

    none_abl = [t for t, rs in by_task.items() if rs[0]["subunits_ablated"] == 0]
    check("every S5 task has >=1 ablated unit", not none_abl,
          "no-ablation=%s" % (none_abl or "none"))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
