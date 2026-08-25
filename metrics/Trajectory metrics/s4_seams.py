# S4 seam analysis: reconstructs each cross-zone edge (probe, ask, answer, cross,
# integrate) from messages and file activity, matching seam symbols between code
# and messages.

import io, json, os, re, sys, glob, keyword
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = r"C:\Users\cz776\Downloads\Runs\S4_enf_pro"
MAPS = os.path.join(HERE, "s4maps")
PRISTINE = os.path.join(HERE, "s4pristine")
OUT = os.path.join(HERE, "out")

PIN = {"node1": "planner1", "node2": "planner2", "node3": "planner3",
       "node4": "executor1", "node5": "executor2", "node6": "executor3",
       "node7": "verifier1", "node8": "verifier2", "node9": "fullstack1"}

ORACLE_DIRECT = {"spec6", "test9", "p5", "cr4", "cross3", "ir2"}
ORACLE_RELAY_ONLY = {"spec5", "crypto1", "pipe3_stream_processing", "multi4", "api1"}

STOP = set(keyword.kwlist) | set(dir(__builtins__)) | {
    "self", "init", "main", "args", "kwargs", "data", "value", "values", "result",
    "results", "test", "tests", "name", "names", "type", "types", "key", "keys",
    "item", "items", "path", "paths", "file", "files", "error", "errors", "none",
    "true", "false", "str", "int", "float", "bool", "dict", "list", "tuple", "get",
    "set", "run", "config", "text", "json", "load", "loads", "dump", "dumps",
    "open", "read", "write", "close", "append", "update", "items", "format",
    "message", "messages", "content", "status", "code", "codes", "field", "fields",
    "input", "output", "start", "stop", "end", "count", "index", "size", "total",
    "process", "handle", "check", "state", "response", "request", "return",
    "default", "options", "params", "util", "utils", "helper", "base", "core",
    "record", "records", "entry", "entries", "line", "lines", "raw", "info",
    "debug", "warning", "level", "time", "timestamp", "version", "email", "user",
    "assert", "equal", "instance", "print", "range", "len", "min", "max", "sum",
}

IDENT_PATTERNS = [
    re.compile(r"^\s*def\s+([A-Za-z_]\w{2,})", re.M),
    re.compile(r"^\s*class\s+([A-Za-z_]\w{2,})", re.M),
    re.compile(r"^\s*([A-Z][A-Z0-9_]{2,})\s*=", re.M),
    re.compile(r"[\"']([A-Za-z_]\w{2,})[\"']\s*:"),
    re.compile(r"self\.([A-Za-z_]\w{2,})\s*="),
]
NOTE_TOKEN = re.compile(r"[A-Za-z_]\w{2,}|\b\d{3}\b")


def read(p):
    try:
        return io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return ""


def files_under(root, rel):
    full = os.path.join(root, rel.replace("/", os.sep))
    if os.path.isfile(full):
        yield rel, read(full)
        return
    for dirp, _dirs, fns in os.walk(full):
        for fn in fns:
            if fn.endswith((".py", ".json", ".md", ".txt", ".yaml", ".yml", ".sh", ".cfg", ".ini")):
                fp = os.path.join(dirp, fn)
                yield os.path.relpath(fp, root).replace(os.sep, "/"), read(fp)


def idents(text):
    out = set()
    for pat in IDENT_PATTERNS:
        out.update(pat.findall(text))
    return {t for t in out if t.lower() not in STOP and not t.startswith("__")}


def word_in(tok, text):
    return re.search(r"(?<![\w])" + re.escape(tok) + r"(?![\w])", text) is not None


# Per-task model of zones, files and identifiers.
class TaskModel:

    def __init__(self, task):
        self.task = task
        self.map = json.load(io.open(os.path.join(MAPS, task + ".split.json"), encoding="utf-8"))
        self.zone_members = {"A": set(self.map["zoneA"]["members"]),
                             "B": set(self.map["zoneB"]["members"])}
        self.pristine_ws = os.path.join(PRISTINE, task, "workspace")
        self.spec = read(os.path.join(PRISTINE, task, "spec.md"))
        self.brief = read(os.path.join(PRISTINE, task, "brief.md"))

        self.zone_idents = {"A": {}, "B": {}}
        self.zone_text = {"A": "", "B": ""}
        for z, key in (("A", "zoneA"), ("B", "zoneB")):
            for p in self.map[key]["paths"]:
                for _rel, text in files_under(self.pristine_ws, p):
                    self.zone_text[z] += "\n" + text
                    for t in idents(text):
                        self.zone_idents[z][t] = self.zone_idents[z].get(t, 0) + 1
        both = set(self.zone_idents["A"]) & set(self.zone_idents["B"])
        self.edges = []
        for i, e in enumerate(self.map.get("cross_edges", [])):
            self.edges.append(self._build_edge(i, e, both))

    def zone_of_path(self, rel):
        for z, key in (("A", "zoneA"), ("B", "zoneB")):
            for p in self.map[key]["paths"]:
                if rel == p or rel.startswith(p.rstrip("/") + "/"):
                    return z
        return "shared"

    def member_zone(self, name):
        for z, mem in self.zone_members.items():
            if name in mem:
                return z
        return "-"

    def _provenance(self, tok):
        if word_in(tok, self.brief):
            return "brief"
        if word_in(tok, self.spec):
            return "spec"
        return "pristine"

    def _build_edge(self, idx, e, both_zones):
        symbols = {}
        for endpoint in ("src", "dst"):
            rel = e[endpoint]
            home = self.zone_of_path(rel)
            if home not in ("A", "B"):
                continue
            other = "B" if home == "A" else "A"
            for frel, text in files_under(self.pristine_ws, rel):
                for t in idents(text):
                    if t in both_zones:
                        continue
                    if word_in(t, self.zone_text[other]):
                        continue
                    symbols.setdefault(t, {"home": home, "prov": self._provenance(t),
                                           "origin": frel})
        for t in NOTE_TOKEN.findall(e.get("note", "")):
            if t.lower() in STOP or t in symbols:
                continue
            if not re.search(r"[0-9_]|[a-z][A-Z]", t) and len(t) < 6:
                continue


            home = self.zone_of_path(e["dst"])
            if home not in ("A", "B"):
                home = self.zone_of_path(e["src"])
            if word_in(t, self.zone_text["B" if home == "A" else "A"]):
                continue
            hit_pris = any(word_in(t, txt) for _r, txt in files_under(self.pristine_ws, e["dst"]))
            if hit_pris or word_in(t, self.spec) or word_in(t, self.brief):
                symbols[t] = {"home": home,
                              "prov": self._provenance(t) if not hit_pris or
                                      word_in(t, self.brief) or word_in(t, self.spec)
                                      else "pristine",
                              "origin": "note"}

        lc = str(e.get("linked_check", ""))
        nums = re.findall(r"(\d+)\s*-\s*(\d+)", lc)
        w = 0
        for a, b in nums:
            w += max(0, int(b) - int(a) + 1)
        if not w:
            w = max(1, len(re.findall(r"\d+", lc)))
        return {"idx": idx, "src": e["src"], "dst": e["dst"], "kind": e.get("kind"),
                "note": e.get("note", ""), "linked_check": lc, "weight": w,
                "symbols": symbols}

    def emergent_symbols(self, final_ws):
        pris_all = set(self.zone_idents["A"]) | set(self.zone_idents["B"])
        out = {}
        for e in self.edges:
            for endpoint in ("src", "dst"):
                home = self.zone_of_path(e[endpoint])
                for frel, text in files_under(final_ws, e[endpoint]):
                    for t in idents(text):
                        if t in pris_all or t in out:
                            continue
                        if word_in(t, self.zone_text["A"]) or word_in(t, self.zone_text["B"]):
                            continue
                        if word_in(t, self.spec) or word_in(t, self.brief):
                            continue
                        out[t] = {"home": home, "prov": "emergent", "origin": frel,
                                  "edge": e["idx"]}
        return out


def channel_of(sender, tm):
    z = tm.member_zone(sender)
    if z in "AB":
        return "direct"
    if sender.startswith("planner"):
        return "planner_relay"
    if sender == "team_leader":
        return "leader_relay"
    if sender.startswith("verifier"):
        return "verifier_relay"
    return "other"


# All seam events for one run.
def analyze(task, archive):
    tm = TaskModel(task)
    run = teamtrace.load_run(archive)
    final_ws = os.path.join(archive, "run_current", "workspace")
    emergent = tm.emergent_symbols(final_ws)


    msgs, writes, denials = [], [], []
    for m in run["members"]:
        name = m["member"] if not m["member"].startswith("cpool") else PIN.get(m["node"], m["member"])
        for tn in m["turns"]:
            for a in tn["actions"]:
                p = a.get("path") or ""
                if a["tool"] == "send_message":
                    try:
                        j = json.loads(a.get("args_text") or "{}")
                    except Exception:
                        continue
                    msgs.append({"ts": a["ts"], "from": name,
                                 "to": str(j.get("to", "")),
                                 "content": str(j.get("content", ""))})
                elif a["tool"] in ("write_file", "edit_file") and "workspace/" in p:
                    ok = not a.get("blocked") and "success=True" in (
                        a.get("result_excerpt") or a.get("result_summary") or "")
                    rel = p.split("workspace/")[-1]
                    (writes if ok else denials).append(
                        {"ts": a["ts"], "who": name, "rel": rel, "ok": ok})
                elif a.get("blocked"):
                    rel = p.split("workspace/")[-1] if "workspace/" in p else p
                    denials.append({"ts": a["ts"], "who": name, "rel": rel,
                                    "tool": a["tool"], "ok": False})
    msgs.sort(key=lambda x: x["ts"])


    edges_out = []
    for e in tm.edges:
        syms = dict(e["symbols"])
        for t, meta in emergent.items():
            if meta["edge"] == e["idx"]:
                syms[t] = meta
        crossings, probes = [], []

        for d in denials:
            for endpoint in ("src", "dst"):
                ep = e[endpoint]
                if d["rel"] == ep or d["rel"].startswith(ep.rstrip("/") + "/"):
                    hz = tm.zone_of_path(ep)
                    if tm.member_zone(d["who"]) in "AB" and tm.member_zone(d["who"]) != hz:
                        probes.append(d)
        for msg in msgs:
            recips = set()
            to = msg["to"]
            if to == "*":
                recips = tm.zone_members["A"] | tm.zone_members["B"]
            elif to:
                recips = {to}
            rzones = {tm.member_zone(r) for r in recips} & {"A", "B"}
            szone = tm.member_zone(msg["from"])
            for tok, meta in syms.items():
                needer = "B" if meta["home"] == "A" else "A"


                if szone == needer:
                    mode = "possession"
                elif needer in rzones:
                    mode = "delivered"
                else:
                    continue
                if not word_in(tok, msg["content"]):
                    continue
                if mode == "delivered":
                    ch = "direct" if szone == meta["home"] else channel_of(msg["from"], tm)
                else:
                    ch = "intra_needer"
                crossings.append({
                    "ts": msg["ts"], "symbol": tok, "prov": meta["prov"],
                    "from": msg["from"], "to": to, "channel": ch, "mode": mode,
                    "snippet": _around(msg["content"], tok)})

        src_writes = [w["ts"] for w in writes
                      if w["rel"] == e["src"] or w["rel"].startswith(e["src"].rstrip("/") + "/")]
        first_impl = min(src_writes) if src_writes else None
        delivered = [c for c in crossings if c["mode"] == "delivered"]
        strong = [c for c in delivered if c["prov"] in ("pristine", "emergent")]
        first_cross = min((c["ts"] for c in delivered), default=None)
        timing = None
        if first_cross is not None and first_impl is not None:
            timing = "proactive" if first_cross <= first_impl else "reactive"
        edges_out.append({
            "edge": f'{e["src"]} -> {e["dst"]}', "kind": e["kind"], "weight": e["weight"],
            "linked_check": e["linked_check"], "n_symbols": len(syms),
            "n_strong_syms": sum(1 for m in syms.values()
                                 if m["prov"] in ("pristine", "emergent")),
            "coord_any": bool(delivered), "coord_strong": bool(strong),
            "channels": sorted({c["channel"] for c in delivered}),
            "best_prov": min((c["prov"] for c in delivered),
                             key=lambda p: ["emergent", "pristine", "spec", "brief"].index(p),
                             default=None),
            "timing": timing, "probes": len(probes),
            "crossings": crossings})
    wsum = sum(e["weight"] for e in edges_out) or 1
    return {
        "task": task, "archive": os.path.basename(archive),
        "n_msgs": len(msgs),
        "congruence_any": round(sum(e["weight"] for e in edges_out if e["coord_any"]) / wsum, 3),
        "congruence_strong": round(sum(e["weight"] for e in edges_out if e["coord_strong"]) / wsum, 3),
        "direct_crossings": sum(1 for e in edges_out for c in e["crossings"]
                                if c["channel"] == "direct" and c["mode"] == "delivered"),
        "relay_crossings": sum(1 for e in edges_out for c in e["crossings"]
                               if c["channel"].endswith("_relay") and c["mode"] == "delivered"),
        "edges": edges_out,
        "_tm": tm, "_writes": writes, "_final_ws": os.path.join(archive, "run_current", "workspace"),
    }


def _around(text, tok, ctx=45):
    m = re.search(r"(?<![\w])" + re.escape(tok) + r"(?![\w])", text)
    if not m:
        return ""
    s, e = max(0, m.start() - ctx), min(len(text), m.end() + ctx)
    return text[s:e].replace("\n", " ")


def provenance_accounting(res):
    tm = res["_tm"]
    viol = []
    for e in res["edges"]:
        crossed = {c["symbol"] for c in e["crossings"] if c["mode"] == "delivered"}
        uttered = {c["symbol"] for c in e["crossings"]}

        for c_sym, meta in _edge_symbols(tm, e):
            if meta["prov"] not in ("pristine", "emergent"):
                continue
            needer = "B" if meta["home"] == "A" else "A"
            for p in tm.map["zone" + needer]["paths"]:
                for frel, text in files_under(res["_final_ws"], p):
                    if word_in(c_sym, text):
                        if c_sym not in crossed and c_sym not in uttered:
                            viol.append({"task": res["task"], "symbol": c_sym,
                                         "edge": e["edge"], "in_file": frel,
                                         "prov": meta["prov"]})
                        break
    return viol


def _edge_symbols(tm, edge_out):
    for e in tm.edges:
        if f'{e["src"]} -> {e["dst"]}' == edge_out["edge"]:
            return list(e["symbols"].items())
    return []


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "table"
    rows, allres = [], []
    tsv = io.open(os.path.join(RUNS, "batch_results.tsv"), encoding="utf-8").read().splitlines()
    picked = {}
    for line in tsv[1:]:
        parts = line.split("\t")
        if len(parts) < 6:
            continue
        task, archive = parts[1], parts[5]
        arch = os.path.join(RUNS, os.path.basename(archive.rstrip("/")))
        if os.path.isdir(arch):
            picked[task] = arch
    for task, arch in picked.items():
        allres.append(analyze(task, arch))

    print(f'{"task":<28}{"C_any":>6}{"C_strong":>9}{"direct":>7}{"relay":>6}  edge detail')
    for r in allres:
        det = "; ".join(
            f'e{i}:{"+" if e["coord_any"] else "-"}{"S" if e["coord_strong"] else ""}'
            f'({",".join(c[0] for c in [(ch[0], ) for ch in e["channels"]]) or "none"}'
            f'|{e["best_prov"] or "-"}|{e["timing"] or "-"})'
            for i, e in enumerate(r["edges"]))
        print(f'{r["task"]:<28}{r["congruence_any"]:>6}{r["congruence_strong"]:>9}'
              f'{r["direct_crossings"]:>7}{r["relay_crossings"]:>6}  {det}')


    try:
        recs = {r["task"]: r for r in json.load(
            io.open(os.path.join(RUNS, "scenario1_regrade_records.json"), encoding="utf-8"))}
    except OSError:
        recs = {}
    print("\n=== congruence x outcome (regrade, never attestation) ===")
    print(f'{"task":<28}{"C_any":>6}{"C_strong":>9}{"strong_syms":>12}{"score":>7}{"pass":>6}')
    for r in allres:
        rec = recs.get(r["task"], {})
        ssyms = sum(e["n_strong_syms"] for e in r["edges"])
        print(f'{r["task"]:<28}{r["congruence_any"]:>6}{r["congruence_strong"]:>9}'
              f'{ssyms:>12}{rec.get("partial_score", "?"):>7}{str(rec.get("pass", "?")):>6}')

    if mode in ("verify", "table"):
        print("\n=== VERIFICATION vs s4_behavior oracle ===")
        ok = True
        for r in allres:
            t = r["task"]
            if r["direct_crossings"] > 0 and t not in ORACLE_DIRECT:
                print(f"  FAIL: {t} shows direct crossings but oracle says zero-seam")
                ok = False
            if t in ORACLE_RELAY_ONLY:
                flag = "OK " if r["direct_crossings"] == 0 else "FAIL"
                relay = "OK " if r["relay_crossings"] > 0 else "WEAK(no relay hit)"
                print(f"  {flag} {t}: zero-seam confirmed; relay: {relay}")
                if r["direct_crossings"] != 0:
                    ok = False
        detected = {r["task"] for r in allres if r["direct_crossings"] > 0}
        print(f"  direct-seam runs detected: {sorted(detected)}")
        print(f"  oracle direct-seam runs  : {sorted(ORACLE_DIRECT)}")
        print(f"  subset-of-oracle: {'YES' if detected <= ORACLE_DIRECT else 'NO'}")
        print("\n--- provenance accounting (watertight check; expect ~none) ---")
        nv = 0
        for r in allres:
            for v in provenance_accounting(r):
                nv += 1
                print(f'  VIOLATION {v["task"]}: {v["prov"]} symbol {v["symbol"]!r} '
                      f'in needer file {v["in_file"]} with no observed crossing')
        print(f"  violations: {nv}")
        print("\n--- sample crossing snippets (eyeball) ---")
        shown = 0
        for r in allres:
            for e in r["edges"]:
                for c in e["crossings"]:
                    if c["mode"] == "delivered" and shown < 12:
                        print(f'  [{r["task"]}] {c["channel"]:<14} {c["from"]:<11}->{c["to"]:<11}'
                              f' {c["prov"]:<8} {c["symbol"]:<24} "...{c["snippet"]}..."')
                        shown += 1
        print(f"\noverall verification: {'PASS' if ok else 'FAIL'}")

    os.makedirs(OUT, exist_ok=True)
    slim = [{k: v for k, v in r.items() if not k.startswith("_")} for r in allres]
    with io.open(os.path.join(OUT, "s4_congruence.json"), "w", encoding="utf-8") as f:
        json.dump(slim, f, indent=1, ensure_ascii=False)
    print(f"\nwrote {os.path.join(OUT, 's4_congruence.json')}")


if __name__ == "__main__":
    main()
