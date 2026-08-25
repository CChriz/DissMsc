from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend


class FileEncryptionService:
    """AES-256-GCM encryption service for file chunks."""

    def encrypt(self, key: bytes, plaintext: bytes, nonce: bytes) -> tuple:
        """Encrypt plaintext and return (ciphertext, auth_tag).

        Args:
            key: 32-byte AES key (from derive_key).
            plaintext: Data to encrypt.
            nonce: 12-byte nonce (from NonceGenerator).

        Returns:
            Tuple of (ciphertext_bytes, auth_tag_bytes).
        """
        encryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend(),
        ).encryptor()
        ciphertext = encryptor.update(plaintext) + encryptor.finalize()
        tag = encryptor.tag  # 16-byte GCM authentication tag — never truncate
        return ciphertext, tag

    def decrypt(self, key: bytes, ciphertext: bytes, tag: bytes, nonce: bytes) -> bytes:
        """Decrypt ciphertext and verify authentication tag.

        Args:
            key: 32-byte AES key.
            ciphertext: Encrypted data.
            tag: Authentication tag (as returned by encrypt).
            nonce: Same 12-byte nonce used during encryption.

        Returns:
            Decrypted plaintext bytes.
        """
        decryptor = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce, tag, min_tag_length=16),
            backend=default_backend(),
        ).decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()
