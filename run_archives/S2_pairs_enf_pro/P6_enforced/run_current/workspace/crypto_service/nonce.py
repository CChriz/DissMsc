import struct


class NonceGenerator:
    """Generates nonces for AES-GCM encryption."""

    def __init__(self):
        self._counter = 0

    def generate(self) -> bytes:
        """Generate a nonce for AES-GCM.

        Returns a 12-byte value derived from an internal counter.
        """
        # Counter-based nonce: only 32 bits of uniqueness
        nonce = struct.pack('>I', self._counter % (2 ** 32))
        self._counter += 1
        # Pad to 12 bytes (GCM requires 96-bit / 12-byte nonce)
        return nonce.ljust(12, b'\x00')
