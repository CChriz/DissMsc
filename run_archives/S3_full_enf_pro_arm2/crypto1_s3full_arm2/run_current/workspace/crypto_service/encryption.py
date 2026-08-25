import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

GCM_NONCE_LENGTH = 12  # 96-bit nonce, NIST SP 800-38D §8.2


class DecryptionError(Exception):
    """Raised when decryption fails due to authentication tag verification
    failure, indicating either ciphertext tampering or incorrect key."""
    pass


def encrypt(plaintext: bytes, key: bytes, associated_data: bytes = b"") -> bytes:
    """Encrypt plaintext using AES-256-GCM.

    Generates a fresh 96-bit cryptographically random nonce for every call.
    The AESGCM primitive appends the full 16-byte (128-bit) authentication
    tag to the ciphertext internally — no manual tag handling is performed,
    eliminating the previous tag-truncation vulnerability.

    Args:
        plaintext: Data to encrypt.
        key: 32-byte (256-bit) AES key from key_derivation.derive_key().
        associated_data: Optional authenticated but unencrypted data (AAD).

    Returns:
        Concatenated bytes: nonce (12) || ciphertext || tag (16).
    """
    nonce = os.urandom(GCM_NONCE_LENGTH)
    aesgcm = AESGCM(key)
    # encrypt() returns ciphertext concatenated with the 16-byte tag
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data)
    return nonce + ciphertext_with_tag


def decrypt(data: bytes, key: bytes, associated_data: bytes = b"") -> bytes:
    """Decrypt AES-256-GCM ciphertext and verify authentication.

    The 16-byte tag is implicitly extracted and verified by AESGCM.decrypt()
    using constant-time comparison — no manual tag comparison, eliminating
    the risk of timing side-channels.

    Args:
        data: Concatenated bytes: nonce (12) || ciphertext || tag (16),
            as produced by encrypt().
        key: 32-byte (256-bit) AES key from key_derivation.derive_key().
        associated_data: Must exactly match the value passed to encrypt().

    Returns:
        Decrypted plaintext bytes.

    Raises:
        DecryptionError: If authentication tag verification fails.
    """
    if len(data) < GCM_NONCE_LENGTH:
        raise DecryptionError("Ciphertext too short: missing nonce")

    nonce = data[:GCM_NONCE_LENGTH]
    ciphertext_with_tag = data[GCM_NONCE_LENGTH:]

    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data)
    except InvalidTag:
        raise DecryptionError("Authentication failed: ciphertext tampered or wrong key")
