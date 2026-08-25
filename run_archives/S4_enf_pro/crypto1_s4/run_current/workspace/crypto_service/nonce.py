import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically secure random nonce for AES-GCM.

        Returns a 12-byte (96-bit) nonce from the OS CSPRNG (os.urandom).
        """
        return os.urandom(12)
