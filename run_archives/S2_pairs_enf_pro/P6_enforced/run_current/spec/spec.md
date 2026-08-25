# Combined task: P6

This workspace contains 2 INDEPENDENT subtasks. Complete ALL of them; each is graded separately. Files for different subtasks are co-located in one workspace — identify which files belong to which subtask.



====================================================================
## Subtask 1: crypto1  (crypto, LB90)
====================================================================

# CRYPTO1: AES-GCM Encryption Service

## Goal
The encryption service must implement AES-256-GCM correctly per CRYPTO_SPEC.md.

## Requirements
1. Nonces must be 96-bit (12 bytes) and cryptographically random — not counter-based
2. Key derivation must use PBKDF2 with >= 100,000 iterations
3. GCM authentication tag must be full 16 bytes — no truncation
4. Salt generation using `os.urandom()` is already correct — do not modify it

## Supporting Documents
- `CRYPTO_SPEC.md`: Full cryptographic requirements with rationale
- `crypto_service/nonce.py`: Nonce generation (has counter-based bug)
- `crypto_service/key_derivation.py`: KDF (has iteration count bug)
- `crypto_service/encryption.py`: Encrypt/decrypt (has tag truncation bug)
- `crypto_service/utils.py`: Salt generation (CORRECT, do not change)

## Important
The basic encrypt/decrypt round-trip tests will pass even with the bugs — the service
is functionally correct but cryptographically weak. The adversarial tests in
`tests/test_nonce_collision.py`, `tests/test_key_strength.py`, and
`tests/test_tag_integrity.py` catch the actual vulnerabilities.

## Real-World Context
These bugs reflect vulnerabilities documented in production systems:
- **Nonce reuse (Bug 1)**: Internet-wide scanning (Joux 2006; Böck et al. 2016,
  "Nonce-Disrespecting Adversaries") found 184 HTTPS servers reusing AES-GCM nonces,
  allowing full plaintext recovery and authentication key extraction.
- **Weak KDF (Bug 2)**: PBKDF2 with 1,000 iterations is breakable in minutes with
  commodity GPUs. OWASP recommends ≥ 600,000 iterations for PBKDF2-SHA256 (2023).
- **Truncated tag (Bug 3)**: CVE-2022-21449-style truncation of authentication tags
  reduces forgery resistance from 2^128 to 2^64, enabling birthday attacks at scale.



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
