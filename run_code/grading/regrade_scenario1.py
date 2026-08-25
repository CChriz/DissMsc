#!/usr/bin/env python3
"""Re-grade scenario-1 team batch archives (S1A/S1B) with the canonical
TeamBench grade.sh contract — adapted from regrade_lb90.py (2026-08-08).

Differences from regrade_lb90.py:
  - eval bundles resolved across LB90 + HTNI + LTNI sets (scenario-1 task mix)
  - task list read from batch_results.tsv (timestamp/task/arm/outcome/archive)
  - archive label fixed to prompt-only; latest archive per task wins
Everything else replicates the canonical contract: 5-arg grade.sh, absolute
paths, cwd = the task's set root, NO attestation fabrication, expected.json
staged into reports/ AND workspace/, CRLF-stripped shim, jwclone-env PATH.

Usage: regrade_scenario1.py /mnt/c/Users/cz776/Downloads/Runs/S1A_team_dyn_pro
"""
import csv, glob, json, os, shutil, subprocess, sys
from pathlib import Path

SETS = [Path("/mnt/c/Users/cz776/Downloads/TeamBenchTasks") / s
        for s in ("LB90", "HTNI", "LTNI")]
RUNS = Path(sys.argv[1])
LABEL = sys.argv[2] if len(sys.argv) > 2 else "prompt-only"
TB_HELPERS = Path("/home/cz776/TeamBench/harness/grader_helpers.sh")
OUT_TSV = RUNS / "scenario1_regrade.tsv"
OUT_JSON = RUNS / "scenario1_regrade_records.json"
TMP = Path("/tmp/regrade_s1")
TIMEOUT = 90

# graders need pytest etc. (jwclone conda env) + go/git-lfs
env = os.environ.copy()
env["PATH"] = ":".join([
    "/home/cz776/miniconda3/envs/jwclone/bin",
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/.local/go/bin"),
    env.get("PATH", ""),
])


def find_eval(task):
    for root in SETS:
        d = root / "evals" / f"{task}_0_eval"
        if d.exists():
            return root, d
    return None, None


def grade_one(task: str) -> dict:
    set_root, eval_dir = find_eval(task)
    if eval_dir is None:
        return {"task": task, "error": "no eval bundle in LB90/HTNI/LTNI"}
    archives = sorted(glob.glob(str(RUNS / f"{task}_{LABEL}-*")))
    if not archives:
        return {"task": task, "error": "no run archive"}
    ws_src = Path(archives[-1]) / "run_current" / "workspace"
    if not ws_src.exists():
        return {"task": task, "error": "no workspace in archive"}

    work = TMP / task
    shutil.rmtree(work, ignore_errors=True)
    ws = work / "workspace"; rep = work / "reports"; sub = work / "submission"
    try:
        shutil.copytree(ws_src, ws, symlinks=True, ignore_dangling_symlinks=True)
    except shutil.Error as e:
        print(f"  ({task}: copytree warnings: {len(e.args[0])} entries skipped)")
    run_datasets = ws_src.parent / "datasets"
    if run_datasets.is_dir():
        try:
            shutil.copytree(run_datasets, work / "datasets", symlinks=True,
                            ignore_dangling_symlinks=True)
        except shutil.Error:
            pass
    rep.mkdir(parents=True); sub.mkdir(parents=True)

    expected = None
    for cand in (eval_dir / "reports" / "expected.json", eval_dir / "expected.json"):
        if cand.exists():
            expected = cand
            break
    if expected:
        shutil.copy(expected, rep / "expected.json")
        shutil.copy(expected, ws / "expected.json")

    run_att = Path(archives[-1]) / "run_current" / "attestation.json"
    if run_att.exists():
        shutil.copy(run_att, sub / "attestation.json")
        att_src = "run"
    else:
        att_src = "none"

    task_dir = eval_dir / "task_dir"
    if not task_dir.exists():
        task_dir = eval_dir
    shim = work / "shim"
    shim_task = shim / "evals" / task
    shim_task.mkdir(parents=True)
    (shim / "harness").mkdir()
    shutil.copy(TB_HELPERS, shim / "harness" / "grader_helpers.sh")
    gs = shim_task / "grade.sh"
    gs.write_bytes((eval_dir / "grade.sh").read_bytes().replace(b"\r\n", b"\n"))
    cmd = ["bash", str(gs), str(ws), str(rep), str(sub),
           str(task_dir)] + ([str(rep / "expected.json")] if expected else [])
    timed_out = False
    try:
        res = subprocess.run(cmd, cwd=str(set_root), env=env, text=True,
                             capture_output=True, timeout=TIMEOUT)
        rc = res.returncode
        stderr_tail = res.stderr[-400:] if res.stderr else ""
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
        "task": task,
        "pass": score.get("pass", False),
        "partial_score": sec.get("partial_score"),
        "checks_passed": sec.get("checks_passed"),
        "checks_total": sec.get("checks_total"),
        "failure_modes": score.get("failure_modes", []),
        "checklist": score.get("checklist"),
        "expected_staged": bool(expected),
        "attestation": att_src,
        "timed_out": timed_out,
        "returncode": rc,
        "stderr_tail": stderr_tail,
        "eval_set": set_root.name,
    }
    shutil.rmtree(work, ignore_errors=True)
    return rec


def main():
    TMP.mkdir(exist_ok=True)
    tasks = []
    with open(RUNS / "batch_results.tsv") as f:
        for row in csv.reader(f, delimiter="\t"):
            if row and row[0] != "timestamp":
                tasks.append((row[1], row[3] if len(row) > 3 else ""))
    seen = set()
    tasks = [(t, o) for t, o in tasks if not (t in seen or seen.add(t))]
    records = []
    for i, (task, old) in enumerate(tasks, 1):
        try:
            rec = grade_one(task)
        except Exception as e:
            rec = {"task": task, "error": f"{type(e).__name__}: {e}"}
        rec["old_outcome"] = old
        records.append(rec)
        ps = rec.get("partial_score")
        print(f"[{i}/{len(tasks)}] {task:26s} attested={old:14s} "
              f"regrade_pass={rec.get('pass', 'ERR')} partial={ps} "
              f"{'ERR:' + rec['error'] if 'error' in rec else ''}"
              f"{'TIMEOUT' if rec.get('timed_out') else ''}", flush=True)
    OUT_JSON.write_text(json.dumps(records, indent=1))
    with open(OUT_TSV, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["task", "old_outcome", "pass", "partial_score",
                    "checks_passed", "checks_total", "failure_modes", "note"])
        for r in records:
            w.writerow([r["task"], r.get("old_outcome", ""), r.get("pass", ""),
                        r.get("partial_score", ""), r.get("checks_passed", ""),
                        r.get("checks_total", ""),
                        ";".join(r.get("failure_modes", []) or []),
                        r.get("error", "") or ("timeout" if r.get("timed_out") else "")])
    print(f"\nwrote {OUT_TSV}\nwrote {OUT_JSON}")


if __name__ == "__main__":
    main()
