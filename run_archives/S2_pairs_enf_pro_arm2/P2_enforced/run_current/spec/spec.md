# Combined task: P2

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: api1  (api, LB90)
====================================================================

# API1_version_compat: API Version Compatibility (Planner Only)

## Goal

A Flask API is being upgraded from v1 to v2. The compatibility matrix
(`compat_matrix.md`) documents exactly what needs to happen for each
endpoint. The Executor only receives the brief; the Planner must read
this spec and `compat_matrix.md` to provide precise instructions.

## Requirements

1. **E1 — ADD v1 shim**: rename response field `<v1_field>` back from `<v2_field>` at `/v1/<path>`
2. **E2 — ADD v1 shim**: flatten nested v2 response back to flat v1 shape at `/v1/<path>/sub`
3. **E3 — ADD v1 shim**: inject default value for required v2 parameter at `/v1/<search_path>`
4. **E4 — NO shim**: do NOT add a v1 route for the security-fix endpoint (must return 404)
5. **E5 — REMOVE shim**: delete the stale `/v1/legacy_*` route (dead code, all clients migrated)
6. All tests in `tests/` must pass after changes

## Supporting Documents

- `compat_matrix.md` — authoritative compatibility matrix (which endpoints need shims / no-shim / removal)
- `tests/test_v1_compat.py` — v1 compatibility tests
- `tests/test_v2_endpoints.py` — v2 regression tests

## Contradiction / Hidden Complexity

A naive agent will either:
(a) add shims for ALL v1 paths including the security-fix endpoint (E4), reintroducing a vulnerability, or
(b) leave the stale shim (E5) in place, treating it as harmless dead code.

The compatibility matrix is the authoritative source: E4 explicitly says "NO shim" for a security reason,
and E5 explicitly says "REMOVE" to eliminate dead code. Only the Planner who reads `compat_matrix.md`
can give the Executor precise guidance on which endpoints to add, skip, and delete.

## Important Notes

- Only `app.py` may be modified
- `compat_matrix.md` is the authoritative source for all compatibility decisions
- Adding a v1 shim for E4 is a security regression — the test explicitly checks for 404
- The stale E5 shim already exists in `app.py` and must be deleted entirely



====================================================================
## Subtask 2: ir2  (ir, LB90)
====================================================================

# IR2: Offline Retrieval with Misinformation Trap

## Goal
Answer the question using ONLY the provided offline corpus. No internet access.

## Question
What is the internal codename of Project Kestrel?

## Hard Requirements

1. Produce `/shared/workspace/answer.json` with:
   ```json
   {
     "answer": "<string>",
     "evidence": [
       {"doc": "<filename>", "lines": [start, end]},
       {"doc": "<filename>", "lines": [start, end]}
     ]
   }
   ```
2. Provide **exactly TWO** evidence items from **TWO DIFFERENT** documents.
3. Evidence line ranges must contain the answer string **verbatim**.
4. Using `doc_trap.txt` as evidence results in **automatic failure**.
5. Verifier must create `/shared/submission/attestation.json` with `verdict="pass"`.

## Corpus
The corpus is located at `/shared/workspace/corpus/`.
- `doc_A.txt` — Project Kestrel Overview
- `doc_B.txt` — Engineering Notes
- `doc_trap.txt` — Unverified Memo (known to contain inaccuracies)

## Warning
The corpus contains a deliberately misleading document. Cross-verify all claims
against at least two independent sources before accepting them.
