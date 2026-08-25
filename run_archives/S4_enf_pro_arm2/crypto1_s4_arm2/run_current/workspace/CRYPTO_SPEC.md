# Cryptographic Specification — FileEncryptionService

This document defines the cryptographic requirements for the file encryption service that encrypts file chunks using AES-256-GCM.

## 1. Nonce Generation (crypto_service/nonce.py)

- **Algorithm**: AES-256-GCM requires a 96-bit (12-byte) nonce per encryption operation.
- **Uniqueness**: Nonces MUST be unique for every encryption performed under the same key.
- **Source**: Nonces MUST be generated from a cryptographically secure random source.
- **Rationale**: Nonce reuse under GCM completely breaks confidentiality and integrity.
  With random 96-bit nonces, the birthday bound is approximately 2^48 messages before
  collision probability becomes significant — sufficient for any realistic workload.

## 2. Key Derivation (crypto_service/key_derivation.py)

- **Algorithm**: PBKDF2-HMAC-SHA256
- **Minimum iterations**: 100,000 (NIST SP 800-132 recommendation; 600,000+ preferred)
- **Output length**: 32 bytes (256-bit key for AES-256)
- **Salt**: Random 128-bit (16-byte) salt generated per-password via generate_salt()
- **Rationale**: Low iteration counts allow GPU-accelerated brute force attacks.
  At 1,000 iterations a modern GPU can test ~10^9 passwords/second; at 100,000
  iterations this drops to ~10^4 per second, making offline attacks infeasible.

## 3. Authentication Tag (crypto_service/encryption.py)

- **Algorithm**: GCM (Galois/Counter Mode) with 128-bit authentication tag
- **Tag length**: 16 bytes (128 bits) — MUST NOT be truncated
- **Rationale**: Truncating the GCM tag to 8 bytes reduces the forgery resistance
  from 2^128 to 2^64. An 8-byte tag can be brute-forced by a determined adversary.

## 4. Salt Generation (crypto_service/utils.py)

- **Source**: os.urandom() — this is CORRECT and MUST NOT be changed.
- os.urandom() uses the operating system's CSPRNG (e.g., /dev/urandom on Linux).
- Do not replace with random.randbytes() or other non-cryptographic sources.
