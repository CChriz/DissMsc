"""Key derivation strength test.

Verifies that PBKDF2 uses >= 100,000 iterations as required by CRYPTO_SPEC.md.
"""
import inspect
import re
from crypto_service import key_derivation


def test_pbkdf2_iterations_sufficient():
    """PBKDF2 must use at least 100,000 iterations."""
    src = inspect.getsource(key_derivation)
    iters = [int(x) for x in re.findall(r'iterations\s*=\s*(\d+)', src)]
    assert iters, "No 'iterations=' found in key_derivation module source"
    assert any(i >= 100_000 for i in iters), (
        f"PBKDF2 must use >= 100,000 iterations per CRYPTO_SPEC.md, found: {iters}"
    )


def test_derived_key_is_32_bytes():
    """Derived key must be 32 bytes (256 bits) for AES-256."""
    from crypto_service.utils import generate_salt
    from crypto_service.key_derivation import derive_key
    key = derive_key("test_password", generate_salt())
    assert len(key) == 32, f"Key must be 32 bytes, got {len(key)}"
