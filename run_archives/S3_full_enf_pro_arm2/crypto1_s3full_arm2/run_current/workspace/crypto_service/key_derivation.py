"""
Key derivation module for AES-GCM encryption service.

Provides PBKDF2-HMAC-SHA256 key derivation with configurable iterations,
and blob-level pack/unpack utilities for the ciphertext header format.

Ciphertext blob format: salt(16) || iterations(4) || nonce(12) || tag(16) || ciphertext
"""

import hashlib
import os

from ._constants import (
    PBKDF2_ITERATIONS,
    PBKDF2_HASH,
    PBKDF2_DKLEN,
    PBKDF2_MIN_ITERATIONS,
    SALT_LEN,
    ITERATIONS_LEN,
    NONCE_LEN,
    TAG_LEN,
    SALT_OFFSET,
    ITERATIONS_OFFSET,
    NONCE_OFFSET,
    TAG_OFFSET,
    CIPHERTEXT_OFFSET,
    HEADER_LEN,
)


def derive_key(password: str, salt: bytes, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """Derive a 32-byte AES-256 key from a password using PBKDF2-HMAC-SHA256.

    Args:
        password: User-provided password string.
        salt: 16-byte cryptographic salt (from os.urandom or stored blob).
        iterations: PBKDF2 iteration count (default: 600,000 per OWASP 2023).

    Returns:
        32-byte derived key suitable for AES-256-GCM.

    Raises:
        ValueError: If salt length != SALT_LEN or iterations < PBKDF2_MIN_ITERATIONS.
    """
    if len(salt) != SALT_LEN:
        raise ValueError(f"Salt must be exactly {SALT_LEN} bytes, got {len(salt)}")
    if iterations < PBKDF2_MIN_ITERATIONS:
        raise ValueError(
            f"Iterations must be >= {PBKDF2_MIN_ITERATIONS} (spec minimum), "
            f"got {iterations}"
        )

    return hashlib.pbkdf2_hmac(
        PBKDF2_HASH,
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=PBKDF2_DKLEN,
    )


def generate_salt() -> bytes:
    """Generate a cryptographically random 16-byte salt using os.urandom."""
    return os.urandom(SALT_LEN)


def pack_iterations(iterations: int) -> bytes:
    """Encode iteration count as 4-byte big-endian unsigned integer.

    Args:
        iterations: PBKDF2 iteration count (must fit in uint32, 0..2^32-1).

    Returns:
        4-byte big-endian encoded bytes.

    Raises:
        ValueError: If iterations is negative or exceeds uint32 range.
    """
    if iterations < 0 or iterations > 0xFFFFFFFF:
        raise ValueError(f"Iterations {iterations} out of uint32 range [0, 2^32-1]")
    return iterations.to_bytes(ITERATIONS_LEN, byteorder="big")


def unpack_iterations(data: bytes) -> int:
    """Decode 4-byte big-endian iteration count from packed header.

    Args:
        data: Exactly 4 bytes of big-endian encoded iterations.

    Returns:
        Decoded integer iteration count.

    Raises:
        ValueError: If data length != ITERATIONS_LEN.
    """
    if len(data) != ITERATIONS_LEN:
        raise ValueError(
            f"Expected {ITERATIONS_LEN} bytes for iterations field, got {len(data)}"
        )
    return int.from_bytes(data, byteorder="big")


def assemble_blob(
    salt: bytes,
    iterations: int,
    nonce: bytes,
    tag: bytes,
    ciphertext: bytes,
) -> bytes:
    """Assemble the complete ciphertext blob from individual components.

    Blob format: salt(16) || iterations(4, big-endian) || nonce(12) || tag(16) || ciphertext

    Args:
        salt: 16-byte cryptographic salt.
        iterations: PBKDF2 iteration count.
        nonce: 12-byte AES-GCM nonce.
        tag: 16-byte AES-GCM authentication tag.
        ciphertext: Variable-length encrypted payload.

    Returns:
        Complete ciphertext blob as bytes.

    Raises:
        ValueError: If any fixed-length component has wrong length.
    """
    if len(salt) != SALT_LEN:
        raise ValueError(f"Invalid salt length: {len(salt)}, expected {SALT_LEN}")
    if len(nonce) != NONCE_LEN:
        raise ValueError(f"Invalid nonce length: {len(nonce)}, expected {NONCE_LEN}")
    if len(tag) != TAG_LEN:
        raise ValueError(f"Invalid tag length: {len(tag)}, expected {TAG_LEN}")

    packed_iters = pack_iterations(iterations)
    return salt + packed_iters + nonce + tag + ciphertext


def disassemble_blob(blob: bytes) -> dict:
    """Parse a ciphertext blob into its constituent components.

    Blob format: salt(16) || iterations(4, big-endian) || nonce(12) || tag(16) || ciphertext

    Args:
        blob: Complete ciphertext blob.

    Returns:
        dict with keys: salt, iterations, nonce, tag, ciphertext
            - salt: bytes (16)
            - iterations: int
            - nonce: bytes (12)
            - tag: bytes (16)
            - ciphertext: bytes (variable length)

    Raises:
        ValueError: If blob is too short for the fixed header (minimum HEADER_LEN bytes).
    """
    if len(blob) < HEADER_LEN:
        raise ValueError(
            f"Blob too short: {len(blob)} bytes, minimum {HEADER_LEN} required"
        )

    return {
        "salt": blob[SALT_OFFSET:SALT_OFFSET + SALT_LEN],
        "iterations": unpack_iterations(
            blob[ITERATIONS_OFFSET:ITERATIONS_OFFSET + ITERATIONS_LEN]
        ),
        "nonce": blob[NONCE_OFFSET:NONCE_OFFSET + NONCE_LEN],
        "tag": blob[TAG_OFFSET:TAG_OFFSET + TAG_LEN],
        "ciphertext": blob[CIPHERTEXT_OFFSET:],
    }
