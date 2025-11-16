"""
API Key Model for 3rd Party Access
"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Annotated, List, Literal, Optional

from pydantic import Field

from lib.models.common import Model
from settings import ENCRYPTION_KEY

ValidPermissions = Literal[
    "patients:read",
    "patients:write",
    "patients:delete",
    "encounters:read",
    "encounters:write",
    "encounters:delete",
    "appointments:read",
    "appointments:write",
    "appointments:delete",
    "users:read",
    "users:write",
    "users:delete",
    "admin:read",
    "admin:write",
    "admin:delete",
    # LLM-specific permissions
    "llm:chat",
    "llm:read",
    "llm:write",
    "llm:delete",
]


class APIKey(Model):
    """
    Represents an API key for 3rd party access to the system
    """

    id: Optional[str] = None
    user_id: Optional[str] = None
    name: Annotated[Optional[str], Field(min_length=3, max_length=50)] = None
    is_active: bool = True
    permissions: List[ValidPermissions] = []
    rate_limit_per_hour: int = 1000
    key_hash: Optional[str] = None
    key_salt: Optional[str] = None
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new API key

        :return: New API key string
        """
        # Generate a secure random key
        return f"ars_{secrets.token_urlsafe(32)}"

    @staticmethod
    def hash_key(key: str) -> str:
        """
        Hash an API key for secure storage

        :param key: Plain text API key
        :return: Hashed API key
        """
        hash = hashlib.sha256((key + ENCRYPTION_KEY).encode("utf-8")).hexdigest()  # type: ignore throws error if not str in settings
        return hash

    def verify_key(self, to_verify_key: str) -> bool:
        """
        Verify an API key against the stored hash

        :param to_verify_key: Plain text API key to verify
        :return: True if key matches, False otherwise
        """
        if not self.key_hash:
            return False

        try:
            to_verify_hash = APIKey.hash_key(to_verify_key)
            return self.key_hash == to_verify_hash
        except (ValueError, AttributeError) as e:
            self.logger.error(f"API key verification error: {e}")
            return False

    def has_permission(self, permission: ValidPermissions) -> bool:
        """
        Check if the API key has a specific permission

        :param permission: Permission to check
        :return: True if key has permission, False otherwise
        """
        return permission in self.permissions

    def has_any_permission(self, permissions: List[ValidPermissions]) -> bool:
        """
        Check if the API key has any of the specified permissions

        :param permissions: List of permissions to check
        :return: True if key has any permission, False otherwise
        """
        return any(permission in self.permissions for permission in permissions)

    def has_all_permissions(self, permissions: List[ValidPermissions]) -> bool:
        """
        Check if the API key has all of the specified permissions

        :param permissions: List of permissions to check
        :return: True if key has all permissions, False otherwise
        """
        return all(permission in self.permissions for permission in permissions)

    def is_expired(self) -> bool:
        """
        Check if the API key has expired

        :return: True if expired, False otherwise
        """
        if not self.expires_at:
            return False

        try:
            return datetime.now(timezone.utc) > self.expires_at
        except (ValueError, AttributeError) as e:
            self.logger.error(f"Error checking API key expiration: {e}")
            return False

    def update_last_used(self) -> None:
        """
        Update the last used timestamp
        """
        self.last_used_at = datetime.now(timezone.utc)

    @classmethod
    def table_name(cls) -> str:
        return "api_key"

    @classmethod
    def table_schema(cls) -> str:
        """
        Defines the schema for the api key table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE api_key SCHEMAFULL;
            DEFINE FIELD name ON api_key TYPE string;
            DEFINE FIELD user_id ON api_key TYPE record<user>;
            DEFINE FIELD key_hash ON api_key TYPE string;
            DEFINE FIELD key_salt ON api_key TYPE string;
            DEFINE INDEX keyHashIndex ON TABLE api_key COLUMNS key_hash UNIQUE;
            DEFINE FIELD permissions ON api_key TYPE array;
            DEFINE FIELD rate_limit_per_hour ON api_key TYPE int;
            DEFINE FIELD is_active ON api_key TYPE bool;
            DEFINE FIELD expires_at ON api_key TYPE datetime;
            DEFINE FIELD last_used_at ON api_key TYPE datetime;
            DEFINE FIELD created_at ON api_key TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON api_key TYPE datetime VALUE time::now();
            DEFINE INDEX idx_api_key_user_id ON api_key FIELDS user_id;
            DEFINE INDEX idx_api_key_active ON api_key FIELDS is_active;
        """
