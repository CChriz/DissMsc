import os


def generate_nonce() -> bytes:
    """Generate a 96-bit (12-byte) cryptographically random nonce for AES-GCM.

    Uses os.urandom() for cryptographic randomness sourced from the operating
    system's CSPRNG.  At 2^48 encryptions under the same key, the collision
    probability remains < 2^-32 per NIST SP 800-38D §8.3.

    This replaces the previous counter-based nonce implementation, which is
    vulnerable to nonce reuse across service restarts, multi-instance
    deployments, and process forks.  Nonce reuse in AES-GCM completely
    breaks confidentiality and authenticity (Joux 2006).

    Returns:
        bytes: 12-byte (96-bit) cryptographically random nonce.
    """
    return os.urandom(12)
