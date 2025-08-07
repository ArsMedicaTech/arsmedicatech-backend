"""
User Model.
"""

import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from settings import logger


class User:
    """
    Represents a user in the system with authentication and role management
    """

    def __init__(
        self,
        username: str,
        email: str,
        password: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        role: str = "patient",
        is_active: bool = True,
        created_at: Optional[str] = None,
        id: Optional[str] = None,
        specialty: Optional[str] = None,
        clinic_name: Optional[str] = None,
        clinic_address: Optional[str] = None,
        phone: Optional[str] = None,
        max_organizations: int = 1,
        user_organizations: int = 0,
        organization_id: Optional[str] = None,
    ) -> None:
        """
        Initialize a User object

        :param username: Unique username
        :param email: User's email address
        :param password: Plain text password (will be hashed)
        :param first_name: User's first name
        :param last_name: User's last name
        :param role: User role (patient, provider, admin)
        :param is_active: Whether the user account is active
        :param created_at: Creation timestamp
        :param id: Database record ID
        :param specialty: Medical specialty (for providers)
        :param clinic_name: Name of the clinic (for providers)
        :param clinic_address: Address of the clinic (for providers)
        :param phone: User's phone number
        :param max_organizations: Maximum number of organizations this user can create (default: 1)
        :param user_organizations: Current number of organizations created by this user (default: 0)
        :param organization_id: ID of the organization this user belongs to (if applicable)
        """
        self.username = username
        self.email = email
        self.first_name = first_name or ""
        self.last_name = last_name or ""
        self.role = role
        self.is_active = is_active
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.id = id
        self.specialty = specialty or ""
        self.clinic_name = clinic_name or ""
        self.clinic_address = clinic_address or ""
        self.phone = phone or ""
        self.max_organizations = max_organizations
        self.user_organizations = user_organizations
        self.organization_id = organization_id

        # Hash password if provided
        self.password_hash: Optional[str] = None
        if password:
            self.password_hash = self.hash_password(password)
        else:
            self.password_hash = None

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a password using SHA-256 with salt

        :param password: Plain text password
        :return: Hashed password with salt in format "salt$hash"
        """
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256()
        hash_obj.update((password + salt).encode("utf-8"))
        return f"{salt}${hash_obj.hexdigest()}"

    def verify_password(self, password: str) -> bool:
        """
        Verify a password against the stored hash

        :param password: Plain text password to verify
        :return: True if password matches, False otherwise
        """
        if not self.password_hash:
            logger.debug("No password hash stored for user")
            return False

        try:
            logger.debug(f"Stored password hash: {self.password_hash}")
            logger.debug(f"Attempting to verify password: {password}")
            salt, hash_value = self.password_hash.split("$", 1)
            logger.debug(f"Extracted salt: {salt}")
            logger.debug(f"Extracted hash: {hash_value}")

            hash_obj = hashlib.sha256()
            hash_obj.update((password + salt).encode("utf-8"))
            computed_hash = hash_obj.hexdigest()
            logger.debug(f"Computed hash: {computed_hash}")
            logger.debug(f"Hash match: {computed_hash == hash_value}")

            return computed_hash == hash_value
        except (ValueError, AttributeError) as e:
            logger.debug(f"Password verification error: {e}")
            return False

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert user to dictionary for database storage

        :return: Dictionary representation of the user
        """
        return {
            "username": self.username,
            "email": self.email,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "password_hash": self.password_hash,
            "specialty": self.specialty,
            "clinic_name": self.clinic_name,
            "clinic_address": self.clinic_address,
            "phone": self.phone,
            "max_organizations": self.max_organizations,
            "user_organizations": self.user_organizations,
            "organization_id": self.organization_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """
        Create user from dictionary

        :param data: Dictionary containing user data
        :return: User object
        """
        # Convert RecordID to string if it exists
        user_id = data.get("id")
        if hasattr(user_id, "__str__"):
            user_id = str(user_id)

        user = cls(
            username=str(data.get("username") or ""),
            email=str(data.get("email") or ""),
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            role=data.get("role", "patient"),
            is_active=data.get("is_active", True),
            created_at=data.get("created_at"),
            id=user_id,
            specialty=data.get("specialty"),
            clinic_name=data.get("clinic_name"),
            clinic_address=data.get("clinic_address"),
            phone=data.get("phone"),
            max_organizations=data.get("max_organizations", 1),
            user_organizations=data.get("user_organizations", 0),
            organization_id=data.get("organization_id"),
        )
        # Set password hash if it exists in the data
        if "password_hash" in data:
            user.password_hash = data["password_hash"]
        return user

    @staticmethod
    def validate_username(username: str) -> tuple[bool, str]:
        """
        Validate username format

        :param username: Username to validate
        :return: Tuple (is_valid: bool, error_message: str)
        """
        if not username:
            return False, "Username is required"
        if len(username) < 3:
            return False, "Username must be at least 3 characters long"
        if len(username) > 30:
            return False, "Username must be less than 30 characters"
        if not re.match(r"^[a-zA-Z0-9_]+$", username):
            return False, "Username can only contain letters, numbers, and underscores"
        return True, ""

    @staticmethod
    def validate_email(email: str) -> tuple[bool, str]:
        """
        Validate email format

        :param email: Email address to validate
        :return: Tuple (is_valid: bool, error_message: str)
        """
        if not email:
            return False, "Email is required"
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, email):
            return False, "Invalid email format"
        return True, ""

    @staticmethod
    def validate_password(password: str) -> tuple[bool, str]:
        """
        Validate password strength

        :param password: Password to validate
        :return: Tuple (is_valid: bool, error_message: str)
        """
        if not password:
            return False, "Password is required"
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"
        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"
        if not re.search(r"\d", password):
            return False, "Password must contain at least one number"
        return True, ""

    @staticmethod
    def validate_phone(phone: str) -> tuple[bool, str]:
        """
        Validate phone number format

        :param phone: Phone number to validate
        :return: Tuple (is_valid: bool, error_message: str)
        """
        if not phone:
            return True, ""  # Phone is optional
        # Basic phone validation - allows various formats
        phone_pattern = r"^[\+]?[1-9][\d]{0,15}$"
        if not re.match(
            phone_pattern,
            phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", ""),
        ):
            return False, "Invalid phone number format"
        return True, ""

    @staticmethod
    def validate_role(role: str) -> tuple[bool, str]:
        """
        Validate user role

        :param role: User role to validate
        :return: Tuple (is_valid: bool, error_message: str)
        """
        valid_roles = ["patient", "provider", "admin", "administrator", "superadmin"]
        if role not in valid_roles:
            return False, f"Role must be one of: {', '.join(valid_roles)}"
        return True, ""

    def get_full_name(self) -> str:
        """
        Get user's full name

        :return: Full name in "First Last" format, or username if not available
        """
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        else:
            return self.username

    def has_role(self, required_role: str) -> bool:
        """
        Check if user has the required role

        :param required_role: Role to check against (patient, provider, admin)
        :return: True if user has the required role, False otherwise
        """
        role_hierarchy = {"patient": 1, "provider": 2, "admin": 3}

        user_level = role_hierarchy.get(self.role, 0)
        required_level = role_hierarchy.get(required_role, 0)

        return user_level >= required_level

    def is_admin(self) -> bool:
        """
        Check if user is an admin

        :return: True if user is an admin, False otherwise
        """
        return self.role == "admin"

    def is_provider(self) -> bool:
        """
        Check if user is a provider or admin

        :return: True if user is a provider or admin, False otherwise
        """
        return self.has_role("provider")

    def is_patient(self) -> bool:
        """
        Check if user is a patient

        :return: True if user is a patient, False otherwise
        """
        return self.role == "patient"

    def can_create_organization(self) -> bool:
        """
        Check if user can create another organization

        :return: True if user can create more organizations, False otherwise
        """
        return self.user_organizations < self.max_organizations

    def get_remaining_organization_slots(self) -> int:
        """
        Get the number of organizations the user can still create

        :return: Number of remaining organization slots
        """
        return max(0, self.max_organizations - self.user_organizations)

    def increment_organization_count(self) -> None:
        """
        Increment the user's organization count when they create a new organization

        :raises ValueError: If user has already reached their organization limit
        :return: None
        """
        if not self.can_create_organization():
            raise ValueError(
                f"User has reached their organization limit of {self.max_organizations}"
            )
        self.user_organizations += 1
