import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically random 96-bit nonce for AES-GCM."""
        return os.urandom(12)
