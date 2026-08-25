#!/usr/bin/env python3
"""archive_run.py — snapshot a complete TeamBench-on-JiuwenSwarm run.

One command, run AFTER a run finishes (before the next configure_task.sh wipes
run_current), captures everything needed to grade and analyse the run:

  * the deliverable workspace + reports + artifacts + attestation (the verifier
    verdict) + spec/brief from /srv/jwteam_clone/shared/run_current
  * every stream trace: per-node (node1/2/3) + leader, plus each node's
    structured full.log (carries the sys_operation fs-op records, incl. ACL
    denials = crossings) and the central sys_operation.log
  * the final task-table state from the shared sqlite DB
  * AND THEN, on the copied traces: per-member turn reconstruction
    (turns_by_member.json) and the boundary-crossing report (crossings.json),
    plus a manifest with provenance (sha256 per member trace) and a headline
    summary for easy arm-vs-arm diffing.

The per-node trace dirs are owned by the jw_cnode users (that's the OS isolation),
so collection uses ``sudo cp`` and then ``sudo chown`` the archive back to you.
Run it as your normal user (cz776) — it will sudo for the privileged copies and
may prompt for your password once. Do NOT run the whole thing under sudo (that
would break the conda import + leave root-owned outputs).

Usage:
  ./archive_run.py                       # label "run", timestamp appended
  ./archive_run.py d6_enforced           # custom label
  ./archive_run.py d6_promptonly --arm prompt-only
  ./archive_run.py d6_enforced --no-sudo # when you already have read access
Output: ~/jwclone/jwruns/<label>-<YYYYmmdd-HHMMSS>/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# Make the co-located analysis modules importable regardless of cwd. Collection
# still works even if these are missing (analysis is just skipped).
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import analyze_trace as at
    import team_turn_grouping as ttg
    _ANALYSIS = True
except Exception as _e:                       # pragma: no cover
    at = ttg = None
    _ANALYSIS = False
    _ANALYSIS_ERR = _e

# ---- config (edit here if paths change) ------------------------------------
RUN_CURRENT  = "/srv/jwteam_clone/shared/run_current"
DB           = "/srv/jwteam_clone/shared/team_shared.db"
LEADER_TRACE = "/home/cz776/jwclone/leader_home/.jiuwenswarm/.agent_teams/traces"
NODE_TRACE   = "/srv/jwteam_clone/cnode{n}/.jiuwenswarm/.agent_teams/traces"
NODE_LOG     = "/srv/jwteam_clone/cnode{n}/.jiuwenswarm/agent/.logs"
SYSOP_LOG    = "/home/cz776/jwclone/jiuwenswarm/logs/logs/sys_operation.log"
OWNER        = "cz776:cz776"
DEST_ROOT    = str(Path.home() / "jwruns")
# node number -> role (node1 Planner, node2 Executor, node3 Verifier)
NODE_ROLE    = {1: "planner", 2: "executor", 3: "verifier"}
# run_current is copied in full (see step 1) — deliverables can land at the root
# (e.g. config_system.py) OR under workspace/, so we never assume a fixed set.
# ----------------------------------------------------------------------------


def run(cmd: list[str]) -> int:
    return subprocess.run(cmd).returncode


def sh_exists(path: str, flag: str, use_sudo: bool) -> bool:
    if use_sudo:
        return subprocess.run(["sudo", "test", f"-{flag}", path]).returncode == 0
    p = Path(path)
    return {"e": p.exists, "d": p.is_dir, "f": p.is_file}[flag]()


def copy_dir(src: str, dst: Path, use_sudo: bool) -> bool:
    if not sh_exists(src, "d", use_sudo):
        return False
    dst.mkdir(parents=True, exist_ok=True)
    if use_sudo:
        return run(["sudo", "cp", "-a", f"{src}/.", f"{dst}/"]) == 0
    shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True,
                    ignore_dangling_symlinks=True)
    return True


def copy_entry(src: str, dst: Path, use_sudo: bool) -> bool:
    """Copy a file OR a directory entry (-a preserves either)."""
    if not sh_exists(src, "e", use_sudo):
        return False
    if use_sudo:
        return run(["sudo", "cp", "-a", src, str(dst)]) == 0
    s = Path(src)
    if s.is_dir():
        shutil.copytree(s, dst, dirs_exist_ok=True, symlinks=True,
                        ignore_dangling_symlinks=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, dst)
    return True


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def snapshot_tree(root: Path) -> tuple[list[dict], int]:
    files, total = [], 0
    if not root.is_dir():
        return files, total
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        b = p.stat().st_size
        total += b
        files.append({"path": str(p.relative_to(root)), "bytes": b,
                      "sha256": sha256(p)})
    return files, total


def newest_full(d: Path, session: str | None) -> Path | None:
    if not d.is_dir():
        return None
    files = sorted(d.glob("stream-node-*-full.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        files = sorted(d.glob("*-full.jsonl"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    if session:
        files = [f for f in files if session in f.name] or files
    return files[0] if files else None


def dump_task_table(db_path: str, out: Path, use_sudo: bool) -> bool:
    """Dump final task-table state from the shared sqlite DB."""
    local = db_path
    tmp = None
    if not sh_exists(db_path, "f", use_sudo):
        return False
    # ensure readable: if direct open fails, sudo-copy to a temp file
    try:
        sqlite3.connect(f"file:{db_path}?mode=ro", uri=True).close()
    except Exception:
        if use_sudo:
            tmp = out.parent / "_task_shared.db"
            if run(["sudo", "cp", db_path, str(tmp)]) == 0:
                run(["sudo", "chown", OWNER, str(tmp)])
                local = str(tmp)
            else:
                return False
        else:
            return False
    try:
        con = sqlite3.connect(local)
        cur = con.cursor()
        lines: list[str] = []
        for (t,) in cur.execute("select name from sqlite_master where type='table'"):
            if t.startswith("team_task") and "depend" not in t:
                lines.append(f"=== {t} ===")
                for row in cur.execute(f"select task_id, assignee, status from {t}"):
                    lines.append("  " + repr(row))
            elif "task_dependency" in t:
                lines.append(f"=== {t} ===")
                for row in cur.execute(f"select * from {t}"):
                    lines.append("  " + repr(row))
        con.close()
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True
    except Exception as e:
        out.write_text(f"(task table dump failed: {e})\n", encoding="utf-8")
        return False
    finally:
        if tmp and tmp.exists():
            tmp.unlink()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("label", nargs="?", default="run",
                    help="archive label (timestamp is appended). e.g. d6_enforced")
    ap.add_argument("--arm", choices=["enforced", "prompt-only"],
                    help="experimental arm (recorded in the manifest)")
    ap.add_argument("--archive-root", default=DEST_ROOT)
    ap.add_argument("--session", help="session id substring (to disambiguate -full)")
    ap.add_argument("--run-current", default=RUN_CURRENT)
    ap.add_argument("--db", default=DB)
    ap.add_argument("--leader-dir", default=LEADER_TRACE)
    ap.add_argument("--nodes", type=int, default=3,
                    help="number of nodes to collect (default 3; dynamic pool sets this higher)")
    ap.add_argument("--node-trace", default=NODE_TRACE,
                    help="template with {n} for per-node traces dir")
    ap.add_argument("--node-log", default=NODE_LOG,
                    help="template with {n} for per-node .logs dir")
    ap.add_argument("--sysop-log", default=SYSOP_LOG)
    ap.add_argument("--owner", default=OWNER)
    ap.add_argument("--no-sudo", action="store_true",
                    help="copy without sudo (when you already have read access)")
    ap.add_argument("--no-analysis", action="store_true",
                    help="collect only; skip turn/crossing analysis")
    ap.add_argument("--exclude", default="",
                    help="comma-sep run_current top-level entries to drop from the "
                         "archive (e.g. skills,trajectories) to save space")
    ap.add_argument("--note", default="")
    args = ap.parse_args()
    use_sudo = not args.no_sudo

    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = Path(args.archive_root) / f"{args.label}-{stamp}"
    (dest / "traces" / "leader").mkdir(parents=True, exist_ok=True)
    (dest / "traces" / "nodes").mkdir(parents=True, exist_ok=True)
    (dest / "members").mkdir(parents=True, exist_ok=True)
    print(f"[archive_run] destination: {dest}  (sudo={'on' if use_sudo else 'off'})")

    manifest: dict = {
        "label": args.label, "arm": args.arm, "session": args.session,
        "note": args.note, "archived_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip(),
        "source": {"run_current": args.run_current, "db": args.db,
                   "leader": args.leader_dir},
        "collected": {}, "members": {},
    }

    # 1. run_current — copy the ENTIRE tree -----------------------------------
    # Deliverables may be written to the run_current ROOT (e.g. config_system.py)
    # or under workspace/; a fixed entry list silently drops root-level files, so
    # snapshot everything and prune only what --exclude names.
    print("[archive_run] copying run_current (full tree)...")
    rc_dest = dest / "run_current"
    if copy_dir(args.run_current, rc_dest, use_sudo):
        try:
            collected_rc = sorted(p.name for p in rc_dest.iterdir())
        except Exception:
            collected_rc = []
        for e in collected_rc:
            print(f"  + {e}")
    else:
        collected_rc = []
        print(f"  WARNING: run_current not found at {args.run_current}", file=sys.stderr)
    manifest["collected"]["run_current"] = collected_rc

    # 2. traces (leader + per-node) + structured logs ------------------------
    print("[archive_run] copying traces...")
    if copy_dir(args.leader_dir, dest / "traces" / "leader", use_sudo):
        print("  + leader traces")
    for n in range(1, args.nodes + 1):
        ntrace = args.node_trace.format(n=n)
        nlog = args.node_log.format(n=n)
        ndst = dest / "traces" / "nodes" / f"node{n}"
        if copy_dir(ntrace, ndst, use_sudo):
            print(f"  + node{n} traces")
        full_log = f"{nlog}/full.log"
        if copy_entry(full_log, ndst / "full.log", use_sudo):
            print(f"  + node{n} full.log")
    if copy_entry(args.sysop_log, dest / "traces" / "sys_operation.log", use_sudo):
        print("  + sys_operation.log")

    # 3. task table ----------------------------------------------------------
    if dump_task_table(args.db, dest / "task_table.txt", use_sudo):
        print("  + task_table.txt")

    # 4. hand ownership of the whole archive back to the user ----------------
    if use_sudo:
        run(["sudo", "chown", "-R", args.owner, str(dest)])

    # prune any --exclude'd run_current entries (now user-owned, plain rm)
    for name in [x.strip() for x in args.exclude.split(",") if x.strip()]:
        victim = rc_dest / name
        if victim.exists():
            shutil.rmtree(victim, ignore_errors=True) if victim.is_dir() else victim.unlink()
            collected_rc = [e for e in collected_rc if e != name]
            print(f"  - pruned run_current/{name}")
    manifest["collected"]["run_current"] = collected_rc

    # 5. identify each member's newest -full.jsonl from the copied traces ----
    member_files: list[Path] = []
    src_for_member: dict[str, Path] = {
        "team_leader": dest / "traces" / "leader",
        **{NODE_ROLE[n]: dest / "traces" / "nodes" / f"node{n}" for n in (1, 2, 3)},
    }
    for role, sdir in src_for_member.items():
        f = newest_full(sdir, args.session)
        if f is None:
            print(f"  WARNING: no -full.jsonl for {role} under {sdir}", file=sys.stderr)
            manifest["members"][role] = None
            continue
        canon = dest / "members" / f"stream-node-{role}-full.jsonl"
        canon.write_text(f.read_text(encoding="utf-8").replace("\r\n", "\n"),
                         encoding="utf-8")
        member_files.append(canon)
        manifest["members"][role] = {
            "from_trace": str(f.relative_to(dest)), "archived_as": canon.name,
            "bytes": canon.stat().st_size, "sha256": sha256(canon),
        }

    # 6. analysis on the copied member traces --------------------------------
    if args.no_analysis:
        print("[archive_run] analysis skipped (--no-analysis).")
    elif not _ANALYSIS:
        print(f"[archive_run] analysis skipped: could not import modules ({_ANALYSIS_ERR}). "
              f"Put analyze_trace.py + team_turn_grouping.py next to this script.",
              file=sys.stderr)
    elif not member_files:
        print("[archive_run] analysis skipped: no member -full.jsonl found.",
              file=sys.stderr)
    else:
        grouped = ttg.group_many(member_files)
        (dest / "turns_by_member.json").write_text(
            json.dumps(grouped, indent=2, ensure_ascii=False), encoding="utf-8")
        # two separate docs: (1) global ts-ordered full-content transcript, and
        # (2) the ordered inter-agent message sequence (the conversation).
        _messages = ttg.extract_messages(grouped)
        (dest / "timeline.json").write_text(
            json.dumps({"timeline": ttg.build_timeline(grouped, _messages)},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        (dest / "messages.json").write_text(
            json.dumps({"messages": ttg.message_sequence(grouped, _messages)},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        report, _calls, _files, _exempt = at.analyze(member_files, args.session)
        (dest / "crossings.json").write_text(
            json.dumps({m: dict(r) for m, r in report.items()}, indent=2,
                       ensure_ascii=False), encoding="utf-8")
        manifest["summary"] = {
            m: {"turns": len(ts),
                "actions": sum(len(t["actions"]) for t in ts),
                "crossings": sum(1 for t in ts for a in t["actions"] if a.get("crossing")),
                "blocked": sum(1 for t in ts for a in t["actions"]
                               if a.get("crossing") and a.get("blocked")),
                "permitted": sum(1 for t in ts for a in t["actions"]
                                 if a.get("crossing") and a.get("blocked") is False),
                "exempt": bool(at and m in at.EXEMPT_ROLES)}
            for m, ts in grouped.items()}

    # 7. provenance: shared-tree listing + manifest + human-readable MANIFEST
    sh_files, sh_total = snapshot_tree(rc_dest)
    manifest["run_current_files"] = {"count": len(sh_files), "total_bytes": sh_total,
                                     "files": sh_files}
    (dest / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    txt = [f"archived_at: {manifest['archived_at']}", f"label: {args.label}",
           f"arm: {args.arm}", f"session: {args.session}",
           f"source: {args.run_current}", f"host: {manifest['host']}", "",
           "contents:"]
    for p in sorted(dest.rglob("*")):
        if p.is_file():
            txt.append("  " + str(p.relative_to(dest)))
    (dest / "MANIFEST.txt").write_text("\n".join(txt) + "\n", encoding="utf-8")

    print(f"\n[archive_run] done -> {dest}")
    print(f"[archive_run] deliverable to grade: {rc_dest}/workspace/")
    if not args.no_analysis and _ANALYSIS and member_files:
        print()
        ttg.summarize(grouped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

