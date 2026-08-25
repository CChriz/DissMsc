# Checks every run archive is complete and its traces are the run's own.
import hashlib, io, json, os, re, sys
from datetime import datetime, timedelta

RUNS_ROOT = r"C:\Users\cz776\Downloads\Runs"
TEAM_BATCHES = [
    "LB90_team3_flash", "LB90_team3_gemini3flash", "LB90_team3_pro", "LB90_team10_pro",
    "S1A_team_dyn_flash", "S1A_team_dyn_pro", "S1A_team_enf_pro",
    "S1B_team_dyn_pro", "S1B_team_enf_pro",
    "S2_pairs_pro", "S2_pairs_enf_pro",
    "S3_partial_enf_pro", "S3_full_enf_pro",
]

SCENARIO_BATCHES = [
    "S1A_team_dyn_pro", "S1A_team_dyn_pro_arm2", "S1A_team_enf_pro",
    "S1B_team_dyn_pro", "S1B_team_enf_pro", "S1B_team_enf_pro_arm2",
    "S2_pairs_pro", "S2_pairs_enf_pro", "S2_pairs_enf_pro_arm2",
    "S3_full_enf_pro", "S3_full_enf_pro_arm2",
    "S3_partial_enf_pro", "S3_partial_enf_pro_arm2",
    "S4_enf_pro", "S4_enf_pro_arm2",
    "S5_partial_enf_pro", "S5_partial_enf_pro_arm2",
    "S5_minimal_enf_pro", "S5_minimal_enf_pro_arm2",
]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
SESS_PAT = re.compile(r"(?:jiuwen_team_)?(sess_[0-9a-f]{12})")
LOG_TS_PAT = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")
UTC_OFFSET = 3600
TOL = 15 * 60

def stream_files(archive):
    out = []
    nodes_dir = os.path.join(archive, "traces", "nodes")
    if os.path.isdir(nodes_dir):
        for node in sorted(os.listdir(nodes_dir)):
            nd = os.path.join(nodes_dir, node)
            if not os.path.isdir(nd):
                continue
            for fn in os.listdir(nd):
                if fn.startswith("stream-") and fn.endswith(".jsonl"):
                    out.append(("node:" + node, os.path.join(nd, fn)))
    ldir = os.path.join(archive, "traces", "leader")
    if os.path.isdir(ldir):
        for fn in os.listdir(ldir):
            if fn.startswith("stream-") and fn.endswith(".jsonl"):
                out.append(("leader", os.path.join(ldir, fn)))
    if not out:
        mdir = os.path.join(archive, "members")
        if os.path.isdir(mdir):
            for fn in sorted(os.listdir(mdir)):
                if fn.endswith(".jsonl"):
                    out.append(("members:" + fn, os.path.join(mdir, fn)))
    return out

def probe_stream(path, scan_bytes=262144):
    size = os.path.getsize(path)
    if size == 0:
        return 0, None, None, set()
    n = 0
    first_ts = last_ts = None
    with io.open(path, "rb") as f:
        head = f.read(scan_bytes)
        if size > 2 * scan_bytes:
            f.seek(size - scan_bytes)
            tail = f.read(scan_bytes)
        else:
            f.seek(0)
            tail = f.read()
        f.seek(0)
        for line in f:
            n += 1
    text = head.decode("utf-8", "replace") + "\n" + tail.decode("utf-8", "replace")
    sessions = set(SESS_PAT.findall(text))
    for blob, which in ((head, "first"), (tail, "last")):
        lines = blob.decode("utf-8", "replace").splitlines()
        if which == "last":
            lines = list(reversed(lines))
        for ln in lines:
            try:
                ts = json.loads(ln).get("ts")
            except Exception:
                continue
            if ts is None:
                continue
            if which == "first":
                first_ts = ts
            else:
                last_ts = ts
            break
    return n, first_ts, last_ts, sessions

def team_log_info(archive):
    d = os.path.join(archive, "traces", "team_logs")
    sessions, tmin, tmax, nlogs = set(), None, None, 0
    if not os.path.isdir(d):
        return sessions, tmin, tmax, nlogs
    for fn in os.listdir(d):
        if not fn.endswith(".log"):
            continue
        nlogs += 1
        p = os.path.join(d, fn)
        with io.open(p, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for ln in lines:
            sessions.update(SESS_PAT.findall(ln))
            m = LOG_TS_PAT.match(ln)
            if m:
                t = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                tmin = t if tmin is None or t < tmin else tmin
                tmax = t if tmax is None or t > tmax else tmax
    return sessions, tmin, tmax, nlogs

def check_manifest(archive):
    mpath = os.path.join(archive, "manifest.json")
    if not os.path.isfile(mpath):
        return None, []
    try:
        man = json.load(io.open(mpath, encoding="utf-8", errors="replace"))
    except Exception as e:
        return False, [f"manifest unreadable: {e}"]
    probs = []
    for role, ent in (man.get("members") or {}).items():
        if not ent:
            continue
        fp = os.path.join(archive, "members", ent["archived_as"])
        if not os.path.isfile(fp):
            probs.append(f"{role}: {ent['archived_as']} missing")
            continue
        if os.path.getsize(fp) != ent.get("bytes"):
            probs.append(f"{role}: bytes {os.path.getsize(fp)} != manifest {ent.get('bytes')}")
            continue
        h = hashlib.sha256()
        with io.open(fp, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        if h.hexdigest() != ent.get("sha256"):
            probs.append(f"{role}: sha256 mismatch")
    return (len(probs) == 0), probs

def audit_archive(archive):
    streams = stream_files(archive)
    log_sessions, log_min, log_max, nlogs = team_log_info(archive)
    flags, details = [], []
    total_lines = 0
    stream_sessions = set()
    ts_lo = ts_hi = None
    live = 0
    for label, path in streams:
        n, t0, t1, sess = probe_stream(path)
        total_lines += n
        stream_sessions |= sess
        if n > 0:
            live += 1
        if t0 is not None:
            ts_lo = t0 if ts_lo is None or t0 < ts_lo else ts_lo
        if t1 is not None:
            ts_hi = t1 if ts_hi is None or t1 > ts_hi else ts_hi

    if not streams or live == 0:
        flags.append("EMPTY")
    else:

        if log_sessions and stream_sessions and not (stream_sessions & log_sessions):
            flags.append("SESS")
            details.append(f"streams={sorted(stream_sessions)} logs={sorted(log_sessions)}")

        if log_min and log_max and ts_lo is not None:
            lo = datetime.utcfromtimestamp(ts_lo + UTC_OFFSET)
            hi = datetime.utcfromtimestamp(ts_hi + UTC_OFFSET)
            if hi < log_min - timedelta(seconds=TOL) or lo > log_max + timedelta(seconds=TOL):
                flags.append("TIME")
                details.append(f"stream {lo:%m-%d %H:%M}-{hi:%H:%M} vs logs "
                               f"{log_min:%m-%d %H:%M}-{log_max:%H:%M}")

        node_streams = {l for l, _ in streams if l.startswith("node:")}
        if nlogs and node_streams and len(node_streams) < nlogs:
            flags.append("PARTIAL")
            details.append(f"{len(node_streams)} node streams vs {nlogs} node logs")
    man_ok, man_probs = check_manifest(archive)
    if man_ok is False:
        flags.append("MANIFEST")
        details += man_probs
    return {
        "archive": os.path.basename(archive),
        "streams": len(streams), "live_streams": live, "lines": total_lines,
        "node_logs": nlogs,
        "sessions_stream": ",".join(sorted(stream_sessions)) or "-",
        "sessions_logs": ",".join(sorted(log_sessions)) or "-",
        "manifest": {None: "none", True: "ok", False: "BAD"}[man_ok],
        "status": "+".join(flags) if flags else "OK",
        "details": "; ".join(details),
    }

# entry point
def main():
    args = sys.argv[1:]
    if args == ["--scenarios"]:
        batches = [os.path.join(RUNS_ROOT, b) for b in SCENARIO_BATCHES]
    elif args == ["--all"] or not args:
        batches = [os.path.join(RUNS_ROOT, b) for b in TEAM_BATCHES]
    else:
        batches = args
    rows, bad = [], 0
    for b in batches:
        if not os.path.isdir(b):
            print(f"-- skip (missing): {b}")
            continue
        arcs = [os.path.join(b, d) for d in sorted(os.listdir(b))
                if os.path.isdir(os.path.join(b, d))]
        print(f"== {os.path.basename(b)} ({len(arcs)} archives)")
        for a in arcs:
            r = audit_archive(a)
            r["batch"] = os.path.basename(b)
            rows.append(r)
            if r["status"] != "OK":
                bad += 1
            mark = "  " if r["status"] == "OK" else "!!"
            print(f" {mark} {r['archive']:44s} {r['status']:12s} "
                  f"streams={r['live_streams']}/{r['streams']} lines={r['lines']:7d} "
                  f"manifest={r['manifest']}"
                  + (f"  [{r['details']}]" if r["details"] else ""))
    os.makedirs(OUT_DIR, exist_ok=True)
    cols = ["batch", "archive", "status", "streams", "live_streams", "lines",
            "node_logs", "sessions_stream", "sessions_logs", "manifest", "details"]
    with io.open(os.path.join(OUT_DIR, "trace_audit.tsv"), "w", encoding="utf-8") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    n_ok = sum(1 for r in rows if r["status"] == "OK")
    print(f"\n{n_ok}/{len(rows)} archives OK; {bad} flagged. "
          f"-> {os.path.join(OUT_DIR, 'trace_audit.tsv')}")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
