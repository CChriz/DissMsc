import hashlib


def derive_key(password: str, salt: bytes, iterations=600000) -> bytes:
    """Derive a 256-bit AES key from a password using PBKDF2-HMAC-SHA256.

    OWASP 2023 recommends 600,000 iterations for PBKDF2-SHA256.
    NIST SP 800-132 minimum is 100,000.

    Args:
        password: The user-supplied password.
        salt: A random salt (use generate_salt() from utils).
        iterations: PBKDF2 iteration count (default 600000).
                    Must be >= 100,000 per NIST SP 800-132.

    Returns:
        32-byte derived key suitable for AES-256.

    Raises:
        ValueError: If iterations < 100,000.
    """
    if iterations < 100000:
        raise ValueError(
            f"PBKDF2 iterations must be >= 100,000, got {iterations}"
        )
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations=iterations,
        dklen=32,
    )
