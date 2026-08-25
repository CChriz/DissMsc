from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from crypto_service.nonce import generate_nonce, NONCE_LENGTH

GCM_TAG_LENGTH = 16


def encrypt(plaintext: bytes, key: bytes, associated_data: bytes = b"") -> tuple[bytes, bytes]:
    """Encrypt plaintext using AES-256-GCM.

    Args:
        plaintext: Data to encrypt (must not be empty).
        key: 32-byte AES-256 key.
        associated_data: Optional authenticated but unencrypted data.

    Returns:
        Tuple of (nonce_bytes, ciphertext_with_tag).
        The ciphertext includes the 16-byte authentication tag appended.
    """
    if len(key) != 32:
        raise ValueError(f"AES-256 requires 32-byte key, got {len(key)}")
    if not plaintext:
        raise ValueError("Plaintext must not be empty")
    nonce = generate_nonce()
    aesgcm = AESGCM(key)
    # AESGCM.encrypt returns ciphertext || 16-byte tag (auto-appended)
    ciphertext_with_tag = aesgcm.encrypt(nonce, plaintext, associated_data)
    return nonce, ciphertext_with_tag


def decrypt(nonce: bytes, ciphertext_with_tag: bytes, key: bytes, associated_data: bytes = b"") -> bytes:
    """Decrypt and verify AES-256-GCM ciphertext.

    Args:
        nonce: 12-byte nonce used during encryption.
        ciphertext_with_tag: Ciphertext with appended 16-byte auth tag.
        key: 32-byte AES-256 key.
        associated_data: Same associated data as used during encryption.

    Returns:
        Decrypted plaintext bytes.

    Raises:
        InvalidTag: If authentication fails (via OpenSSL libcrypto constant-time
                    verification).
    """
    if len(key) != 32:
        raise ValueError(f"AES-256 requires 32-byte key, got {len(key)}")
    if len(nonce) != NONCE_LENGTH:
        raise ValueError(f"Nonce must be {NONCE_LENGTH} bytes, got {len(nonce)}")
    if len(ciphertext_with_tag) < GCM_TAG_LENGTH:
        raise ValueError(
            f"Ciphertext too short — must include {GCM_TAG_LENGTH}-byte authentication tag"
        )
    aesgcm = AESGCM(key)
    # Constant-time tag verification via OpenSSL libcrypto
    return aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data)
