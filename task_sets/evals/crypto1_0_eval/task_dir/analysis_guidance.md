# Analysis Guidance — CRYPTO1_nonce_reuse

## Tools to run
- `cat crypto_service/nonce.py` — find counter-based nonce bug
- `cat crypto_service/key_derivation.py` — find iteration count
- `cat crypto_service/encryption.py` — find tag truncation
- `cat crypto_service/utils.py` — verify salt uses os.urandom (do NOT flag as bug)
- `cat CRYPTO_SPEC.md` — read all requirements

## Bug Locations and Fixes

### Bug 1: Counter-based nonce (nonce.py)
**Current**: `nonce = struct.pack('>I', self._counter)` (4 bytes) padded to 12
or similar counter-based generation
**Fix**: `nonce = os.urandom(12)` — 96-bit random nonce every time
**Why**: Counter nonces collide after 2^32 messages; random nonces have birthday
bound at 2^48 (safe for reasonable message counts)

### Bug 2: Weak KDF iterations (key_derivation.py)
**Current**: `iterations=1000` in PBKDF2 call
**Fix**: `iterations=100000` (100K minimum, 600K recommended)
**Why**: 1000 iterations takes ~0.001s to crack on GPU; 100K takes ~0.1s per attempt

### Bug 3: Truncated auth tag (encryption.py)
**Current**: Tag sliced to 8 bytes: `tag = ciphertext[-8:]` or `tag_length=8`
**Fix**: Use full 16-byte tag (default GCM tag length)
**Why**: 8-byte tag has 2^64 forgery probability; 16-byte has 2^128

### False Positive (do NOT change)
- `crypto_service/utils.py` uses `os.urandom(16)` for salt — THIS IS CORRECT
- A static analyzer might flag os.urandom as "weak random" — ignore this

## Tell Executor
Fix bugs in nonce.py, key_derivation.py, and encryption.py.
Do NOT touch utils.py.
