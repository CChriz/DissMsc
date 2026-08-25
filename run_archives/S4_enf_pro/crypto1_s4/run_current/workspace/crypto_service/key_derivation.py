import hashlib


def derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a password using PBKDF2-HMAC-SHA256.

    Args:
        password: The user-supplied password.
        salt: A random salt (use generate_salt() from utils).

    Returns:
        32-byte derived key suitable for AES-256.
    """
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations=100000,  # >= 100,000 per NIST SP 800-132 / OWASP 2023
        dklen=32,
    )
