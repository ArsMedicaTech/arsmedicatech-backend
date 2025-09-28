"""
LoginRadius OIDC Service for token verification and user management.
"""

import json
import secrets
from typing import Any, Dict, Optional, Tuple

import jwt
import requests

from lib.models.user.user import User, UserRoles
from settings import (
    LOGINRADIUS_CLIENT_ID,
    LOGINRADIUS_CLIENT_SECRET,
    LOGINRADIUS_OIDC_APP_NAME,
    LOGINRADIUS_SITE_URL,
    logger,
)


class LoginRadiusService:
    """
    Service for handling LoginRadius OIDC authentication and user management.
    """

    def __init__(self):
        self.site_url = LOGINRADIUS_SITE_URL
        self.client_id = LOGINRADIUS_CLIENT_ID
        self.client_secret = LOGINRADIUS_CLIENT_SECRET
        self.oidc_app_name = LOGINRADIUS_OIDC_APP_NAME

    def verify_id_token(
        self, id_token: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Verify LoginRadius ID token and extract user information.

        :param id_token: The ID token from LoginRadius
        :return: Tuple (is_valid: bool, user_info: Optional[Dict], error_message: str)
        """
        try:
            # Get LoginRadius public keys for token verification
            jwks_url = f"{self.site_url}/service/oidc/{self.oidc_app_name}/.well-known/openid-configuration"
            logger.debug(f"Fetching JWKS from: {jwks_url}")

            jwks_response = requests.get(jwks_url, timeout=10)
            if jwks_response.status_code != 200:
                error_msg = f"Failed to fetch JWKS: {jwks_response.status_code}"
                logger.error(error_msg)
                return False, None, error_msg

            jwks = jwks_response.json()
            logger.debug("JWKS fetched successfully")

            # Decode token header to get key ID
            try:
                header = jwt.get_unverified_header(id_token)
                kid = header.get("kid")
                if not kid:
                    return False, None, "Token header missing key ID"
            except Exception as e:
                return False, None, f"Failed to decode token header: {str(e)}"

            # Find the public key
            public_key = self._get_public_key(jwks, kid)
            if not public_key:
                return False, None, "Public key not found for token"

            # Verify and decode the token
            try:
                payload = jwt.decode(
                    id_token,
                    public_key,
                    algorithms=["RS256"],
                    audience=self.client_id,
                    issuer=f"{self.site_url}/service/oidc/{self.oidc_app_name}",
                    options={"verify_exp": True},
                )

                logger.debug(
                    f"Token verified successfully for user: {payload.get('sub')}"
                )
                return True, payload, ""

            except jwt.ExpiredSignatureError:
                return False, None, "Token has expired"
            except jwt.InvalidAudienceError:
                return False, None, "Invalid token audience"
            except jwt.InvalidIssuerError:
                return False, None, "Invalid token issuer"
            except jwt.InvalidTokenError as e:
                return False, None, f"Invalid token: {str(e)}"

        except requests.RequestException as e:
            error_msg = f"Network error during token verification: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error during token verification: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

    def _get_public_key(self, jwks: Dict[str, Any], kid: str) -> Optional[Any]:
        """
        Extract public key from JWKS for token verification.

        :param jwks: JSON Web Key Set
        :param kid: Key ID from token header
        :return: Public key for verification or None if not found
        """
        try:
            for key in jwks.get("keys", []):
                if key.get("kid") == kid:
                    return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
            return None
        except Exception as e:
            logger.error(f"Error extracting public key: {str(e)}")
            return None

    def get_user_info_from_token(
        self, id_token: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Get user information from LoginRadius ID token.

        :param id_token: The ID token from LoginRadius
        :return: Tuple (is_valid: bool, user_info: Optional[Dict], error_message: str)
        """
        is_valid, payload, error = self.verify_id_token(id_token)
        if not is_valid:
            return False, None, error

        try:
            # Extract user information from token payload
            user_info = {
                "sub": payload.get("sub"),  # Subject (user ID)
                "email": payload.get("email", ""),
                "given_name": payload.get("given_name", ""),
                "family_name": payload.get("family_name", ""),
                "preferred_username": payload.get("preferred_username", ""),
                "name": payload.get("name", ""),
                "email_verified": payload.get("email_verified", False),
                "raw_payload": payload,  # Store full payload for reference
            }

            # Generate username if not provided
            if not user_info["preferred_username"]:
                user_info["preferred_username"] = self._generate_username(
                    user_info["email"], user_info["sub"]
                )

            logger.debug(f"User info extracted: {user_info['sub']}")
            return True, user_info, ""

        except Exception as e:
            error_msg = f"Error extracting user info from token: {str(e)}"
            logger.error(error_msg)
            return False, None, error_msg

    def _generate_username(self, email: str, sub: str) -> str:
        """
        Generate a safe username based on email or subject ID.

        :param email: User's email address
        :param sub: Subject ID from LoginRadius
        :return: Safe username string
        """
        import re

        if email:
            base = email.split("@")[0]
        else:
            base = f"user_{sub[:8]}"

        # Strip invalid characters
        base = re.sub(r"[^a-zA-Z0-9_]", "_", base)

        # Pad if too short
        if len(base) < 3:
            base = f"{base}_{sub[:4]}"

        # Truncate if too long
        return base[:30]

    def _generate_session_token(self) -> str:
        """
        Generate a secure session token.

        :return: Secure session token
        """
        return secrets.token_urlsafe(32)

    def create_user_from_loginradius(
        self, user_info: Dict[str, Any], role: UserRoles = "patient"
    ) -> User:
        """
        Create a User object from LoginRadius user information.

        :param user_info: User information from LoginRadius token
        :param role: User role to assign
        :return: User object
        """
        return User(
            username=user_info["preferred_username"],
            email=user_info["email"],
            first_name=user_info["given_name"],
            last_name=user_info["family_name"],
            role=role,
            is_active=True,
            is_federated=True,
            auth_provider="loginradius",
            external_id=user_info["sub"],
            external_data=user_info["raw_payload"],
            password=None,  # No password for OAuth users
        )

    def update_user_from_loginradius(
        self, user: User, user_info: Dict[str, Any]
    ) -> User:
        """
        Update an existing User object with LoginRadius user information.

        :param user: Existing User object
        :param user_info: User information from LoginRadius token
        :return: Updated User object
        """
        # Update user information from LoginRadius
        user.email = user_info["email"]
        user.first_name = user_info["given_name"]
        user.last_name = user_info["family_name"]
        user.external_data = user_info["raw_payload"]
        user.updated_at = user_info["raw_payload"].get("iat")  # Use issued at time

        return user

    def validate_external_account(self, user: User) -> bool:
        """
        Validate that external LoginRadius account is still active.
        This is a placeholder for future implementation.

        :param user: User object to validate
        :return: True if account is valid, False otherwise
        """
        if user.auth_provider != "loginradius":
            return True

        # TODO: Implement actual validation with LoginRadius API
        # For now, return True to allow access
        return True

    def revoke_tokens(self, access_token: str) -> Tuple[bool, str]:
        """
        Revoke LoginRadius tokens (if supported by LoginRadius API).

        :param access_token: Access token to revoke
        :return: Tuple (success: bool, message: str)
        """
        try:
            # LoginRadius token revocation endpoint
            revoke_url = f"{self.site_url}/api/oidc/{self.oidc_app_name}/revoke"

            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Bearer {access_token}",
            }

            data = {"token": access_token, "token_type_hint": "access_token"}

            response = requests.post(revoke_url, headers=headers, data=data, timeout=10)

            if response.status_code in [200, 204]:
                logger.debug("Tokens revoked successfully")
                return True, "Tokens revoked successfully"
            else:
                error_msg = f"Failed to revoke tokens: {response.status_code}"
                logger.error(error_msg)
                return False, error_msg

        except Exception as e:
            error_msg = f"Error revoking tokens: {str(e)}"
            logger.error(error_msg)
            return False, error_msg
