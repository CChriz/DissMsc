#!/usr/bin/env python3
"""Grade scenario-2 bundle archives per-subtask.

Each P<k> bundle archive has ONE shared workspace containing both subtasks'
files; each subtask is graded by its own self-contained grader at
~/jwclone/multitask/combos_s2/P<k>_grading/<SET>_<subtask>/grade.sh
(4-arg contract: WORKSPACE REPORTS SUBMISSION TASK_DIR; expected.json in
the grading bundle's reports/).

Per-subtask attestation: bundle runs write ONE merged attestation.json in
team-improvised shapes ({"subtasks": {...}} dict, {"results": [...]} list,
or single-subtask top-level). We extract the entry whose 'subtask' matches
and stage it as a top-level attestation for the grader's attestation check;
if no entry matches, the merged file is staged as-is.

Usage: regrade_s2_pairs.py [P1 P2 ...]   (default: all P dirs with archives)
Writes s2_regrade.tsv / s2_regrade_records.json into the runs dir.
"""
import csv, glob, json, os, shutil, subprocess, sys
from pathlib import Path

COMBOS = Path("/home/cz776/jwclone/multitask/combos_s2")
RUNS = Path(os.environ.get("JW_S2_RUNS", "/mnt/c/Users/cz776/Downloads/Runs/S2_pairs_pro"))
LABEL = os.environ.get("JW_S2_LABEL", "prompt-only")
TMP = Path("/tmp/regrade_s2")
TIMEOUT = 120

env = os.environ.copy()
env["PATH"] = ":".join([
    "/home/cz776/miniconda3/envs/jwclone/bin",
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/.local/go/bin"),
    env.get("PATH", ""),
])


def extract_attestation(merged, subtask: str):
    """Pull the per-subtask entry out of a merged bundle attestation."""
    if isinstance(merged, list):
        merged = {"results": merged}
    if not isinstance(merged, dict):
        return {"raw": merged}, "non-dict"
    cands = []
    for key in ("subtasks", "results"):
        s = merged.get(key)
        if isinstance(s, dict):
            for name, x in s.items():
                if isinstance(x, dict):
                    cands.append((str(name), x))
        elif isinstance(s, list):
            for x in s:
                if isinstance(x, dict):
                    cands.append((str(x.get("subtask", "")), x))
    if isinstance(merged.get("verdict"), str) and merged.get("subtask"):
        cands.append((str(merged["subtask"]), merged))
    for name, x in cands:
        if name == subtask or name.endswith("_" + subtask) or subtask in name:
            out = dict(x)
            out.setdefault("verdict", x.get("verdict"))
            out.setdefault("subtask", subtask)
            return out, "extracted"
    return merged, "merged-as-is"


def grade_subtask(bundle: str, sub_dir: Path, archive: Path) -> dict:
    subtask = sub_dir.name.split("_", 1)[1] if "_" in sub_dir.name else sub_dir.name
    ws_src = archive / "run_current" / "workspace"
    work = TMP / f"{bundle}_{subtask}"
    shutil.rmtree(work, ignore_errors=True)
    ws = work / "workspace"; rep = work / "reports"; sub = work / "submission"
    try:
        shutil.copytree(ws_src, ws, symlinks=True, ignore_dangling_symlinks=True)
    except shutil.Error:
        pass
    rep.mkdir(parents=True); sub.mkdir(parents=True)

    src_reports = sub_dir / "reports"
    if src_reports.is_dir():
        for f in src_reports.iterdir():
            shutil.copy(f, rep / f.name)
        exp = rep / "expected.json"
        if exp.exists():
            shutil.copy(exp, ws / "expected.json")

    att_note = "none"
    att_path = archive / "run_current" / "attestation.json"
    if att_path.exists():
        try:
            merged = json.loads(att_path.read_text())
            att, att_note = extract_attestation(merged, subtask)
            (sub / "attestation.json").write_text(json.dumps(att, ensure_ascii=False))
        except (json.JSONDecodeError, OSError):
            shutil.copy(att_path, sub / "attestation.json")
            att_note = "copy-unparsed"

    task_dir = sub_dir / "task_dir"
    if not task_dir.exists():
        task_dir = sub_dir
    gs = work / "grade.sh"
    gs.write_bytes((sub_dir / "grade.sh").read_bytes().replace(b"\r\n", b"\n"))
    cmd = ["bash", str(gs), str(ws), str(rep), str(sub), str(task_dir)]
    timed_out = False
    try:
        res = subprocess.run(cmd, cwd=str(sub_dir), env=env, text=True,
                             capture_output=True, timeout=TIMEOUT)
        rc = res.returncode
        stderr_tail = res.stderr[-300:] if res.stderr else ""
    except subprocess.TimeoutExpired:
        timed_out, rc, stderr_tail = True, -1, "TIMEOUT"

    score_path = rep / "score.json"
    if score_path.exists():
        try:
            score = json.loads(score_path.read_text())
        except json.JSONDecodeError:
            score = {"pass": False, "failure_modes": ["unparseable_score_json"]}
    else:
        score = {"pass": False, "failure_modes": ["missing_score_json"]}
    sec = score.get("secondary", {}) or {}
    rec = {
        "bundle": bundle, "subtask": subtask,
        "pass": score.get("pass", False),
        "partial_score": sec.get("partial_score"),
        "checks_passed": sec.get("checks_passed"),
        "checks_total": sec.get("checks_total"),
        "failure_modes": score.get("failure_modes", []),
        "attestation": att_note, "timed_out": timed_out, "returncode": rc,
        "stderr_tail": stderr_tail,
    }
    shutil.rmtree(work, ignore_errors=True)
    return rec


def main():
    TMP.mkdir(exist_ok=True)
    bundles = sys.argv[1:] or [f"P{i}" for i in range(1, 11)]
    records = []
    for b in bundles:
        archives = sorted(glob.glob(str(RUNS / f"{b}_{LABEL}-*")))
        gdir = COMBOS / f"{b}_grading"
        if not archives or not gdir.is_dir():
            print(f"{b}: skipped (archive={bool(archives)} grading={gdir.is_dir()})")
            continue
        archive = Path(archives[-1])
        for sub_dir in sorted(p for p in gdir.iterdir() if p.is_dir()):
            try:
                rec = grade_subtask(b, sub_dir, archive)
            except Exception as e:
                rec = {"bundle": b, "subtask": sub_dir.name,
                       "error": f"{type(e).__name__}: {e}"}
            records.append(rec)
            print(f"{b:4s} {rec.get('subtask',''):26s} pass={rec.get('pass','ERR')} "
                  f"partial={rec.get('partial_score')} "
                  f"att={rec.get('attestation','')} "
                  f"{'ERR:' + rec['error'] if 'error' in rec else ''}", flush=True)
    (RUNS / "s2_regrade_records.json").write_text(json.dumps(records, indent=1))
    with open(RUNS / "s2_regrade.tsv", "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["bundle", "subtask", "pass", "partial_score", "checks_passed",
                    "checks_total", "failure_modes", "attestation", "note"])
        for r in records:
            w.writerow([r.get("bundle"), r.get("subtask"), r.get("pass", ""),
                        r.get("partial_score", ""), r.get("checks_passed", ""),
                        r.get("checks_total", ""),
                        ";".join(r.get("failure_modes", []) or []),
                        r.get("attestation", ""),
                        r.get("error", "") or ("timeout" if r.get("timed_out") else "")])
    print(f"\nwrote {RUNS/'s2_regrade.tsv'}")


if __name__ == "__main__":
    main()
