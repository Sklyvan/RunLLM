"""Symmetric encryption for user-provided third-party credentials.

Wraps :class:`cryptography.fernet.Fernet`. The key lives in settings as
:class:`pydantic.SecretStr` and is never logged.
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from runllm.config import Settings, get_settings


class CredentialCipherError(Exception):
    """Raised when ciphertext cannot be decrypted."""


class CredentialCipher:
    """Encrypt and decrypt opaque secrets using a Fernet key."""

    def __init__(self, key: bytes | str | None = None, settings: Settings | None = None) -> None:
        if key is None:
            key = (settings or get_settings()).fernet_key.get_secret_value()
        if isinstance(key, str):
            key = key.encode("utf-8")
        self._fernet = Fernet(key)

    def encrypt(self, data: str) -> bytes:
        """Encrypt a UTF-8 string and return the ciphertext."""

        return self._fernet.encrypt(data.encode("utf-8"))

    def decrypt(self, token: bytes) -> str:
        """Decrypt ciphertext into the original string."""

        try:
            return self._fernet.decrypt(token).decode("utf-8")
        except InvalidToken as exc:  # pragma: no cover - defensive
            raise CredentialCipherError("invalid or tampered ciphertext") from exc

    def encrypt_dict(self, data: dict[str, Any]) -> bytes:
        """Encrypt a JSON-serializable dictionary."""

        return self.encrypt(json.dumps(data, sort_keys=True))

    def decrypt_dict(self, token: bytes) -> dict[str, Any]:
        """Decrypt ciphertext back into a dictionary."""

        return json.loads(self.decrypt(token))  # type: ignore[no-any-return]

    @staticmethod
    def generate_key() -> str:
        """Return a freshly generated Fernet key as a UTF-8 string."""

        return Fernet.generate_key().decode("utf-8")

