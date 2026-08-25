import os


class NonceGenerator:
    """Generates cryptographically secure random nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically secure random nonce for AES-GCM.

        Uses os.urandom(12) to generate a 96-bit random nonce from the
        operating system's CSPRNG. Each call produces an independent,
        unpredictable 12-byte value, preventing nonce reuse attacks.

        Returns:
            12-byte (96-bit) cryptographically secure random nonce.
        """
        return os.urandom(12)
