# S5 funnel: for each ablated spec requirement, whether the team ever named it and
# what verdict disposed of it.

import csv, io, json, os, re, sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import teamtrace
import run_index as rix
import s5_splits as S5

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")

PASS_VERDICT = re.compile(r'"(?:overall_)?verdict"\s*:\s*"(\w+)"', re.I)


def units_by_run():
    path = os.path.join(OUT, "s5_units.tsv")
    if not os.path.isfile(path):
        sys.exit("out/s5_units.tsv missing — run `python s5_splits.py` first")
    out = defaultdict(list)
    with io.open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            if r["side"] != "ablated":
                continue
            if r["not_hidden"] == "1":
                continue
            if not r["canaries_silent"].strip():
                continue
            out[r["run_id"]].append(r)
    return out


def attestation(archive):
    for rel in ("run_current/attestation.json", "run_current/output/attestation.json"):
        p = os.path.join(archive, *rel.split("/"))
        if os.path.isfile(p):
            txt = io.open(p, encoding="utf-8", errors="replace").read()
            m = PASS_VERDICT.search(txt)
            return txt, (m.group(1).lower() if m else "")
    return "", ""


def messages(run):
    out = []
    for mem in run["members"]:
        role = rix.role_group(mem["member"])
        for t in mem["turns"]:
            for a in t["actions"]:
                if a["tool"] != "send_message" or not a["args_text"]:
                    continue
                try:
                    j = json.loads(a["args_text"])
                    txt = str(j.get("content", ""))
                except Exception:
                    txt = a["args_text"]
                out.append((a["ts"], mem["member"], role, txt))
    return sorted(out)


# Trace one run's ablated units through named -> disposed.
def score_run(rec, units):
    run = teamtrace.load_run(rec["archive_path"])
    t0 = min((t["start_ts"] for m in run["members"] for t in m["turns"]), default=0)
    msgs = messages(run)
    att_text, verdict = attestation(rec["archive_path"])
    ws = S5.workspace_text(rec["archive_path"])

    rows = []
    for u in units:
        cans = [c.strip() for c in u["canaries_silent"].split(";") if c.strip()]
        first = None
        by_verifier = None
        for ts, member, role, txt in msgs:
            if any(S5.canary_hit(c, txt) for c in cans):
                if first is None:
                    first = (ts, member, role)
                if role == "verifier" and by_verifier is None:
                    by_verifier = (ts, member)
        in_att = any(S5.canary_hit(c, att_text) for c in cans)
        satisfied = any(S5.canary_hit(c, ws) for c in cans)
        detected_by = ("verifier" if by_verifier else
                       "other" if first else
                       "attestation" if in_att else "none")


        if detected_by == "none":
            disp = "never-named"
        elif not verdict:
            disp = "named-no-attest"
        elif verdict in ("pass", "passed", "success"):
            disp = "downgraded-in-pass"
        else:
            disp = "hard-fail-emitted"
        rows.append(dict(
            run_id=rec["run_id"], task=rec["task"], arm=rec["arm"], dose=rec["dose"],
            stratum="recoverable" if u["artifact_recoverable"] == "1" else "silent",
            section=u["section"][:60], unit=u["text"][:120],
            canaries="; ".join(cans)[:80],
            detected_by=detected_by,
            first_namer=first[1] if first else "",
            t_first_mention_rel=round(first[0] - t0, 1) if first else "",
            named_by_verifier=int(bool(by_verifier)),
            in_attestation=int(in_att), satisfied_in_workspace=int(satisfied),
            attestation_verdict=verdict or "(none)", disposition=disp))
    return rows


def load_s5():
    return [r for r in rix.read_tsv(os.path.join(OUT, "run_index.tsv"))
            if r["scenario"] == "S5"]


def build():
    ubr = units_by_run()
    urows = []
    for rec in load_s5():
        us = ubr.get(rec["run_id"], [])
        if us:
            urows += score_run(rec, us)
    _write(os.path.join(OUT, "s5_funnel_units.tsv"), urows)

    runs = defaultdict(lambda: Counter())
    meta = {}
    for r in urows:
        k = r["run_id"]
        meta[k] = (r["task"], r["arm"], r["dose"], r["attestation_verdict"])
        runs[k]["units"] += 1
        runs[k]["det_" + r["detected_by"]] += 1
        runs[k]["disp_" + r["disposition"]] += 1
    rrows = []
    for k, c in sorted(runs.items()):
        task, arm, dose, verdict = meta[k]
        rrows.append(dict(run_id=k, task=task, arm=arm, dose=dose,
                          attestation_verdict=verdict, units=c["units"],
                          **{n: c[n] for n in sorted(c) if n != "units"}))
    _write(os.path.join(OUT, "s5_funnel_runs.tsv"), rrows)
    print("wrote out/s5_funnel_units.tsv (%d units over %d runs)\n"
          "wrote out/s5_funnel_runs.tsv" % (len(urows), len(rrows)))
    report(urows)
    return urows


def _write(path, rows):
    if not rows:
        return
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write("\t".join(cols) + "\n")
        for r in rows:
            f.write("\t".join(str(r.get(c, "")) for c in cols) + "\n")


def report(all_rows):
    print("\nSTRATA (ablated sub-units carrying a matchable literal)")
    for st in ("silent", "recoverable"):
        rs = [r for r in all_rows if r["stratum"] == st]
        det = Counter(r["detected_by"] for r in rs)
        print("  %-12s n=%2d  named-by-verifier %2d  named-by-anyone %2d  never %2d"
              % (st, len(rs), sum(1 for r in rs if r["named_by_verifier"]),
                 len(rs) - det["none"], det["none"]))
    print("\n--- strict stratum (silent units) ---")
    _report_stratum([r for r in all_rows if r["stratum"] == "silent"])
    print("\n--- recoverable stratum ---")
    _report_stratum([r for r in all_rows if r["stratum"] == "recoverable"])


def _report_stratum(urows):
    n = len(urows)
    if not n:
        print("  (empty)")
        return
    det = Counter(r["detected_by"] for r in urows)
    disp = Counter(r["disposition"] for r in urows)
    print("\nDETECTION (n=%d)" % n)
    for k in ("verifier", "other", "attestation", "none"):
        print("  %-12s %3d  %4.0f%%" % (k, det[k], 100.0 * det[k] / n if n else 0))
    print("\nDISPOSITION")
    for k, v in disp.most_common():
        print("  %-20s %3d  %4.0f%%" % (k, v, 100.0 * v / n))
    sfa = [r for r in urows if r["disposition"] == "never-named"]
    print("\nsilent-false-accept candidates (never named, not satisfied): %d" % len(sfa))
    for r in sfa[:12]:
        print("   %-34s %s" % (r["run_id"][:34], r["unit"][:70]))
    print("\nby arm:")
    for arm in ("1", "2"):
        rs = [r for r in urows if r["arm"] == arm]
        if not rs:
            continue
        v = sum(1 for r in rs if r["named_by_verifier"])
        d = sum(1 for r in rs if r["disposition"] == "downgraded-in-pass")
        h = sum(1 for r in rs if r["disposition"] == "hard-fail-emitted")
        print("  arm-%s n=%2d  named-by-verifier %2d (%.0f%%)  downgraded-in-pass %2d  "
              "hard-fail %2d" % (arm, len(rs), v, 100.0 * v / len(rs), d, h))
    print("\nper run:")
    by_run = defaultdict(list)
    for r in urows:
        by_run[r["run_id"]].append(r)
    print("    %-38s %5s %6s %8s  %s" % ("run", "units", "verif", "verdict",
                                        "dispositions"))
    for k in sorted(by_run):
        rs = by_run[k]
        c = Counter(r["disposition"] for r in rs)
        print("    %-38s %5d %6d %8s  %s" % (
            k[:38], len(rs), sum(1 for r in rs if r["named_by_verifier"]),
            rs[0]["attestation_verdict"],
            ", ".join("%s=%d" % (a, b) for a, b in c.most_common())))


# Oracle gate.
def verify():
    ubr = units_by_run()
    urows = []
    for rec in load_s5():
        us = ubr.get(rec["run_id"], [])
        if us:
            urows += score_run(rec, us)
    by_run = defaultdict(list)
    for r in urows:
        by_run[r["run_id"]].append(r)
    bad = 0

    def check(label, ok, detail):
        nonlocal bad
        print("  %-5s %-60s %s" % ("OK" if ok else "FLAG", label, detail))
        if not ok:
            bad += 1


    rs = by_run.get("spec5_s5partial-20260809-154345", [])
    check("spec5 arm-1: every silent unit is named by a verifier",
          bool(rs) and all(r["named_by_verifier"] for r in rs),
          "%d/%d named by verifier" % (sum(1 for r in rs if r["named_by_verifier"]), len(rs)))

    rs = by_run.get("spec5_s5partial_arm2-20260809-185711", [])
    check("spec5 arm-2: named by a verifier AND a fail verdict is emitted",
          bool(rs) and any(r["named_by_verifier"] for r in rs)
          and all(r["disposition"] == "hard-fail-emitted" for r in rs),
          "verdict=%s dispositions=%s" % (rs[0]["attestation_verdict"] if rs else "?",
                                          sorted({r["disposition"] for r in rs})))

    silent = [r for r in urows if r["stratum"] == "silent"]
    named = sum(1 for r in silent if r["detected_by"] != "none")
    check("detection dominates on the silent stratum",
          silent and named / len(silent) >= 0.5,
          "%d/%d named (%.0f%%)" % (named, len(silent), 100.0 * named / len(silent)))

    named_rows = [r for r in silent if r["detected_by"] != "none"]
    lost = sum(1 for r in named_rows if r["disposition"] == "downgraded-in-pass")
    check("most named silent units are downgraded inside a PASS",
          named_rows and lost / len(named_rows) >= 0.5,
          "%d/%d downgraded" % (lost, len(named_rows)))

    rec_rows = [r for r in urows if r["stratum"] == "recoverable"]
    rn = sum(1 for r in rec_rows if r["detected_by"] != "none") / len(rec_rows)
    sn = named / len(silent)
    check("naming rate is higher for artifact-recoverable units than silent ones",
          rn > sn, "recoverable %.0f%% vs silent %.0f%%" % (100 * rn, 100 * sn))
    check("units come from most S5 runs", len(by_run) >= 15,
          "runs with measurable units=%d/24" % len(by_run))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    build()
