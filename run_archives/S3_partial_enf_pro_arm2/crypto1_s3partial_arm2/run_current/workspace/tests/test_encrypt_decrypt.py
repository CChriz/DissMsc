"""Basic encrypt/decrypt round-trip tests.

These tests verify functional correctness of AES-256-GCM encryption and
decryption with the fixed cryptographic parameters.
"""
import pytest
from crypto_service.encryption import encrypt, decrypt
from crypto_service.key_derivation import derive_key
from crypto_service.utils import generate_salt


@pytest.fixture
def key():
    key, salt = derive_key("file_encryption_key_2024", generate_salt())
    return key


def test_roundtrip_basic(key):
    """Encrypt then decrypt returns original plaintext."""
    plaintext = b'Sensitive file chunk data goes here.'
    nonce, ct_with_tag = encrypt(plaintext, key)
    recovered = decrypt(nonce, ct_with_tag, key)
    assert recovered == plaintext


def test_roundtrip_empty(key):
    """Empty plaintext is rejected with a clear error."""
    with pytest.raises(ValueError, match="Plaintext must not be empty"):
        encrypt(b"", key)


def test_different_keys_produce_different_ciphertexts():
    """Different keys produce different ciphertexts for the same plaintext."""
    salt = generate_salt()
    key1, _ = derive_key("password_one", salt)
    key2, _ = derive_key("password_two", salt)
    plaintext = b"same plaintext"
    nonce1, ct1 = encrypt(plaintext, key1)
    nonce2, ct2 = encrypt(plaintext, key2)
    assert ct1 != ct2


def test_decrypt_with_wrong_key_fails(key):
    """Decryption with a wrong key must fail (InvalidTag)."""
    from cryptography.exceptions import InvalidTag
    wrong_key, _ = derive_key("wrong_password", generate_salt())
    nonce, ct_with_tag = encrypt(b"secret data", key)
    with pytest.raises(InvalidTag):
        decrypt(nonce, ct_with_tag, wrong_key)


def test_tampered_ciphertext_fails(key):
    """Tampering with ciphertext must cause decryption failure."""
    nonce, ct_with_tag = encrypt(b"sensitive data", key)
    # Flip a bit in the ciphertext (before the tag)
    tampered = bytearray(ct_with_tag)
    tampered[0] ^= 0x01
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):
        decrypt(nonce, bytes(tampered), key)


def test_tampered_tag_fails(key):
    """Tampering with the auth tag must cause decryption failure."""
    nonce, ct_with_tag = encrypt(b"sensitive data", key)
    # Flip the last byte (in the tag region)
    tampered = bytearray(ct_with_tag)
    tampered[-1] ^= 0xFF
    from cryptography.exceptions import InvalidTag
    with pytest.raises(InvalidTag):
        decrypt(nonce, bytes(tampered), key)
