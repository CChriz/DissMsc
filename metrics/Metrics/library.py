# Renders the gold and failure exemplar library from the annotation flags.
import io, os, re, sys, glob
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_index as rix
import trajectory as TR

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
ROOT = os.path.dirname(HERE)
ANN = os.path.join(ROOT, "annotations")
DOC = os.path.join(ROOT, "TRAJECTORY_LIBRARY.md")

SELECTION = [

    dict(run="crypto1_enforced-20260808-114845", cls="gold", scenario="S1A",
         label="textbook pipeline, requirement named at every stage",
         reading="Six assignments announced in one DAG and all six carried to `reported`; "
                 "the dependency gate is visible in the trajectory as executor3's `fix-tag` "
                 "claim landing only after `plan` completes."),
    dict(run="spec5_enforced-20260808-073823", cls="gold", scenario="S1A",
         label="up-front DAG, one claimant per task",
         reading="Clean single-claimant funnel with no races; the assignment backbone shows "
                 "the shape S1A was designed to elicit."),
    dict(run="cr4_enforced-20260808-114309", cls="failure", scenario="S1A",
         label="verification laundering — attested pass on a known-red suite",
         reading="The assignment funnel is spotless — every unit announced, claimed, "
                 "executed, reported, verified — which is exactly the point: the defect is "
                 "in the deliverable's content, where this backbone cannot see it."),
    dict(run="ir2_prompt-only-20260810-100536", cls="failure", scenario="S1A",
         label="self-inflicted path defect thin coordination should have caught",
         reading="Correct content, real dual verification, and still a graded loss — a "
                 "delivery defect, not a coordination one."),

    dict(run="test4_prompt-only-20260808-032933", cls="gold", scenario="S1B",
         label="distinct plan/implement/verify by three members, benign claim arbitration",
         reading="Plan claimed by planner2 rather than the pinned planner1 and the run is "
                 "still clean: the trajectory records the de-facto claimant, and the leader "
                 "ratified it in ~30 s."),
    dict(run="dist1_enforced-20260808-123938", cls="gold", scenario="S1B",
         label="partitioned implement + dual independent verify",
         reading="The only S1B-enforced run whose funnel completes on every unit with two "
                 "verifiers acting independently."),
    dict(run="test1_enforced-20260808-125124", cls="failure", scenario="S1B",
         label="threshold-satisficing + acl-info-loss; verifier attested before the evidence existed",
         reading="The fourth assignment (`run-coverage-mutation`) is announced 351 s after "
                 "the first three and reported after the attestation was already written — "
                 "the trajectory dates the verdict before its own evidence."),
    dict(run="synth1_enforced-20260808-122922", cls="failure", scenario="S1B",
         label="thin, fast coordination over a skeleton deliverable",
         reading="Coordination shape is near-gold while the product is not; process metrics "
                 "and outcome part company here more sharply than anywhere else in S1B."),

    dict(run="P10_prompt-only-20260808-055135", cls="gold", scenario="S2",
         label="the S2 parallel-execution exemplar",
         reading="Two three-stage chains interleave in the event stream — ir2's whole chain "
                 "runs inside test9's window — and the one claim race (fullstack1 taking "
                 "test9-verify) resolves without stalling either chain."),
    dict(run="P3_enforced-20260808-134613", cls="failure", scenario="S2",
         label="deliverable-misplacement: test file written to tests/ instead of root",
         reading="Parallelism worked and the funnel completes on all six units; the loss is "
                 "a path convention nobody in either chain questioned."),
    dict(run="P6_enforced-20260808-143229", cls="failure", scenario="S2",
         label="INFRASTRUCTURE — llm-stream truncation SPOF, no plan ever delivered",
         reading="The only run in the corpus with no assignment units at all: it stalled at "
                 "3 turns before the board existed. Kept as the boundary case that shows "
                 "what an empty trajectory means; excluded from behavioural S2 claims."),

    dict(run="crypto1_s3partial-20260808-211436", cls="gold", scenario="S3",
         label="the S3-partial survivor-path exemplar",
         reading="The blocked-capability unit runs the full automaton — encountered, raised, "
                 "rerouted, recovered — with the survivor, not the leader, landing the "
                 "deliverable."),
    dict(run="multi4_s3partial_arm2-20260810-044037", cls="gold", scenario="S3",
         label="the arm-2 verify-block survivor exemplar",
         reading="Raised to a peer and the leader at once; the peer channel is what carried "
                 "it, which is the arm-2 mechanism doing what it was added for."),
    dict(run="p5_s3partial-20260808-204549", cls="failure", scenario="S3",
         label="reroute decided, never landed (claim-race hijack)",
         reading="The unit reaches `rerouted` and stops. This is the run that forced the "
                 "landing definition to mean the phase deliverable — the survivor read the "
                 "workspace and never wrote to it."),
    dict(run="crypto1_s3full-20260808-230358", cls="failure", scenario="S3",
         label="full block: raised fast, no capable path to reroute to",
         reading="Encountered and raised inside 75 s, and then nothing: with every holder "
                 "stripped there is no survivor lane, and the funnel simply ends."),

    dict(run="lh5_s4_arm2-20260809-224047", cls="gold", scenario="S4",
         label="the S4 seam-integration exemplar on outcome (qualified)",
         reading="The seam facts cross and the run scores; the caveat in the annotation is "
                 "about how much of the crossing was pre-disclosed by the leader."),
    dict(run="spec6_s4_arm2-20260809-225446", cls="process-gold", scenario="S4",
         label="near-gold process: thin leader, both zones crossing and integrating",
         reading="One of only three runs in the corpus where a cross-edge reaches "
                 "`integrated` — and it does it on both of its edges."),
    dict(run="p5_s4_arm2-20260809-231931", cls="process-gold", scenario="S4",
         label="cleanest seam funnel in the corpus, 55 s probe->integration; outcome 0.4",
         reading="Every stage of the cross-edge automaton fires, bidirectionally, and the "
                 "run still scores 0.4 — the sharpest evidence in the corpus that seam "
                 "coordination is not sufficient for the seam outcome."),
    dict(run="lh5_s4-20260809-081250", cls="failure", scenario="S4",
         label="the S4 failure exemplar",
         reading="The cleanest case of the seam need going unmet: probing without asking, "
                 "and a score of 0.08 to show what that costs."),
    dict(run="test9_s4-20260809-083623", cls="failure", scenario="S4",
         label="probe loop against the other zone; verification never executed",
         reading="The trajectory shows repeated denied probes on the far zone's paths and no "
                 "ask — the annotated probe loop, in stage form."),

    dict(run="cr4_s5partial-20260809-161851", cls="gold", scenario="S5",
         label="verifier emits FAIL, fix loop closes",
         reading="The only shape in S5 where a named unit is disposed as a hard fail and the "
                 "team then acts on it, rather than downgrading it inside a pass."),
    dict(run="crypto1_s5minimal-20260809-164101", cls="gold", scenario="S5",
         label="exemplary team behaviour, qualified as an S5 exemplar",
         reading="Clean pipeline and honest reporting; qualified because the ablation was "
                 "not what drove the outcome."),
    dict(run="spec5_s5partial-20260809-154345", cls="failure", scenario="S5",
         label="flagship negative specimen: detected, named, and overruled",
         reading="Every ablated unit is named by a verifier — detection is not the problem — "
                 "and the disposition is what loses them."),
    dict(run="multi4_s5minimal-20260809-165336", cls="failure", scenario="S5",
         label="near-exemplary delivery, verifier drove nothing (⚠ quarantined split)",
         reading="Included for its shape only: multi4's ablation split is inverted relative "
                 "to the design table, so this run must never be used in a dose comparison."),
]

GOLD_RE = re.compile(r"\*\*GOLD flag\*\*\s*:?\s*\*{0,2}\s*(yes|no|qualified|YES|NO)", re.I)
RUNID_RE = re.compile(r"([\w-]+-\d{8}-\d{6})")

def annotation_blocks():
    out = {}
    for p in sorted(glob.glob(os.path.join(ANN, "*.md"))):
        if os.path.basename(p) in ("CODEBOOK.md", "TEMPLATE.md"):
            continue
        cur = None
        for line in io.open(p, encoding="utf-8"):
            if line.startswith("### "):
                m = RUNID_RE.search(line)
                cur = m.group(1) if m else None
                if cur:
                    out[cur] = {"file": os.path.basename(p), "failure_mode": "",
                                "gold": "", "gold_verdict": ""}
            elif cur:
                if "**failure mode**" in line and not out[cur]["failure_mode"]:
                    out[cur]["failure_mode"] = _clean(line.split("**failure mode**", 1)[1])
                elif "**GOLD flag**" in line and not out[cur]["gold"]:
                    txt = line.split("**GOLD flag**", 1)[1]
                    out[cur]["gold"] = _clean(txt)
                    v = txt.lstrip(": *").lower()
                    out[cur]["gold_verdict"] = ("yes" if v.startswith("yes") else
                                                "qualified" if "qualified" in v[:30]
                                                or "with caveat" in v[:40] else "no")
    return out

def _clean(s):
    return re.sub(r"\s+", " ", s).strip(" :*—-")

def _cut(s, n=300):
    if len(s) <= n:
        return s
    head = s[:n]
    return head[:head.rfind(" ")].rstrip(" ,;(—-") + " …"

def entry_events(rec):
    evs, notes = TR.build_events([rec], quiet=True)
    units = TR.units_table(evs)
    return evs, units, notes

def fmt_units(units, unit_type):
    rows = [u for u in units if u["unit_type"] == unit_type]
    if not rows:
        return []
    out = []
    for u in sorted(rows, key=lambda r: (r["t_first"] if r["t_first"] != "" else 0)):
        out.append("| `%s` | %s | %s | %s | %s |" % (
            u["unit"][:44], u["stage_path"], u["deepest_stage"],
            ("%.1f" % u["t_first"]) if u["t_first"] != "" else "—",
            ("%.1f" % u["span_s"]) if u["span_s"] != "" else "—"))
    return out

# build the output tables from the raw streams
def build():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    ann = annotation_blocks()
    doc = ["# Trajectory libraries — gold and failure exemplars (Phase 5)", "",
           "Generated by `tbmetrics/library.py`. Each entry is one archived run: the",
           "Phase-4 event sequence (`trajectory.py`, frozen 2026-08-12), the frozen",
           "annotation's own words, and the regraded outcome. Selection is by hand from the",
           "Phase-1 GOLD flags and is listed in the module — no run was chosen by a metric,",
           "and none of these runs was used to tune one.", "",
           "**How to read a stage path.** Units run their automaton left to right; a path",
           "that stops early is a unit that died there. Entering mid-automaton is legal (a",
           "survivor can recover with no leader decision). `assignment` units exist in every",
           "run; the scenario unit type is the one that carries the collaboration need.", ""]
    index_rows = []

    for scen in ("S1A", "S1B", "S2", "S3", "S4", "S5"):
        sel = [s for s in SELECTION if s["scenario"] == scen]
        if not sel:
            continue
        doc += ["---", "", "## %s" % scen, ""]
        order = {"gold": 0, "process-gold": 1, "failure": 2}
        for s in sorted(sel, key=lambda x: (order[x["cls"]], x["run"])):
            rec = idx.get(s["run"])
            if rec is None:
                doc += ["> **MISSING** %s — not in run_index" % s["run"], ""]
                continue
            evs, units, notes = entry_events(rec)
            a = ann.get(s["run"], {})
            scen_type = {"S3": "blocked-capability", "S4": "cross-edge",
                         "S5": "ablated-requirement"}.get(scen)
            doc += ["### %s — %s  ·  `%s`" % (
                {"gold": "GOLD", "failure": "FAILURE",
                 "process-gold": "PROCESS-GOLD / OUTCOME-FAIL"}[s["cls"]],
                s["label"], s["run"]), ""]
            doc += ["- **outcome**: regrade %s (%s), framework `%s` · arm %s, dose %s, "
                    "task `%s`" % (rec["regrade_score"], "pass" if rec["regrade_pass"] ==
                                   "True" else "fail", rec["framework_outcome"], rec["arm"],
                                   rec["dose"], rec["task"]),
                    "- **annotation** (`%s`): %s" % (a.get("file", "?"),
                                                     _cut(a.get("gold", "—"))),
                    "- **failure mode** (annotation): %s" % (_cut(a.get("failure_mode", ""))
                                                             or "none recorded"),
                    "- **trajectory reading**: %s" % s["reading"], ""]
            if scen_type:
                rows = fmt_units(units, scen_type)
                if rows:
                    doc += ["**%s units**" % scen_type, "",
                            "| unit | stage path | died/ended at | t_first (s) | span (s) |",
                            "|---|---|---|---|---|"] + rows + [""]
            rows = fmt_units(units, "assignment")
            doc += ["**assignment units**", "",
                    "| unit | stage path | died/ended at | t_first (s) | span (s) |",
                    "|---|---|---|---|---|"] + rows + [""]
            asg = [u for u in units if u["unit_type"] == "assignment"]
            comp = (sum(u["completion"] for u in asg) / len(asg)) if asg else 0.0
            sig = " | ".join(sorted({u["stage_path"] for u in asg}))
            index_rows.append(dict(
                run_id=s["run"], scenario=scen, cls=s["cls"], label=s["label"],
                task=rec["task"], arm=rec["arm"], dose=rec["dose"],
                regrade_score=rec["regrade_score"], regrade_pass=rec["regrade_pass"],
                gold_verdict=a.get("gold_verdict", "?"), assignment_units=len(asg),
                assignment_completion=round(comp, 3),
                scenario_units=len([u for u in units if u["unit_type"] == scen_type]) if
                scen_type else 0,
                terminal_units=(len([u for u in units if u["unit_type"] == scen_type
                                     and u["complete"]]) if scen_type else 0),
                scen_deepest=(";".join("%s=%d" % kv for kv in sorted(Counter(
                    u["deepest_stage"] for u in units
                    if u["unit_type"] == scen_type).items())) if scen_type else ""),
                scen_channels=(";".join(sorted({c for u in units
                                                if u["unit_type"] == scen_type
                                                for c in u["channels"].split(";") if c}))
                               if scen_type else ""),
                signature=sig[:200]))
            if notes:
                doc += ["> module notes: %s" % "; ".join(notes), ""]

    doc += _shape_section(index_rows)
    with io.open(DOC, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(doc) + "\n")
    TR._write(os.path.join(OUT, "library_index.tsv"), index_rows)
    cnt = Counter(r["cls"] for r in index_rows)
    print("wrote %s (%d entries: %s)" % (
        os.path.relpath(DOC, ROOT), len(index_rows),
        ", ".join("%d %s" % (v, k) for k, v in sorted(cnt.items()))))
    print("wrote out/library_index.tsv")
    for line in _shape_section(index_rows):
        print(line)

def _shape_section(rows):
    g = [r for r in rows if r["cls"] == "gold"]
    f = [r for r in rows if r["cls"] == "failure"]
    if not g or not f:
        return []
    gm = sum(r["assignment_completion"] for r in g) / len(g)
    fm = sum(r["assignment_completion"] for r in f) / len(f)
    gs = Counter(s for r in g for s in r["signature"].split(" | ") if s)
    fs = Counter(s for r in f for s in r["signature"].split(" | ") if s)
    only_f = [s for s in fs if s not in gs]

    TERMINAL = {"S3": "recovered", "S4": "integrated", "S5": "disposed"}
    sep = []
    for scen, term in TERMINAL.items():
        gg = [r for r in g if r["scenario"] == scen]
        ff = [r for r in f if r["scenario"] == scen]
        if not gg or not ff:
            continue
        sep.append((scen, term,
                    sum(1 for r in gg if r["terminal_units"]), len(gg),
                    sum(1 for r in ff if r["terminal_units"]), len(ff)))
    out = ["---", "", "## Does the shape separate gold from failure?", "",
           "Assignment-level funnel completion: **gold %.3f (n=%d) vs failure %.3f (n=%d)** —"
           % (gm, len(g), fm, len(f)),
           "a gap of %.3f, which is not a usable discriminator on its own." % abs(gm - fm),
           "",
           "Stage-path signatures present in failures and absent from golds: %s."
           % (", ".join("`%s`" % s for s in only_f[:6]) if only_f else
              "none — the same shapes occur on both sides"),
           "",
           "The scenario unit separates them only where the automaton's terminal stage is",
           "the thing at stake. Entries with at least one unit reaching that stage:", ""] + [
           "- **%s** (`%s`): gold %d/%d · failure %d/%d" % (sc, t, a, b, c, d)
           for sc, t, a, b, c, d in sep] + ["",
           "S3 separates cleanly. **S4 does not** — `integrated` fires for neither class,",
           "because the corpus has only three integrating edges in total and the one",
           "GOLD-flagged S4 run is not among them; the S4 signal is at `crossed`, and the",
           "two process-gold entries show why an outcome split cannot be read off it.",
           "**S5 does not either** — `disposed` only records that a verdict was emitted, and",
           "both classes emit one. The fate that matters (honoured vs overruled) sits in the",
           "disposition channel and, for `spec5_s5partial`, in a downstream override the",
           "event stream does not carry at all. Two concrete gaps for the next iteration.", "",
           "This is the Phase-4 limit restated with the library as evidence: the assignment",
           "backbone measures process shape, and two of these failures (cr4, P3) have",
           "textbook shape. What separates the classes is the SCENARIO unit — a",
           "blocked-capability unit that stops at `rerouted`, a cross-edge that never reaches",
           "`integrated`, an ablated requirement disposed inside a pass — and, for content",
           "defects, nothing in the current representation at all. That is the case for the",
           "check-lifecycle backbone, which is the one Phase-4 emitter still unbuilt.", ""]
    return out

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    idx = {r["run_id"]: r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))}
    ann = annotation_blocks()
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-62s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    missing = [s["run"] for s in SELECTION if s["run"] not in idx]
    check("every selected run exists in the run index", not missing, missing or "-")
    unann = [s["run"] for s in SELECTION if idx.get(s["run"], {}).get("annotated") != "yes"]
    check("every selected run is annotated (Phase-1 ground truth)", not unann,
          unann or "-")

    badgold = [s["run"] for s in SELECTION if s["cls"] == "gold"
               and ann.get(s["run"], {}).get("gold_verdict") not in ("yes", "qualified")]
    check("every gold entry is GOLD-flagged in its annotation", not badgold,
          badgold or "-")

    badfail = [s["run"] for s in SELECTION if s["cls"] == "failure"
               and ann.get(s["run"], {}).get("gold_verdict") == "yes"]
    check("no failure entry is an unqualified GOLD in its annotation", not badfail,
          badfail or "-")

    badproc = [s["run"] for s in SELECTION if s["cls"] == "process-gold"
               and not (ann.get(s["run"], {}).get("gold_verdict") == "no"
                        and "process" in ann.get(s["run"], {}).get("gold", "").lower())]
    check("every process-gold entry is annotated `no` on the grounds of outcome, not process",
          not badproc, badproc or "-")

    grd = [s["run"] for s in SELECTION if s["cls"] == "failure"
           and idx.get(s["run"], {}).get("grader_artifact_only") == "yes"]
    check("no failure exemplar is a grader-artifact-only run (standing rule 5)", not grd,
          grd or "-")

    per = defaultdict(Counter)
    for s in SELECTION:
        per[s["scenario"]][s["cls"]] += 1
    thin = {k: dict(v) for k, v in per.items()
            if v["gold"] < 2 or v["failure"] < 2}
    check("every scenario has >=2 gold and >=2 failure, bar the two documented gaps",
          set(thin) <= {"S2", "S4"},
          "%s (S2: only 3 S2 runs annotated; S4: NO run is GOLD-flagged outright — the "
          "two process-golds are the annotators' own verdict)" % (dict(thin) or "-"))

    empty = []
    for s in SELECTION:
        st = {"S3": "blocked-capability", "S4": "cross-edge",
              "S5": "ablated-requirement"}.get(s["scenario"])
        if not st or s["run"] not in idx:
            continue
        _e, units, _n = entry_events(idx[s["run"]])
        if not [u for u in units if u["unit_type"] == st]:
            empty.append(s["run"])
    check("every S3/S4/S5 entry carries its scenario unit type", not empty, empty or "-")

    _e, u, _n = entry_events(idx["p5_s3partial-20260808-204549"])
    bc = [x for x in u if x["unit_type"] == "blocked-capability"]
    check("p5_s3partial still stops at `rerouted` (the landing anti-exemplar)",
          bc and bc[0]["deepest_stage"] == "rerouted",
          bc[0]["stage_path"] if bc else "-")
    _e, u, _n = entry_events(idx["P6_enforced-20260808-143229"])
    check("P6_enforced still has no assignment units (the empty-trajectory boundary case)",
          not [x for x in u if x["unit_type"] == "assignment"],
          "%d units total" % len(u))
    return 1 if bad else 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
