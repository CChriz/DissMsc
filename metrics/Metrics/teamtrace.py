# Loads a run archive and recomputes turns, actions, tokens and messages
# from each member's raw node stream.
import io, json, os, re, sys, bisect
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

JWRUNS = "//wsl.localhost/Ubuntu/home/cz776/jwclone/jwruns"

STALL_THRESHOLD = 90.0
MIN_GAP = 5.0
NOTIFY_WINDOW = 60.0

_BLOCKED_PAT = re.compile(r"Permission denied|Errno 13|Operation not permitted")
_FAILED_PAT = re.compile(r"success=False")
_PATH_PAT = re.compile(r"(?:Permission denied|denied):?\s*'([^']+)'|'file_path':\s*'([^']+)'")
_PERSONA_PAT = re.compile(r"Message sent from (\w+) to")
_CALLID_PAT = re.compile(r"tool_call_id':\s*'([^']+)'")

def _read_json(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        return json.load(f)

def _iter_events(path):
    with io.open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                yield json.loads(line)
            except Exception:
                continue

def discover_streams(archive):
    out = []
    nodes_dir = os.path.join(archive, "traces", "nodes")
    if os.path.isdir(nodes_dir):
        for node in sorted(os.listdir(nodes_dir),
                           key=lambda n: int(re.sub(r"\D", "", n) or 0)):
            for fn in os.listdir(os.path.join(nodes_dir, node)):
                if fn.startswith("stream-node-") and fn.endswith("-full.jsonl"):
                    out.append({"label": fn[len("stream-node-"):-len("-full.jsonl")],
                                "node": node,
                                "path": os.path.join(nodes_dir, node, fn)})
    leader_dir = os.path.join(archive, "traces", "leader")
    if os.path.isdir(leader_dir):
        for fn in os.listdir(leader_dir):
            if fn.startswith("stream-node-") and fn.endswith("-full.jsonl"):
                out.append({"label": "team_leader", "node": "leader",
                            "path": os.path.join(leader_dir, fn)})
    if not out:
        mdir = os.path.join(archive, "members")
        if os.path.isdir(mdir):
            for fn in os.listdir(mdir):
                if fn.endswith(".jsonl"):
                    out.append({"label": fn[len("stream-node-"):-len("-full.jsonl")],
                                "node": fn, "path": os.path.join(mdir, fn)})
    return out

def _new_turn(idx, ev):
    return {"turn": idx, "start_seq": ev["seq"], "start_ts": ev["ts"],
            "end_seq": ev["seq"], "end_ts": ev["ts"], "usage": None,
            "reasoning_chars": 0, "output_chars": 0, "actions": []}

def parse_stream(path):
    turns, cur = [], None
    pending = {}
    pending_args = None
    unmatched_results = 0
    max_backstep = 0.0
    prev_ts = None
    persona_votes = Counter()
    for ev in _iter_events(path):
        t = ev["type"]
        if prev_ts is not None and ev["ts"] < prev_ts:
            max_backstep = max(max_backstep, prev_ts - ev["ts"])
        prev_ts = ev["ts"]
        if t in ("llm_reasoning", "llm_output") and cur and cur["usage"] is not None:
            turns.append(cur)
            cur = None
        if cur is None:
            cur = _new_turn(len(turns), ev)

        cur["end_seq"] = ev["seq"]
        cur["start_ts"] = min(cur["start_ts"], ev["ts"])
        cur["end_ts"] = max(cur["end_ts"], ev["ts"])
        d = ev.get("data") or {}
        if t == "llm_reasoning":
            cur["reasoning_chars"] += d.get("len", 0)
        elif t == "llm_output":
            cur["output_chars"] += d.get("len", 0)
        elif t == "llm_usage":
            u = d.get("usage_metadata") or {}
            cur["usage"] = {k: u.get(k, 0) for k in
                            ("model_name", "input_tokens", "output_tokens",
                             "cache_tokens", "total_tokens")}
            cur["usage"]["code"] = u.get("code", 0)
            perf = d.get("perf") or u.get("perf") or {}
            cur["usage"]["ttft_ms"] = perf.get("ttft_ms")
        elif t == "tool_call":

            args_txt = ((d.get("tool_args") or {}).get("text")) or ""
            if d.get("tool_name") or args_txt:
                pending_args = (d.get("tool_name", ""), args_txt)
        elif t == "tool_update":
            act = {"tool": d.get("tool_name", ""), "call_id": d.get("tool_call_id", ""),
                   "ts": ev["ts"], "blocked": False, "failed": False,
                   "args_text": None, "path": None, "result_excerpt": None}
            if pending_args and pending_args[0] == act["tool"]:
                act["args_text"] = pending_args[1]
                pending_args = None
                try:
                    j = json.loads(act["args_text"] or "{}")
                    act["path"] = j.get("file_path") or j.get("path") or j.get("command")
                except Exception:
                    pass
            cur["actions"].append(act)
            if act["call_id"]:
                pending[act["call_id"]] = act
        elif t == "tool_result":
            txt = ((d.get("tool_result") or {}).get("text")) or ""
            m = _CALLID_PAT.search(txt)
            if not m:
                continue
            act = pending.pop(m.group(1), None)
            if act is None:
                unmatched_results += 1
                continue
            act["result_excerpt"] = txt[:200]
            if _BLOCKED_PAT.search(txt):
                act["blocked"] = True
            elif _FAILED_PAT.search(txt):
                act["failed"] = True
            if act["path"] is None:
                pm = _PATH_PAT.search(txt)
                if pm:
                    act["path"] = pm.group(1) or pm.group(2)
            for name in _PERSONA_PAT.findall(txt):
                persona_votes[name] += 1
    if cur is not None:
        turns.append(cur)
    return {"turns": turns,
            "persona": persona_votes.most_common(1)[0][0] if persona_votes else None,
            "unmatched_results": unmatched_results,
            "max_ts_backstep": round(max_backstep, 3)}

def load_run(archive):
    if not os.path.isdir(archive):
        cand = os.path.join(JWRUNS, archive)
        if os.path.isdir(cand):
            archive = cand
        else:
            raise FileNotFoundError(archive)
    parsed_streams = []
    for st in discover_streams(archive):
        parsed = parse_stream(st["path"])
        if not parsed["turns"]:
            continue
        parsed_streams.append((st, parsed))

    _PIN = {"node1": "planner1", "node2": "planner2", "node3": "planner3",
            "node4": "executor1", "node5": "executor2", "node6": "executor3",
            "node7": "verifier1", "node8": "verifier2",
            "node9": "fullstack1", "node10": "fullstack2"}
    _pin_evidence = [(p["persona"], _PIN.get(s["node"]))
                     for s, p in parsed_streams
                     if p["persona"] and s["label"].startswith("cpool") and s["node"] in _PIN]
    _pins_ok = bool(_pin_evidence) and all(a == b for a, b in _pin_evidence)
    members = []
    for st, parsed in parsed_streams:
        if st["label"] == "team_leader":
            name = "team_leader"
        elif parsed["persona"]:
            name = parsed["persona"]
        elif _pins_ok and st["label"].startswith("cpool") and st["node"] in _PIN:
            name = _PIN[st["node"]]
        else:
            name = f'{st["label"]}@{st["node"]}'
        members.append({"member": name, "label": st["label"], "node": st["node"],
                        "turns": parsed["turns"],
                        "unmatched_results": parsed["unmatched_results"],
                        "max_ts_backstep": parsed["max_ts_backstep"]})
    msgs = []
    mpath = os.path.join(archive, "messages.json")
    if os.path.isfile(mpath):
        msgs = _read_json(mpath).get("messages", [])
    return {"archive": archive, "name": os.path.basename(archive.rstrip("/\\")),
            "members": members, "messages": msgs}

def member_intervals(m):
    merged = []
    for t in sorted(m["turns"], key=lambda t: t["start_ts"]):
        if merged and t["start_ts"] <= merged[-1][1]:
            s, e, lt = merged[-1]
            merged[-1] = (s, max(e, t["end_ts"]),
                          t if t["end_ts"] >= e else lt)
        else:
            merged.append((t["start_ts"], t["end_ts"], t))
    return merged

def member_summary(m):
    turns = m["turns"]
    usages = [t["usage"] for t in turns if t["usage"]]
    acts = [a for t in turns for a in t["actions"]]
    return {"member": m["member"], "node": m["node"], "label": m["label"],
            "llm_calls": len(usages),
            "input_tokens": sum(u["input_tokens"] for u in usages),
            "output_tokens": sum(u["output_tokens"] for u in usages),
            "cache_tokens": sum(u["cache_tokens"] for u in usages),
            "actions": len(acts),
            "with_args": sum(1 for a in acts if a["args_text"] is not None),
            "blocked": sum(1 for a in acts if a["blocked"]),
            "failed": sum(1 for a in acts if a["failed"]),
            "tools": dict(Counter(a["tool"] for a in acts)),
            "max_ts_backstep": m["max_ts_backstep"],
            "active_s": round(sum(e - s for s, e, _ in member_intervals(m)), 1)}

def cost_usd(summary, prices):
    fresh = summary["input_tokens"] - summary["cache_tokens"]
    return round((fresh * prices["input"]
                  + summary["cache_tokens"] * prices.get("cache", prices["input"])
                  + summary["output_tokens"] * prices["output"]) / 1e6, 4)

_TRANSITION_PAT = re.compile(r"Task #?([\w-]+)\s+([\w-]+)\s*(?:→|->)\s*([\w-]+)")
_BOARD_TOOLS = ("create_task", "claim_task", "update_task", "complete_task")

def task_board_events(run):
    evs = []
    for m in run["members"]:
        for t in m["turns"]:
            for a in t["actions"]:
                if a["tool"] not in _BOARD_TOOLS:
                    continue
                task_id = None
                if a["args_text"]:
                    try:
                        task_id = json.loads(a["args_text"]).get("task_id")
                    except Exception:
                        pass
                tr = _TRANSITION_PAT.search(a["result_excerpt"] or "")
                evs.append({"ts": a["ts"], "member": m["member"], "tool": a["tool"],
                            "task_id": task_id or (tr.group(1) if tr else None),
                            "from": tr.group(2) if tr else None,
                            "to": tr.group(3) if tr else None,
                            "ok": not (a["blocked"] or a["failed"])})
    return sorted(evs, key=lambda e: e["ts"])

def stall_windows(run, threshold=STALL_THRESHOLD):
    ivs = sorted((s, e) for m in run["members"] for s, e, _ in member_intervals(m))
    if not ivs:
        return []
    merged = [[ivs[0][0], ivs[0][1]]]
    for s, e in ivs[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(a[1], b[0]) for a, b in zip(merged, merged[1:])
            if b[0] - a[1] > threshold]

def classify_gaps(run, stall_threshold=STALL_THRESHOLD, min_gap=MIN_GAP):
    stalls = stall_windows(run, stall_threshold)
    deliveries = defaultdict(list)
    for msg in run["messages"]:
        for r in (msg.get("recipients") or []):

            for name in (r if isinstance(r, list) else [r]):
                if isinstance(name, str):
                    deliveries[name].append(msg.get("send_ts") or 0)
    out = []
    for m in run["members"]:
        ivs = member_intervals(m)
        for (s1, e1, t1), (s2, _e2, _t2) in zip(ivs, ivs[1:]):
            if s2 - e1 < min_gap:
                continue
            gap = {"member": m["member"], "start": e1, "end": s2,
                   "dur_s": round(s2 - e1, 1)}
            ov = sum(min(s2, b) - max(e1, a) for a, b in stalls
                     if min(s2, b) > max(e1, a))
            last = t1["actions"][-1] if t1["actions"] else None
            note = next((ts for ts in deliveries.get(m["member"], [])
                         if e1 <= ts <= s2 and s2 - ts <= NOTIFY_WINDOW), None)
            if ov >= 0.5 * (s2 - e1):
                gap["kind"], gap["stall_overlap_s"] = "stall", round(ov, 1)
            elif last is not None and last["blocked"]:
                gap["kind"], gap["blocked_tool"] = "blocked_waiting", last["tool"]
            elif note is not None:
                gap["kind"], gap["woken_by_msg_at"] = "dependency_wait", note
            else:
                gap["kind"] = "idle"
            out.append(gap)
    return out

def concurrency_profile(run):
    edges = []
    for m in run["members"]:
        for s, e, _ in member_intervals(m):
            edges += [(s, 1), (e, -1)]
    edges.sort()
    prof, k, prev = Counter(), 0, None
    for ts, d in edges:
        if prev is not None and ts > prev:
            prof[k] += ts - prev
        k += d
        prev = ts
    return {k: round(v, 1) for k, v in sorted(prof.items())}

def cross_check(run):
    checks = []
    summaries = list(map(member_summary, run["members"]))
    ours = {s["member"]: s for s in summaries}

    by_label = defaultdict(list)
    for s in summaries:
        by_label[s["label"]].append(s)
    for lbl, group in by_label.items():
        if len(group) == 1 and lbl not in ours:
            ours[lbl] = group[0]

    derived = {}
    for fn, key in (("turns_by_member.json", None), ("timeline.json", "timeline")):
        p = os.path.join(run["archive"], fn)
        if not os.path.isfile(p):
            continue
        d = _read_json(p)
        rows = d[key] if key else [t for v in d.values() for t in v]
        for t in rows:
            mem = t.get("member")
            if not isinstance(mem, str) or mem.startswith("["):
                continue
            u = t.get("usage") or {}
            e = derived.setdefault(mem, Counter())
            e["turns"] += 1
            e["input_tokens"] += u.get("input_tokens", 0)
            e["output_tokens"] += u.get("output_tokens", 0)
        break

    for mem, d in sorted(derived.items()):
        o = ours.get(mem)
        if o is None:
            checks.append(("MISS", f"derived member {mem!r} not matched in raw recompute"))
            continue
        for field, dkey in (("llm_calls", "turns"), ("input_tokens", "input_tokens"),
                            ("output_tokens", "output_tokens")):
            a, b = o[field], d[dkey]
            checks.append(("OK" if a == b else "MISMATCH",
                           f"{mem}.{field}: raw={a} derived={b}"))

    cpath = os.path.join(run["archive"], "crossings.json")
    if os.path.isfile(cpath):
        cross = _read_json(cpath)
        for role, info in cross.items():
            o = ours.get(role)
            if o is None:
                checks.append(("MISS", f"crossings role {role!r} not matched in raw recompute"))
                continue
            a, b = o["blocked"], info.get("blocked", 0)
            checks.append(("OK" if a == b else "MISMATCH",
                           f"{role}.blocked: raw={a} crossings.json={b}"))
    return checks

# print the human-readable summary
def report(name):
    run = load_run(name)
    print(f"\n=== {run['name']} ===")
    print(f"{'member':<14}{'node':<8}{'calls':>6}{'in_tok':>9}{'out_tok':>9}"
          f"{'cache':>8}{'acts':>6}{'blk':>5}{'fail':>6}{'active_s':>9}")
    for m in run["members"]:
        s = member_summary(m)
        print(f"{s['member']:<14}{s['node']:<8}{s['llm_calls']:>6}"
              f"{s['input_tokens']:>9}{s['output_tokens']:>9}{s['cache_tokens']:>8}"
              f"{s['actions']:>6}{s['blocked']:>5}{s['failed']:>6}{s['active_s']:>9}")
    stalls = stall_windows(run)
    print(f"stall windows (> {STALL_THRESHOLD:.0f}s team-wide silence): "
          + (", ".join(f"{b-a:.0f}s" for a, b in stalls) if stalls else "none"))
    kinds = Counter()
    tot = Counter()
    for g in classify_gaps(run):
        kinds[g["kind"]] += 1
        tot[g["kind"]] += g["dur_s"]
    print("gaps: " + (", ".join(f"{k}={kinds[k]} ({tot[k]:.0f}s)" for k in kinds)
                      if kinds else "none >= min_gap"))
    print("concurrency (s at k active):", concurrency_profile(run))
    summ = [member_summary(m) for m in run["members"]]
    n_acts = sum(s["actions"] for s in summ)
    n_args = sum(s["with_args"] for s in summ)
    skew = max((s["max_ts_backstep"] for s in summ), default=0)
    print(f"args coverage: {n_args}/{n_acts} actions; "
          f"ts ordering resolution: +/-{skew}s (max backstep)")
    board = task_board_events(run)
    trans = [e for e in board if e["to"]]
    print(f"task-board events: {len(board)} ({len(trans)} state transitions)")
    print("cross-checks:")
    for status, msg in cross_check(run):
        print(f"  [{status}] {msg}")

def sweep(root=JWRUNS):
    ok = bad = 0
    for name in sorted(os.listdir(root)):
        p = os.path.join(root, name)
        if not os.path.isdir(p):
            continue
        try:
            run = load_run(p)
            if not run["members"]:
                print(f"EMPTY    {name}: no parseable member streams")
                bad += 1
                continue
            summ = [member_summary(m) for m in run["members"]]
            stalls = stall_windows(run)
            checks = cross_check(run)
            n_flag = sum(1 for st, _ in checks if st != "OK")
            flags = []
            if stalls:
                flags.append(f"stalls={[round(b - a) for a, b in stalls]}")
            if not run["messages"]:
                flags.append("no-messages.json")
            print(f"OK       {name}: members={len(summ)} "
                  f"calls={sum(s['llm_calls'] for s in summ)} "
                  f"xchk_flags={n_flag} {' '.join(flags)}")
            ok += 1
        except Exception as e:
            print(f"ERROR    {name}: {type(e).__name__}: {e}")
            bad += 1
    print(f"\n{ok} parsed, {bad} problems")

if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--sweep":
        sweep(args[1] if len(args) > 1 else JWRUNS)
    else:
        for arg in args or ["d6_enforced-20260706-052406"]:
            report(arg)
