"""
User Session model.
"""
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from dateutil.parser import isoparse  # type: ignore[import-untyped]


class UserSession:
    """
    Manages user sessions and authentication tokens
    """
    
    def __init__(
            self,
            user_id: str,
            username: str,
            role: str,
            created_at: Optional[str] = None,
            expires_at: Optional[str] = None,
            session_token: Optional[str] = None
    ) -> None:
        """
        Initialize a UserSession object
        :param user_id: Unique user ID
        :param username: User's username
        :param role: User's role (patient, provider, admin)
        :param created_at: Creation timestamp (ISO format)
        :param expires_at: Expiration timestamp (ISO format, defaults to 24 hours from now)
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
        if role not in ['patient', 'provider', 'admin', 'administrator', 'superadmin']:
            print(f"Invalid role: {role}. Defaulting to 'patient'.")
            raise ValueError("Role must be one of: patient, provider, admin")

        self.user_id = user_id
        self.username = username
        self.role = role

        if created_at:
            try:
                datetime.fromisoformat(created_at)
            except ValueError:
                raise ValueError("created_at must be in ISO format")

        if expires_at:
            try:
                if not isinstance(expires_at, str):
                    # expires_at <class 'int'> 1753196293
                    # 2025-07-22 13:58:14,043 - logger - ERROR - Failed to create/update user in database: expires_at must be in ISO format (logger.py:122)
                    if isinstance(expires_at, int):
                        expires_at = datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat()
                    else:
                        raise ValueError("expires_at must be a string in ISO format")
                expires = isoparse(expires_at)
                if expires < datetime.fromisoformat(created_at or datetime.now(timezone.utc).isoformat()):
                    raise ValueError("expires_at must be after created_at")
            except ValueError:
                raise ValueError("expires_at must be in ISO format")
        else:
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

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
        try:
            expires = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > expires
        except (ValueError, TypeError):
            return True
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert session to dictionary

        :return: Dictionary representation of the session
        """
        return {
            'user_id': self.user_id,
            'username': self.username,
            'role': self.role,
            'created_at': self.created_at,
            'expires_at': self.expires_at,
            'session_token': self.session_token
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'UserSession':
        """
        Create session from dictionary

        :param data: Dictionary containing session data
        :return: UserSession object
        """
        session = cls(
            user_id=str(data.get('user_id', '')),
            username=str(data.get('username', '')),
            role=str(data.get('role', 'patient')),
            created_at=data.get('created_at'),
            expires_at=data.get('expires_at')
        )
        # Set the token from the data if it exists
        if 'session_token' in data:
            session.session_token = data['session_token']
        return session
