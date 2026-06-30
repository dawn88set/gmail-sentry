"""
At-rest encryption for integration credentials.

Uses Fernet (AES-128-CBC + HMAC) keyed by APP_ENCRYPTION_KEY, injected by the
platform. Ciphertext is wrapped in a small versioned envelope {kid, enc} so the
key can be rotated later: set APP_ENCRYPTION_KEY to the new key and list older
keys in APP_ENCRYPTION_KEYS (comma-separated) for decrypt-only.
"""
import json
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

_KID = "v1"


class CredentialEncryptionUnavailable(Exception):
    """Raised when APP_ENCRYPTION_KEY is missing or invalid."""


def _fernet() -> MultiFernet:
    primary = (os.getenv("APP_ENCRYPTION_KEY") or "").strip()
    if not primary:
        raise CredentialEncryptionUnavailable(
            "APP_ENCRYPTION_KEY is not configured — refusing to store credentials "
            "in plaintext."
        )
    keys = [primary]
    extra = (os.getenv("APP_ENCRYPTION_KEYS") or "").strip()
    if extra:
        keys += [k.strip() for k in extra.split(",") if k.strip()]
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as e:
        raise CredentialEncryptionUnavailable(f"APP_ENCRYPTION_KEY is invalid: {e}")


def encrypt(data: Dict[str, Any]) -> Dict[str, str]:
    token = _fernet().encrypt(json.dumps(data).encode())
    return {"kid": _KID, "enc": token.decode()}


def decrypt(envelope: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not envelope or not isinstance(envelope, dict) or "enc" not in envelope:
        return {}
    try:
        raw = _fernet().decrypt(envelope["enc"].encode())
        return json.loads(raw.decode())
    except (InvalidToken, ValueError):
        return {}
