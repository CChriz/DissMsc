import os

NONCE_LENGTH = 12  # 96-bit per NIST SP 800-38D §8.2.1


def generate_nonce() -> bytes:
    """Generate a cryptographically random 96-bit nonce for AES-GCM.

    Uses os.urandom() — no fallback, fail-closed on CSPRNG failure.
    Collision probability at 10^6 encryptions under same key ≈ 1.26×10^(-17).
    """
    return os.urandom(NONCE_LENGTH)
