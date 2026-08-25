from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

# GCM authentication tag length in bytes.
# 16 bytes (128 bits) provides 2^-128 forgery resistance.
# MUST NOT be truncated — NIST SP 800-38D Section 8.
_GCM_TAG_LENGTH = 16


class FileEncryptionService:
    """AES-256-GCM encryption service for file chunks."""

    def encrypt(self, key: bytes, plaintext: bytes, nonce: bytes) -> tuple:
        """Encrypt plaintext and return (ciphertext, auth_tag).

        Args:
            key: 32-byte AES key (from derive_key).
            plaintext: Data to encrypt.
            nonce: 12-byte cryptographically random nonce.

        Returns:
            Tuple of (ciphertext_bytes, auth_tag_bytes).
            auth_tag is the full 16-byte GCM authentication tag.
        """
        encryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend(),
        ).encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        return ciphertext, encryptor.tag

    def decrypt(self, key: bytes, ciphertext: bytes, tag: bytes, nonce: bytes) -> bytes:
        """Decrypt ciphertext and verify authentication tag.

        Args:
            key: 32-byte AES key.
            ciphertext: Encrypted data.
            tag: 16-byte GCM authentication tag (from encrypt).
            nonce: Same 12-byte nonce used during encryption.

        Returns:
            Decrypted plaintext bytes.

        Raises:
            cryptography.exceptions.InvalidTag: If authentication fails.
        """
        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend(),
        ).decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize_with_tag(tag)
