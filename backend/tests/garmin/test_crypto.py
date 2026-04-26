"""Round-trip tests for the credential cipher."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from runllm.garmin.crypto import CredentialCipher, CredentialCipherError


@pytest.fixture()
def cipher() -> CredentialCipher:
    return CredentialCipher(key=Fernet.generate_key())


def test_encrypt_decrypt_string_roundtrip(cipher: CredentialCipher) -> None:
    plaintext = "hunter2 — secret password"
    token = cipher.encrypt(plaintext)
    assert isinstance(token, bytes)
    assert token != plaintext.encode()
    assert cipher.decrypt(token) == plaintext


def test_encrypt_decrypt_dict_roundtrip(cipher: CredentialCipher) -> None:
    payload = {"refresh_token": "abc", "nested": {"a": 1, "b": [1, 2, 3]}}
    token = cipher.encrypt_dict(payload)
    assert cipher.decrypt_dict(token) == payload


def test_decrypt_with_wrong_key_raises() -> None:
    a = CredentialCipher(key=Fernet.generate_key())
    b = CredentialCipher(key=Fernet.generate_key())
    token = a.encrypt("data")
    with pytest.raises(CredentialCipherError):
        b.decrypt(token)


def test_generate_key_is_valid_fernet_key() -> None:
    key = CredentialCipher.generate_key()
    cipher = CredentialCipher(key=key)
    assert cipher.decrypt(cipher.encrypt("x")) == "x"
