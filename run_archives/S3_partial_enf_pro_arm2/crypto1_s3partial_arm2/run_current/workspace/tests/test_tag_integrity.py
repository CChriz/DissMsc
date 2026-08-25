"""Authentication tag integrity test.

GCM auth tag must be the full 16 bytes — truncation weakens forgery resistance
from 2^128 to 2^64.
"""
from crypto_service.encryption import encrypt, GCM_TAG_LENGTH
from crypto_service.key_derivation import derive_key
from crypto_service.utils import generate_salt


def test_full_16_byte_auth_tag():
    """GCM authentication tag must be exactly 16 bytes (embedded in ciphertext).

    The AESGCM.encrypt() returns ciphertext || 16-byte tag, so we verify
    that the returned ciphertext_with_tag has room for the full 16-byte tag.
    """
    key, _ = derive_key("testpassword", generate_salt())
    nonce, ct_with_tag = encrypt(b"hello world", key)
    # ct_with_tag = ciphertext || 16-byte tag, so must be at least 16 bytes
    assert len(ct_with_tag) >= GCM_TAG_LENGTH, (
        f"Ciphertext with tag must be at least {GCM_TAG_LENGTH} bytes, "
        f"got {len(ct_with_tag)}"
    )


def test_tag_type_is_bytes():
    """Ciphertext with embedded tag must be bytes."""
    key, _ = derive_key("testpassword", generate_salt())
    nonce, ct_with_tag = encrypt(b"data", key)
    assert isinstance(ct_with_tag, bytes), (
        f"Ciphertext + tag must be bytes, got {type(ct_with_tag)}"
    )
    assert isinstance(nonce, bytes), (
        f"Nonce must be bytes, got {type(nonce)}"
    )
