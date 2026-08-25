import os


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def generate(self) -> bytes:
        """Generate a cryptographically random 96-bit nonce for AES-GCM.

        Returns a 12-byte value from the OS CSPRNG (os.urandom).
        With random 96-bit nonces, the birthday bound is approximately
        2^48 messages before collision probability becomes significant —
        sufficient for any realistic workload under a single key.

        Returns:
            12-byte random nonce.
        """
        return os.urandom(12)
