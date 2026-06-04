# api/app/infrastructure/security/credential_encryption.py

"""Fernet-based two-way encryption for secret-class credential fields."""

import base64
import os
from enum import Enum
from typing import Any, Dict, Optional

from contracts.redaction import is_sensitive_key
from cryptography.fernet import Fernet

from app.config.settings import settings


class CredentialType(str, Enum):
    """Types of credentials that can be encrypted."""

    API_KEY = "api_key"
    PASSWORD = "password"
    SECRET_KEY = "secret_key"
    ACCESS_TOKEN = "access_token"
    OAUTH_TOKEN = "oauth_token"


class CredentialEncryption:
    """Fernet encryption for secret-class fields. The list of sensitive field names is governed centrally in contracts - do not define a local list."""

    def __init__(self, encryption_key: Optional[str] = None):
        key = encryption_key or settings.CREDENTIAL_ENCRYPTION_KEY
        if not key:
            raise ValueError(
                "Encryption key not configured. Set CREDENTIAL_ENCRYPTION_KEY environment variable "
                "or pass encryption_key parameter."
            )

        try:
            self.fernet = Fernet(key.encode())
        except Exception as e:
            raise ValueError(f"Invalid encryption key format: {str(e)}")

    def encrypt(self, plaintext: str) -> str:
        if not plaintext:
            return plaintext

        encrypted = self.fernet.encrypt(plaintext.encode())
        return encrypted.decode()

    def decrypt(self, encrypted: str) -> str:
        if not encrypted:
            return encrypted

        try:
            decrypted = self.fernet.decrypt(encrypted.encode())
            return decrypted.decode()
        except Exception as e:
            raise ValueError(f"Failed to decrypt credential: {str(e)}")

    def encrypt_credential_dict(
        self, credential_data: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not credential_data:
            return credential_data

        result = credential_data.copy()

        # Mark as encrypted to prevent double-encryption.
        result["_encrypted"] = True

        # Encrypt sensitive fields. Substring match covers provider-prefixed
        # variants (e.g. leonardo_api_key). Skips the marker and non-string values.
        for field_name, field_value in list(result.items()):
            if field_name == "_encrypted":
                continue
            if isinstance(field_value, str) and is_sensitive_key(field_name):
                result[field_name] = self.encrypt(field_value)

        return result

    def decrypt_credential_dict(
        self, encrypted_data: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if not encrypted_data:
            return encrypted_data

        # If not marked as encrypted, return as-is
        if not encrypted_data.get("_encrypted", False):
            return encrypted_data

        result = encrypted_data.copy()

        # Remove encryption marker.
        if "_encrypted" in result:
            del result["_encrypted"]

        # Decrypt sensitive fields - same policy as encrypt for round-trip symmetry.
        for field_name, field_value in list(result.items()):
            if isinstance(field_value, str) and is_sensitive_key(field_name):
                result[field_name] = self.decrypt(field_value)

        return result


def generate_encryption_key() -> str:
    """Generate a random Fernet-compatible encryption key."""
    return base64.urlsafe_b64encode(os.urandom(32)).decode()


_global_encryption_instance = None


def get_credential_encryption() -> CredentialEncryption:
    """Lazy-init global encryption singleton."""
    global _global_encryption_instance

    if _global_encryption_instance is None:
        encryption_key = settings.CREDENTIAL_ENCRYPTION_KEY
        if not encryption_key:
            raise ValueError(
                "Credential encryption key not configured. Set CREDENTIAL_ENCRYPTION_KEY "
                "environment variable."
            )

        _global_encryption_instance = CredentialEncryption(encryption_key)

    return _global_encryption_instance
