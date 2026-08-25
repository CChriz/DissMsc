import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically secure random nonce for AES-GCM.

        Returns a 12-byte (96-bit) value from the OS CSPRNG.
        """
        return os.urandom(12)
