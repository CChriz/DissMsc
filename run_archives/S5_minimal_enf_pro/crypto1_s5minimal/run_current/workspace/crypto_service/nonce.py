import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically secure random 96-bit nonce for AES-GCM.

        Returns a 12-byte value from os.urandom.
        """
        return os.urandom(12)
