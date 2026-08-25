import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically random 12-byte nonce for AES-GCM.

        Uses os.urandom as the CSPRNG source per NIST SP 800-38D §8.2.1
        recommendation for random 96-bit nonces.
        """
        return os.urandom(12)
