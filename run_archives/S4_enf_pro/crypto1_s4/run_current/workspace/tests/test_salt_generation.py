"""Salt generation correctness test.

Verifies that utils.py still uses os.urandom for salt generation.
This is the false positive — it is CORRECT and must not be modified.
"""
import inspect
from crypto_service import utils


def test_salt_uses_os_urandom():
    """generate_salt() must use os.urandom (the correct CSPRNG)."""
    src = inspect.getsource(utils)
    assert 'os.urandom' in src, (
        "generate_salt() must use os.urandom — do not remove or replace it"
    )


def test_salt_default_size():
    """generate_salt() with default size returns 16 bytes."""
    from crypto_service.utils import generate_salt
    salt = generate_salt()
    assert len(salt) == 16, f"Default salt must be 16 bytes, got {len(salt)}"


def test_salts_are_unique():
    """Each call to generate_salt() must return a different value."""
    from crypto_service.utils import generate_salt
    salts = {generate_salt() for _ in range(100)}
    assert len(salts) == 100, "Salts must be unique (random)"
