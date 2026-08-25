# When the zone map was disclosed vs when members first probed across
# the seam, for all 24 S4 runs.
import io, json, os, re, sys
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
S4MAPS = os.path.join(HERE, "s4maps")

def split_map(task):
    p = os.path.join(S4MAPS, "%s.split.json" % task)
    if not os.path.isfile(p):
        return None
    return json.load(io.open(p, encoding="utf-8"))

def zone_of(m, member):
    for z in ("zoneA", "zoneB"):
        if member in m.get(z, {}).get("members", []):
            return z
    return None

def path_zone(m, path):
    if not path:
        return None
    tail = path.replace("\\", "/").split("workspace/", 1)
    if len(tail) < 2:
        return None
    tail = tail[1]
    for z in ("zoneA", "zoneB"):
        for q in m[z].get("paths", []):
            if tail == q or tail.startswith(q.rstrip("/") + "/"):
                return z
    return None

def leader_disclosures(run):
    out = []
    for mem in run["members"]:
        if mem["member"] != "team_leader":
            continue
        for t in mem["turns"]:
            for a in t["actions"]:
                args = a["args_text"] or ""
                if not args:
                    continue
                if a["tool"] == "build_team":
                    try:
                        j = json.loads(args)
                        out.append((a["ts"], "build_team",
                                    " ".join(str(v) for v in j.values())))
                    except Exception:
                        out.append((a["ts"], "build_team", args))
                elif a["tool"] == "send_message":
                    try:
                        j = json.loads(args)
                        to, content = j.get("to", ""), j.get("content", "")
                    except Exception:
                        to, content = "", args
                    if str(to).strip() in ("*", "all", "broadcast", "@all"):
                        out.append((a["ts"], "broadcast", content))
    return sorted(out)

def score_text(m, text):
    low = text.lower()
    named, zones, pairs = [], set(), 0
    for z in ("zoneA", "zoneB"):
        for q in m[z].get("paths", []):
            if q.lower() in low:
                named.append(q)
                zones.add(z)
        for member in m[z].get("members", []):
            i = low.find(member.lower())
            while i >= 0:
                window = low[max(0, i - 160):i + 160]
                if any(q.lower() in window for q in m[z].get("paths", [])):
                    pairs += 1
                    break
                i = low.find(member.lower(), i + 1)
    return named, zones, pairs

def first_probe(run, m):
    best = None
    for mem in run["members"]:
        z = zone_of(m, mem["member"])
        if z is None or mem["member"] == "team_leader":
            continue
        other = "zoneB" if z == "zoneA" else "zoneA"
        for t in mem["turns"]:
            for a in t["actions"]:
                pz = path_zone(m, a["path"] or "")
                if pz == other and (best is None or a["ts"] < best[0]):
                    best = (a["ts"], mem["member"], (a["path"] or "")[:90], a["blocked"])
    return best

def cross_zone_attempts(run, m):
    out = []
    for mem in run["members"]:
        z = zone_of(m, mem["member"])
        if z is None:
            continue
        other = "zoneB" if z == "zoneA" else "zoneA"
        opaths = [q for q in m[other].get("paths", []) if q]
        if not opaths:
            continue
        for t in mem["turns"]:
            for a in t["actions"]:
                kind = None
                if a["tool"] in ("read_file", "write_file", "edit_file", "list_files",
                                 "glob", "grep"):

                    if path_zone(m, a["path"] or "") == other:
                        kind = "file-tool"
                elif a["tool"] == "bash":
                    cmd = a["args_text"] or ""
                    if any(re.search(r"(?:^|[/\s'\"])%s(?:[\s'\"/:]|$)" % re.escape(q), cmd)
                           for q in opaths):
                        kind = "shell"
                elif a["tool"] == "send_message":
                    txt = a["args_text"] or ""
                    if any(re.search(r"(?:^|[/\s'\"])%s(?:[\s'\"/:]|$)" % re.escape(q), txt)
                           for q in opaths):
                        kind = "message-mention"
                if kind is None:
                    continue
                out.append(dict(member=mem["member"], role=rix.role_group(mem["member"]),
                                zone=z, tool=a["tool"], kind=kind, ts=a["ts"],
                                blocked=int(bool(a["blocked"])),
                                target=(a["path"] or a["args_text"] or "")[:80]))
    return sorted(out, key=lambda x: x["ts"])

def audit(rec, denials_by_run):
    m = split_map(rec["task"])
    if m is None:
        return None
    run = teamtrace.load_run(rec["archive_path"])
    t0 = min((t["start_ts"] for mem in run["members"] for t in mem["turns"]), default=0)
    discl = leader_disclosures(run)
    t_disc = None
    best_named, best_zones, best_pairs, best_kind = [], set(), 0, ""
    cum_zones, cum_named = set(), set()
    for ts, kind, text in discl:
        named, zones, pairs = score_text(m, text)
        cum_zones |= zones
        cum_named |= set(named)
        if len(zones) > len(best_zones) or (zones == best_zones and pairs > best_pairs):
            best_named, best_zones, best_pairs, best_kind = named, zones, pairs, kind
        need_now = {z for z in ("zoneA", "zoneB") if m[z].get("paths")}
        if t_disc is None and need_now <= cum_zones:
            t_disc = ts
    probe = first_probe(run, m)
    t_probe = probe[0] if probe else None

    probe_turns = ""
    if t_disc is not None and t_probe is not None and probe:
        mem = next((x for x in run["members"] if x["member"] == probe[1]), None)
        if mem:
            probe_turns = sum(1 for t in mem["turns"]
                              if t_disc <= t["start_ts"] <= t_probe)

    need = {z for z in ("zoneA", "zoneB") if m[z].get("paths")}
    if need <= cum_zones and t_disc is not None:
        cls = ("disclosed-pre-probe" if (t_probe is None or t_disc <= t_probe)
               else "disclosed-late")
    elif cum_zones:
        cls = "partial"
    else:
        cls = "undisclosed"
    d = denials_by_run.get(rec["run_id"], {})
    return dict(
        run_id=rec["run_id"], task=rec["task"], arm=rec["arm"],
        disclosure_class=cls, zones_named=len(cum_zones), zones_with_paths=len(need),
        paths_named=len(cum_named),
        member_path_pairings=best_pairs, best_channel=best_kind,
        t_disclosure_rel=round(t_disc - t0, 1) if t_disc else "",
        t_first_probe_rel=round(t_probe - t0, 1) if t_probe else "",
        probe_member=probe[1] if probe else "", probe_blocked=int(probe[3]) if probe else "",
        probe_turns_after_disc=probe_turns,
        treatment_denials=d.get("treatment", 0), all_denials=d.get("all", 0),
        outcome=rec["framework_outcome"], score=rec["regrade_score"])

def denial_counts():
    out = defaultdict(lambda: {"treatment": 0, "all": 0})
    path = os.path.join(OUT, "violations.csv")
    if os.path.isfile(path):
        import csv
        with io.open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out[r["run_id"]]["all"] += 1
                if r["denial_class"] == "treatment":
                    out[r["run_id"]]["treatment"] += 1
    return out

def load_s4():
    return [r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
            if r["scenario"] == "S4"]

# build the output tables from the raw streams
def build():
    dc = denial_counts()
    rows = [x for x in (audit(r, dc) for r in load_s4()) if x]
    cols = list(rows[0].keys())
    p = os.path.join(OUT, "s4_disclosure.tsv")
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r[c]) for c in cols) + "\n")
    print("wrote %s (%d runs)\n" % (p, len(rows)))

    print("%-34s %-4s %-20s %6s %6s %8s %9s %7s" % (
        "run", "arm", "class", "zones", "pairs", "t_discl", "t_probe", "treat"))
    for r in sorted(rows, key=lambda x: (x["disclosure_class"], x["task"], x["arm"])):
        print("%-34s %-4s %-20s %6d %6d %8s %9s %7d" % (
            r["run_id"][:34], r["arm"], r["disclosure_class"], r["zones_named"],
            r["member_path_pairings"], r["t_disclosure_rel"], r["t_first_probe_rel"],
            r["treatment_denials"]))

    print("\nsplit and treatment denials by class:")
    by = defaultdict(list)
    for r in rows:
        by[r["disclosure_class"]].append(r)
    for cls, rs in sorted(by.items()):
        td = [r["treatment_denials"] for r in rs]
        print("  %-20s n=%2d  treatment denials: mean %5.1f  range %d-%d"
              % (cls, len(rs), sum(td) / len(td), min(td), max(td)))
    probed = [r for r in rows if r["t_first_probe_rel"] != ""]
    print("\nruns where a member touched the other zone at all: %d/%d"
          % (len(probed), len(rows)))
    return rows

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    dc = denial_counts()
    rows = {r["run_id"]: r for r in (audit(r, dc) for r in load_s4()) if r}
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-56s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1

    p5a2 = rows.get("p5_s4_arm2-20260809-231931")
    check("p5 arm-2 discloses the zone map pre-probe (the run the pass flagged)",
          p5a2 is not None and p5a2["disclosure_class"] == "disclosed-pre-probe",
          "" if p5a2 is None else "%s, zones=%d/%d, pairings=%d, t=%s vs probe %s"
          % (p5a2["disclosure_class"], p5a2["zones_named"], p5a2["zones_with_paths"],
             p5a2["member_path_pairings"], p5a2["t_disclosure_rel"],
             p5a2["t_first_probe_rel"]))
    check("every S4 run has a split map and was audited", len(rows) == 24,
          "audited=%d" % len(rows))

    undis = [r for r in rows.values() if r["disclosure_class"] == "undisclosed"]
    check("NO run is undisclosed (so no discovery contrast exists)", not undis,
          "undisclosed=%s" % ([r["run_id"] for r in undis] or "none"))
    late = [r for r in rows.values() if r["disclosure_class"] == "disclosed-late"]
    check("disclosure always precedes the first cross-zone touch", not late,
          "late=%s" % ([r["run_id"] for r in late] or "none"))

    pt = [r for r in rows.values()
          if r["t_disclosure_rel"] != "" and r["t_first_probe_rel"] != ""]
    okpt = all(r["probe_turns_after_disc"] != "" and r["probe_turns_after_disc"] >= 0
               for r in pt)
    check("probe_turns_after_disc present and >=0 wherever disclosure+probe exist",
          okpt and pt, "n=%d, max=%s" % (len(pt), max((r["probe_turns_after_disc"]
                                                       for r in pt), default="")))

    lh5 = rows.get("lh5_s4-20260809-081250")
    check("the p5-vs-lh5 denial gap is NOT explained by disclosure class",
          p5a2 is not None and lh5 is not None
          and p5a2["disclosure_class"] == lh5["disclosure_class"],
          "p5-arm2 %s treat=%d | lh5-arm1 %s treat=%d"
          % (p5a2["disclosure_class"], p5a2["treatment_denials"],
             lh5["disclosure_class"], lh5["treatment_denials"]))
    return 1 if bad else 0

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
