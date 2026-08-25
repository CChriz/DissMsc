import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically random 96-bit (12-byte) nonce.

        AES-GCM requires a unique nonce for every encryption under the same key.
        Reusing a nonce with the same key catastrophically breaks both
        confidentiality and authentication. os.urandom(12) produces unpredictable,
        collision-resistant nonces without the reuse risk of counter-based schemes.
        """
        return os.urandom(12)
