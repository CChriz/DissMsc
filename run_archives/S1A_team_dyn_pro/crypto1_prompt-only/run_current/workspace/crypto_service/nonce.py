import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a 96-bit cryptographically random nonce for AES-GCM.

        Returns a 12-byte value from the OS CSPRNG.
        """
        return os.urandom(12)
