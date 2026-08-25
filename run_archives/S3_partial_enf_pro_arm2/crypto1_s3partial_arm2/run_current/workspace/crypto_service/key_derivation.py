import hashlib
from crypto_service.utils import generate_salt

PBKDF2_ITERATIONS = 600_000   # OWASP 2023
PBKDF2_HASH = "sha256"
PBKDF2_KEY_LENGTH = 32
PBKDF2_SALT_LENGTH = 16


def derive_key(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a 256-bit AES key from a password using PBKDF2-HMAC-SHA256.

    Args:
        password: The user-supplied password (must not be empty).
        salt: A 16-byte random salt. If None, one is generated automatically.

    Returns:
        Tuple of (derived_key_bytes, salt_bytes).
    """
    if not password:
        raise ValueError("Password must not be empty")
    if salt is None:
        salt = generate_salt()
    if len(salt) != PBKDF2_SALT_LENGTH:
        raise ValueError(f"Salt must be {PBKDF2_SALT_LENGTH} bytes, got {len(salt)}")

    key = hashlib.pbkdf2_hmac(
        hash_name=PBKDF2_HASH,
        password=password.encode("utf-8"),
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        dklen=PBKDF2_KEY_LENGTH,
    )
    return key, salt
