import os


def generate_salt(size: int = 16) -> bytes:
    """Generate a cryptographically secure random salt.

    Args:
        size: Number of bytes for the salt (default 16).

    Returns:
        Random bytes suitable for use as a KDF salt.
    """
    return os.urandom(size)  # Correct: os.urandom is the right choice here
