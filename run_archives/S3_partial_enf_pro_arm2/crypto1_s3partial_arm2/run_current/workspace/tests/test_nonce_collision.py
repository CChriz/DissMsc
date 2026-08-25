"""Adversarial nonce randomness and uniqueness tests.

Counter-based nonces are predictable and wrap at 2^32.
AES-GCM nonces MUST be cryptographically random (96-bit / os.urandom(12)).
"""
import os
import statistics
from crypto_service.nonce import generate_nonce, NONCE_LENGTH


def test_nonce_is_12_bytes():
    """Nonce must be exactly 12 bytes (96 bits) for AES-GCM."""
    for _ in range(10):
        nonce = generate_nonce()
        assert len(nonce) == NONCE_LENGTH, (
            f"Nonce must be {NONCE_LENGTH} bytes (96-bit), got {len(nonce)}"
        )


def test_nonces_are_not_sequential():
    """Nonces must not be sequential (counter-based).

    A counter-based nonce generator produces values like:
      0x00000001000000000000000000000000
      0x00000002000000000000000000000000
    which differ by exactly 1 in the first 4 bytes and are zero elsewhere.
    Random nonces have high entropy across all 12 bytes.
    """
    nonces = [generate_nonce() for _ in range(256)]

    # Check entropy across all byte positions.
    # For a random 12-byte nonce, each byte position should vary across samples.
    # Counter-based nonces have zero variance in bytes 4-11.
    low_variance_positions = 0
    for byte_pos in range(12):
        byte_values = [n[byte_pos] for n in nonces]
        unique_vals = len(set(byte_values))
        if unique_vals == 1:  # All identical — zero entropy
            low_variance_positions += 1

    assert low_variance_positions == 0, (
        f"{low_variance_positions} byte positions have zero variance across 256 nonces. "
        "Nonces must be cryptographically random (os.urandom(12)), not counter-based. "
        "Counter-based nonces leave most bytes as zero."
    )


def test_nonces_pass_basic_randomness_check():
    """Nonces must have high entropy: all 12 bytes should vary.

    Counter nonces pad with zero bytes, producing nonces like:
      b'\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00'
    where bytes 4-11 are always zero. This is a clear sign of non-randomness.
    """
    nonces = [generate_nonce() for _ in range(100)]

    # Count how many nonces have 5 or more zero bytes in positions 4-11
    counter_pattern_count = 0
    for n in nonces:
        zero_count = sum(1 for b in n[4:] if b == 0)
        if zero_count >= 7:  # 7+ of 8 bytes are zero -> counter padding
            counter_pattern_count += 1

    assert counter_pattern_count == 0, (
        f"{counter_pattern_count}/100 nonces look counter-based "
        "(bytes 4-11 are mostly zero). Use os.urandom(12) for nonce generation."
    )


def test_two_generators_produce_different_nonces():
    """Two independent calls to generate_nonce must not produce the same nonces.

    Counter-based generators both start at 0, so they produce identical sequences.
    Random generators produce independent, unique values.
    """
    nonces1 = [generate_nonce() for _ in range(20)]
    nonces2 = [generate_nonce() for _ in range(20)]
    overlap = set(nonces1) & set(nonces2)
    assert len(overlap) == 0, (
        f"Two independent nonce sequences produced {len(overlap)} identical "
        "nonces. Counter-based generators are predictable and reuse nonces across "
        "instances. Use os.urandom(12)."
    )
