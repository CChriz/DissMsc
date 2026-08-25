# Maps the annotation tag strings onto canonical tags and families, and
# writes the per-run tag join.
import os, re, sys
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ANN = os.path.join(os.path.dirname(HERE), "annotations")
OUT = os.path.join(HERE, "out")

FAMILIES = [
    ("GRD",  "Grader & environment artifacts (measurement, not team behavior)"),
    ("ORC",  "Oracle / graded-contract erasure"),
    ("DLV",  "Delivery integrity (artifact or fact exists, never reaches the graded place)"),
    ("VDET", "Verification: detection gap"),
    ("VDIS", "Verification: disposition failure (detected, then not acted on)"),
    ("INF",  "Information attrition & blind planning"),
    ("RTE",  "Blockage navigation & reroute (S3 treatment)"),
    ("LDR",  "Leader substitution & authority"),
    ("LIV",  "Liveness, concurrency & allocation"),
    ("VAL",  "Treatment-integrity / validity threats (not failure modes)"),
    ("MEC",  "Mechanisms, co-variates and positive behaviors (not failure modes)"),
]

ALIAS = {

    "attestation-schema-mismatch": "format-lottery",
    "attestation-schema-drift": "format-lottery",
    "attestation-contract-miss": "format-lottery",
    "attestation-contract-mismatch": "format-lottery",
    "grader-contract-artifact": "format-lottery",
    "grader-contract-case-miss": "format-lottery",
    "grader-schema-mismatch": "format-lottery",
    "schema-free-attestation": "format-lottery",
    "attest-verdict-casing": "format-lottery",

    "unwinnable-check": "grader-defect-ceiling",
    "unwinnable-ceiling": "grader-defect-ceiling",
    "grader-false-negative-cluster": "grader-defect-ceiling",

    "grader-env-missing-dep": "grader-env-artifact",
    "grader-env-false-negative": "grader-env-artifact",
    "regrade-env-artifact": "grader-env-artifact",

    "llm-stream-truncation-on-critical-path": "llm-stream-truncation",
    "verifier-threshold-stop": "threshold-satisficing",
    "satisficing-to-threshold": "satisficing-ceiling",
    "shadow-review-finding-never-sent": "shadow-review",
    "verifier-static-only": "verifier-no-execute",
}

FAMILY = {

    "format-lottery": "GRD",
    "grader-defect-ceiling": "GRD",
    "grader-env-artifact": "GRD",
    "grader-comment-grep-fn": "GRD",
    "grader-variant-mismatch": "GRD",
    "grader-config-case-bug": "GRD",
    "grader-capture-bug": "GRD",
    "grader-sentinel-literal-miss": "GRD",
    "spec-rule-vs-grader-mismatch": "GRD",

    "grader-contract-erased": "ORC",
    "oracle-rewrite": "ORC",
    "test-mutated-to-fit-implementation": "ORC",
    "self-inflicted-oracle": "ORC",
    "blind-rewrite-under-block": "ORC",
    "review-induced-regression": "ORC",
    "post-hoc-mutation": "ORC",
    "fixture-workaround-in-deliverable": "ORC",
    "spec-invention-from-plan": "ORC",
    "api-shape-drift": "ORC",

    "plan-never-delivered": "DLV",
    "answer-never-sent": "DLV",
    "seam-answer-lossy-reformulation": "DLV",
    "dual-relay-contract-drift": "DLV",
    "relay-monopoly": "DLV",
    "deliverable-misplacement": "DLV",
    "shadow-deliverable": "DLV",
    "attestation-path-split": "DLV",
    "spec-literal-path-trap": "DLV",
    "shadow-review": "DLV",
    "plan-stage-signal-dropped-by-leader": "DLV",
    "diagnosis-lost-to-stall": "DLV",
    "stale-attestation-survives-fix-round": "DLV",

    "verifier-rubber-stamp": "VDET",
    "verifier-no-execute": "VDET",
    "secondhand-test-evidence": "VDET",
    "verifier-tool-gap": "VDET",
    "no-exec-environment": "VDET",
    "mutant-guessing": "VDET",
    "fabricated-verification-claim": "VDET",
    "verify-before-execute": "VDET",
    "silent-false-accept": "VDET",

    "attest-despite-known-fail": "VDIS",
    "hidden-profile-overruled": "VDIS",
    "hidden-profile-downgraded": "VDIS",
    "authority-dismissal-of-true-defect": "VDIS",
    "detected-misjudged": "VDIS",
    "known-fail-rationalized": "VDIS",
    "known-residue-deferred": "VDIS",
    "threshold-satisficing": "VDIS",
    "verifier-praised-the-regression": "VDIS",
    "peer-challenge-launders-omission": "VDIS",
    "honest-disclosure-absent": "VDIS",
    "attested-wrong-artifact": "VDIS",
    "false-task-completion": "VDIS",
    "harness-bug-not-neutralized": "VDIS",

    "silent-spec-miss": "INF",
    "brief-compression-loss": "INF",
    "acl-info-loss": "INF",
    "interface-mismatch": "INF",
    "planner-fabricated-interface": "INF",
    "plan-injected-defect": "INF",
    "hallucinated-data-claim": "INF",
    "satisficing-ceiling": "INF",
    "leader-anchor-frame": "INF",
    "pick-n-menu-frame": "INF",
    "frame-amplification": "INF",
    "scaffolding-ignored": "INF",

    "identity-map-error": "RTE",
    "reroute-never-landed": "RTE",
    "reroute-not-migrated": "RTE",
    "reroute-to-blocked-member": "RTE",
    "reroute-misconfig": "RTE",
    "shadow-workspace-reroute": "RTE",
    "survivor-never-invoked": "RTE",
    "leader-state-garble": "RTE",
    "denial-misdiagnosis": "RTE",
    "unverified-denial-propagation": "RTE",
    "acl-circumvention-attempt": "RTE",
    "leader-acl-escalation": "RTE",
    "tamper-attempt-blocked": "RTE",
    "write-proxy-recovery": "RTE",

    "leader-did-it": "LDR",
    "authorship-laundering": "LDR",
    "leader-artifact-preemption": "LDR",
    "leader-relay-bypass": "LDR",
    "leader-induced-denial": "LDR",

    "scheduler-stall": "LIV",
    "standby-no-terminate": "LIV",
    "cap-exhaustion": "LIV",
    "budget-overrun-mid-attest": "LIV",
    "llm-stream-truncation": "LIV",
    "leader-crash": "LIV",
    "post-wake-context-amnesia": "LIV",
    "task-never-closed": "LIV",
    "verify-window-collapse": "LIV",
    "orphaned-claim-timeout": "LIV",
    "roster-inflation-standby": "LIV",
    "ghost-kickoff": "LIV",
    "claim-race": "LIV",
    "claim-race-hijack": "LIV",
    "claim-race-duplicate-work": "LIV",
    "claim-race-induced-stall": "LIV",
    "duplicate-plan-race": "LIV",
    "encroachment": "LIV",
    "plan-contains-implementation": "LIV",
    "concurrent-edit-test-race": "LIV",
    "attestation-write-race": "LIV",
    "attestation-overwrite": "LIV",
    "attestation-overwrite-race": "LIV",
    "dual-attestation-overwrite": "LIV",
    "attestation-merge-clobber": "LIV",
    "dual-verifier-lock-negotiation": "LIV",
    "attestation-write-guard-block": "LIV",

    "treatment-leak-via-workspace": "VAL",
    "survivor-relay-leak": "VAL",
    "spec-note-neutralizes-artifact-recovery": "VAL",
    "spec-recoverable-from-code-comments": "VAL",
    "ablation-cascade": "VAL",

    "reconstruct-not-edit": "MEC",
    "peer-read-relay": "MEC",
    "independent-nonauthor-execution": "MEC",
    "verifier-as-spec-source": "MEC",
    "prompt-boundary-violation": "MEC",
}

NON_BEHAVIORAL = {"GRD"}

NON_FAILURE = {"VAL", "MEC"}
FAILURE_FAMILIES = [c for c, _ in FAMILIES if c not in NON_BEHAVIORAL | NON_FAILURE]

STAGE_VOCAB = {

    "reroute-decided", "reroute-landed", "reroute-landed-wrong-target",

    "plan-flagged", "caught-at-verify", "artifact-recovered", "raise-dismissed",

    "delivery-integrity", "relay-fidelity", "re-verification-shallowness",
    "authority-not-information",
}

DETECTOR_TAGS = {
    "S3": ["identity-map-error", "reroute-never-landed", "reroute-not-migrated",
           "reroute-to-blocked-member", "shadow-workspace-reroute", "survivor-never-invoked",
           "leader-did-it", "claim-race-hijack"],
    "S4": ["seam-answer-lossy-reformulation", "answer-never-sent", "dual-relay-contract-drift",
           "relay-monopoly", "interface-mismatch", "planner-fabricated-interface"],
    "S5": ["hidden-profile-overruled", "hidden-profile-downgraded", "threshold-satisficing",
           "silent-false-accept", "attest-despite-known-fail", "verifier-rubber-stamp"],
    "S2": ["deliverable-misplacement", "llm-stream-truncation", "claim-race"],
}

BATCH_ORDER = ["S1A_team_dyn_pro", "S1A_team_dyn_pro_arm2", "S1A_team_enf_pro",
               "S1B_team_dyn_pro", "S1B_team_enf_pro", "S2_pairs_pro", "S2_pairs_enf_pro",
               "S3_full_enf_pro", "S3_partial_enf_pro", "S3_arm2_full_partial",
               "S4_enf_pro", "S5_enf_pro"]

TICKED = re.compile(r"`\**([a-z][a-z0-9]*(?:-[a-z0-9]+)*)\**`")
BARE_NEW = re.compile(r"new:\s*\**`?([a-z][a-z0-9-]+)`?\**")
ARCHIVE = re.compile(r"([A-Za-z0-9_.-]+-\d{8}-\d{6})")

NEG = re.compile(r"\b(?:NOT|not|never|neither|no)\b(?:\s+tagged|\s+a)?[\s*`:_]{0,6}$")

def canon(tag):
    return ALIAS.get(tag, tag)

def blocks():
    for fn in sorted(os.listdir(ANN)):
        if not fn.endswith(".md") or fn in ("TEMPLATE.md", "CODEBOOK.md"):
            continue
        batch = fn[:-3]
        txt = open(os.path.join(ANN, fn), encoding="utf-8").read()
        for part in re.split(r"^### ", txt, flags=re.M)[1:]:
            header = part.split("\n", 1)[0].strip()
            body = "### " + part
            m = re.search(r"-\s*\*\*failure mode\*\*:(.*?)(?=\n\s*-\s\*\*|\Z)", body, re.S)
            slot = m.group(1) if m else ""
            arc = ARCHIVE.search(header)
            out = re.search(r"\[([^\]]+)\]\s*$", header)
            task = re.split(r"\s+[—(\[]", header)[0].strip()
            yield (batch, header, task, arc.group(1) if arc else "",
                   out.group(1) if out else "", slot, body)

def tags_in(text):
    pos, neg = set(), set()
    for m in list(TICKED.finditer(text)) + list(BARE_NEW.finditer(text)):
        t = m.group(1)
        if t not in FAMILY and t not in ALIAS:
            continue
        pre = text[max(0, m.start() - 60):m.start()]
        (neg if NEG.search(pre.replace("\n", " ")) else pos).add(canon(t))
    return pos - neg, neg

def collect():
    rows = []
    prim, negs, ment, synth = (defaultdict(Counter) for _ in range(4))
    for batch, header, task, archive, outcome, slot, body in blocks():
        rest = body.replace(slot, "")
        if not archive:
            s, _ = tags_in(body)
            for t in s:
                synth[t][batch] += 1
            continue
        p, n = tags_in(slot)
        declared, dneg = tags_in("\n".join(re.findall(r".*new:.*", rest)))
        p |= declared
        n |= dneg
        p -= n
        m, rest_neg = tags_in(rest)
        n |= rest_neg - p
        m -= p | n
        rows.append(dict(batch=batch, task=task, archive=archive, outcome=outcome,
                         header=header, primary=sorted(p), negated=sorted(n),
                         mentioned=sorted(m)))
        for t in p:
            prim[t][batch] += 1
        for t in n:
            negs[t][batch] += 1
        for t in m:
            ment[t][batch] += 1
    return rows, prim, negs, ment, synth

def write_tables():
    os.makedirs(OUT, exist_ok=True)
    rows, prim, negs, ment, synth = collect()

    all_tags = sorted(set(prim) | set(negs) | set(ment) | set(synth),
                      key=lambda t: (FAMILY.get(t, "ZZZ"), -sum(prim[t].values()), t))
    p1 = os.path.join(OUT, "codebook_counts.tsv")
    with open(p1, "w", encoding="utf-8") as fh:
        fh.write("family\ttag\truns\tnegated\tmentioned\tsynth\t" + "\t".join(BATCH_ORDER) + "\n")
        for t in all_tags:
            cells = [str(prim[t].get(b, 0)) for b in BATCH_ORDER]
            fh.write("%s\t%s\t%d\t%d\t%d\t%d\t%s\n" % (
                FAMILY.get(t, "?"), t, sum(prim[t].values()), sum(negs[t].values()),
                sum(ment[t].values()), sum(synth[t].values()), "\t".join(cells)))

    p2 = os.path.join(OUT, "run_tags.tsv")
    with open(p2, "w", encoding="utf-8") as fh:
        fh.write("batch\ttask\tarchive\toutcome\tfamilies\tbehavioral_families\t"
                 "behavioral_tags\tgrader_artifact_only\tprimary_tags\tnegated_tags\n")
        for r in rows:
            fams = sorted({FAMILY.get(t, "?") for t in r["primary"]})
            beh = sorted(t for t in r["primary"] if FAMILY.get(t) not in NON_BEHAVIORAL)
            bfams = sorted({FAMILY[t] for t in beh})
            only_grd = bool(r["primary"]) and not beh
            fh.write("%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n" % (
                r["batch"], r["task"], r["archive"], r["outcome"], ",".join(fams),
                ",".join(bfams), ",".join(beh), "yes" if only_grd else "",
                ",".join(r["primary"]), ",".join(r["negated"])))

    fam = Counter()
    for t, c in prim.items():
        fam[FAMILY.get(t, "?")] += sum(c.values())
    print("wrote %s (%d tags)\nwrote %s (%d annotated runs)" % (
        p1, len(all_tags), p2, len(rows)))
    print("\nrun-level tag assertions by family:")
    for code, desc in FAMILIES:
        mark = "  (excluded from behavioral views)" if code in NON_BEHAVIORAL else \
               "  (behavioral, not a failure)" if code in NON_FAILURE else ""
        print("  %-5s %4d   %s%s" % (code, fam.get(code, 0), desc, mark))
    grd_only = [r for r in rows if r["primary"] and
                not any(FAMILY.get(t) not in NON_BEHAVIORAL for t in r["primary"])]
    print("\nruns whose entire annotation is a grader/env artifact (set aside): %d"
          % len(grd_only))
    for r in grd_only:
        print("  %-24s %-46s %s" % (r["batch"], r["archive"], ",".join(r["primary"])))

# oracle gate: assertions are facts read by hand off the frozen annotations
def verify():
    bad = 0
    seen = set()
    for batch, header, task, archive, outcome, slot, body in blocks():
        for m in list(TICKED.finditer(body)) + list(BARE_NEW.finditer(body)):
            seen.add(m.group(1))
    unmapped = {t for t in seen if re.search(r"-", t)} - set(FAMILY) - set(ALIAS)
    known_nontags = STAGE_VOCAB | {

        "verify-full", "verify-nonce", "pytest-timeout", "steps-out-of-order", "run-current",
        "test-service", "read-only", "cross-arm", "wall-clock", "near-miss", "self-report",
        "r-x", "shadow-workspace", "honest-scope", "impl-bug12", "not-ablated",

        "extend-tests", "fix-nonce", "fix-pagesize", "implement-app", "implement-audit",
        "implement-crypto1", "plan-audit", "verify-integration", "verify-unit",
    }
    strays = sorted(t for t in unmapped if t not in known_nontags)
    print("distinct tag-shaped tokens seen: %d ; unmapped after known non-tags: %d"
          % (len(seen), len(strays)))
    if strays:
        print("  UNMAPPED (add to FAMILY/ALIAS or to known_nontags):")
        for t in strays:
            print("   ", t)

    rows, prim, negs, ment, synth = collect()
    by_key = {r["archive"]: r for r in rows if r["archive"]}

    ORACLE = [

        ("lh5_s4-20260809-081250", "relay-monopoly", True),
        ("lh5_s4-20260809-081250", "plan-never-delivered", True),
        ("cr4_s4-20260809-090420", "answer-never-sent", True),
        ("spec5_s5partial-20260809-154345", "hidden-profile-overruled", True),
        ("p5_s3partial-20260808-204549", "reroute-never-landed", True),
        ("crypto1_prompt-only-20260808-003003", "format-lottery", True),
        ("ir2_prompt-only-20260810-100536", "deliverable-misplacement", True),

        ("p5_prompt-only-20260808-000337", "verifier-rubber-stamp", False),
        ("p5_prompt-only-20260808-000337", "attest-despite-known-fail", False),
        ("spec6_s5partial_arm2-20260809-191214", "silent-false-accept", False),
    ]
    for archive, tag, want in ORACLE:
        r = by_key.get(archive)
        if r is None:
            print("  ORACLE MISS: no block for archive %s" % archive); bad += 1; continue
        got = tag in r["primary"]
        if got != want:
            print("  ORACLE FAIL: %s / %s -> primary=%s (want %s); negated=%s"
                  % (archive, tag, got, want, r["negated"])); bad += 1
    print("oracle assertions: %d checked, %d failed" % (len(ORACLE), bad))

    for scen, tags in sorted(DETECTOR_TAGS.items()):
        empty = [t for t in tags if not sum(prim[t].values())]
        print("%s detector tags: %d, without a primary-tagged run: %s"
              % (scen, len(tags), empty or "none"))
    return 1 if bad or strays else 0

def show(tag):
    t = canon(tag)
    rows, prim, negs, ment, synth = collect()
    print("canonical: %s  (family %s)" % (t, FAMILY.get(t, "?")))
    for r in rows:
        where = ("primary" if t in r["primary"] else
                 "negated" if t in r["negated"] else
                 "mention" if t in r["mentioned"] else None)
        if where:
            print("  %-8s %-24s %-28s %s" % (where, r["batch"], r["task"], r["archive"]))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        sys.exit(verify())
    elif len(sys.argv) > 1:
        show(sys.argv[1])
    else:
        write_tables()
