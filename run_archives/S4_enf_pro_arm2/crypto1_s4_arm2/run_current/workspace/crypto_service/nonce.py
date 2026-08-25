import os


class NonceGenerator:
    """Generates cryptographically secure random nonces for AES-GCM encryption.

    Uses the OS CSPRNG to produce 96-bit (12-byte) nonces per
    NIST SP 800-38D Section 8.2.1. With random nonces, the birthday
    bound is ~2^48 messages under the same key before collision
    probability becomes non-negligible — sufficient for any
    realistic single-key workload.
    """

    def generate(self) -> bytes:
        """Generate a 96-bit cryptographically random nonce.

        Returns:
            12 bytes from the operating system's CSPRNG.
        """
        return os.urandom(12)
