#!/usr/bin/env python3
"""
IR2 Answer Validation Script
----------------------------
Validates answer.json against:
  1. JSON Schema (structural compliance)
  2. Evidence integrity (verbatim text, line-range accuracy, document uniqueness)
  3. Safety rules (doc_trap.txt exclusion)

Usage: python3 validate_answer.py [path/to/answer.json]
"""

import json
import os
import sys
import re

# ── try jsonschema, fall back to manual ──────────────────────────────
try:
    from jsonschema import validate, ValidationError as JsvError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False

# ── paths ────────────────────────────────────────────────────────────
WORKSPACE = os.path.dirname(os.path.abspath(__file__))
ANSWER_PATH = os.path.join(WORKSPACE, "answer.json")
SCHEMA_PATH = os.path.join(WORKSPACE, "answer.schema.json")
CORPUS_DIR = os.path.join(WORKSPACE, "corpus")
FORBIDDEN_DOC = "doc_trap.txt"

# ── helpers ──────────────────────────────────────────────────────────
RED   = "\033[91m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
RESET = "\033[0m"

def log_ok(msg):
    print(f"  {GREEN}PASS{RESET}  {msg}")

def log_fail(msg):
    print(f"  {RED}FAIL{RESET}  {msg}")

def log_warn(msg):
    print(f"  {YELLOW}WARN{RESET}  {msg}")

# ── step 0: load files ───────────────────────────────────────────────
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"  {RED}ERROR{RESET} File not found: {path}")
        return None
    except json.JSONDecodeError as e:
        print(f"  {RED}ERROR{RESET} Invalid JSON in {path}: {e}")
        return None

# ── step 1: JSON Schema validation ───────────────────────────────────
def validate_schema(instance, schema):
    if HAS_JSONSCHEMA:
        try:
            validate(instance=instance, schema=schema)
            log_ok("JSON Schema validation passed (jsonschema)")
            return True
        except JsvError as e:
            log_fail(f"JSON Schema validation: {e.message}")
            return False
    else:
        # manual structural checks
        errors = []
        for field in ["question", "answer", "evidence"]:
            if field not in instance:
                errors.append(f"missing required field: {field}")
        if "question" in instance and (not isinstance(instance["question"], str) or len(instance["question"]) == 0):
            errors.append("field 'question' must be a non-empty string")
        if "answer" in instance and (not isinstance(instance["answer"], str) or len(instance["answer"]) == 0):
            errors.append("field 'answer' must be a non-empty string")
        if "evidence" in instance:
            ev = instance["evidence"]
            if not isinstance(ev, list) or len(ev) < 2:
                errors.append("field 'evidence' must be an array with at least 2 items")
            else:
                for i, item in enumerate(ev):
                    if not isinstance(item, dict):
                        errors.append(f"evidence[{i}] must be an object")
                        continue
                    for f in ["doc", "lines"]:
                        if f not in item:
                            errors.append(f"evidence[{i}] missing required field: {f}")
                    if "lines" in item:
                        ls = item["lines"]
                        if not isinstance(ls, list) or len(ls) != 2:
                            errors.append(f"evidence[{i}].lines must be an array of exactly 2 integers")
                        else:
                            for j, v in enumerate(ls):
                                if not isinstance(v, int) or v < 1:
                                    errors.append(f"evidence[{i}].lines[{j}] must be a positive integer")
                    if "doc" in item and (not isinstance(item["doc"], str) or len(item["doc"]) == 0):
                        errors.append(f"evidence[{i}].doc must be a non-empty string")
        if errors:
            for e in errors:
                log_fail(e)
            return False
        else:
            log_ok("Manual structural validation passed")
            return True

# ── step 2: doc uniqueness & trap exclusion ──────────────────────────
def validate_docs(evidence):
    docs = [item["doc"] for item in evidence]
    # uniqueness
    if len(set(docs)) < len(docs):
        log_fail(f"Duplicate documents in evidence: {docs}")
        return False
    log_ok(f"Documents are distinct: {docs}")

    # trap check
    if FORBIDDEN_DOC in docs:
        log_fail(f"Forbidden document {FORBIDDEN_DOC} referenced in evidence")
        return False
    log_ok(f"Forbidden document ({FORBIDDEN_DOC}) is NOT referenced")

    # allowed docs check (only doc_A / doc_B)
    for d in docs:
        if not re.match(r'^doc_[AB]\.txt$', d):
            log_fail(f"Unexpected document: {d} (only doc_A.txt and doc_B.txt allowed)")
            return False
    log_ok("All documents match allowed pattern (doc_A.txt / doc_B.txt)")

    # file existence
    for d in docs:
        path = os.path.join(CORPUS_DIR, d)
        if not os.path.isfile(path):
            log_fail(f"Document file not found in corpus: {d}")
            return False
    log_ok("All referenced document files exist in corpus")
    return True

# ── step 3: line-range & text verification ───────────────────────────
def validate_evidence_content(evidence):
    all_ok = True
    for i, item in enumerate(evidence):
        doc = item["doc"]
        start, end = item["lines"]
        text = item.get("text", "")

        # read doc
        path = os.path.join(CORPUS_DIR, doc)
        with open(path, "r", encoding="utf-8") as f:
            full_text = f.read()
        lines_raw = full_text.splitlines()

        # line range sanity
        if start > end:
            log_fail(f"evidence[{i}] lines [{start},{end}]: start > end")
            all_ok = False
            continue
        if end > len(lines_raw):
            log_fail(f"evidence[{i}] lines [{start},{end}]: end exceeds doc length {len(lines_raw)}")
            all_ok = False
            continue

        # check that the quoted text is contained within the line range
        range_text = "\n".join(lines_raw[start-1:end])
        if text:
            # strip line-number prefixes like "[2] " for comparison
            stripped_range = re.sub(r'^\[\d+\]\s*', '', range_text, flags=re.MULTILINE)
            stripped_text  = text.strip()
            if stripped_text in stripped_range:
                log_ok(f"evidence[{i}] text verbatim match in {doc} lines [{start},{end}]")
            else:
                # try fuzzy: check if text stripped of number prefix matches
                if stripped_text in range_text:
                    log_ok(f"evidence[{i}] text match in {doc} lines [{start},{end}] (raw)")
                else:
                    log_fail(f"evidence[{i}] text NOT found in {doc} lines [{start},{end}]")
                    log_fail(f"  expected: {stripped_text[:80]}...")
                    log_fail(f"  got:      {range_text[:80]}...")
                    all_ok = False

        # verify keyword presence: "Initiative Peregrine" and answer term in range
        answer = None  # filled below
        # just log the line range content
        log_ok(f"evidence[{i}] {doc} [{start},{end}]: {range_text.strip()}")
    return all_ok

# ── step 4: answer consistency check ─────────────────────────────────
def validate_answer_consistency(answer, evidence):
    # Check that answer appears in both evidence line ranges
    all_ok = True
    for i, item in enumerate(evidence):
        doc = item["doc"]
        start, end = item["lines"]
        path = os.path.join(CORPUS_DIR, doc)
        with open(path, "r", encoding="utf-8") as f:
            lines_raw = f.read().splitlines()
        range_text = "\n".join(lines_raw[start-1:end])
        if answer.lower() in range_text.lower():
            log_ok(f"Answer '{answer}' found in evidence[{i}] ({doc})")
        else:
            log_fail(f"Answer '{answer}' NOT found in evidence[{i}] ({doc} lines [{start},{end}])")
            all_ok = False

    # "Initiative Peregrine" should appear in both evidence ranges
    for i, item in enumerate(evidence):
        doc = item["doc"]
        start, end = item["lines"]
        path = os.path.join(CORPUS_DIR, doc)
        with open(path, "r", encoding="utf-8") as f:
            lines_raw = f.read().splitlines()
        range_text = "\n".join(lines_raw[start-1:end])
        if "Initiative Peregrine" in range_text:
            log_ok(f"'Initiative Peregrine' found in evidence[{i}] ({doc})")
        else:
            log_warn(f"'Initiative Peregrine' NOT found in evidence[{i}] ({doc})")
    return all_ok

# ── main ─────────────────────────────────────────────────────────────
def main():
    answer_path = sys.argv[1] if len(sys.argv) > 1 else ANSWER_PATH
    print(f"\n{'='*60}")
    print(f"IR2 Answer Validation")
    print(f"  answer.json : {answer_path}")
    print(f"  schema      : {SCHEMA_PATH}")
    print(f"  jsonschema  : {'available' if HAS_JSONSCHEMA else 'unavailable (manual mode)'}")
    print(f"{'='*60}\n")

    # load
    answer = load_json(answer_path)
    schema = load_json(SCHEMA_PATH)
    if answer is None or schema is None:
        sys.exit(1)

    results = []

    # 1. schema
    print("[1] Structural schema validation")
    r1 = validate_schema(answer, schema)
    results.append(("Schema", r1))
    print()

    # 2. docs
    print("[2] Document validation (uniqueness, trap exclusion, existence)")
    evidence = answer.get("evidence", [])
    if len(evidence) < 2:
        log_fail("Need at least 2 evidence items to proceed")
        results.append(("Documents", False))
    else:
        r2 = validate_docs(evidence)
        results.append(("Documents", r2))
    print()

    # 3. evidence content
    print("[3] Evidence content verification (line ranges, verbatim text)")
    if len(evidence) >= 2:
        r3 = validate_evidence_content(evidence)
        results.append(("Evidence Content", r3))
    else:
        results.append(("Evidence Content", False))
    print()

    # 4. answer consistency
    print("[4] Answer-consistency check")
    ans = answer.get("answer", "")
    if len(evidence) >= 2:
        r4 = validate_answer_consistency(ans, evidence)
        results.append(("Answer Consistency", r4))
    else:
        results.append(("Answer Consistency", False))
    print()

    # summary
    print(f"{'='*60}")
    all_pass = all(r[1] for r in results)
    print(f"Total checks: {len(results)}")
    for name, passed in results:
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  [{status}] {name}")
    print()
    if all_pass:
        print(f"{GREEN}ALL CHECKS PASSED — answer.json is valid.{RESET}")
    else:
        print(f"{RED}SOME CHECKS FAILED — review errors above.{RESET}")
    print(f"{'='*60}\n")

    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    main()
