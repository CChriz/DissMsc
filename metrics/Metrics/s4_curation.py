# Links seam symbols to grader checks to test whether communicating
# them was actually required.
import io, json, os, re, sys
from collections import defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import s4_seams as S4
import run_index as rix

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RUNS_ROOT = rix.RUNS_ROOT
S4_BATCHES = ["S4_enf_pro", "S4_enf_pro_arm2"]

def check_surface(task):
    parts, srcs = [], []
    ws = os.path.join(S4.PRISTINE, task, "workspace")
    for root, _dirs, files in os.walk(ws):
        for fn in files:
            if not re.match(r"test.*\.py$|.*_test\.py$|conftest\.py$", fn):
                continue
            parts.append(S4.read(os.path.join(root, fn)))
            srcs.append(os.path.relpath(os.path.join(root, fn), ws).replace("\\", "/"))
    for batch in S4_BATCHES:
        p = os.path.join(RUNS_ROOT, batch, "scenario1_regrade_records.json")
        if not os.path.isfile(p):
            continue
        try:
            recs = json.load(io.open(p, encoding="utf-8"))
        except Exception:
            continue
        for r in recs:
            if r.get("task") != task:
                continue
            notes = " ".join(str(c.get("note", "")) for c in (r.get("checklist") or []))
            if notes:
                parts.append(notes)
                srcs.append("%s:checklist" % batch)
    return "\n".join(parts), srcs

def curate(task):
    tm = S4.TaskModel(task)
    surface, srcs = check_surface(task)
    tests_only = "\n".join(p for p, s in zip(surface.split("\n"), []) if False)
    rows = []
    for e in tm.edges:
        for tok, meta in sorted(e["symbols"].items()):
            linked = S4.word_in(tok, surface)
            rows.append(dict(task=task, edge=e["idx"], src=e["src"], dst=e["dst"],
                             symbol=tok, provenance=meta["prov"], origin=meta["origin"],
                             check_linked=int(linked)))
    return tm, rows, srcs

def recompute(task, tm, linked_syms):
    out = []
    for batch in S4_BATCHES:
        d = os.path.join(RUNS_ROOT, batch)
        if not os.path.isdir(d):
            continue
        for arc in sorted(os.listdir(d)):
            if not arc.startswith(task + "_"):
                continue
            path = os.path.join(d, arc)
            if not os.path.isdir(path):
                continue
            saved = S4.RUNS
            S4.RUNS = d
            try:
                res = S4.analyze(task, path)
            finally:
                S4.RUNS = saved
            wsum = sum(e["weight"] for e in res["edges"]) or 1
            cur_any = cur_strong = 0
            n_link = n_link_crossed = 0
            for e in res["edges"]:
                delivered = [c for c in e["crossings"] if c["mode"] == "delivered"
                             and c["symbol"] in linked_syms]
                strong = [c for c in delivered if c["prov"] in ("pristine", "emergent")]
                cur_any += e["weight"] if delivered else 0
                cur_strong += e["weight"] if strong else 0
                n_link_crossed += len({c["symbol"] for c in delivered})
            out.append(dict(
                task=task, batch=batch, run_id=arc,
                curatable=int(bool(linked_syms)),
                congruence_any=res["congruence_any"],
                congruence_strong=res["congruence_strong"],
                curated_any=round(cur_any / wsum, 3),
                curated_strong=round(cur_strong / wsum, 3),
                linked_symbols_crossed=n_link_crossed))
    return out

# build the output tables from the raw streams
def build():
    tasks = sorted(f[:-len(".split.json")] for f in os.listdir(S4.MAPS)
                   if f.endswith(".split.json"))
    sym_rows, task_rows, run_rows = [], [], []
    for task in tasks:
        tm, rows, srcs = curate(task)
        sym_rows += rows
        linked = {r["symbol"] for r in rows if r["check_linked"]}
        strong = [r for r in rows if r["provenance"] in ("pristine", "emergent")]
        strong_linked = [r for r in strong if r["check_linked"]]
        task_rows.append(dict(
            task=task, edges=len(tm.edges), symbols=len(rows),
            check_linked=len(linked), strong=len(strong),
            strong_check_linked=len(strong_linked),
            dropped=len(rows) - len(linked),
            surface_sources=";".join(srcs)[:120]))
        run_rows += recompute(task, tm, linked)

    _write(os.path.join(OUT, "s4_curation_symbols.tsv"), sym_rows)
    _write(os.path.join(OUT, "s4_curation_tasks.tsv"), task_rows)
    _write(os.path.join(OUT, "s4_curation_runs.tsv"), run_rows)
    print("wrote out/s4_curation_{symbols,tasks,runs}.tsv "
          "(%d symbols, %d tasks, %d runs)\n" % (len(sym_rows), len(task_rows),
                                                 len(run_rows)))

    print("%-28s %6s %8s %8s %8s %8s" % ("task", "edges", "symbols", "linked",
                                         "strong", "str+link"))
    for r in task_rows:
        print("%-28s %6d %8d %8d %8d %8d" % (r["task"], r["edges"], r["symbols"],
                                             r["check_linked"], r["strong"],
                                             r["strong_check_linked"]))
    tot_s = sum(r["symbols"] for r in task_rows)
    tot_l = sum(r["check_linked"] for r in task_rows)
    print("\n%d of %d seam symbols are check-linked (%.0f%%); the rest are internal "
          "identifiers of seam files and leave the denominator."
          % (tot_l, tot_s, 100.0 * tot_l / tot_s if tot_s else 0))

    print("\ncongruence, uncurated vs curated (per run)")
    print("%-40s %8s %9s %9s %10s" % ("run", "C_any", "C_strong", "cur_any", "cur_strong"))
    for r in run_rows:
        print("%-40s %8s %9s %9s %10s" % (r["run_id"][:40], r["congruence_any"],
                                          r["congruence_strong"], r["curated_any"],
                                          r["curated_strong"]))
    cur = [r for r in run_rows if r["curatable"]]
    non = sorted({r["task"] for r in run_rows if not r["curatable"]})
    n = len(cur) or 1
    print("\nover the %d CURATABLE runs: mean C_any %.2f -> curated %.2f | "
          "mean C_strong %.2f -> curated %.2f"
          % (len(cur),
             sum(r["congruence_any"] for r in cur) / n,
             sum(r["curated_any"] for r in cur) / n,
             sum(r["congruence_strong"] for r in cur) / n,
             sum(r["curated_strong"] for r in cur) / n))
    print("NOT curatable from the archives (no check surface recoverable): %s\n"
          "  -> their curated columns are MISSING DATA, not zero congruence; they need\n"
          "     grade.sh (WSL tree) or a hand pass before any H1-style claim." % (non or "none"))
    return sym_rows, task_rows, run_rows

def _write(path, rows):
    if not rows:
        return
    cols = list(rows[0].keys())
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-58s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    tm, rows, srcs = curate("pipe3_stream_processing")
    strong = [r for r in rows if r["provenance"] in ("pristine", "emergent")]
    linked_strong = [r for r in strong if r["check_linked"]]
    check("pipe3: strong seam symbols exist in quantity (pass reported 21)",
          len(strong) >= 10, "strong=%d" % len(strong))
    check("pipe3: a check surface was actually found", bool(srcs),
          "sources=%s" % (srcs[:2] or "none"))

    check("pipe3: the 'they are just internal identifiers' hypothesis is REFUTED",
          len(strong) and len(linked_strong) / len(strong) >= 0.5,
          "check-linked %d/%d strong" % (len(linked_strong), len(strong)))

    tasks = sorted(f[:-len(".split.json")] for f in os.listdir(S4.MAPS)
                   if f.endswith(".split.json"))
    worse = []
    for task in tasks[:4]:
        tm2, rows2, _ = curate(task)
        linked = {r["symbol"] for r in rows2 if r["check_linked"]}
        for r in recompute(task, tm2, linked):
            if r["curated_any"] > r["congruence_any"] or \
               r["curated_strong"] > r["congruence_strong"]:
                worse.append(r["run_id"])
    check("curated congruence never exceeds uncurated (monotone)", not worse,
          "violations=%s" % (worse or "none"))
    return 1 if bad else 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
