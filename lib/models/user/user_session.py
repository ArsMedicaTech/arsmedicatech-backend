"""
User Session model.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from lib.models.user.user import UserRoles


class UserSession:
    """
    Manages user sessions and authentication tokens
    """

    def __init__(
        self,
        user_id: str,
        username: str,
        role: UserRoles,
        created_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        session_token: Optional[str] = None,
    ) -> None:
        """
        Initialize a UserSession object
        :param user_id: Unique user ID
        :param username: User's username
        :param role: User's role (patient, provider, admin)
        :param created_at: Creation timestamp
        :param expires_at: Expiration timestamp (defaults to 24 hours from now)
        :param session_token: Optional pre-generated token [for federated sign in], if None a new one will be generated
        :raises ValueError: If user_id or username is empty
        :raises ValueError: If role is not one of the valid roles
        :raises ValueError: If created_at or expires_at is not in ISO format
        :raises ValueError: If expires_at is before created_at
        :raises ValueError: If token generation fails
        :return: None
        """
        if not user_id or not username:
            raise ValueError("user_id and username cannot be empty")
        if role not in ["patient", "provider", "admin", "administrator", "superadmin"]:
            print(f"Invalid role: {role}. Defaulting to 'patient'.")
            raise ValueError("Role must be one of: patient, provider, admin")

        self.user_id = user_id
        self.username = username
        self.role = role

        if created_at is None:
            try:
                created_at = datetime.now(timezone.utc)
            except ValueError:
                raise ValueError("created_at must be in ISO format")

        if expires_at:
            try:
                if expires_at < created_at:
                    raise ValueError("expires_at must be after created_at")
            except ValueError:
                raise ValueError("expires_at must be in ISO format")
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        self.created_at = created_at or datetime.now(timezone.utc)
        self.expires_at = expires_at or (
            datetime.now(timezone.utc) + timedelta(hours=24)
        )

        if session_token:
            self.session_token = session_token
        else:
            try:
                self.session_token = secrets.token_urlsafe(32)
            except Exception as e:
                raise ValueError(f"Failed to generate token: {e}")

    def is_expired(self) -> bool:
        """
        Check if session has expired

        :return: True if session is expired, False otherwise
        """
        if not self.expires_at:
            return True

        expires_dt = self.expires_at

        # --- CONVERSION LOGIC ---
        # If it's an integer (Unix timestamp), convert it
        if isinstance(expires_dt, (int, float)):
            expires_dt = datetime.fromtimestamp(expires_dt, tz=timezone.utc)

        # If it's a string, convert it
        elif isinstance(expires_dt, str):
            # The 'Z' at the end means UTC (Zulu time)
            if expires_dt.endswith("Z"):
                expires_dt = expires_dt[:-1] + "+00:00"
            expires_dt = datetime.fromisoformat(expires_dt)

        # Now, ensure it's timezone-aware before comparing
        if expires_dt.tzinfo is None:
            expires_dt = expires_dt.replace(tzinfo=timezone.utc)
        # --- END CONVERSION LOGIC ---

        # The comparison will now work correctly
        return datetime.now(timezone.utc) > expires_dt

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert session to dictionary

        :return: Dictionary representation of the session
        """
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "session_token": self.session_token,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserSession":
        """
        Create session from dictionary

        :param data: Dictionary containing session data
        :return: UserSession object
        """
        session = cls(
            user_id=data.get("user_id", ""),
            username=data.get("username", ""),
            role=data.get("role", "patient"),
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
        )
        # Set the token from the data if it exists
        if "session_token" in data:
            session.session_token = data["session_token"]
        print("1`1```1212`23` ABOUT TO RETURN:", session)
        return session

    @classmethod
    def schema(cls) -> str:
        """
        Defines the schema for the user session table in SurrealDB.
        :return: The entire schema definition for the table in a single string containing all statements.
        """
        return """
            DEFINE TABLE user_session SCHEMAFULL;
            DEFINE FIELD user_id ON user_session TYPE record<user>;
            DEFINE FIELD username ON user_session TYPE string;
            DEFINE FIELD role ON user_session TYPE "patient" | "provider" | "admin";
            DEFINE FIELD expires_at ON user_session TYPE datetime;
            DEFINE FIELD created_at ON user_session TYPE datetime VALUE time::now() READONLY;
            DEFINE FIELD updated_at ON user_session TYPE datetime VALUE time::now();
        """
