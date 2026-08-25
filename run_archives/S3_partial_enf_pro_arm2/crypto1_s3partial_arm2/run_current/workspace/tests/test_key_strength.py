"""Key derivation strength test.

Verifies that PBKDF2 uses >= 100,000 iterations as required by CRYPTO_SPEC.md.
"""
import inspect
import re
from crypto_service import key_derivation
from crypto_service.key_derivation import PBKDF2_ITERATIONS


def test_pbkdf2_iterations_sufficient():
    """PBKDF2 must use at least 100,000 iterations."""
    assert PBKDF2_ITERATIONS >= 100_000, (
        f"PBKDF2 must use >= 100,000 iterations per CRYPTO_SPEC.md, "
        f"found: {PBKDF2_ITERATIONS}"
    )


def test_derived_key_is_32_bytes():
    """Derived key must be 32 bytes (256 bits) for AES-256."""
    from crypto_service.utils import generate_salt
    from crypto_service.key_derivation import derive_key, PBKDF2_KEY_LENGTH
    key, salt = derive_key("test_password", generate_salt())
    assert len(key) == PBKDF2_KEY_LENGTH, (
        f"Key must be {PBKDF2_KEY_LENGTH} bytes, got {len(key)}"
    )
    assert len(salt) == 16, f"Salt must be 16 bytes, got {len(salt)}"
