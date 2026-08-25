"""Authentication tag integrity test.

GCM auth tag must be the full 16 bytes — truncation weakens forgery resistance
from 2^128 to 2^64.
"""
import crypto_service.encryption as _enc_mod
from crypto_service.key_derivation import derive_key
from crypto_service.nonce import NonceGenerator
from crypto_service.utils import generate_salt


def _get_service():
    """Find the encryption service class regardless of seed-parameterised name."""
    for name in dir(_enc_mod):
        obj = getattr(_enc_mod, name)
        if isinstance(obj, type) and 'encrypt' in name.lower():
            return obj()
    raise RuntimeError("No encryption service class found in crypto_service.encryption")


def test_full_16_byte_auth_tag():
    """GCM authentication tag must be exactly 16 bytes."""
    svc = _get_service()
    key = derive_key("testpassword", generate_salt())
    nonce = NonceGenerator().generate()
    ciphertext, tag = svc.encrypt(key, b"hello world", nonce)
    assert len(tag) == 16, (
        f"GCM auth tag must be 16 bytes per CRYPTO_SPEC.md, got {len(tag)}. "
        "Do not truncate the authentication tag."
    )


def test_tag_type_is_bytes():
    """Authentication tag must be bytes."""
    svc = _get_service()
    key = derive_key("testpassword", generate_salt())
    nonce = NonceGenerator().generate()
    _, tag = svc.encrypt(key, b"data", nonce)
    assert isinstance(tag, bytes), f"Tag must be bytes, got {type(tag)}"
