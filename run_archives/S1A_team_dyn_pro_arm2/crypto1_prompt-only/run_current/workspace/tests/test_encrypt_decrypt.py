"""Basic encrypt/decrypt round-trip tests.

These tests pass even with the cryptographic bugs — the service is
functionally correct but cryptographically weak.
"""
import pytest
from crypto_service.encryption import FileEncryptionService
from crypto_service.key_derivation import derive_key
from crypto_service.nonce import NonceGenerator
from crypto_service.utils import generate_salt


@pytest.fixture
def svc():
    return FileEncryptionService()


@pytest.fixture
def key():
    return derive_key("file_encryption_key_2024", generate_salt())


@pytest.fixture
def nonce_gen():
    return NonceGenerator()


def test_roundtrip_basic(svc, key, nonce_gen):
    """Encrypt then decrypt returns original plaintext."""
    plaintext = b'Sensitive file chunk data goes here.'
    nonce = nonce_gen.generate()
    ciphertext, tag = svc.encrypt(key, plaintext, nonce)
    recovered = svc.decrypt(key, ciphertext, tag, nonce)
    assert recovered == plaintext


def test_roundtrip_empty(svc, key, nonce_gen):
    """Empty plaintext round-trips correctly."""
    nonce = nonce_gen.generate()
    ciphertext, tag = svc.encrypt(key, b"", nonce)
    recovered = svc.decrypt(key, ciphertext, tag, nonce)
    assert recovered == b""


def test_different_keys_produce_different_ciphertexts(svc, nonce_gen):
    """Different keys produce different ciphertexts for the same plaintext."""
    salt = generate_salt()
    key1 = derive_key("password_one", salt)
    key2 = derive_key("password_two", salt)
    plaintext = b"same plaintext"
    nonce = nonce_gen.generate()
    ct1, _ = svc.encrypt(key1, plaintext, nonce)
    ct2, _ = svc.encrypt(key2, plaintext, nonce)
    assert ct1 != ct2


def test_nonce_generator_produces_bytes(nonce_gen):
    """NonceGenerator.generate() returns bytes."""
    nonce = nonce_gen.generate()
    assert isinstance(nonce, bytes)
